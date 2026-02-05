"""
VWAP Bounce Strategy.
Trades bounces off VWAP as dynamic support/resistance.
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from src.strategies.base import (
    Strategy, StrategyConfig, Signal,
    SignalDirection, SignalType, SignalStrength
)
from src.data.models.market_snapshot import MarketSnapshot


class VWAPBounce(Strategy):
    """
    VWAP Bounce strategy - trades price reactions at VWAP.

    VWAP acts as institutional benchmark and dynamic S/R level.

    Entry conditions (LONG bounce):
    - Price approaches VWAP from above
    - Price touches or slightly pierces VWAP
    - Shows rejection candle (long lower wick)
    - Volume confirmation
    - RSI not oversold (> 35)

    Entry conditions (SHORT bounce):
    - Price approaches VWAP from below
    - Price touches or slightly pierces VWAP
    - Shows rejection candle (long upper wick)
    - Volume confirmation
    - RSI not overbought (< 65)

    Exit: 1.5 ATR target, 1 ATR stop (tighter for bounces)
    """

    def __init__(self, config: StrategyConfig = None):
        if config is None:
            config = StrategyConfig(
                name="vwap_bounce",
                min_confidence=0.40,  # Lowered from 0.60 - AGGRESSIVE
                ai_threshold=0.55,  # Lowered from 0.80
                max_position_pct=0.04,  # Increased from 0.02
                default_stop_atr_mult=1.5,  # Wider stops
                default_target_atr_mult=2.0,
                params={
                    'vwap_threshold_pct': 0.30,  # Widened from 0.15 - more distance allowed
                    'min_wick_ratio': 0.3,  # Lowered from 0.5 - less strict wick
                    'volume_increase_pct': 10,  # Lowered from 20%
                    'rsi_long_min': 25,  # Lowered from 35
                    'rsi_short_max': 75,  # Increased from 65
                    'lookback_bars': 7,  # Increased from 5
                }
            )
        super().__init__(config)

    @property
    def name(self) -> str:
        return "vwap_bounce"

    @property
    def description(self) -> str:
        return "Trade bounces off VWAP as dynamic support/resistance"

    def get_required_indicators(self) -> List[str]:
        return ['vwap', 'rsi_14', 'atr_14', 'rvol']

    def generate_signal(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        indicators: Dict[str, float]
    ) -> Optional[Signal]:

        vwap = indicators.get('vwap')
        rsi = indicators.get('rsi_14')
        atr = indicators.get('atr_14')
        rvol = indicators.get('rvol', 1.0)

        if any(v is None for v in [vwap, rsi, atr]):
            return None

        bars = snapshot.bars_1m
        if len(bars) < 5:
            return None

        price = snapshot.last_price
        if price <= 0:
            return None

        params = self.config.params
        threshold_pct = params.get('vwap_threshold_pct', 0.15)

        # Check proximity to VWAP
        vwap_distance_pct = abs(price - vwap) / vwap * 100

        if vwap_distance_pct > threshold_pct * 3:  # Too far from VWAP
            return None

        # Check for bounce setup
        long_bounce = self._check_long_bounce(
            bars, price, vwap, rsi, rvol, params
        )
        short_bounce = self._check_short_bounce(
            bars, price, vwap, rsi, rvol, params
        )

        if not long_bounce['valid'] and not short_bounce['valid']:
            return None

        # Select better signal
        if long_bounce['valid'] and long_bounce['score'] >= short_bounce.get('score', 0):
            direction = SignalDirection.LONG
            score = long_bounce['score']
            reasoning = long_bounce['reasoning']
        elif short_bounce['valid']:
            direction = SignalDirection.SHORT
            score = short_bounce['score']
            reasoning = short_bounce['reasoning']
        else:
            return None

        # Calculate confidence
        confidence = min(score / 100, 0.92)

        if confidence < self.config.min_confidence:
            return None

        # Calculate stops (tighter for VWAP bounces)
        entry_price = price
        stop_loss = self.calculate_stop_loss(entry_price, direction, atr)
        take_profit = self.calculate_take_profit(entry_price, direction, atr)

        # Strength
        if confidence >= 0.82:
            strength = SignalStrength.VERY_STRONG
        elif confidence >= 0.72:
            strength = SignalStrength.STRONG
        elif confidence >= 0.62:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK

        return Signal(
            symbol=symbol,
            direction=direction,
            signal_type=SignalType.ENTRY,
            strategy=self.name,
            confidence=confidence,
            strength=strength,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            suggested_size_pct=self.config.max_position_pct * confidence,
            reasoning=reasoning,
            indicators_used={
                'vwap': vwap,
                'vwap_distance_pct': vwap_distance_pct,
                'rsi': rsi,
                'rvol': rvol,
                'atr': atr
            },
            market_context={
                'price': price,
                'day_high': snapshot.day_high,
                'day_low': snapshot.day_low
            },
            valid_until=datetime.now() + timedelta(minutes=10)
        )

    def _check_long_bounce(
        self,
        bars: List,
        price: float,
        vwap: float,
        rsi: float,
        rvol: float,
        params: Dict
    ) -> Dict:
        """Check for bullish VWAP bounce"""
        score = 0
        reasons = []

        # Price must be at or slightly below VWAP
        if price > vwap * 1.002:  # More than 0.2% above
            return {'valid': False, 'score': 0, 'reasoning': ''}

        # Check recent price action approached from above
        recent_highs = [b.high for b in bars[-5:]]
        if max(recent_highs) < vwap:  # Was never above VWAP
            return {'valid': False, 'score': 0, 'reasoning': ''}

        score += 15
        reasons.append("Price at VWAP support")

        # Check for rejection (lower wick)
        current_bar = bars[-1]
        bar_range = current_bar.high - current_bar.low
        if bar_range > 0:
            lower_wick = min(current_bar.open, current_bar.close) - current_bar.low
            wick_ratio = lower_wick / bar_range
            if wick_ratio >= params.get('min_wick_ratio', 0.5):
                score += 25
                reasons.append(f"Strong rejection wick ({wick_ratio:.1%})")
            elif wick_ratio >= 0.3:
                score += 15
                reasons.append("Moderate rejection wick")

        # Bullish close
        if current_bar.close > current_bar.open:
            score += 15
            reasons.append("Bullish candle")

        # RSI check
        rsi_min = params.get('rsi_long_min', 35)
        if rsi > rsi_min:
            score += 10
            reasons.append(f"RSI supportive ({rsi:.1f})")
        else:
            score -= 10

        # Volume confirmation
        if rvol > 1.2:
            score += 15
            reasons.append(f"Volume confirmation (RVOL: {rvol:.1f})")
        elif rvol > 1.0:
            score += 5

        # Price holding above day low
        if price > bars[-1].low:
            score += 5

        valid = score >= 30  # Lowered from 45 - AGGRESSIVE

        return {
            'valid': valid,
            'score': score,
            'reasoning': "; ".join(reasons)
        }

    def _check_short_bounce(
        self,
        bars: List,
        price: float,
        vwap: float,
        rsi: float,
        rvol: float,
        params: Dict
    ) -> Dict:
        """Check for bearish VWAP bounce"""
        score = 0
        reasons = []

        # Price must be at or slightly above VWAP
        if price < vwap * 0.998:  # More than 0.2% below
            return {'valid': False, 'score': 0, 'reasoning': ''}

        # Check recent price action approached from below
        recent_lows = [b.low for b in bars[-5:]]
        if min(recent_lows) > vwap:  # Was never below VWAP
            return {'valid': False, 'score': 0, 'reasoning': ''}

        score += 15
        reasons.append("Price at VWAP resistance")

        # Check for rejection (upper wick)
        current_bar = bars[-1]
        bar_range = current_bar.high - current_bar.low
        if bar_range > 0:
            upper_wick = current_bar.high - max(current_bar.open, current_bar.close)
            wick_ratio = upper_wick / bar_range
            if wick_ratio >= params.get('min_wick_ratio', 0.5):
                score += 25
                reasons.append(f"Strong rejection wick ({wick_ratio:.1%})")
            elif wick_ratio >= 0.3:
                score += 15
                reasons.append("Moderate rejection wick")

        # Bearish close
        if current_bar.close < current_bar.open:
            score += 15
            reasons.append("Bearish candle")

        # RSI check
        rsi_max = params.get('rsi_short_max', 65)
        if rsi < rsi_max:
            score += 10
            reasons.append(f"RSI supportive ({rsi:.1f})")
        else:
            score -= 10

        # Volume confirmation
        if rvol > 1.2:
            score += 15
            reasons.append(f"Volume confirmation (RVOL: {rvol:.1f})")
        elif rvol > 1.0:
            score += 5

        valid = score >= 30  # Lowered from 45 - AGGRESSIVE

        return {
            'valid': valid,
            'score': score,
            'reasoning': "; ".join(reasons)
        }
