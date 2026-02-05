"""
Relative Strength Index (RSI) indicator.
"""
from typing import List, Optional
import numpy as np

from src.indicators.base import Indicator, get_closes
from src.data.models.market_snapshot import Bar


class RSI(Indicator):
    """
    Relative Strength Index.
    Measures momentum on a 0-100 scale.

    Interpretation:
    - > 70: Overbought
    - < 30: Oversold
    - 50 is neutral
    """

    def __init__(self, period: int = 14):
        super().__init__(f"rsi_{period}", period=period)
        self.period = period
        self._avg_gain = None
        self._avg_loss = None

    def required_bars(self) -> int:
        return self.period + 1

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        if len(bars) < self.required_bars():
            return None

        closes = get_closes(bars)

        # Calculate price changes
        deltas = np.diff(closes)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # Use Wilder's smoothing (exponential moving average)
        # First calculation uses simple average
        if len(gains) >= self.period:
            first_avg_gain = np.mean(gains[:self.period])
            first_avg_loss = np.mean(losses[:self.period])

            avg_gain = first_avg_gain
            avg_loss = first_avg_loss

            # Subsequent calculations use Wilder's smoothing
            for i in range(self.period, len(gains)):
                avg_gain = (avg_gain * (self.period - 1) + gains[i]) / self.period
                avg_loss = (avg_loss * (self.period - 1) + losses[i]) / self.period

            self._avg_gain = avg_gain
            self._avg_loss = avg_loss

            if avg_loss == 0:
                return 100.0

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

            self._values.append(rsi)
            return rsi

        return None

    def update(self, bar: Bar) -> Optional[float]:
        """Incremental update with new bar"""
        if self._avg_gain is None or self._avg_loss is None:
            return None

        # Would need previous close - simplified version
        return None

    @staticmethod
    def interpret(value: float) -> str:
        """Interpret RSI value"""
        if value >= 80:
            return "extremely_overbought"
        elif value >= 70:
            return "overbought"
        elif value >= 60:
            return "bullish"
        elif value >= 40:
            return "neutral"
        elif value >= 30:
            return "bearish"
        elif value >= 20:
            return "oversold"
        else:
            return "extremely_oversold"


class StochasticRSI(Indicator):
    """
    Stochastic RSI - RSI of RSI.
    More sensitive than regular RSI.
    """

    def __init__(self, rsi_period: int = 14, stoch_period: int = 14, k_period: int = 3, d_period: int = 3):
        super().__init__(f"stoch_rsi_{rsi_period}_{stoch_period}")
        self.rsi_period = rsi_period
        self.stoch_period = stoch_period
        self.k_period = k_period
        self.d_period = d_period
        self._rsi = RSI(rsi_period)

    def required_bars(self) -> int:
        return self.rsi_period + self.stoch_period + self.k_period

    def calculate(self, bars: List[Bar]) -> Optional[float]:
        if len(bars) < self.required_bars():
            return None

        # Calculate RSI for each point
        rsi_values = []
        for i in range(self.rsi_period, len(bars)):
            window = bars[:i + 1]
            rsi = self._rsi.calculate(window)
            if rsi is not None:
                rsi_values.append(rsi)

        if len(rsi_values) < self.stoch_period:
            return None

        # Calculate Stochastic of RSI
        recent_rsi = rsi_values[-self.stoch_period:]
        current_rsi = recent_rsi[-1]
        lowest_rsi = min(recent_rsi)
        highest_rsi = max(recent_rsi)

        if highest_rsi == lowest_rsi:
            stoch_rsi = 50.0
        else:
            stoch_rsi = (current_rsi - lowest_rsi) / (highest_rsi - lowest_rsi) * 100

        self._values.append(stoch_rsi)
        return stoch_rsi
