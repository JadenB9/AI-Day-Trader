"""
Utility functions and helpers.
"""
import asyncio
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, TypeVar
import pytz
from decimal import Decimal, ROUND_DOWN
import hashlib
import uuid

T = TypeVar('T')


def get_eastern_time() -> datetime:
    """Get current time in Eastern timezone"""
    et = pytz.timezone('America/New_York')
    return datetime.now(et)


def is_crypto_symbol(symbol: str) -> bool:
    """Check if symbol is a crypto pair (e.g., BTC/USD)"""
    return "/" in symbol


def is_market_open(extended_hours: bool = True, symbol: str = None) -> bool:
    """
    Check if market is currently open.
    Crypto markets are always open (24/7).
    """
    # Crypto is always open
    if symbol and is_crypto_symbol(symbol):
        return True

    now = get_eastern_time()

    # Weekend check for stocks
    if now.weekday() >= 5:
        return False

    current_time = now.time()

    if extended_hours:
        # Extended hours: 4:00 AM - 8:00 PM ET
        market_start = time(4, 0)
        market_end = time(20, 0)
    else:
        # Regular hours: 9:30 AM - 4:00 PM ET
        market_start = time(9, 30)
        market_end = time(16, 0)

    return market_start <= current_time <= market_end


def is_premarket() -> bool:
    """Check if currently in pre-market session"""
    now = get_eastern_time()
    if now.weekday() >= 5:
        return False
    current_time = now.time()
    return time(4, 0) <= current_time < time(9, 30)


def is_regular_hours() -> bool:
    """Check if currently in regular market hours"""
    now = get_eastern_time()
    if now.weekday() >= 5:
        return False
    current_time = now.time()
    return time(9, 30) <= current_time <= time(16, 0)


def is_afterhours() -> bool:
    """Check if currently in after-hours session"""
    now = get_eastern_time()
    if now.weekday() >= 5:
        return False
    current_time = now.time()
    return time(16, 0) < current_time <= time(20, 0)


def time_until_market_open() -> timedelta:
    """Get time until market opens"""
    now = get_eastern_time()
    today_open = now.replace(hour=9, minute=30, second=0, microsecond=0)

    if now.time() < time(9, 30):
        # Before open today
        return today_open - now
    else:
        # After today's open, calculate tomorrow
        if now.weekday() == 4:  # Friday
            days_until = 3
        elif now.weekday() == 5:  # Saturday
            days_until = 2
        else:
            days_until = 1
        next_open = today_open + timedelta(days=days_until)
        return next_open - now


def round_price(price: float, tick_size: float = 0.01) -> float:
    """Round price to valid tick size"""
    d = Decimal(str(price))
    tick = Decimal(str(tick_size))
    return float(d.quantize(tick, rounding=ROUND_DOWN))


def round_shares(shares: float) -> int:
    """Round shares to whole number"""
    return int(shares)


def calculate_position_value(shares: int, price: float) -> float:
    """Calculate total position value"""
    return shares * price


def generate_order_id() -> str:
    """Generate unique order ID"""
    return str(uuid.uuid4())[:8]


def generate_correlation_id() -> str:
    """Generate correlation ID for tracking related events"""
    return str(uuid.uuid4())


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """Safe division with default for zero divisor"""
    if b == 0:
        return default
    return a / b


def percent_change(old: float, new: float) -> float:
    """Calculate percent change"""
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max"""
    return max(min_val, min(max_val, value))


def chunks(lst: List[T], n: int) -> List[List[T]]:
    """Split list into chunks of size n"""
    return [lst[i:i + n] for i in range(0, len(lst), n)]


async def retry_async(
    func,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """Retry async function with exponential backoff"""
    last_exception = None
    current_delay = delay

    for attempt in range(max_retries):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries - 1:
                await asyncio.sleep(current_delay)
                current_delay *= backoff

    raise last_exception


def hash_dict(d: Dict) -> str:
    """Create hash of dictionary for caching"""
    import json
    serialized = json.dumps(d, sort_keys=True, default=str)
    return hashlib.md5(serialized.encode()).hexdigest()


def get_trading_capital(actual_equity: float) -> float:
    """
    Get effective trading capital.
    Uses virtual_capital setting if configured, otherwise actual equity.

    If virtual_capital is $1,000 and actual equity is $100,000,
    we treat it as if we only have $1,000 to trade with.
    """
    from config.settings import get_settings
    s = get_settings()

    if s.portfolio.virtual_capital > 0:
        return s.portfolio.virtual_capital
    return actual_equity


def is_capital_depleted(actual_equity: float) -> bool:
    """
    Check if trading should stop due to capital depletion.

    If virtual_capital is $1,000 starting from $100,000,
    and equity drops to $99,000 (lost $1,000), we're out of capital.
    """
    from config.settings import get_settings
    s = get_settings()

    if s.portfolio.capital_reserve > 0:
        return actual_equity <= s.portfolio.capital_reserve
    return actual_equity <= 0


def get_available_capital(actual_equity: float) -> float:
    """
    Get remaining capital available for trading.

    If actual equity is $100,500 and reserve is $99,000,
    available capital is $1,500.
    """
    from config.settings import get_settings
    s = get_settings()

    if s.portfolio.capital_reserve > 0:
        return max(0, actual_equity - s.portfolio.capital_reserve)

    if s.portfolio.virtual_capital > 0:
        return s.portfolio.virtual_capital

    return actual_equity


class MovingWindow:
    """Fixed-size moving window for streaming calculations"""

    def __init__(self, size: int):
        self.size = size
        self.data: List[float] = []

    def add(self, value: float) -> None:
        self.data.append(value)
        if len(self.data) > self.size:
            self.data.pop(0)

    def is_full(self) -> bool:
        return len(self.data) >= self.size

    def mean(self) -> float:
        if not self.data:
            return 0.0
        return sum(self.data) / len(self.data)

    def std(self) -> float:
        if len(self.data) < 2:
            return 0.0
        m = self.mean()
        variance = sum((x - m) ** 2 for x in self.data) / len(self.data)
        return variance ** 0.5

    def max(self) -> float:
        return max(self.data) if self.data else 0.0

    def min(self) -> float:
        return min(self.data) if self.data else 0.0

    def latest(self) -> Optional[float]:
        return self.data[-1] if self.data else None
