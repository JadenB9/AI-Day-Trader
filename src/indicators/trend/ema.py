"""
Exponential Moving Average indicators.
"""
from typing import List, Optional, Dict
import numpy as np

from src.indicators.base import Indicator, get_closes
from src.data.models.market_snapshot import Bar


class EMA(Indicator):
    """
    Exponential Moving Average.
    Gives more weight to recent prices.
    """

    def __init__(self, period: int = 20):
        super().__init__(f"ema_{period}", period=period)
        self.period = period
        self._multiplier = 2 / (period + 1)
        self._prev_ema: Optional[float] = None

    def required_bars(self) -> int:
        return self.period

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        if len(bars) < self.period:
            return None

        closes = get_closes(bars)

        # Start with SMA for first EMA value
        if self._prev_ema is None:
            sma = np.mean(closes[:self.period])
            ema_values = [sma]

            # Calculate EMA for remaining values
            for close in closes[self.period:]:
                ema_val = (close * self._multiplier) + (ema_values[-1] * (1 - self._multiplier))
                ema_values.append(ema_val)

            current_ema = ema_values[-1]
        else:
            current_ema = (closes[-1] * self._multiplier) + (self._prev_ema * (1 - self._multiplier))

        self._prev_ema = current_ema
        self._values.append(current_ema)
        return current_ema

    def update(self, bar: Bar) -> Optional[float]:
        """Incremental EMA update with new bar"""
        if self._prev_ema is None:
            return None

        new_ema = (bar.close * self._multiplier) + (self._prev_ema * (1 - self._multiplier))
        self._prev_ema = new_ema
        self._values.append(new_ema)
        return new_ema


class SMA(Indicator):
    """Simple Moving Average"""

    def __init__(self, period: int = 20):
        super().__init__(f"sma_{period}", period=period)
        self.period = period

    def required_bars(self) -> int:
        return self.period

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        if len(bars) < self.period:
            return None

        closes = get_closes(bars[-self.period:])
        sma = np.mean(closes)
        self._values.append(sma)
        return sma


class MultiEMA(Indicator):
    """
    Multiple EMAs calculated together.
    Common for scalping: 9, 21, 55
    """

    def __init__(self, periods: List[int] = None):
        if periods is None:
            periods = [9, 21, 55]
        super().__init__(f"multi_ema_{'_'.join(map(str, periods))}")
        self.periods = sorted(periods)
        self._emas: Dict[int, EMA] = {p: EMA(p) for p in periods}
        self._current_values: Dict[int, float] = {}

    def required_bars(self) -> int:
        return max(self.periods)

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        """
        Calculate all EMAs. Returns shortest EMA value.
        Use get_all() for all values.
        """
        if len(bars) < self.required_bars():
            return None

        self._current_values.clear()
        for period, ema in self._emas.items():
            value = ema.calculate(bars)
            if value is not None:
                self._current_values[period] = value

        # Return fastest EMA
        fastest = self.periods[0]
        return self._current_values.get(fastest)

    def get(self, period: int) -> Optional[float]:
        """Get specific EMA value"""
        return self._current_values.get(period)

    def get_all(self) -> Dict[int, float]:
        """Get all EMA values"""
        return self._current_values.copy()

    def get_trend(self) -> str:
        """
        Determine trend from EMA alignment.

        Returns:
            'strong_bullish': All EMAs aligned (9 > 21 > 55)
            'bullish': Price above all EMAs
            'bearish': Price below all EMAs
            'strong_bearish': Reverse alignment
            'mixed': No clear trend
        """
        if len(self._current_values) < 2:
            return "mixed"

        sorted_periods = sorted(self.periods)
        values = [self._current_values.get(p) for p in sorted_periods]

        if any(v is None for v in values):
            return "mixed"

        # Check alignment
        bullish_align = all(values[i] > values[i+1] for i in range(len(values)-1))
        bearish_align = all(values[i] < values[i+1] for i in range(len(values)-1))

        if bullish_align:
            return "strong_bullish"
        elif bearish_align:
            return "strong_bearish"

        # Check just fast vs slow
        if values[0] > values[-1]:
            return "bullish"
        elif values[0] < values[-1]:
            return "bearish"

        return "mixed"


class EMACrossover:
    """
    Detect EMA crossovers.
    Common: 9/21 or 12/26
    """

    def __init__(self, fast: int = 9, slow: int = 21):
        self.fast_period = fast
        self.slow_period = slow
        self._fast_ema = EMA(fast)
        self._slow_ema = EMA(slow)
        self._prev_diff: Optional[float] = None

    def calculate(self, bars: List[Bar]) -> Optional[str]:
        """
        Calculate and detect crossover.

        Returns:
            'bullish_cross': Fast crossed above slow
            'bearish_cross': Fast crossed below slow
            'above': Fast above slow, no cross
            'below': Fast below slow, no cross
            None: Insufficient data
        """
        if len(bars) < self.slow_period:
            return None

        fast = self._fast_ema.calculate(bars)
        slow = self._slow_ema.calculate(bars)

        if fast is None or slow is None:
            return None

        diff = fast - slow

        # Detect crossover
        result = None
        if self._prev_diff is not None:
            if self._prev_diff < 0 and diff > 0:
                result = "bullish_cross"
            elif self._prev_diff > 0 and diff < 0:
                result = "bearish_cross"
            elif diff > 0:
                result = "above"
            else:
                result = "below"
        elif diff > 0:
            result = "above"
        else:
            result = "below"

        self._prev_diff = diff
        return result

    @property
    def fast_value(self) -> Optional[float]:
        return self._fast_ema.last_value

    @property
    def slow_value(self) -> Optional[float]:
        return self._slow_ema.last_value

    @property
    def spread(self) -> Optional[float]:
        """Difference between fast and slow EMA"""
        if self._prev_diff is not None:
            return self._prev_diff
        return None
