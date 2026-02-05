"""
Bollinger Band Bounce Strategy.
Mean reversion trading at band extremes.
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from src.strategies.base import (
    Strategy, StrategyConfig, Signal,
    SignalDirection, SignalType, SignalStrength
)
from src.data.models.market_snapshot import MarketSnapshot


class BollingerBounce(Strategy):
    """
    Bollinger Band Bounce - Mean reversion strategy.

    Trades bounces off upper/lower Bollinger Bands.
    Per the PDF: 77-80% success rate when conditions are right.

    Entry conditions (LONG - lower band bounce):
    - Price touches or pierces lower band
    - %B <= 0.1 (at or below lower band)
    - RSI oversold but turning up (30-45)
    - Volume spike on touch
    - Not in strong downtrend (ADX < 30 or +DI > -DI)
    - Bullish candle pattern forming

    Entry conditions (SHORT - upper band bounce):
    - Price touches or pierces upper band
    - %B >= 0.9 (at or above upper band)
    - RSI overbought but turning down (55-70)
    - Volume spike
    - Not in strong uptrend

    Target: Middle band (SMA 20)
    Stop: Beyond the band (tighter for mean reversion)
    """

    def __init__(self, config: StrategyConfig = None):
        if config is None:
            config = StrategyConfig(
                name="bollinger_bounce",
                min_confidence=0.62,
                ai_threshold=0.82,
                max_position_pct=0.02,
                default_stop_atr_mult=1.2,
                default_target_atr_mult=1.5,
                params={
                    'pct_b_long_threshold': 0.1,  # At lower band
                    'pct_b_short_threshold': 0.9,  # At upper band
                    'rsi_long_min': 25,
                    'rsi_long_max': 45,
                    'rsi_short_min': 55,
                    'rsi_short_max': 75,
                    'adx_max': 35,  # Avoid strong trends
                    'require_reversal_candle': True,
                    'target_middle_band': True
                }
            )
        super().__init__(config)

    @property
    def name(self) -> str:
        return "bollinger_bounce"

    @property
    def description(self) -> str:
        return "Mean reversion at Bollinger Band extremes (77-80% win rate)"

    def get_required_indicators(self) -> List[str]:
        return [
            'bb_upper', 'bb_middle', 'bb_lower', 'bb_pct_b', 'bb_width',
            'rsi_14', 'atr_14', 'adx', 'plus_di', 'minus_di', 'rvol'
        ]

    def generate_signal(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        indicators: Dict[str, float]
    ) -> Optional[Signal]:

        bb_upper = indicators.get('bb_upper')
        bb_middle = indicators.get('bb_middle')
        bb_lower = indicators.get('bb_lower')
        pct_b = indicators.get('bb_pct_b')
        bb_width = indicators.get('bb_width')
        rsi = indicators.get('rsi_14')
        atr = indicators.get('atr_14')
        adx = indicators.get('adx')
        plus_di = indicators.get('plus_di')
        minus_di = indicators.get('minus_di')
        rvol = indicators.get('rvol', 1.0)

        if any(v is None for v in [bb_upper, bb_middle, bb_lower, pct_b, rsi, atr]):
            return None

        bars = snapshot.bars_1m
        if len(bars) < 3:
            return None

        price = snapshot.last_price
        params = self.config.params

        # Check for bounce setups
        long_bounce = self._check_long_bounce(
            price, bars, pct_b, bb_lower, bb_middle, rsi, adx, plus_di, minus_di, rvol, params
        )
        short_bounce = self._check_short_bounce(
            price, bars, pct_b, bb_upper, bb_middle, rsi, adx, plus_di, minus_di, rvol, params
        )

        if not long_bounce['valid'] and not short_bounce['valid']:
            return None

        # Select direction
        if long_bounce['valid'] and long_bounce['score'] >= short_bounce.get('score', 0):
            direction = SignalDirection.LONG
            score = long_bounce['score']
            reasoning = long_bounce['reasoning']
            # Target is middle band for mean reversion
            take_profit = bb_middle if params.get('target_middle_band') else None
            stop_loss = bb_lower - (atr * 0.5)  # Slightly below lower band
        elif short_bounce['valid']:
            direction = SignalDirection.SHORT
            score = short_bounce['score']
            reasoning = short_bounce['reasoning']
            take_profit = bb_middle if params.get('target_middle_band') else None
            stop_loss = bb_upper + (atr * 0.5)  # Slightly above upper band
        else:
            return None

        confidence = min(score / 100, 0.92)

        if confidence < self.config.min_confidence:
            return None

        # Use ATR-based stop if not targeting middle band
        if take_profit is None:
            take_profit = self.calculate_take_profit(price, direction, atr)
        if stop_loss is None:
            stop_loss = self.calculate_stop_loss(price, direction, atr)

        # Strength
        if confidence >= 0.82:
            strength = SignalStrength.VERY_STRONG
        elif confidence >= 0.72:
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
            entry_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            suggested_size_pct=self.config.max_position_pct * confidence,
            reasoning=reasoning,
            indicators_used={
                'bb_upper': bb_upper,
                'bb_middle': bb_middle,
                'bb_lower': bb_lower,
                'pct_b': pct_b,
                'bb_width': bb_width,
                'rsi': rsi,
                'adx': adx,
                'rvol': rvol,
                'atr': atr
            },
            market_context={
                'price': price,
                'band_distance': abs(price - bb_middle)
            },
            valid_until=datetime.now() + timedelta(minutes=20)
        )

    def _check_long_bounce(
        self,
        price: float,
        bars: List,
        pct_b: float,
        bb_lower: float,
        bb_middle: float,
        rsi: float,
        adx: float,
        plus_di: float,
        minus_di: float,
        rvol: float,
        params: Dict
    ) -> Dict:
        """Check for bullish bounce off lower band"""
        score = 0
        reasons = []

        # Price at lower band
        threshold = params.get('pct_b_long_threshold', 0.1)
        if pct_b > threshold:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        score += 25
        reasons.append(f"%B at lower band ({pct_b:.2f})")

        # RSI in bounce zone
        rsi_min = params.get('rsi_long_min', 25)
        rsi_max = params.get('rsi_long_max', 45)
        if rsi_min <= rsi <= rsi_max:
            score += 20
            reasons.append(f"RSI oversold bounce zone ({rsi:.1f})")
        elif rsi < rsi_min:
            score += 10  # Very oversold - could be strong
        else:
            score -= 10

        # Avoid strong downtrends
        adx_max = params.get('adx_max', 35)
        if adx is not None:
            if adx < adx_max:
                score += 10
                reasons.append(f"ADX low ({adx:.1f}) - not strong trend")
            elif minus_di is not None and plus_di is not None and plus_di > minus_di:
                score += 5  # Uptrend still, ok to buy
            else:
                score -= 15
                reasons.append(f"Warning: Strong downtrend ADX={adx:.1f}")

        # Check for reversal candle
        if params.get('require_reversal_candle', True) and len(bars) >= 2:
            current = bars[-1]
            # Bullish reversal: close near high, long lower wick
            if current.close > current.open:
                bar_range = current.high - current.low
                if bar_range > 0:
                    lower_wick = current.open - current.low
                    if lower_wick / bar_range > 0.3:
                        score += 15
                        reasons.append("Bullish reversal candle")

        # Volume confirmation
        if rvol > 1.5:
            score += 10
            reasons.append(f"Volume spike (RVOL: {rvol:.1f})")

        # Price recovering
        if price > bb_lower:
            score += 5
            reasons.append("Price recovering from band")

        valid = score >= 50

        return {
            'valid': valid,
            'score': score,
            'reasoning': "; ".join(reasons)
        }

    def _check_short_bounce(
        self,
        price: float,
        bars: List,
        pct_b: float,
        bb_upper: float,
        bb_middle: float,
        rsi: float,
        adx: float,
        plus_di: float,
        minus_di: float,
        rvol: float,
        params: Dict
    ) -> Dict:
        """Check for bearish bounce off upper band"""
        score = 0
        reasons = []

        # Price at upper band
        threshold = params.get('pct_b_short_threshold', 0.9)
        if pct_b < threshold:
            return {'valid': False, 'score': 0, 'reasoning': ''}

        score += 25
        reasons.append(f"%B at upper band ({pct_b:.2f})")

        # RSI in bounce zone
        rsi_min = params.get('rsi_short_min', 55)
        rsi_max = params.get('rsi_short_max', 75)
        if rsi_min <= rsi <= rsi_max:
            score += 20
            reasons.append(f"RSI overbought bounce zone ({rsi:.1f})")
        elif rsi > rsi_max:
            score += 10  # Very overbought
        else:
            score -= 10

        # Avoid strong uptrends
        adx_max = params.get('adx_max', 35)
        if adx is not None:
            if adx < adx_max:
                score += 10
                reasons.append(f"ADX low ({adx:.1f}) - not strong trend")
            elif plus_di is not None and minus_di is not None and minus_di > plus_di:
                score += 5  # Downtrend, ok to short
            else:
                score -= 15
                reasons.append(f"Warning: Strong uptrend ADX={adx:.1f}")

        # Check for reversal candle
        if params.get('require_reversal_candle', True) and len(bars) >= 2:
            current = bars[-1]
            # Bearish reversal: close near low, long upper wick
            if current.close < current.open:
                bar_range = current.high - current.low
                if bar_range > 0:
                    upper_wick = current.high - current.open
                    if upper_wick / bar_range > 0.3:
                        score += 15
                        reasons.append("Bearish reversal candle")

        # Volume confirmation
        if rvol > 1.5:
            score += 10
            reasons.append(f"Volume spike (RVOL: {rvol:.1f})")

        # Price turning
        if price < bb_upper:
            score += 5
            reasons.append("Price pulling back from band")

        valid = score >= 50

        return {
            'valid': valid,
            'score': score,
            'reasoning': "; ".join(reasons)
        }
