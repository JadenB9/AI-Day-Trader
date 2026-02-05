"""
VWAP (Volume Weighted Average Price) indicator.
"""
from typing import List, Optional, Tuple
import numpy as np
from datetime import datetime, time

from src.indicators.base import Indicator
from src.data.models.market_snapshot import Bar


class VWAP(Indicator):
    """
    Volume Weighted Average Price.
    Calculates the average price weighted by volume for the trading day.

    VWAP = Cumulative(Typical Price * Volume) / Cumulative(Volume)
    Typical Price = (High + Low + Close) / 3

    Usage:
    - Institutional benchmark
    - Dynamic support/resistance
    - Price above VWAP = bullish
    - Price below VWAP = bearish
    """

    def __init__(self):
        super().__init__("vwap")
        self._cumulative_tp_vol: float = 0.0
        self._cumulative_vol: int = 0
        self._vwap: Optional[float] = None
        self._last_reset_date: Optional[datetime] = None

    def required_bars(self) -> int:
        return 1

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        if not bars:
            return None

        current_bar = bars[-1]

        # Reset at start of new day
        current_date = current_bar.timestamp.date() if current_bar.timestamp else None
        if current_date and current_date != self._last_reset_date:
            self._reset_day()
            self._last_reset_date = current_date

        # Calculate typical price
        typical_price = (current_bar.high + current_bar.low + current_bar.close) / 3

        # Update cumulative values
        self._cumulative_tp_vol += typical_price * current_bar.volume
        self._cumulative_vol += current_bar.volume

        # Calculate VWAP
        if self._cumulative_vol > 0:
            self._vwap = self._cumulative_tp_vol / self._cumulative_vol
        else:
            self._vwap = typical_price

        self._values.append(self._vwap)
        return self._vwap

    def calculate_from_session(self, bars: List[Bar]) -> Optional[float]:
        """
        Calculate VWAP from a full session's bars.
        More accurate than incremental for backtesting.
        """
        if not bars:
            return None

        cumulative_tp_vol = 0.0
        cumulative_vol = 0

        vwap_values = []
        for bar in bars:
            typical_price = (bar.high + bar.low + bar.close) / 3
            cumulative_tp_vol += typical_price * bar.volume
            cumulative_vol += bar.volume

            if cumulative_vol > 0:
                vwap = cumulative_tp_vol / cumulative_vol
            else:
                vwap = typical_price

            vwap_values.append(vwap)

        self._vwap = vwap_values[-1] if vwap_values else None
        return self._vwap

    def _reset_day(self) -> None:
        """Reset for new trading day"""
        self._cumulative_tp_vol = 0.0
        self._cumulative_vol = 0
        self._values.clear()

    def update(self, bar: Bar) -> Optional[float]:
        """Update VWAP with new bar"""
        return self.calculate([bar])

    @property
    def value(self) -> Optional[float]:
        return self._vwap


class VWAPBands(Indicator):
    """
    VWAP with standard deviation bands.
    Similar to Bollinger Bands but around VWAP.
    """

    def __init__(self, std_multiplier: float = 2.0):
        super().__init__("vwap_bands")
        self.std_multiplier = std_multiplier
        self._vwap: Optional[float] = None
        self._upper_1: Optional[float] = None
        self._lower_1: Optional[float] = None
        self._upper_2: Optional[float] = None
        self._lower_2: Optional[float] = None
        self._prices: List[float] = []
        self._volumes: List[int] = []

    def required_bars(self) -> int:
        return 5  # Need some bars for std dev

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        if len(bars) < self.required_bars():
            return None

        # Calculate VWAP
        tp_vol_sum = 0.0
        vol_sum = 0
        typical_prices = []

        for bar in bars:
            tp = (bar.high + bar.low + bar.close) / 3
            typical_prices.append(tp)
            tp_vol_sum += tp * bar.volume
            vol_sum += bar.volume

        if vol_sum == 0:
            return None

        self._vwap = tp_vol_sum / vol_sum

        # Calculate standard deviation of typical prices from VWAP
        deviations = [(tp - self._vwap) ** 2 for tp in typical_prices]
        variance = sum(deviations) / len(deviations)
        std = variance ** 0.5

        # Set bands
        self._upper_1 = self._vwap + std
        self._lower_1 = self._vwap - std
        self._upper_2 = self._vwap + (std * self.std_multiplier)
        self._lower_2 = self._vwap - (std * self.std_multiplier)

        self._values.append(self._vwap)
        return self._vwap

    def get_bands(self) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Get (upper_2, upper_1, vwap, lower_1, lower_2)"""
        return self._upper_2, self._upper_1, self._vwap, self._lower_1, self._lower_2

    def get_position(self, price: float) -> str:
        """
        Get position relative to VWAP bands.

        Returns:
            'above_2': Above upper 2 std band
            'above_1': Between VWAP and upper 1 std
            'at_vwap': At VWAP
            'below_1': Between VWAP and lower 1 std
            'below_2': Below lower 2 std band
        """
        if self._vwap is None:
            return "unknown"

        if price >= self._upper_2:
            return "above_2"
        elif price >= self._upper_1:
            return "above_1"
        elif price > self._lower_1:
            return "at_vwap"
        elif price > self._lower_2:
            return "below_1"
        else:
            return "below_2"


class RelativeVolume(Indicator):
    """
    Relative Volume - Current volume vs average.
    High RVOL indicates unusual activity.
    """

    def __init__(self, lookback: int = 20):
        super().__init__(f"rvol_{lookback}")
        self.lookback = lookback

    def required_bars(self) -> int:
        return self.lookback + 1

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        if len(bars) < self.required_bars():
            return None

        # Average volume (excluding current bar)
        past_volumes = [b.volume for b in bars[:-1]]
        avg_volume = np.mean(past_volumes[-self.lookback:])

        if avg_volume == 0:
            return None

        # Current volume
        current_volume = bars[-1].volume

        rvol = current_volume / avg_volume
        self._values.append(rvol)
        return rvol
