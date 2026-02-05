"""
MACD (Moving Average Convergence Divergence) indicator.
"""
from typing import List, Optional, Tuple
import numpy as np

from src.indicators.base import Indicator, get_closes
from src.data.models.market_snapshot import Bar


def ema(data: np.ndarray, period: int) -> np.ndarray:
    """Calculate Exponential Moving Average"""
    multiplier = 2 / (period + 1)
    ema_values = np.zeros(len(data))
    ema_values[0] = data[0]

    for i in range(1, len(data)):
        ema_values[i] = (data[i] * multiplier) + (ema_values[i-1] * (1 - multiplier))

    return ema_values


class MACD(Indicator):
    """
    MACD - Moving Average Convergence Divergence.

    Components:
    - MACD Line: Fast EMA - Slow EMA
    - Signal Line: EMA of MACD Line
    - Histogram: MACD Line - Signal Line

    Default periods: 12, 26, 9
    """

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__(f"macd_{fast}_{slow}_{signal}", fast=fast, slow=slow, signal=signal)
        self.fast = fast
        self.slow = slow
        self.signal_period = signal

        # Store components
        self._macd_line: Optional[float] = None
        self._signal_line: Optional[float] = None
        self._histogram: Optional[float] = None

    def required_bars(self) -> int:
        return self.slow + self.signal_period

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        """
        Calculate MACD. Returns histogram value (most commonly used for signals).
        Use get_components() for full MACD data.
        """
        if len(bars) < self.required_bars():
            return None

        closes = get_closes(bars)

        # Calculate EMAs
        fast_ema = ema(closes, self.fast)
        slow_ema = ema(closes, self.slow)

        # MACD line
        macd_line = fast_ema - slow_ema

        # Signal line (EMA of MACD)
        if len(macd_line) >= self.signal_period:
            signal_line = ema(macd_line[self.slow-1:], self.signal_period)
            signal_value = signal_line[-1]
        else:
            return None

        macd_value = macd_line[-1]
        histogram = macd_value - signal_value

        # Store values
        self._macd_line = macd_value
        self._signal_line = signal_value
        self._histogram = histogram
        self._values.append(histogram)

        return histogram

    def get_components(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Get all MACD components: (macd_line, signal_line, histogram)"""
        return self._macd_line, self._signal_line, self._histogram

    @property
    def macd_line(self) -> Optional[float]:
        return self._macd_line

    @property
    def signal_line(self) -> Optional[float]:
        return self._signal_line

    @property
    def histogram(self) -> Optional[float]:
        return self._histogram

    def get_signal(self) -> str:
        """
        Get trading signal from MACD.

        Returns:
            'bullish_cross': MACD crossed above signal
            'bearish_cross': MACD crossed below signal
            'bullish': MACD above signal, histogram positive
            'bearish': MACD below signal, histogram negative
            'neutral': No clear signal
        """
        if self._macd_line is None or self._signal_line is None:
            return "neutral"

        # Check histogram for momentum
        if self._histogram is not None:
            if self._histogram > 0:
                if self._macd_line > 0:
                    return "strong_bullish"
                return "bullish"
            elif self._histogram < 0:
                if self._macd_line < 0:
                    return "strong_bearish"
                return "bearish"

        return "neutral"


class MACDHistogram(Indicator):
    """
    Just the MACD histogram component.
    Useful for divergence analysis.
    """

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__(f"macd_hist_{fast}_{slow}_{signal}")
        self._macd = MACD(fast, slow, signal)

    def required_bars(self) -> int:
        return self._macd.required_bars()

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        return self._macd.calculate(bars)
