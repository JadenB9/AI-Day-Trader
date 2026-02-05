"""
Bollinger Bands indicator.
"""
from typing import List, Optional, Tuple
import numpy as np

from src.indicators.base import Indicator, get_closes
from src.data.models.market_snapshot import Bar


class BollingerBands(Indicator):
    """
    Bollinger Bands.
    Moving average with upper/lower bands based on standard deviation.

    Components:
    - Middle: SMA(period)
    - Upper: Middle + (std_dev * multiplier)
    - Lower: Middle - (std_dev * multiplier)

    Default: 20-period, 2 standard deviations

    Trading signals:
    - Price at lower band: potential oversold
    - Price at upper band: potential overbought
    - Band squeeze: volatility contraction, big move coming
    - Band expansion: trend starting
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        super().__init__(f"bbands_{period}_{std_dev}")
        self.period = period
        self.std_dev = std_dev

        self._upper: Optional[float] = None
        self._middle: Optional[float] = None
        self._lower: Optional[float] = None
        self._width: Optional[float] = None
        self._pct_b: Optional[float] = None

    def required_bars(self) -> int:
        return self.period

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        """
        Calculate Bollinger Bands.
        Returns %B (position within bands).
        """
        if len(bars) < self.period:
            return None

        closes = get_closes(bars[-self.period:])
        current_close = bars[-1].close

        # Middle band (SMA)
        self._middle = np.mean(closes)

        # Standard deviation
        std = np.std(closes, ddof=0)  # Population std dev

        # Upper and lower bands
        self._upper = self._middle + (std * self.std_dev)
        self._lower = self._middle - (std * self.std_dev)

        # Band width (normalized)
        if self._middle != 0:
            self._width = (self._upper - self._lower) / self._middle * 100
        else:
            self._width = 0

        # %B - where price is within bands
        band_range = self._upper - self._lower
        if band_range != 0:
            self._pct_b = (current_close - self._lower) / band_range
        else:
            self._pct_b = 0.5

        self._values.append(self._pct_b)
        return self._pct_b

    def get_bands(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Get (upper, middle, lower) band values"""
        return self._upper, self._middle, self._lower

    @property
    def upper(self) -> Optional[float]:
        return self._upper

    @property
    def middle(self) -> Optional[float]:
        return self._middle

    @property
    def lower(self) -> Optional[float]:
        return self._lower

    @property
    def width(self) -> Optional[float]:
        """Band width as percentage"""
        return self._width

    @property
    def pct_b(self) -> Optional[float]:
        """
        %B - Position within bands.
        0 = at lower band
        0.5 = at middle
        1 = at upper band
        < 0 = below lower band
        > 1 = above upper band
        """
        return self._pct_b

    def get_signal(self, price: float = None) -> str:
        """
        Get trading signal from Bollinger Bands.

        Returns:
            'squeeze': Bands very narrow, expect volatility
            'oversold': Price at/below lower band
            'overbought': Price at/above upper band
            'neutral': Price between bands
        """
        if self._pct_b is None or self._width is None:
            return "unknown"

        # Check for squeeze (low volatility)
        if self._width < 5:  # Narrow bands
            return "squeeze"

        # Position signals
        if self._pct_b <= 0:
            return "oversold"
        elif self._pct_b >= 1:
            return "overbought"
        elif self._pct_b < 0.2:
            return "near_lower"
        elif self._pct_b > 0.8:
            return "near_upper"

        return "neutral"

    def is_squeeze(self, threshold: float = 5.0) -> bool:
        """Check if bands are in squeeze (low volatility)"""
        return self._width is not None and self._width < threshold


class BollingerBandWidth(Indicator):
    """Just the Bollinger Band Width (volatility measure)"""

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        super().__init__(f"bb_width_{period}")
        self._bb = BollingerBands(period, std_dev)

    def required_bars(self) -> int:
        return self._bb.required_bars()

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        self._bb.calculate(bars)
        width = self._bb.width
        if width is not None:
            self._values.append(width)
        return width


class BollingerPercentB(Indicator):
    """Just %B from Bollinger Bands"""

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        super().__init__(f"bb_pct_b_{period}")
        self._bb = BollingerBands(period, std_dev)

    def required_bars(self) -> int:
        return self._bb.required_bars()

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        return self._bb.calculate(bars)
