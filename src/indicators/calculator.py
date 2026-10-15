"""
Indicator calculator - batch computation of all indicators.
"""
from typing import List, Dict, Optional, Set
import structlog

from src.data.models.market_snapshot import Bar, MarketSnapshot
from src.indicators.base import Indicator
from src.indicators.momentum.rsi import RSI
from src.indicators.momentum.macd import MACD
from src.indicators.momentum.stochastic import Stochastic, FastStochastic
from src.indicators.trend.ema import EMA, SMA
from src.indicators.trend.adx import ADX
from src.indicators.volatility.atr import ATR, ATRPercent
from src.indicators.volatility.bollinger import BollingerBands
from src.indicators.volume.vwap import VWAP, VWAPBands, RelativeVolume

logger = structlog.get_logger()


# Standard indicator configurations for scalping
DEFAULT_INDICATORS = {
    # Momentum
    'rsi_14': RSI(14),
    'rsi_9': RSI(9),
    'macd': MACD(12, 26, 9),
    'stoch': Stochastic(14, 1, 3),
    'fast_stoch': FastStochastic(14, 3),

    # Trend
    'ema_9': EMA(9),
    'ema_21': EMA(21),
    'ema_55': EMA(55),
    'sma_20': SMA(20),
    'sma_50': SMA(50),
    'sma_200': SMA(200),
    'adx': ADX(14),

    # Volatility
    'atr_14': ATR(14),
    'atr_pct': ATRPercent(14),
    'bbands': BollingerBands(20, 2),

    # Volume
    'vwap': VWAP(),
    'vwap_bands': VWAPBands(2.0),
    'rvol': RelativeVolume(20),
}


class IndicatorCalculator:
    """
    Calculates all technical indicators for a given symbol.
    Designed for efficient batch processing.
    """

    def __init__(self, indicators: Dict[str, Indicator] = None):
        """
        Initialize calculator with indicator set.

        Args:
            indicators: Dict of name -> Indicator instances.
                       Uses DEFAULT_INDICATORS if not specified.
        """
        self._indicators = indicators or self._create_default_indicators()
        self._cache: Dict[str, Dict[str, float]] = {}

    def _create_default_indicators(self) -> Dict[str, Indicator]:
        """Create fresh instances of default indicators"""
        return {
            'rsi_14': RSI(14),
            'rsi_9': RSI(9),
            'macd': MACD(12, 26, 9),
            'stoch': Stochastic(14, 1, 3),
            'fast_stoch': FastStochastic(14, 3),
            'ema_9': EMA(9),
            'ema_21': EMA(21),
            'ema_55': EMA(55),
            'sma_20': SMA(20),
            'sma_50': SMA(50),
            'adx': ADX(14),
            'atr_14': ATR(14),
            'atr_pct': ATRPercent(14),
            'bbands': BollingerBands(20, 2),
            'vwap': VWAP(),
            'rvol': RelativeVolume(20),
        }

    def calculate(self, bars: List[Bar]) -> Dict[str, float]:
        """
        Calculate all indicators for given bars.

        Args:
            bars: List of Bar objects (oldest first)

        Returns:
            Dict of indicator name -> value
        """
        results = {}

        for name, indicator in self._indicators.items():
            try:
                if len(bars) >= indicator.required_bars():
                    value = indicator.calculate(bars)
                    if value is not None:
                        results[name] = value

                        # Add sub-components for certain indicators
                        if name == 'macd' and isinstance(indicator, MACD):
                            macd_line, signal_line, hist = indicator.get_components()
                            if macd_line is not None:
                                results['macd_line'] = macd_line
                            if signal_line is not None:
                                results['macd_signal'] = signal_line
                            if hist is not None:
                                results['macd_histogram'] = hist

                        elif name == 'stoch' and isinstance(indicator, Stochastic):
                            k, d = indicator.get_values()
                            if k is not None:
                                results['stoch_k'] = k
                            if d is not None:
                                results['stoch_d'] = d

                        elif name == 'bbands' and isinstance(indicator, BollingerBands):
                            upper, middle, lower = indicator.get_bands()
                            if upper is not None:
                                results['bb_upper'] = upper
                            if middle is not None:
                                results['bb_middle'] = middle
                            if lower is not None:
                                results['bb_lower'] = lower
                            if indicator.width is not None:
                                results['bb_width'] = indicator.width
                            if indicator.pct_b is not None:
                                results['bb_pct_b'] = indicator.pct_b

                        elif name == 'adx' and isinstance(indicator, ADX):
                            plus_di, minus_di, adx = indicator.get_components()
                            if plus_di is not None:
                                results['plus_di'] = plus_di
                            if minus_di is not None:
                                results['minus_di'] = minus_di

            except Exception as e:
                logger.debug("indicator_calc_error", indicator=name, error=str(e))

        return results

    def calculate_for_snapshot(self, snapshot: MarketSnapshot) -> MarketSnapshot:
        """
        Calculate indicators and populate snapshot.

        Args:
            snapshot: MarketSnapshot with bars populated

        Returns:
            Same snapshot with indicators dict filled
        """
        # Use 1-minute bars for most indicators
        bars = snapshot.bars_1m

        if bars:
            indicators = self.calculate(bars)
            snapshot.indicators.update(indicators)

        # Calculate average volume from bars
        if len(bars) >= 20:
            avg_vol = sum(b.volume for b in bars[-20:]) / 20
            snapshot.indicators['avg_volume'] = avg_vol

        return snapshot

    def get_indicator(self, name: str) -> Optional[Indicator]:
        """Get indicator instance by name"""
        return self._indicators.get(name)

    def add_indicator(self, name: str, indicator: Indicator) -> None:
        """Add custom indicator"""
        self._indicators[name] = indicator

    def remove_indicator(self, name: str) -> None:
        """Remove indicator"""
        self._indicators.pop(name, None)

    def reset_all(self) -> None:
        """Reset all indicator states"""
        for indicator in self._indicators.values():
            indicator.reset()
        self._cache.clear()

    @property
    def indicator_names(self) -> Set[str]:
        """Get names of all configured indicators"""
        return set(self._indicators.keys())


# Singleton calculator instance
_calculator: Optional[IndicatorCalculator] = None


def get_calculator() -> IndicatorCalculator:
    """Get or create calculator singleton"""
    global _calculator
    if _calculator is None:
        _calculator = IndicatorCalculator()
    return _calculator


def calculate_indicators(bars: List[Bar]) -> Dict[str, float]:
    """Convenience function to calculate all indicators"""
    return get_calculator().calculate(bars)


def enrich_snapshot(snapshot: MarketSnapshot) -> MarketSnapshot:
    """Convenience function to enrich snapshot with indicators"""
    return get_calculator().calculate_for_snapshot(snapshot)
