#!/usr/bin/env python3
"""
Main entry point for the AI Day Trading System.
"""
import asyncio
import argparse
import signal
import sys
from datetime import datetime
from typing import Optional
import structlog

# Add project root to path
sys.path.insert(0, '/Users/jaden/Library/Mobile Documents/com~apple~CloudDocs/Projects/AI-Day-Trader')

from config.settings import get_settings
from src.utils.logging import setup_logging
from src.utils.helpers import is_market_open, is_premarket, get_eastern_time, time_until_market_open
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

        # State
        self._portfolio_state: Optional[PortfolioState] = None
        self._snapshots = {}

    async def start(self) -> None:
        """Initialize and start the trading engine"""
        logger.info("trading_engine_starting", dry_run=self.dry_run)

        # Initialize database
        await init_db()

        # Initialize event bus
        self._event_bus = get_event_bus()
        await self._event_bus.start()

        # Initialize broker and get account
        self._broker = get_broker()
        account = await self._broker.get_account()

        logger.info(
            "account_loaded",
            equity=account['equity'],
            buying_power=account['buying_power']
        )

        # Initialize limits manager
        init_limits_manager(account['equity'])

        # Initialize portfolio state
        positions = await self._broker.get_positions()
        self._portfolio_state = PortfolioState(
            equity=account['equity'],
            cash=account['cash'],
            buying_power=account['buying_power'],
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

        # Set up signal handlers
        self._setup_signal_handlers()

        self._running = True

        # Run main loop
        await self._main_loop()

    async def _main_loop(self) -> None:
        """Main trading loop"""
        logger.info("main_loop_started")

        historical = get_historical_client()
        cycle_count = 0

        while self._running and not self._shutdown_event.is_set():
            try:
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

                cycle_count += 1
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
                logger.debug("cycle_complete", cycle=cycle_count, time_sec=cycle_time)

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

        logger.info("main_loop_stopped", cycles=cycle_count)

    async def _process_symbol(self, symbol: str, historical) -> None:
        """Process a single symbol - fetch data, calculate indicators, generate signals"""
        # Build market snapshot
        snapshot = await historical.build_market_snapshot(symbol)

        if not snapshot.bars_1m:
            return

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

        # Process each signal
        for signal in signals:
            await self._process_signal(signal, snapshot)

    async def _process_signal(self, signal, snapshot) -> None:
        """Process a trading signal through AI and execution"""
        # Check if AI evaluation needed
        needs_ai = await self._decision_engine.should_evaluate(signal)

        if needs_ai:
            # Get AI decision
            decision = await self._decision_engine.evaluate(
                signal,
                snapshot,
                {
                    'equity': self._portfolio_state.equity,
                    'position_count': len(self._portfolio_state.positions),
                    'daily_pnl_pct': self._portfolio_state.daily_pnl / self._portfolio_state.equity if self._portfolio_state.equity > 0 else 0,
                    'portfolio_heat': self._portfolio_state.open_risk / self._portfolio_state.equity if self._portfolio_state.equity > 0 else 0
                }
            )

            if decision.is_rejected:
                logger.info(
                    "signal_ai_rejected",
                    symbol=signal.symbol,
                    strategy=signal.strategy,
                    reason=decision.reasoning
                )
                return

            if decision.is_modified:
                signal = self._decision_engine.apply_modifications(signal, decision)

        # Execute the signal
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

    async def _update_portfolio_state(self) -> None:
        """Update portfolio state from broker"""
        account = await self._broker.get_account()
        positions = await self._broker.get_positions()

        # Calculate open risk
        open_risk = 0
        for symbol, pos in positions.items():
            entry = pos.get('avg_entry_price', 0)
            current = pos.get('current_price', entry)
            qty = abs(pos.get('qty', 0))
            # Simplified risk calc
            risk_per_share = abs(current - entry) if entry != 0 else current * 0.02
            open_risk += qty * risk_per_share

        self._portfolio_state = PortfolioState(
            equity=account['equity'],
            cash=account['cash'],
            buying_power=account['buying_power'],
            positions=positions,
            daily_pnl=account['equity'] - self._portfolio_state.equity if self._portfolio_state else 0,
            open_risk=open_risk
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
