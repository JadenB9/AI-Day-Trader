"""
Alpaca crypto historical data client using alpaca-py.
Supports 24/7 crypto trading with all available symbols.
"""
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import structlog

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import (
    CryptoBarsRequest,
    CryptoLatestQuoteRequest,
    CryptoSnapshotRequest
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from config.settings import get_settings
from src.data.models.market_snapshot import Bar, Quote, MarketSnapshot, BarTimeframe
from src.core.exceptions import DataError

logger = structlog.get_logger()
settings = get_settings()


class AlpacaCryptoClient:
    """
    Client for fetching crypto market data from Alpaca.
    Works 24/7 - no market hours restrictions.
    """

    def __init__(self):
        self._client = CryptoHistoricalDataClient(
            api_key=settings.alpaca.api_key,
            secret_key=settings.alpaca.secret_key
        )

    def _timeframe_to_alpaca(self, tf: BarTimeframe) -> TimeFrame:
        mapping = {
            BarTimeframe.MIN_1: TimeFrame(1, TimeFrameUnit.Minute),
            BarTimeframe.MIN_5: TimeFrame(5, TimeFrameUnit.Minute),
            BarTimeframe.MIN_15: TimeFrame(15, TimeFrameUnit.Minute),
            BarTimeframe.HOUR: TimeFrame(1, TimeFrameUnit.Hour),
            BarTimeframe.DAY: TimeFrame(1, TimeFrameUnit.Day),
        }
        return mapping.get(tf, TimeFrame(1, TimeFrameUnit.Minute))

    def _normalize_symbol(self, symbol: str) -> str:
        """Ensure symbol is in crypto format (BTC/USD)"""
        if "/" not in symbol:
            return f"{symbol}/USD"
        return symbol

    async def get_bars(
        self,
        symbol: str,
        timeframe: BarTimeframe = BarTimeframe.MIN_1,
        start: datetime = None,
        end: datetime = None,
        limit: int = 100
    ) -> List[Bar]:
        """Fetch historical crypto bars"""
        symbol = self._normalize_symbol(symbol)

        try:
            if end is None:
                end = datetime.now()
            if start is None:
                if timeframe == BarTimeframe.MIN_1:
                    start = end - timedelta(minutes=limit)
                elif timeframe == BarTimeframe.MIN_5:
                    start = end - timedelta(minutes=limit * 5)
                elif timeframe == BarTimeframe.MIN_15:
                    start = end - timedelta(minutes=limit * 15)
                elif timeframe == BarTimeframe.HOUR:
                    start = end - timedelta(hours=limit)
                else:
                    start = end - timedelta(days=limit)

            request = CryptoBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=self._timeframe_to_alpaca(timeframe),
                start=start,
                end=end,
                limit=limit
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.get_crypto_bars(request)
            )

            bars = []
            if symbol in response:
                for bar_data in response[symbol]:
                    bars.append(Bar(
                        symbol=symbol,
                        timestamp=bar_data.timestamp,
                        open=float(bar_data.open),
                        high=float(bar_data.high),
                        low=float(bar_data.low),
                        close=float(bar_data.close),
                        volume=float(bar_data.volume),
                        vwap=float(bar_data.vwap) if bar_data.vwap else None,
                        trade_count=bar_data.trade_count if hasattr(bar_data, 'trade_count') else None,
                        timeframe=timeframe
                    ))

            return bars

        except Exception as e:
            logger.error("crypto_get_bars_error", symbol=symbol, error=str(e))
            raise DataError(f"Failed to fetch crypto bars for {symbol}: {e}")

    async def get_latest_quote(self, symbol: str) -> Optional[Quote]:
        """Get latest crypto quote"""
        symbol = self._normalize_symbol(symbol)

        try:
            request = CryptoLatestQuoteRequest(symbol_or_symbols=symbol)

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.get_crypto_latest_quote(request)
            )

            if symbol in response:
                q = response[symbol]
                return Quote(
                    symbol=symbol,
                    bid=float(q.bid_price),
                    ask=float(q.ask_price),
                    bid_size=float(q.bid_size),
                    ask_size=float(q.ask_size),
                    timestamp=q.timestamp
                )
            return None

        except Exception as e:
            logger.error("crypto_get_quote_error", symbol=symbol, error=str(e))
            return None

    async def get_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get crypto market snapshot"""
        symbol = self._normalize_symbol(symbol)

        try:
            request = CryptoSnapshotRequest(symbol_or_symbols=symbol)

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.get_crypto_snapshot(request)
            )

            if symbol in response:
                snap = response[symbol]
                return {
                    'symbol': symbol,
                    'latest_trade': {
                        'price': float(snap.latest_trade.price) if snap.latest_trade else None,
                        'size': float(snap.latest_trade.size) if snap.latest_trade else None,
                        'timestamp': snap.latest_trade.timestamp if snap.latest_trade else None
                    },
                    'latest_quote': {
                        'bid': float(snap.latest_quote.bid_price) if snap.latest_quote else None,
                        'ask': float(snap.latest_quote.ask_price) if snap.latest_quote else None,
                        'bid_size': float(snap.latest_quote.bid_size) if snap.latest_quote else None,
                        'ask_size': float(snap.latest_quote.ask_size) if snap.latest_quote else None
                    },
                    'minute_bar': {
                        'open': float(snap.minute_bar.open) if snap.minute_bar else None,
                        'high': float(snap.minute_bar.high) if snap.minute_bar else None,
                        'low': float(snap.minute_bar.low) if snap.minute_bar else None,
                        'close': float(snap.minute_bar.close) if snap.minute_bar else None,
                        'volume': float(snap.minute_bar.volume) if snap.minute_bar else None,
                        'vwap': float(snap.minute_bar.vwap) if snap.minute_bar and snap.minute_bar.vwap else None
                    },
                    'daily_bar': {
                        'open': float(snap.daily_bar.open) if snap.daily_bar else None,
                        'high': float(snap.daily_bar.high) if snap.daily_bar else None,
                        'low': float(snap.daily_bar.low) if snap.daily_bar else None,
                        'close': float(snap.daily_bar.close) if snap.daily_bar else None,
                        'volume': float(snap.daily_bar.volume) if snap.daily_bar else None
                    },
                    'prev_daily_bar': {
                        'close': float(snap.previous_daily_bar.close) if snap.previous_daily_bar else None,
                        'volume': float(snap.previous_daily_bar.volume) if snap.previous_daily_bar else None
                    }
                }
            return None

        except Exception as e:
            logger.error("crypto_get_snapshot_error", symbol=symbol, error=str(e))
            return None

    async def get_multi_bars(
        self,
        symbols: List[str],
        timeframe: BarTimeframe = BarTimeframe.MIN_1,
        limit: int = 100
    ) -> Dict[str, List[Bar]]:
        """Fetch bars for multiple crypto symbols"""
        symbols = [self._normalize_symbol(s) for s in symbols]
        end = datetime.now()

        if timeframe == BarTimeframe.MIN_1:
            start = end - timedelta(minutes=limit)
        elif timeframe == BarTimeframe.MIN_5:
            start = end - timedelta(minutes=limit * 5)
        else:
            start = end - timedelta(days=limit)

        try:
            request = CryptoBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=self._timeframe_to_alpaca(timeframe),
                start=start,
                end=end,
                limit=limit
            )

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self._client.get_crypto_bars(request)
            )

            result = {}
            for symbol in symbols:
                if symbol in response:
                    result[symbol] = [
                        Bar(
                            symbol=symbol,
                            timestamp=b.timestamp,
                            open=float(b.open),
                            high=float(b.high),
                            low=float(b.low),
                            close=float(b.close),
                            volume=float(b.volume),
                            vwap=float(b.vwap) if b.vwap else None,
                            timeframe=timeframe
                        )
                        for b in response[symbol]
                    ]
                else:
                    result[symbol] = []

            return result

        except Exception as e:
            logger.error("crypto_get_multi_bars_error", symbols=symbols, error=str(e))
            raise DataError(f"Failed to fetch crypto multi bars: {e}")

    async def build_market_snapshot(self, symbol: str) -> MarketSnapshot:
        """Build complete market snapshot for a crypto symbol"""
        symbol = self._normalize_symbol(symbol)

        snapshot = MarketSnapshot(
            symbol=symbol,
            timestamp=datetime.now(),
            asset_class="crypto"
        )

        quote_task = self.get_latest_quote(symbol)
        snap_task = self.get_snapshot(symbol)
        bars_1m_task = self.get_bars(symbol, BarTimeframe.MIN_1, limit=60)
        bars_5m_task = self.get_bars(symbol, BarTimeframe.MIN_5, limit=30)
        bars_15m_task = self.get_bars(symbol, BarTimeframe.MIN_15, limit=20)

        quote, snap_data, bars_1m, bars_5m, bars_15m = await asyncio.gather(
            quote_task, snap_task, bars_1m_task, bars_5m_task, bars_15m_task
        )

        if quote:
            snapshot.bid = quote.bid
            snapshot.ask = quote.ask

        if snap_data:
            if snap_data.get('latest_trade', {}).get('price'):
                snapshot.last_price = snap_data['latest_trade']['price']
                snapshot.last_size = snap_data['latest_trade'].get('size', 0)

            daily = snap_data.get('daily_bar', {})
            if daily.get('open'):
                snapshot.day_open = daily['open']
                snapshot.day_high = daily['high']
                snapshot.day_low = daily['low']
                snapshot.day_volume = daily.get('volume', 0)

            prev = snap_data.get('prev_daily_bar', {})
            if prev.get('close'):
                snapshot.prev_close = prev['close']

        snapshot.bars_1m = bars_1m
        snapshot.bars_5m = bars_5m
        snapshot.bars_15m = bars_15m

        return snapshot


_crypto_client: Optional[AlpacaCryptoClient] = None


def get_crypto_client() -> AlpacaCryptoClient:
    """Get or create crypto client singleton"""
    global _crypto_client
    if _crypto_client is None:
        _crypto_client = AlpacaCryptoClient()
    return _crypto_client
