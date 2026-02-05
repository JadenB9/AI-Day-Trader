"""
Base interface for technical indicators.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
import pandas as pd
import numpy as np

from src.data.models.market_snapshot import Bar


@dataclass
class IndicatorResult:
    """Result from indicator calculation"""
    name: str
    value: float
    timestamp: Any = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class Indicator(ABC):
    """
    Base class for all technical indicators.
    """

    def __init__(self, name: str, **params):
        self.name = name
        self.params = params
        self._values: List[float] = []

    @abstractmethod
    def calculate(self, bars: List[Bar]) -> Optional[float]:
        """
        Calculate indicator value from bars.

        Args:
            bars: List of Bar objects (most recent last)

        Returns:
            Indicator value or None if insufficient data
        """
        pass

    @abstractmethod
    def required_bars(self) -> int:
        """Minimum bars needed for calculation"""
        pass

    def update(self, bar: Bar) -> Optional[float]:
        """
        Update indicator with new bar (for streaming).
        Override for efficient incremental calculation.
        """
        # Default: recalculate from scratch
        # Subclasses can override for efficiency
        return None

    def reset(self) -> None:
        """Reset internal state"""
        self._values.clear()

    @property
    def last_value(self) -> Optional[float]:
        """Get most recent calculated value"""
        return self._values[-1] if self._values else None

    def to_series(self, bars: List[Bar]) -> pd.Series:
        """Calculate indicator for all bars, return as Series"""
        if len(bars) < self.required_bars():
            return pd.Series(dtype=float)

        # Calculate for each valid window
        values = []
        timestamps = []
        for i in range(self.required_bars() - 1, len(bars)):
            window = bars[:i + 1]
            val = self.calculate(window)
            values.append(val)
            timestamps.append(bars[i].timestamp)

        return pd.Series(values, index=timestamps, name=self.name)


def bars_to_df(bars: List[Bar]) -> pd.DataFrame:
    """Convert Bar list to DataFrame"""
    if not bars:
        return pd.DataFrame()

    data = {
        'timestamp': [b.timestamp for b in bars],
        'open': [b.open for b in bars],
        'high': [b.high for b in bars],
        'low': [b.low for b in bars],
        'close': [b.close for b in bars],
        'volume': [b.volume for b in bars]
    }

    # Add VWAP if available
    if bars[0].vwap is not None:
        data['vwap'] = [b.vwap for b in bars]

    df = pd.DataFrame(data)
    df.set_index('timestamp', inplace=True)
    return df


def get_closes(bars: List[Bar]) -> np.ndarray:
    """Extract close prices as numpy array"""
    return np.array([b.close for b in bars])


def get_highs(bars: List[Bar]) -> np.ndarray:
    """Extract high prices as numpy array"""
    return np.array([b.high for b in bars])


def get_lows(bars: List[Bar]) -> np.ndarray:
    """Extract low prices as numpy array"""
    return np.array([b.low for b in bars])


def get_volumes(bars: List[Bar]) -> np.ndarray:
    """Extract volumes as numpy array"""
    return np.array([b.volume for b in bars])


# Type alias for indicator config
IndicatorConfig = Dict[str, Dict[str, Any]]
