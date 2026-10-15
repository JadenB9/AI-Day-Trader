"""
Alpaca WebSocket streaming for real-time crypto data.
24/7 operation - no market hours restrictions.
"""
import asyncio
from typing import Set, Callable, Optional, Dict, List
import structlog

from alpaca.data.live import CryptoDataStream
from alpaca.data.models import Quote as AlpacaQuote, Trade as AlpacaTrade, Bar as AlpacaBar

from config.settings import get_settings
from src.core.event_bus import get_event_bus, EventType, Event
from src.core.exceptions import StreamDisconnected
from src.data.models.market_snapshot import Quote, Trade, Bar, BarTimeframe

logger = structlog.get_logger()
settings = get_settings()


class AlpacaCryptoStream:
    """
    Real-time crypto data streaming via Alpaca WebSocket.
    Works 24/7 - no market hours restrictions.
    """

    def __init__(self, symbols: Set[str] = None):
        self.symbols = symbols or set(settings.crypto.symbols)
        self._stream: Optional[CryptoDataStream] = None
        self._running = False
        self._reconnect_attempts = 0
        self._max_reconnects = 5
        self._event_bus = get_event_bus()

        self._quote_callbacks: List[Callable] = []
        self._trade_callbacks: List[Callable] = []
        self._bar_callbacks: List[Callable] = []

        self._quote_count = 0
        self._trade_count = 0
        self._bar_count = 0

    def _normalize_symbols(self, symbols: Set[str]) -> Set[str]:
        """Ensure all symbols are in crypto format"""
        return {s if "/" in s else f"{s}/USD" for s in symbols}

    def _create_stream(self) -> CryptoDataStream:
        return CryptoDataStream(
            api_key=settings.alpaca.api_key,
            secret_key=settings.alpaca.secret_key,
            raw_data=False
        )

    async def _handle_quote(self, data: AlpacaQuote) -> None:
        try:
            quote = Quote(
                symbol=data.symbol,
                bid=float(data.bid_price),
                ask=float(data.ask_price),
                bid_size=float(data.bid_size),
                ask_size=float(data.ask_size),
                timestamp=data.timestamp
            )

            self._quote_count += 1

            for cb in self._quote_callbacks:
                try:
                    result = cb(quote)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error("crypto_quote_callback_error", error=str(e))

            await self._event_bus.publish(Event(
                type=EventType.QUOTE_UPDATE,
                data=quote,
                source="crypto_stream"
            ))

        except Exception as e:
            logger.error("crypto_quote_handler_error", error=str(e), symbol=data.symbol)

    async def _handle_trade(self, data: AlpacaTrade) -> None:
        try:
            trade = Trade(
                symbol=data.symbol,
                price=float(data.price),
                size=float(data.size),
                timestamp=data.timestamp,
                exchange=data.exchange if hasattr(data, 'exchange') else ""
            )

            self._trade_count += 1

            for cb in self._trade_callbacks:
                try:
                    result = cb(trade)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error("crypto_trade_callback_error", error=str(e))

            await self._event_bus.publish(Event(
                type=EventType.TRADE_TICK,
                data=trade,
                source="crypto_stream"
            ))

        except Exception as e:
            logger.error("crypto_trade_handler_error", error=str(e), symbol=data.symbol)

    async def _handle_bar(self, data: AlpacaBar) -> None:
        try:
            bar = Bar(
                symbol=data.symbol,
                timestamp=data.timestamp,
                open=float(data.open),
                high=float(data.high),
                low=float(data.low),
                close=float(data.close),
                volume=float(data.volume),
                vwap=float(data.vwap) if data.vwap else None,
                trade_count=data.trade_count if hasattr(data, 'trade_count') else None,
                timeframe=BarTimeframe.MIN_1
            )

            self._bar_count += 1

            for cb in self._bar_callbacks:
                try:
                    result = cb(bar)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error("crypto_bar_callback_error", error=str(e))

            await self._event_bus.publish(Event(
                type=EventType.BAR_COMPLETE,
                data=bar,
                source="crypto_stream"
            ))

        except Exception as e:
            logger.error("crypto_bar_handler_error", error=str(e), symbol=data.symbol)

    async def start(self) -> None:
        if self._running:
            return

        if not self.symbols:
            logger.warning("no_crypto_symbols_to_stream")
            return

        self.symbols = self._normalize_symbols(self.symbols)
        self._stream = self._create_stream()

        self._stream.subscribe_quotes(self._handle_quote, *self.symbols)
        self._stream.subscribe_trades(self._handle_trade, *self.symbols)
        self._stream.subscribe_bars(self._handle_bar, *self.symbols)

        self._running = True
        self._reconnect_attempts = 0

        logger.info("crypto_stream_starting", symbols=list(self.symbols))

        try:
            await self._stream._run_forever()
        except Exception as e:
            logger.error("crypto_stream_error", error=str(e))
            self._running = False
            await self._handle_disconnect()

    async def _handle_disconnect(self) -> None:
        self._reconnect_attempts += 1

        if self._reconnect_attempts > self._max_reconnects:
            raise StreamDisconnected("Max crypto reconnection attempts exceeded")

        wait_time = min(2 ** self._reconnect_attempts, 60)
        logger.warning(
            "crypto_stream_reconnecting",
            attempt=self._reconnect_attempts,
            wait_seconds=wait_time
        )

        await asyncio.sleep(wait_time)
        await self.start()

    async def stop(self) -> None:
        self._running = False
        if self._stream:
            await self._stream.stop()
            self._stream = None
        logger.info("crypto_stream_stopped", quotes=self._quote_count, trades=self._trade_count)

    def add_symbols(self, symbols: Set[str]) -> None:
        new_symbols = self._normalize_symbols(symbols) - self.symbols
        if new_symbols:
            self.symbols.update(new_symbols)
            logger.info("crypto_symbols_added", new=list(new_symbols))

    def remove_symbols(self, symbols: Set[str]) -> None:
        self.symbols -= self._normalize_symbols(symbols)

    def on_quote(self, callback: Callable) -> None:
        self._quote_callbacks.append(callback)

    def on_trade(self, callback: Callable) -> None:
        self._trade_callbacks.append(callback)

    def on_bar(self, callback: Callable) -> None:
        self._bar_callbacks.append(callback)

    @property
    def stats(self) -> Dict:
        return {
            "running": self._running,
            "symbols": len(self.symbols),
            "quotes_received": self._quote_count,
            "trades_received": self._trade_count,
            "bars_received": self._bar_count,
            "reconnect_attempts": self._reconnect_attempts
        }


_crypto_stream: Optional[AlpacaCryptoStream] = None


def get_crypto_stream() -> AlpacaCryptoStream:
    global _crypto_stream
    if _crypto_stream is None:
        _crypto_stream = AlpacaCryptoStream()
    return _crypto_stream


async def start_crypto_stream(symbols: Set[str] = None) -> AlpacaCryptoStream:
    stream = get_crypto_stream()
    if symbols:
        stream.add_symbols(symbols)
    await stream.start()
    return stream
