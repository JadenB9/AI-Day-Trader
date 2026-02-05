"""
ADX (Average Directional Index) - Trend strength indicator.
"""
from typing import List, Optional, Tuple
import numpy as np

from src.indicators.base import Indicator, get_highs, get_lows, get_closes
from src.data.models.market_snapshot import Bar


class ADX(Indicator):
    """
    Average Directional Index.
    Measures trend strength regardless of direction.

    Components:
    - +DI: Positive Directional Indicator
    - -DI: Negative Directional Indicator
    - ADX: Smoothed average of DX

    Interpretation:
    - ADX < 20: Weak/no trend
    - ADX 20-25: Trend may be emerging
    - ADX 25-50: Strong trend
    - ADX > 50: Very strong trend
    """

    def __init__(self, period: int = 14):
        super().__init__(f"adx_{period}", period=period)
        self.period = period

        self._plus_di: Optional[float] = None
        self._minus_di: Optional[float] = None
        self._adx: Optional[float] = None

        # Internal smoothing
        self._smooth_plus_dm: Optional[float] = None
        self._smooth_minus_dm: Optional[float] = None
        self._smooth_tr: Optional[float] = None
        self._adx_values: List[float] = []

    def required_bars(self) -> int:
        return self.period * 2 + 1  # Need extra for smoothing

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        if len(bars) < self.required_bars():
            return None

        highs = get_highs(bars)
        lows = get_lows(bars)
        closes = get_closes(bars)

        # Calculate True Range
        tr_list = []
        for i in range(1, len(bars)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i-1])
            lc = abs(lows[i] - closes[i-1])
            tr_list.append(max(hl, hc, lc))

        # Calculate Directional Movement
        plus_dm_list = []
        minus_dm_list = []
        for i in range(1, len(bars)):
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]

            if up_move > down_move and up_move > 0:
                plus_dm_list.append(up_move)
            else:
                plus_dm_list.append(0)

            if down_move > up_move and down_move > 0:
                minus_dm_list.append(down_move)
            else:
                minus_dm_list.append(0)

        # First smoothed values (Wilder's smoothing)
        smooth_tr = sum(tr_list[:self.period])
        smooth_plus_dm = sum(plus_dm_list[:self.period])
        smooth_minus_dm = sum(minus_dm_list[:self.period])

        # Calculate subsequent smoothed values
        dx_values = []
        for i in range(self.period, len(tr_list)):
            smooth_tr = smooth_tr - (smooth_tr / self.period) + tr_list[i]
            smooth_plus_dm = smooth_plus_dm - (smooth_plus_dm / self.period) + plus_dm_list[i]
            smooth_minus_dm = smooth_minus_dm - (smooth_minus_dm / self.period) + minus_dm_list[i]

            # +DI and -DI
            if smooth_tr != 0:
                plus_di = (smooth_plus_dm / smooth_tr) * 100
                minus_di = (smooth_minus_dm / smooth_tr) * 100
            else:
                plus_di = 0
                minus_di = 0

            # DX
            di_sum = plus_di + minus_di
            if di_sum != 0:
                dx = abs(plus_di - minus_di) / di_sum * 100
            else:
                dx = 0

            dx_values.append(dx)

        # ADX is smoothed DX
        if len(dx_values) >= self.period:
            # First ADX is simple average
            adx = sum(dx_values[:self.period]) / self.period

            # Subsequent ADX values
            for i in range(self.period, len(dx_values)):
                adx = ((adx * (self.period - 1)) + dx_values[i]) / self.period

            self._adx = adx
            self._plus_di = plus_di
            self._minus_di = minus_di

            self._values.append(adx)
            return adx

        return None

    def get_components(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Get (+DI, -DI, ADX)"""
        return self._plus_di, self._minus_di, self._adx

    @property
    def plus_di(self) -> Optional[float]:
        return self._plus_di

    @property
    def minus_di(self) -> Optional[float]:
        return self._minus_di

    @property
    def adx(self) -> Optional[float]:
        return self._adx

    def get_signal(self) -> str:
        """
        Get trend signal from ADX.

        Returns:
            'strong_uptrend': ADX > 25 and +DI > -DI
            'strong_downtrend': ADX > 25 and -DI > +DI
            'weak_uptrend': ADX < 25 and +DI > -DI
            'weak_downtrend': ADX < 25 and -DI > +DI
            'no_trend': ADX < 20
        """
        if self._adx is None or self._plus_di is None or self._minus_di is None:
            return "unknown"

        if self._adx < 20:
            return "no_trend"
        elif self._adx < 25:
            if self._plus_di > self._minus_di:
                return "weak_uptrend"
            else:
                return "weak_downtrend"
        else:  # ADX >= 25
            if self._plus_di > self._minus_di:
                return "strong_uptrend"
            else:
                return "strong_downtrend"

    @staticmethod
    def interpret(adx: float) -> str:
        """Interpret ADX value for trend strength"""
        if adx < 20:
            return "absent_weak"
        elif adx < 25:
            return "emerging"
        elif adx < 50:
            return "strong"
        elif adx < 75:
            return "very_strong"
        else:
            return "extreme"
