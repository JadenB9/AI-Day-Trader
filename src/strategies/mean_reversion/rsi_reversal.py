"""
RSI Reversal Strategy.
Trades RSI failure swings and divergences.
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from src.strategies.base import (
    Strategy, StrategyConfig, Signal,
    SignalDirection, SignalType, SignalStrength
)
from src.data.models.market_snapshot import MarketSnapshot


class RSIReversal(Strategy):
    """
    RSI Reversal - Failure swing method.

    Identifies RSI divergences and failure swings for reversal trades.

    Bullish Failure Swing:
    1. RSI falls below 30 (oversold)
    2. RSI bounces above 30
    3. RSI pulls back but stays above 30
    4. RSI breaks above the previous swing high

    Bearish Failure Swing:
    1. RSI rises above 70 (overbought)
    2. RSI falls below 70
    3. RSI bounces but stays below 70
    4. RSI breaks below the previous swing low

    Also detects price/RSI divergence for stronger signals.
    """

    def __init__(self, config: StrategyConfig = None):
        if config is None:
            config = StrategyConfig(
                name="rsi_reversal",
                min_confidence=0.40,  # Lowered from 0.60 - AGGRESSIVE
                ai_threshold=0.55,  # Lowered from 0.80
                max_position_pct=0.04,  # Increased from 0.018
                default_stop_atr_mult=2.0,  # Wider stops
                default_target_atr_mult=2.5,
                params={
                    'rsi_oversold': 35,  # Widened from 30
                    'rsi_overbought': 65,  # Widened from 70
                    'lookback_bars': 15,  # Reduced from 20
                    'require_divergence': False,
                    'min_swing_separation': 2,  # Reduced from 3
                }
            )
        super().__init__(config)
        self._rsi_history: Dict[str, List[float]] = {}  # symbol -> RSI values

    @property
    def name(self) -> str:
        return "rsi_reversal"

    @property
    def description(self) -> str:
        return "RSI failure swing reversals with optional divergence"

    def get_required_indicators(self) -> List[str]:
        return ['rsi_14', 'rsi_9', 'atr_14', 'ema_21', 'rvol']

    def generate_signal(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        indicators: Dict[str, float]
    ) -> Optional[Signal]:

        rsi_14 = indicators.get('rsi_14')
        rsi_9 = indicators.get('rsi_9')
        atr = indicators.get('atr_14')
        ema_21 = indicators.get('ema_21')
        rvol = indicators.get('rvol', 1.0)

        if any(v is None for v in [rsi_14, atr]):
            return None

        bars = snapshot.bars_1m
        if len(bars) < 20:
            return None

        price = snapshot.last_price
        params = self.config.params

        # Build RSI history for failure swing detection
        if symbol not in self._rsi_history:
            self._rsi_history[symbol] = []
        self._rsi_history[symbol].append(rsi_14)
        if len(self._rsi_history[symbol]) > 50:
            self._rsi_history[symbol] = self._rsi_history[symbol][-50:]

        rsi_history = self._rsi_history[symbol]

        # Check for failure swings
        bullish = self._check_bullish_failure_swing(
            price, bars, rsi_14, rsi_history, ema_21, rvol, params
        )
        bearish = self._check_bearish_failure_swing(
            price, bars, rsi_14, rsi_history, ema_21, rvol, params
        )

        if not bullish['valid'] and not bearish['valid']:
            return None

        # Select direction
        if bullish['valid'] and bullish['score'] >= bearish.get('score', 0):
            direction = SignalDirection.LONG
            score = bullish['score']
            reasoning = bullish['reasoning']
        elif bearish['valid']:
            direction = SignalDirection.SHORT
            score = bearish['score']
            reasoning = bearish['reasoning']
        else:
            return None

        confidence = min(score / 100, 0.90)

        if confidence < self.config.min_confidence:
            return None

        # Calculate stops
        entry_price = price
        stop_loss = self.calculate_stop_loss(entry_price, direction, atr)
        take_profit = self.calculate_take_profit(entry_price, direction, atr)

        # Strength
        if confidence >= 0.80:
            strength = SignalStrength.VERY_STRONG
        elif confidence >= 0.70:
            strength = SignalStrength.STRONG
        else:
            strength = SignalStrength.MODERATE

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
                'rsi_14': rsi_14,
                'rsi_9': rsi_9,
                'ema_21': ema_21,
                'rvol': rvol,
                'atr': atr
            },
            market_context={
                'price': price,
                'rsi_history_length': len(rsi_history)
            },
            valid_until=datetime.now() + timedelta(minutes=15)
        )

    def _check_bullish_failure_swing(
        self,
        price: float,
        bars: List,
        current_rsi: float,
        rsi_history: List[float],
        ema_21: float,
        rvol: float,
        params: Dict
    ) -> Dict:
        """
        Check for bullish failure swing pattern.

        Pattern:
        1. RSI dips below oversold (30)
        2. RSI bounces above 30
        3. RSI pulls back but stays above 30
        4. RSI breaks above previous bounce high
        """
        score = 0
        reasons = []

        oversold = params.get('rsi_oversold', 30)
        min_separation = params.get('min_swing_separation', 3)

        if len(rsi_history) < 10:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        # Look for pattern in RSI history
        # Find if RSI was recently oversold
        oversold_indices = [i for i, r in enumerate(rsi_history) if r < oversold]

        if not oversold_indices:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        # Check if most recent oversold was within lookback
        last_oversold = oversold_indices[-1]
        if len(rsi_history) - last_oversold > 15:  # Too old
            return {'valid': False, 'score': 0, 'reasoning': ''}

        score += 20
        reasons.append("RSI was recently oversold")

        # Current RSI should be above oversold
        if current_rsi < oversold:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        score += 15
        reasons.append(f"RSI recovered above {oversold}")

        # Look for failure swing - RSI making higher low
        recent_rsi = rsi_history[-10:]
        local_min = min(recent_rsi[-5:])
        prev_min = min(recent_rsi[:5])

        if local_min > prev_min:
            score += 20
            reasons.append("RSI higher low (failure swing)")

        # RSI turning up
        if len(rsi_history) >= 3:
            if current_rsi > rsi_history[-2] > rsi_history[-3]:
                score += 10
                reasons.append("RSI turning up")

        # Check for bullish divergence (price lower low, RSI higher low)
        if len(bars) >= 10:
            price_lows = [b.low for b in bars[-10:]]
            if min(price_lows[-5:]) < min(price_lows[:5]) and local_min > prev_min:
                score += 15
                reasons.append("Bullish divergence detected")

        # Price context
        if ema_21 and price < ema_21 * 1.02:  # Near or below EMA
            score += 5
            reasons.append("Price near support")

        # Volume
        if rvol > 1.3:
            score += 5

        valid = score >= 30  # Lowered from 45 - AGGRESSIVE

        return {
            'valid': valid,
            'score': score,
            'reasoning': "; ".join(reasons)
        }

    def _check_bearish_failure_swing(
        self,
        price: float,
        bars: List,
        current_rsi: float,
        rsi_history: List[float],
        ema_21: float,
        rvol: float,
        params: Dict
    ) -> Dict:
        """
        Check for bearish failure swing pattern.

        Pattern:
        1. RSI rises above overbought (70)
        2. RSI falls below 70
        3. RSI bounces but stays below 70
        4. RSI breaks below previous swing low
        """
        score = 0
        reasons = []

        overbought = params.get('rsi_overbought', 70)

        if len(rsi_history) < 10:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        # Find if RSI was recently overbought
        overbought_indices = [i for i, r in enumerate(rsi_history) if r > overbought]

        if not overbought_indices:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        last_overbought = overbought_indices[-1]
        if len(rsi_history) - last_overbought > 15:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        score += 20
        reasons.append("RSI was recently overbought")

        # Current RSI below overbought
        if current_rsi > overbought:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        score += 15
        reasons.append(f"RSI fell below {overbought}")

        # Look for failure swing - RSI making lower high
        recent_rsi = rsi_history[-10:]
        local_max = max(recent_rsi[-5:])
        prev_max = max(recent_rsi[:5])

        if local_max < prev_max:
            score += 20
            reasons.append("RSI lower high (failure swing)")

        # RSI turning down
        if len(rsi_history) >= 3:
            if current_rsi < rsi_history[-2] < rsi_history[-3]:
                score += 10
                reasons.append("RSI turning down")

        # Check for bearish divergence (price higher high, RSI lower high)
        if len(bars) >= 10:
            price_highs = [b.high for b in bars[-10:]]
            if max(price_highs[-5:]) > max(price_highs[:5]) and local_max < prev_max:
                score += 15
                reasons.append("Bearish divergence detected")

        # Price context
        if ema_21 and price > ema_21 * 0.98:  # Near or above EMA
            score += 5
            reasons.append("Price near resistance")

        # Volume
        if rvol > 1.3:
            score += 5

        valid = score >= 30  # Lowered from 45 - AGGRESSIVE

        return {
            'valid': valid,
            'score': score,
            'reasoning': "; ".join(reasons)
        }
