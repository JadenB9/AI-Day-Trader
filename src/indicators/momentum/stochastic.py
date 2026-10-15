"""
Stochastic Oscillator indicator.
"""
from typing import List, Optional, Tuple
import numpy as np

from src.indicators.base import Indicator, get_highs, get_lows
from src.data.models.market_snapshot import Bar


class Stochastic(Indicator):
    """
    Stochastic Oscillator.
    Compares closing price to price range over period.

    %K = (Current Close - Lowest Low) / (Highest High - Lowest Low) * 100
    %D = SMA of %K

    Default: 14, 3, 3 (K period, K smoothing, D period)
    """

    def __init__(self, k_period: int = 14, k_smooth: int = 1, d_period: int = 3):
        super().__init__(f"stoch_{k_period}_{k_smooth}_{d_period}")
        self.k_period = k_period
        self.k_smooth = k_smooth
        self.d_period = d_period

        self._k_value: Optional[float] = None
        self._d_value: Optional[float] = None
        self._k_history: List[float] = []

    def required_bars(self) -> int:
        return self.k_period + self.d_period

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        """Calculate Stochastic. Returns %K value."""
        if len(bars) < self.k_period:
            return None

        # Calculate raw %K values
        k_values = []
        for i in range(self.k_period - 1, len(bars)):
            window = bars[i - self.k_period + 1:i + 1]
            highs = get_highs(window)
            lows = get_lows(window)

            highest = np.max(highs)
            lowest = np.min(lows)
            current_close = bars[i].close

            if highest == lowest:
                k = 50.0
            else:
                k = ((current_close - lowest) / (highest - lowest)) * 100

            k_values.append(k)

        if not k_values:
            return None

        # Apply smoothing to %K if specified
        if self.k_smooth > 1 and len(k_values) >= self.k_smooth:
            smoothed_k = np.convolve(k_values, np.ones(self.k_smooth)/self.k_smooth, mode='valid')
            k_values = list(smoothed_k)

        self._k_value = k_values[-1]
        self._k_history.append(self._k_value)

        # Calculate %D (SMA of %K)
        if len(self._k_history) >= self.d_period:
            self._d_value = np.mean(self._k_history[-self.d_period:])
        else:
            self._d_value = self._k_value

        self._values.append(self._k_value)
        return self._k_value

    def get_values(self) -> Tuple[Optional[float], Optional[float]]:
        """Get both %K and %D values"""
        return self._k_value, self._d_value

    @property
    def k(self) -> Optional[float]:
        return self._k_value

    @property
    def d(self) -> Optional[float]:
        return self._d_value

    def get_signal(self) -> str:
        """
        Get trading signal from Stochastic.

        Returns:
            'overbought': Both K and D > 80
            'oversold': Both K and D < 20
            'bullish_cross': K crossed above D in oversold
            'bearish_cross': K crossed below D in overbought
            'neutral': No clear signal
        """
        if self._k_value is None or self._d_value is None:
            return "neutral"

        # Overbought/Oversold zones
        if self._k_value > 80 and self._d_value > 80:
            return "overbought"
        if self._k_value < 20 and self._d_value < 20:
            return "oversold"

        # Cross signals (simplified - would need history for actual cross detection)
        if self._k_value > self._d_value and self._k_value < 30:
            return "bullish_momentum"
        if self._k_value < self._d_value and self._k_value > 70:
            return "bearish_momentum"

        return "neutral"

    @staticmethod
    def interpret(k: float, d: float) -> str:
        """Interpret Stochastic values"""
        if k > 80:
            if k > d:
                return "overbought_rising"
            return "overbought_falling"
        elif k < 20:
            if k > d:
                return "oversold_rising"
            return "oversold_falling"
        elif k > d:
            return "bullish"
        elif k < d:
            return "bearish"
        return "neutral"


class FastStochastic(Stochastic):
    """Fast Stochastic (unsmoothed %K)"""

    def __init__(self, k_period: int = 14, d_period: int = 3):
        super().__init__(k_period, k_smooth=1, d_period=d_period)
        self.name = f"fast_stoch_{k_period}_{d_period}"


class SlowStochastic(Stochastic):
    """Slow Stochastic (smoothed %K)"""

    def __init__(self, k_period: int = 14, d_period: int = 3):
        super().__init__(k_period, k_smooth=3, d_period=d_period)
        self.name = f"slow_stoch_{k_period}_{d_period}"
