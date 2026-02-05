"""
Alpaca WebSocket streaming for real-time market data.
Uses alpaca-py (new SDK).
"""
import asyncio
from typing import Set, Callable, Optional, Dict, List
from datetime import datetime
import structlog

from alpaca.data.live import StockDataStream
from alpaca.data.models import Quote as AlpacaQuote, Trade as AlpacaTrade, Bar as AlpacaBar

from config.settings import get_settings
from src.core.event_bus import get_event_bus, EventType, Event
from src.core.exceptions import StreamDisconnected, ConnectionError as ConnError
from src.data.models.market_snapshot import Quote, Trade, Bar, BarTimeframe

logger = structlog.get_logger()
settings = get_settings()


class AlpacaStream:
    """
    Real-time market data streaming via Alpaca WebSocket.
    Publishes events to the event bus.
    """

    def __init__(self, symbols: Set[str] = None):
        self.symbols = symbols or set()
        self._stream: Optional[StockDataStream] = None
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnects = 5
        self._event_bus = get_event_bus()

        # Callbacks for direct subscription (bypass event bus)
        self._quote_callbacks: List[Callable] = []
        self._trade_callbacks: List[Callable] = []
        self._bar_callbacks: List[Callable] = []

        # Stats
        self._quote_count = 0
        self._trade_count = 0
        self._bar_count = 0
        self._last_heartbeat = None

    def _create_stream(self) -> StockDataStream:
        """Create new stream instance"""
        return StockDataStream(
            api_key=settings.alpaca.api_key,
            secret_key=settings.alpaca.secret_key,
            raw_data=False  # Get parsed objects
        )

    async def _handle_quote(self, data: AlpacaQuote) -> None:
        """Handle incoming quote"""
        try:
            quote = Quote(
                symbol=data.symbol,
                bid=float(data.bid_price),
                ask=float(data.ask_price),
                bid_size=data.bid_size,
                ask_size=data.ask_size,
                timestamp=data.timestamp
            )

            self._quote_count += 1

            # Direct callbacks
            for cb in self._quote_callbacks:
                try:
                    result = cb(quote)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error("quote_callback_error", error=str(e))

            # Event bus
            await self._event_bus.publish(Event(
                type=EventType.QUOTE_UPDATE,
                data=quote,
                source="alpaca_stream"
            ))

        except Exception as e:
            logger.error("quote_handler_error", error=str(e), symbol=data.symbol)

    async def _handle_trade(self, data: AlpacaTrade) -> None:
        """Handle incoming trade tick"""
        try:
            trade = Trade(
                symbol=data.symbol,
                price=float(data.price),
                size=data.size,
                timestamp=data.timestamp,
                exchange=data.exchange if hasattr(data, 'exchange') else ""
            )

            self._trade_count += 1

            # Direct callbacks
            for cb in self._trade_callbacks:
                try:
                    result = cb(trade)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error("trade_callback_error", error=str(e))

            # Event bus
            await self._event_bus.publish(Event(
                type=EventType.TRADE_TICK,
                data=trade,
                source="alpaca_stream"
            ))

        except Exception as e:
            logger.error("trade_handler_error", error=str(e), symbol=data.symbol)

    async def _handle_bar(self, data: AlpacaBar) -> None:
        """Handle incoming bar"""
        try:
            bar = Bar(
                symbol=data.symbol,
                timestamp=data.timestamp,
                open=float(data.open),
                high=float(data.high),
                low=float(data.low),
                close=float(data.close),
                volume=data.volume,
                vwap=float(data.vwap) if data.vwap else None,
                trade_count=data.trade_count if hasattr(data, 'trade_count') else None,
                timeframe=BarTimeframe.MIN_1
            )

            self._bar_count += 1

            # Direct callbacks
            for cb in self._bar_callbacks:
                try:
                    result = cb(bar)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error("bar_callback_error", error=str(e))

            # Event bus
            await self._event_bus.publish(Event(
                type=EventType.BAR_COMPLETE,
                data=bar,
                source="alpaca_stream"
            ))

        except Exception as e:
            logger.error("bar_handler_error", error=str(e), symbol=data.symbol)

    async def start(self) -> None:
        """Start the WebSocket stream"""
        if self._running:
            logger.warning("stream_already_running")
            return

        if not self.symbols:
            logger.warning("no_symbols_to_stream")
            return

        self._stream = self._create_stream()

        # Register handlers
        self._stream.subscribe_quotes(self._handle_quote, *self.symbols)
        self._stream.subscribe_trades(self._handle_trade, *self.symbols)
        self._stream.subscribe_bars(self._handle_bar, *self.symbols)

        self._running = True
        self._reconnect_attempts = 0

        logger.info("stream_starting", symbols=list(self.symbols))

        try:
            # Run in background - alpaca-py handles the event loop
            await self._stream._run_forever()
        except Exception as e:
            logger.error("stream_error", error=str(e))
            self._running = False
            await self._handle_disconnect()

    async def _handle_disconnect(self) -> None:
        """Handle stream disconnection with reconnect logic"""
        self._reconnect_attempts += 1

        if self._reconnect_attempts > self._max_reconnects:
            logger.error("max_reconnects_exceeded")
            raise StreamDisconnected("Max reconnection attempts exceeded")

        wait_time = min(2 ** self._reconnect_attempts, 60)
        logger.warning(
            "stream_reconnecting",
            attempt=self._reconnect_attempts,
            wait_seconds=wait_time
        )

        await asyncio.sleep(wait_time)
        await self.start()

    async def stop(self) -> None:
        """Stop the stream"""
        self._running = False
        if self._stream:
            await self._stream.stop()
            self._stream = None
        logger.info("stream_stopped", quotes=self._quote_count, trades=self._trade_count)

    def add_symbols(self, symbols: Set[str]) -> None:
        """Add symbols to stream (requires restart)"""
        new_symbols = symbols - self.symbols
        if new_symbols:
            self.symbols.update(new_symbols)
            logger.info("symbols_added", new=list(new_symbols))

    def remove_symbols(self, symbols: Set[str]) -> None:
        """Remove symbols from stream (requires restart)"""
        self.symbols -= symbols
        logger.info("symbols_removed", removed=list(symbols))

    def on_quote(self, callback: Callable) -> None:
        """Register quote callback"""
        self._quote_callbacks.append(callback)

    def on_trade(self, callback: Callable) -> None:
        """Register trade callback"""
        self._trade_callbacks.append(callback)

    def on_bar(self, callback: Callable) -> None:
        """Register bar callback"""
        self._bar_callbacks.append(callback)

    @property
    def stats(self) -> Dict:
        """Get stream statistics"""
        return {
            "running": self._running,
            "symbols": len(self.symbols),
            "quotes_received": self._quote_count,
            "trades_received": self._trade_count,
            "bars_received": self._bar_count,
            "reconnect_attempts": self._reconnect_attempts
        }


# Module-level instance management
_stream_instance: Optional[AlpacaStream] = None


def get_stream() -> AlpacaStream:
    """Get or create stream singleton"""
    global _stream_instance
    if _stream_instance is None:
        _stream_instance = AlpacaStream()
    return _stream_instance


async def start_stream(symbols: Set[str]) -> AlpacaStream:
    """Start stream with given symbols"""
    stream = get_stream()
    stream.add_symbols(symbols)
    await stream.start()
    return stream
