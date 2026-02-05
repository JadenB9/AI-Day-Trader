"""
Market data models for the trading system.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum


class BarTimeframe(str, Enum):
    MIN_1 = "1Min"
    MIN_5 = "5Min"
    MIN_15 = "15Min"
    HOUR = "1Hour"
    DAY = "1Day"


@dataclass
class Quote:
    """Real-time quote data"""
    symbol: str
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    timestamp: datetime

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        if self.mid == 0:
            return 0
        return (self.spread / self.mid) * 100


@dataclass
class Trade:
    """Individual trade tick"""
    symbol: str
    price: float
    size: int
    timestamp: datetime
    exchange: str = ""
    conditions: List[str] = field(default_factory=list)


@dataclass
class Bar:
    """OHLCV bar data"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None
    trade_count: Optional[int] = None
    timeframe: BarTimeframe = BarTimeframe.MIN_1

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low


@dataclass
class MarketSnapshot:
    """
    Complete market state for a symbol at a point in time.
    Used as input for strategy evaluation and AI context.
    """
    symbol: str
    timestamp: datetime

    # Current quote
    bid: float = 0.0
    ask: float = 0.0
    last_price: float = 0.0
    last_size: int = 0

    # Daily stats
    day_open: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    prev_close: float = 0.0
    day_volume: int = 0

    # Pre-market (if applicable)
    premarket_high: Optional[float] = None
    premarket_low: Optional[float] = None
    premarket_volume: Optional[int] = None

    # Recent bars (most recent first)
    bars_1m: List[Bar] = field(default_factory=list)
    bars_5m: List[Bar] = field(default_factory=list)
    bars_15m: List[Bar] = field(default_factory=list)

    # Calculated indicators (filled by IndicatorCalculator)
    indicators: Dict[str, float] = field(default_factory=dict)

    # News and sentiment
    recent_news: List[Dict[str, Any]] = field(default_factory=list)
    sentiment_score: Optional[float] = None

    @property
    def mid_price(self) -> float:
        if self.bid and self.ask:
            return (self.bid + self.ask) / 2
        return self.last_price

    @property
    def gap_pct(self) -> float:
        """Pre-market gap percentage"""
        if self.prev_close == 0 or self.day_open == 0:
            return 0
        return ((self.day_open - self.prev_close) / self.prev_close) * 100

    @property
    def day_change_pct(self) -> float:
        """Current day change percentage"""
        if self.prev_close == 0:
            return 0
        return ((self.last_price - self.prev_close) / self.prev_close) * 100

    @property
    def intraday_range_pct(self) -> float:
        """Intraday range as percentage"""
        if self.day_low == 0:
            return 0
        return ((self.day_high - self.day_low) / self.day_low) * 100

    @property
    def relative_volume(self) -> float:
        """Relative volume vs average (requires avg_volume in indicators)"""
        avg_vol = self.indicators.get('avg_volume', 0)
        if avg_vol == 0:
            return 0
        return self.day_volume / avg_vol

    def get_indicator(self, name: str, default: float = 0.0) -> float:
        """Safely get indicator value"""
        return self.indicators.get(name, default)

    def has_indicator(self, name: str) -> bool:
        """Check if indicator is calculated"""
        return name in self.indicators

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'bid': self.bid,
            'ask': self.ask,
            'last_price': self.last_price,
            'day_open': self.day_open,
            'day_high': self.day_high,
            'day_low': self.day_low,
            'prev_close': self.prev_close,
            'day_volume': self.day_volume,
            'gap_pct': self.gap_pct,
            'day_change_pct': self.day_change_pct,
            'indicators': self.indicators
        }


@dataclass
class PortfolioSnapshot:
    """Current portfolio state"""
    timestamp: datetime
    equity: float
    cash: float
    buying_power: float
    positions: Dict[str, 'PositionInfo'] = field(default_factory=dict)
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    portfolio_heat: float = 0.0  # Total risk exposure

    @property
    def position_count(self) -> int:
        return len(self.positions)


@dataclass
class PositionInfo:
    """Position information"""
    symbol: str
    quantity: int
    avg_entry: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    strategy: str = ""


@dataclass
class ScannerResult:
    """Result from pre-market scanner"""
    symbol: str
    score: float  # Composite score for ranking
    gap_pct: float
    premarket_volume: int
    relative_volume: float
    avg_volume: int
    price: float
    has_news: bool = False
    news_headlines: List[str] = field(default_factory=list)
    scan_type: str = ""  # gap, volume, momentum, earnings
    timestamp: datetime = field(default_factory=datetime.now)
