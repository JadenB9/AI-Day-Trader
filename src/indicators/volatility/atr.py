"""
ATR (Average True Range) - Volatility indicator.
"""
from typing import List, Optional
import numpy as np

from src.indicators.base import Indicator
from src.data.models.market_snapshot import Bar


class ATR(Indicator):
    """
    Average True Range.
    Measures market volatility.

    True Range = max(H-L, |H-Pc|, |L-Pc|)
    where Pc = previous close

    Used for:
    - Stop loss placement (e.g., 2 ATR from entry)
    - Position sizing
    - Volatility filtering
    """

    def __init__(self, period: int = 14):
        super().__init__(f"atr_{period}", period=period)
        self.period = period
        self._prev_atr: Optional[float] = None

    def required_bars(self) -> int:
        return self.period + 1

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        if len(bars) < self.required_bars():
            return None

        # Calculate True Ranges
        tr_values = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i-1].close

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)

        # Wilder's smoothing for ATR
        if len(tr_values) >= self.period:
            if self._prev_atr is None:
                # First ATR is simple average
                atr = np.mean(tr_values[:self.period])
            else:
                # Subsequent ATR uses smoothing
                atr = ((self._prev_atr * (self.period - 1)) + tr_values[-1]) / self.period

            self._prev_atr = atr
            self._values.append(atr)
            return atr

        return None

    def update(self, bar: Bar, prev_close: float) -> Optional[float]:
        """Incremental update with new bar"""
        if self._prev_atr is None:
            return None

        tr = max(
            bar.high - bar.low,
            abs(bar.high - prev_close),
            abs(bar.low - prev_close)
        )

        atr = ((self._prev_atr * (self.period - 1)) + tr) / self.period
        self._prev_atr = atr
        self._values.append(atr)
        return atr

    def get_stop_distance(self, multiplier: float = 2.0) -> Optional[float]:
        """Get stop loss distance based on ATR"""
        if self._prev_atr is None:
            return None
        return self._prev_atr * multiplier

    def get_position_size(
        self,
        account_risk: float,
        multiplier: float = 2.0
    ) -> Optional[float]:
        """
        Calculate position size based on ATR risk.

        Args:
            account_risk: Dollar amount to risk
            multiplier: ATR multiplier for stop distance

        Returns:
            Number of shares
        """
        stop_distance = self.get_stop_distance(multiplier)
        if stop_distance is None or stop_distance == 0:
            return None

        return account_risk / stop_distance


class ATRPercent(Indicator):
    """
    ATR as percentage of price.
    Useful for comparing volatility across different price levels.
    """

    def __init__(self, period: int = 14):
        super().__init__(f"atr_pct_{period}", period=period)
        self._atr = ATR(period)

    def required_bars(self) -> int:
        return self._atr.required_bars()

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        atr = self._atr.calculate(bars)
        if atr is None:
            return None

        current_price = bars[-1].close
        if current_price == 0:
            return None

        atr_pct = (atr / current_price) * 100
        self._values.append(atr_pct)
        return atr_pct


class TrueRange(Indicator):
    """Single True Range calculation (not averaged)"""

    def __init__(self):
        super().__init__("true_range")

    def required_bars(self) -> int:
        return 2

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        if len(bars) < 2:
            return None

        current = bars[-1]
        prev = bars[-2]

        tr = max(
            current.high - current.low,
            abs(current.high - prev.close),
            abs(current.low - prev.close)
        )

        self._values.append(tr)
        return tr
