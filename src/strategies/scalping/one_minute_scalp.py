"""
One Minute Scalping Strategy.
Uses EMA crossovers, RSI, VWAP, and Stochastic for quick entries.
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from src.strategies.base import (
    Strategy, StrategyConfig, Signal,
    SignalDirection, SignalType, SignalStrength
)
from src.data.models.market_snapshot import MarketSnapshot


class OneMinuteScalp(Strategy):
    """
    One-minute scalping strategy combining multiple indicators.

    Entry conditions (LONG):
    - EMA 9 > EMA 21 (short-term bullish)
    - Price above VWAP
    - RSI between 40-70 (not overbought)
    - Stochastic %K > %D and < 80
    - Price closing above EMA 9

    Entry conditions (SHORT):
    - EMA 9 < EMA 21
    - Price below VWAP
    - RSI between 30-60
    - Stochastic %K < %D and > 20
    - Price closing below EMA 9

    Exit: 2 ATR target, 1.5 ATR stop, or time stop (15 min)
    """

    def __init__(self, config: StrategyConfig = None):
        if config is None:
            config = StrategyConfig(
                name="one_minute_scalp",
                min_confidence=0.65,
                ai_threshold=0.85,
                max_position_pct=0.015,
                default_stop_atr_mult=1.5,
                default_target_atr_mult=2.0,
                params={
                    'ema_fast': 9,
                    'ema_slow': 21,
                    'rsi_period': 14,
                    'rsi_long_min': 40,
                    'rsi_long_max': 70,
                    'rsi_short_min': 30,
                    'rsi_short_max': 60,
                    'stoch_overbought': 80,
                    'stoch_oversold': 20,
                    'min_volume_ratio': 0.8,  # vs average
                    'time_stop_minutes': 15
                }
            )
        super().__init__(config)

    @property
    def name(self) -> str:
        return "one_minute_scalp"

    @property
    def description(self) -> str:
        return "Quick scalping using EMA crossover, RSI, VWAP, and Stochastic"

    def get_required_indicators(self) -> List[str]:
        return [
            'ema_9', 'ema_21',
            'rsi_14',
            'vwap',
            'stoch_k', 'stoch_d',
            'atr_14'
        ]

    def generate_signal(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        indicators: Dict[str, float]
    ) -> Optional[Signal]:

        # Get values
        ema_fast = indicators.get('ema_9')
        ema_slow = indicators.get('ema_21')
        rsi = indicators.get('rsi_14')
        vwap = indicators.get('vwap')
        stoch_k = indicators.get('stoch_k')
        stoch_d = indicators.get('stoch_d')
        atr = indicators.get('atr_14')

        if any(v is None for v in [ema_fast, ema_slow, rsi, vwap, stoch_k, stoch_d, atr]):
            return None

        price = snapshot.last_price
        if price <= 0:
            return None

        params = self.config.params

        # Check for LONG setup
        long_conditions = self._check_long_conditions(
            price, ema_fast, ema_slow, rsi, vwap, stoch_k, stoch_d, params
        )

        # Check for SHORT setup
        short_conditions = self._check_short_conditions(
            price, ema_fast, ema_slow, rsi, vwap, stoch_k, stoch_d, params
        )

        if not long_conditions['valid'] and not short_conditions['valid']:
            return None

        # Determine direction
        if long_conditions['valid'] and long_conditions['score'] >= short_conditions.get('score', 0):
            direction = SignalDirection.LONG
            score = long_conditions['score']
            reasoning = long_conditions['reasoning']
        elif short_conditions['valid']:
            direction = SignalDirection.SHORT
            score = short_conditions['score']
            reasoning = short_conditions['reasoning']
        else:
            return None

        # Calculate confidence (normalized score)
        confidence = min(score / 100, 0.95)

        if confidence < self.config.min_confidence:
            return None

        # Calculate stops and targets
        entry_price = price
        stop_loss = self.calculate_stop_loss(entry_price, direction, atr)
        take_profit = self.calculate_take_profit(entry_price, direction, atr)

        # Determine signal strength
        if confidence >= 0.85:
            strength = SignalStrength.VERY_STRONG
        elif confidence >= 0.75:
            strength = SignalStrength.STRONG
        elif confidence >= 0.65:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK

        # Time stop
        time_stop = params.get('time_stop_minutes', 15)
        valid_until = datetime.now() + timedelta(minutes=time_stop)

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
                'ema_9': ema_fast,
                'ema_21': ema_slow,
                'rsi': rsi,
                'vwap': vwap,
                'stoch_k': stoch_k,
                'stoch_d': stoch_d,
                'atr': atr
            },
            market_context={
                'price': price,
                'spread': snapshot.ask - snapshot.bid if snapshot.ask and snapshot.bid else 0,
                'day_change_pct': snapshot.day_change_pct
            },
            valid_until=valid_until
        )

    def _check_long_conditions(
        self,
        price: float,
        ema_fast: float,
        ema_slow: float,
        rsi: float,
        vwap: float,
        stoch_k: float,
        stoch_d: float,
        params: Dict
    ) -> Dict:
        """Check long entry conditions and return score"""
        score = 0
        reasons = []

        # EMA alignment (required)
        if ema_fast <= ema_slow:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        score += 20
        reasons.append(f"EMA bullish (9:{ema_fast:.2f} > 21:{ema_slow:.2f})")

        # Price above VWAP
        if price > vwap:
            score += 20
            reasons.append(f"Price above VWAP ({price:.2f} > {vwap:.2f})")
        else:
            score -= 10

        # RSI in range
        rsi_min = params.get('rsi_long_min', 40)
        rsi_max = params.get('rsi_long_max', 70)
        if rsi_min <= rsi <= rsi_max:
            score += 20
            reasons.append(f"RSI in range ({rsi:.1f})")
        elif rsi > rsi_max:
            score -= 15  # Overbought
            reasons.append(f"RSI overbought ({rsi:.1f})")

        # Stochastic
        stoch_ob = params.get('stoch_overbought', 80)
        if stoch_k > stoch_d and stoch_k < stoch_ob:
            score += 20
            reasons.append(f"Stoch bullish (%K:{stoch_k:.1f} > %D:{stoch_d:.1f})")
        elif stoch_k > stoch_ob:
            score -= 10

        # Price above fast EMA (momentum)
        if price > ema_fast:
            score += 10
            reasons.append("Price above EMA 9")

        # EMA spread (wider = stronger trend)
        ema_spread_pct = ((ema_fast - ema_slow) / ema_slow) * 100
        if ema_spread_pct > 0.2:
            score += 10

        valid = score >= 50

        return {
            'valid': valid,
            'score': score,
            'reasoning': "; ".join(reasons)
        }

    def _check_short_conditions(
        self,
        price: float,
        ema_fast: float,
        ema_slow: float,
        rsi: float,
        vwap: float,
        stoch_k: float,
        stoch_d: float,
        params: Dict
    ) -> Dict:
        """Check short entry conditions and return score"""
        score = 0
        reasons = []

        # EMA alignment (required)
        if ema_fast >= ema_slow:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        score += 20
        reasons.append(f"EMA bearish (9:{ema_fast:.2f} < 21:{ema_slow:.2f})")

        # Price below VWAP
        if price < vwap:
            score += 20
            reasons.append(f"Price below VWAP ({price:.2f} < {vwap:.2f})")
        else:
            score -= 10

        # RSI in range
        rsi_min = params.get('rsi_short_min', 30)
        rsi_max = params.get('rsi_short_max', 60)
        if rsi_min <= rsi <= rsi_max:
            score += 20
            reasons.append(f"RSI in range ({rsi:.1f})")
        elif rsi < rsi_min:
            score -= 15  # Oversold

        # Stochastic
        stoch_os = params.get('stoch_oversold', 20)
        if stoch_k < stoch_d and stoch_k > stoch_os:
            score += 20
            reasons.append(f"Stoch bearish (%K:{stoch_k:.1f} < %D:{stoch_d:.1f})")
        elif stoch_k < stoch_os:
            score -= 10

        # Price below fast EMA
        if price < ema_fast:
            score += 10
            reasons.append("Price below EMA 9")

        valid = score >= 50

        return {
            'valid': valid,
            'score': score,
            'reasoning': "; ".join(reasons)
        }
