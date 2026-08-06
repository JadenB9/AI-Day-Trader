#!/usr/bin/env python3
"""
Main entry point for the AI Day Trading System.
"""
import asyncio
import argparse
import signal
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import structlog

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import get_settings
from src.utils.logging import setup_logging
from src.utils.helpers import is_market_open, is_premarket, get_eastern_time, time_until_market_open, get_trading_capital, is_capital_depleted, get_available_capital
from src.core.event_bus import get_event_bus, EventType, Event
from src.data.streams.alpaca_stream import AlpacaStream
from src.data.historical.alpaca_client import get_historical_client
from src.data.scanner.watchlist import get_watchlist, initialize_watchlist
from src.indicators.calculator import get_calculator, enrich_snapshot
from src.strategies.registry import get_registry, register_all_strategies, StrategyEngine
from src.ai.decision_engine import get_decision_engine
from src.risk.daily_limits import init_limits_manager
from src.risk.validators import get_validator, PortfolioState
from src.execution.alpaca_broker import get_broker
from src.execution.order_manager import get_order_manager
from storage.database import init_db

logger = structlog.get_logger()
settings = get_settings()


class TradingEngine:
    """
    Main trading engine orchestrator.
    Coordinates all components for live trading.
    """

    def __init__(self, dry_run: bool = False, single_cycle: bool = False):
        self.dry_run = dry_run
        self.single_cycle = single_cycle
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Components (initialized in start())
        self._event_bus = None
        self._stream: Optional[AlpacaStream] = None
        self._watchlist = None
        self._calculator = None
        self._strategy_engine = None
        self._decision_engine = None
        self._order_manager = None
        self._broker = None
        self._researcher = None  # Market researcher

        # State
        self._portfolio_state: Optional[PortfolioState] = None
        self._snapshots = {}
        self._last_research_time = None
        self._cycle_count = 0

    async def start(self) -> None:
        """Initialize and start the trading engine"""
        logger.info("trading_engine_starting", dry_run=self.dry_run)

        # Test connections first
        from src.utils.connection_test import test_all_connections
        logger.info("testing_connections")
        conn_results = await test_all_connections()

        if not conn_results['all_passed']:
            logger.error("connection_tests_failed", results=conn_results)
            if not conn_results['alpaca']['connected']:
                raise RuntimeError("Alpaca API connection failed. Check your API keys.")
            if not conn_results['claude']['connected']:
                logger.warning("claude_api_failed", error=conn_results['claude'].get('error'))
                # Continue but log warning - AI features may not work

        logger.info("connections_verified")

        # Initialize database
        await init_db()

        # Initialize event bus
        self._event_bus = get_event_bus()
        await self._event_bus.start()

        # Initialize broker and get account
        self._broker = get_broker()
        account = await self._broker.get_account()

        # Calculate trading capital (virtual or actual)
        actual_equity = account['equity']
        trading_capital = get_trading_capital(actual_equity)
        available_capital = get_available_capital(actual_equity)

        logger.info(
            "account_loaded",
            actual_equity=actual_equity,
            trading_capital=trading_capital,
            available_capital=available_capital,
            virtual_mode=settings.portfolio.virtual_capital > 0
        )

        # Check if capital is depleted
        if is_capital_depleted(actual_equity):
            logger.error(
                "capital_depleted",
                actual_equity=actual_equity,
                reserve=settings.portfolio.capital_reserve
            )
            raise RuntimeError(f"Capital depleted. Equity ${actual_equity:.2f} is at or below reserve ${settings.portfolio.capital_reserve:.2f}")

        # Initialize limits manager with trading capital (not actual equity)
        init_limits_manager(trading_capital)

        # Initialize portfolio state with trading capital
        positions = await self._broker.get_positions()
        self._portfolio_state = PortfolioState(
            equity=trading_capital,  # Use trading capital, not actual
            cash=min(account['cash'], available_capital),
            buying_power=min(account['buying_power'], available_capital),
            positions=positions,
            daily_pnl=0,
            open_risk=0
        )

        # Initialize validator with portfolio state
        validator = get_validator()
        validator.update_portfolio(self._portfolio_state)

        # Initialize watchlist (run scanner if premarket)
        self._watchlist = await initialize_watchlist(run_scan=is_premarket())
        logger.info("watchlist_ready", symbols=len(self._watchlist.symbols))

        # Register strategies
        register_all_strategies()
        self._strategy_engine = StrategyEngine()

        # Initialize AI decision engine
        self._decision_engine = get_decision_engine()

        # Initialize order manager
        self._order_manager = get_order_manager(dry_run=self.dry_run)

        # Initialize indicator calculator
        self._calculator = get_calculator()

        # Initialize market researcher
        from src.ai.market_research import get_researcher
        self._researcher = get_researcher()

        # Set up signal handlers
        self._setup_signal_handlers()

        self._running = True

        # Run initial market research
        logger.info("running_initial_market_research")
        try:
            await self._run_market_research()
        except Exception as e:
            logger.warning("initial_research_failed", error=str(e))

        # Run main loop
        await self._main_loop()

    async def _run_market_research(self) -> None:
        """
        Run hourly market research - THIS IS THE ONLY TIME AI IS CALLED.

        The AI searches the web for news on all symbols, analyzes sentiment,
        and caches the results. These cached results are used for the next hour
        to filter trading signals without making additional AI calls.
        """
        if not self._researcher:
            return

        symbols = list(self._watchlist.symbols) if self._watchlist else settings.default_symbols

        logger.info("running_market_research", symbols=len(symbols))

        # Log start of AI research
        try:
            from api.routers.system import log_activity
            log_activity(
                "research",
                "Hourly AI Research Starting",
                f"Researching {len(symbols)} symbols with web search. This is the only AI call for the next hour.",
                {"symbols": symbols[:10], "total_symbols": len(symbols)}
            )
        except ImportError:
            pass

        try:
            from src.ai.market_research import run_hourly_research
            results = await run_hourly_research(symbols)
            self._last_research_time = datetime.now()

            logger.info(
                "market_research_complete",
                symbols=results.get('symbols_researched'),
                sentiment=results.get('sentiment_summary')
            )

            # Log completion
            try:
                from api.routers.system import log_activity
                sentiment = results.get('sentiment_summary', {})
                log_activity(
                    "research",
                    "Hourly AI Research Complete",
                    f"Bullish: {sentiment.get('bullish', 0)}, Bearish: {sentiment.get('bearish', 0)}, Neutral: {sentiment.get('neutral', 0)}",
                    {
                        "symbols_researched": results.get('symbols_researched'),
                        "sentiment_summary": sentiment,
                        "high_confidence": results.get('high_confidence', [])
                    }
                )
            except ImportError:
                pass

        except Exception as e:
            logger.error("market_research_error", error=str(e))
            try:
                from api.routers.system import log_activity
                log_activity(
                    "error",
                    "Research Failed",
                    f"Hourly research failed: {str(e)[:100]}",
                    {"error": str(e)}
                )
            except ImportError:
                pass

    async def _main_loop(self) -> None:
        """Main trading loop"""
        logger.info("main_loop_started")

        historical = get_historical_client()

        while self._running and not self._shutdown_event.is_set():
            try:
                # Check if hourly research is due
                if self._last_research_time is None or \
                   (datetime.now() - self._last_research_time).total_seconds() > 3600:
                    await self._run_market_research()

                # Check market status
                if not is_market_open(extended_hours=settings.trading_hours.extended_hours_enabled):
                    wait_time = time_until_market_open()
                    if wait_time.total_seconds() > 300:  # More than 5 min
                        logger.info(
                            "market_closed",
                            opens_in=str(wait_time)
                        )
                        # Wait shorter interval and check again
                        await asyncio.sleep(60)
                        continue

                self._cycle_count += 1
                cycle_start = datetime.now()

                # Update portfolio state
                await self._update_portfolio_state()

                # Process each symbol
                symbols = list(self._watchlist.symbols)
                logger.debug("processing_symbols", count=len(symbols))

                for symbol in symbols:
                    if not self._running:
                        break

                    try:
                        await self._process_symbol(symbol, historical)
                    except Exception as e:
                        logger.error("symbol_processing_error", symbol=symbol, error=str(e))

                # Check stops for all positions
                for symbol in self._portfolio_state.positions.keys():
                    pos = self._portfolio_state.positions[symbol]
                    await self._order_manager.check_stops(
                        symbol,
                        pos.get('current_price', 0)
                    )

                cycle_time = (datetime.now() - cycle_start).total_seconds()
                logger.debug("cycle_complete", cycle=self._cycle_count, time_sec=cycle_time)

                # Log cycle to activity feed (every 12 cycles = ~1 min)
                if self._cycle_count % 12 == 0:
                    try:
                        from api.routers.system import log_activity
                        log_activity(
                            "info",
                            f"Trading Cycle #{self._cycle_count}",
                            f"Processed {len(symbols)} symbols in {cycle_time:.2f}s. Positions: {len(self._portfolio_state.positions)}",
                            {
                                "cycle": self._cycle_count,
                                "symbols_processed": len(symbols),
                                "cycle_time_sec": round(cycle_time, 2),
                                "positions": len(self._portfolio_state.positions)
                            }
                        )
                    except ImportError:
                        pass

                # Single cycle mode
                if self.single_cycle:
                    logger.info("single_cycle_complete")
                    break

                # Wait before next cycle (scalping = fast cycles)
                await asyncio.sleep(5)  # 5 second cycles

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("main_loop_error", error=str(e), exc_info=True)
                await asyncio.sleep(10)

        logger.info("main_loop_stopped", cycles=self._cycle_count)

    async def _process_symbol(self, symbol: str, historical) -> None:
        """Process a single symbol - fetch data, calculate indicators, generate signals"""
        # Build market snapshot
        snapshot = await historical.build_market_snapshot(symbol)

        if not snapshot.bars_1m:
            return

        # Log data fetch (occasionally, not every symbol)
        if self._cycle_count % 60 == 1:  # Every ~5 min
            try:
                from api.routers.system import log_activity
                current_price = snapshot.bars_1m[-1].close if snapshot.bars_1m else 0
                log_activity(
                    "data",
                    f"Data: {symbol}",
                    f"Fetched {len(snapshot.bars_1m)} bars. Current: ${current_price:.2f}",
                    {
                        "symbol": symbol,
                        "bars_1m": len(snapshot.bars_1m),
                        "current_price": current_price
                    }
                )
            except (ImportError, Exception):
                pass

        # Calculate indicators
        snapshot = enrich_snapshot(snapshot)
        self._snapshots[symbol] = snapshot

        # Run strategies
        signals = await self._strategy_engine.process_snapshot(
            symbol,
            snapshot,
            snapshot.indicators
        )

        if not signals:
            return

        # Log signals generated
        try:
            from api.routers.system import log_activity
            for sig in signals:
                log_activity(
                    "signal",
                    f"Signal: {sig.direction.value.upper()} {symbol}",
                    f"Strategy: {sig.strategy}. Confidence: {sig.confidence*100:.0f}%",
                    {
                        "symbol": symbol,
                        "direction": sig.direction.value,
                        "strategy": sig.strategy,
                        "confidence": sig.confidence,
                        "entry": sig.entry_price
                    }
                )
        except ImportError:
            pass

        # Process each signal
        for signal in signals:
            await self._process_signal(signal, snapshot)

    async def _process_signal(self, signal, snapshot) -> None:
        """
        Process a trading signal using CACHED hourly research (no real-time AI calls).

        Flow:
        1. Check cached research sentiment for the symbol
        2. If research is bearish → skip the trade
        3. If research is neutral/bullish → proceed with technical signal
        4. AI is only called HOURLY during research, not per-signal
        """
        # Get cached research (updated hourly, no API call)
        research = None
        if self._researcher:
            research = self._researcher.get_cached_research(signal.symbol)

        # Only skip on VERY STRONG bearish sentiment (85%+ confidence) - AGGRESSIVE SETTINGS
        # Previously skipped at 60% confidence, now only skip on extreme bearish calls
        if research and research.sentiment == "bearish" and research.confidence >= 85:
            logger.info(
                "signal_skipped_strong_bearish",
                symbol=signal.symbol,
                strategy=signal.strategy,
                research_sentiment=research.sentiment,
                research_confidence=research.confidence
            )
            try:
                from api.routers.system import log_activity
                log_activity(
                    "signal",
                    f"Skipped: {signal.symbol}",
                    f"STRONG bearish research ({research.confidence}% confidence). Strategy: {signal.strategy}",
                    {
                        "symbol": signal.symbol,
                        "strategy": signal.strategy,
                        "research_sentiment": research.sentiment,
                        "research_confidence": research.confidence,
                        "skip_reason": "strong_bearish_research"
                    }
                )
            except ImportError:
                pass
            return

        # Log research-backed trade
        research_note = ""
        if research:
            research_note = f" Research: {research.sentiment} ({research.confidence}%)"

        logger.info(
            "signal_approved_by_research",
            symbol=signal.symbol,
            strategy=signal.strategy,
            research_sentiment=research.sentiment if research else "none",
            research_confidence=research.confidence if research else 0
        )

        # Execute the signal (no AI call - uses cached research)
        order = await self._order_manager.execute_signal(
            signal,
            self._portfolio_state,
            use_limit=False,  # Market orders for scalping
            extended_hours=settings.trading_hours.extended_hours_enabled
        )

        if order:
            logger.info(
                "signal_executed",
                symbol=signal.symbol,
                strategy=signal.strategy,
                direction=signal.direction.value,
                shares=order.quantity
            )
            # Log trade execution with research context
            try:
                from api.routers.system import log_activity
                research_info = ""
                if research:
                    research_info = f" | Research: {research.sentiment} ({research.confidence}%)"

                log_activity(
                    "trade",
                    f"Trade: {signal.direction.value.upper()} {signal.symbol}",
                    f"Strategy: {signal.strategy}. Shares: {order.quantity}. Entry: ${signal.entry_price:.2f}{research_info}",
                    {
                        "symbol": signal.symbol,
                        "direction": signal.direction.value,
                        "strategy": signal.strategy,
                        "shares": order.quantity,
                        "entry_price": signal.entry_price,
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
                        "research_sentiment": research.sentiment if research else None,
                        "research_confidence": research.confidence if research else None
                    }
                )
            except ImportError:
                pass

    async def _update_portfolio_state(self) -> None:
        """Update portfolio state from broker"""
        account = await self._broker.get_account()
        positions = await self._broker.get_positions()

        actual_equity = account['equity']
        trading_capital = get_trading_capital(actual_equity)
        available_capital = get_available_capital(actual_equity)

        # Check for capital depletion
        if is_capital_depleted(actual_equity):
            logger.error("capital_depleted_during_trading", actual_equity=actual_equity)
            self._running = False
            return

        # Calculate open risk
        open_risk = 0
        for symbol, pos in positions.items():
            entry = pos.get('avg_entry_price', 0)
            current = pos.get('current_price', entry)
            qty = abs(pos.get('qty', 0))
            risk_per_share = abs(current - entry) if entry != 0 else current * 0.02
            open_risk += qty * risk_per_share

        # Track P&L relative to trading capital
        prev_equity = self._portfolio_state.equity if self._portfolio_state else trading_capital

        self._portfolio_state = PortfolioState(
            equity=trading_capital,
            cash=min(account['cash'], available_capital),
            buying_power=min(account['buying_power'], available_capital),
            positions=positions,
            daily_pnl=trading_capital - prev_equity,
            open_risk=open_risk
        )

        # Log capital status periodically
        if self._cycle_count % 60 == 0:  # Every ~5 minutes
            logger.info(
                "capital_status",
                trading_capital=trading_capital,
                available=available_capital,
                open_risk=open_risk,
                positions=len(positions)
            )

        # Update validator
        get_validator().update_portfolio(self._portfolio_state)

    def _setup_signal_handlers(self) -> None:
        """Set up graceful shutdown handlers"""
        def shutdown_handler(signum, frame):
            logger.info("shutdown_signal_received", signal=signum)
            self._running = False
            self._shutdown_event.set()

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

    async def stop(self) -> None:
        """Stop the trading engine gracefully"""
        logger.info("trading_engine_stopping")
        self._running = False
        self._shutdown_event.set()

        # Stop event bus
        if self._event_bus:
            await self._event_bus.stop()

        # Stop stream
        if self._stream:
            await self._stream.stop()

        logger.info("trading_engine_stopped")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='AI Day Trading System')
    parser.add_argument('--dry-run', action='store_true', help='Run without executing trades')
    parser.add_argument('--single-cycle', action='store_true', help='Run single cycle and exit')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    parser.add_argument('--extended-hours', action='store_true', help='Enable extended hours trading')

    args = parser.parse_args()

    # Setup logging
    log_level = 'DEBUG' if args.verbose else settings.logging.level
    setup_logging(
        level=log_level,
        format='console' if args.verbose else settings.logging.format,
        log_file=settings.logging.file_path
    )

    logger.info(
        "ai_day_trader_starting",
        version="1.0.0",
        dry_run=args.dry_run,
        extended_hours=args.extended_hours or settings.trading_hours.extended_hours_enabled
    )

    # Create and run engine
    engine = TradingEngine(
        dry_run=args.dry_run or settings.dry_run,
        single_cycle=args.single_cycle
    )

    try:
        await engine.start()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception as e:
        logger.error("fatal_error", error=str(e), exc_info=True)
    finally:
        await engine.stop()


if __name__ == "__main__":
    asyncio.run(main())
