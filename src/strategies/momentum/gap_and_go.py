"""
Gap and Go Strategy.
Trades pre-market gaps with momentum continuation.
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from src.strategies.base import (
    Strategy, StrategyConfig, Signal,
    SignalDirection, SignalType, SignalStrength
)
from src.data.models.market_snapshot import MarketSnapshot
from src.utils.helpers import is_premarket, get_eastern_time


class GapAndGo(Strategy):
    """
    Gap and Go momentum strategy.

    Trades stocks that gap significantly in pre-market and continue
    in the direction of the gap at market open.

    Entry conditions (LONG gap up):
    - Gap > 4% from previous close
    - Pre-market volume > 100k
    - Price holding above VWAP
    - News catalyst preferred
    - RSI between 50-75 (momentum, not overbought)
    - First pullback to VWAP or prior resistance

    Entry conditions (SHORT gap down):
    - Gap < -4% from previous close
    - Pre-market volume > 100k
    - Price holding below VWAP
    - RSI between 25-50

    Best window: First 30 minutes after market open
    """

    def __init__(self, config: StrategyConfig = None):
        if config is None:
            config = StrategyConfig(
                name="gap_and_go",
                min_confidence=0.40,  # Lowered from 0.65 - AGGRESSIVE
                ai_threshold=0.55,  # Lowered from 0.85
                max_position_pct=0.05,  # Increased from 0.025
                default_stop_atr_mult=2.0,  # Wider stops
                default_target_atr_mult=3.0,
                trade_premarket=True,  # Allow premarket trading
                trade_regular=True,
                params={
                    'min_gap_pct': 1.5,  # Lowered from 4.0 - trade smaller gaps
                    'max_gap_pct': 20.0,  # Increased from 15.0
                    'min_premarket_volume': 25000,  # Lowered from 100000
                    'min_rvol': 1.0,  # Lowered from 2.0
                    'rsi_long_min': 40,  # Widened from 50
                    'rsi_long_max': 80,  # Widened from 75
                    'rsi_short_min': 20,  # Widened from 25
                    'rsi_short_max': 60,  # Widened from 50
                    'first_candle_filter': False,  # Don't wait - AGGRESSIVE
                    'trade_window_minutes': 120  # Extended from 60
                }
            )
        super().__init__(config)
        self._gaps_identified: Dict[str, float] = {}  # symbol -> gap %

    @property
    def name(self) -> str:
        return "gap_and_go"

    @property
    def description(self) -> str:
        return "Trade momentum continuation on pre-market gaps"

    def get_required_indicators(self) -> List[str]:
        return ['vwap', 'rsi_14', 'atr_14', 'ema_9', 'ema_21', 'rvol']

    def validate_conditions(self, symbol: str, snapshot: MarketSnapshot) -> bool:
        """Check if gap conditions are met"""
        if not super().validate_conditions(symbol, snapshot):
            return False

        # Check for significant gap
        gap_pct = snapshot.gap_pct
        params = self.config.params
        min_gap = params.get('min_gap_pct', 4.0)
        max_gap = params.get('max_gap_pct', 15.0)

        if abs(gap_pct) < min_gap or abs(gap_pct) > max_gap:
            return False

        # Store gap for signal generation
        self._gaps_identified[symbol] = gap_pct

        return True

    def generate_signal(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        indicators: Dict[str, float]
    ) -> Optional[Signal]:

        gap_pct = self._gaps_identified.get(symbol, snapshot.gap_pct)

        vwap = indicators.get('vwap')
        rsi = indicators.get('rsi_14')
        atr = indicators.get('atr_14')
        ema_9 = indicators.get('ema_9')
        ema_21 = indicators.get('ema_21')
        rvol = indicators.get('rvol', 1.0)

        if any(v is None for v in [vwap, rsi, atr, ema_9, ema_21]):
            return None

        price = snapshot.last_price
        if price <= 0:
            return None

        params = self.config.params

        # Volume filter - relaxed for aggressive trading
        min_rvol = params.get('min_rvol', 1.0)
        # Skip volume filter if rvol data is missing or too restrictive
        if rvol is not None and rvol < min_rvol * 0.5:  # Very low threshold
            return None

        # Determine gap direction
        if gap_pct > 0:
            signal = self._check_long_gap(
                price, gap_pct, vwap, rsi, ema_9, ema_21, rvol, params
            )
        else:
            signal = self._check_short_gap(
                price, gap_pct, vwap, rsi, ema_9, ema_21, rvol, params
            )

        if not signal['valid']:
            return None

        direction = signal['direction']
        score = signal['score']
        reasoning = signal['reasoning']

        # Confidence
        confidence = min(score / 100, 0.93)

        if confidence < self.config.min_confidence:
            return None

        # Calculate stops
        entry_price = price
        stop_loss = self.calculate_stop_loss(entry_price, direction, atr)
        take_profit = self.calculate_take_profit(entry_price, direction, atr)

        # Strength
        if confidence >= 0.85:
            strength = SignalStrength.VERY_STRONG
        elif confidence >= 0.75:
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
                'gap_pct': gap_pct,
                'vwap': vwap,
                'rsi': rsi,
                'rvol': rvol,
                'ema_9': ema_9,
                'ema_21': ema_21,
                'atr': atr
            },
            market_context={
                'price': price,
                'prev_close': snapshot.prev_close,
                'day_open': snapshot.day_open,
                'has_news': len(snapshot.recent_news) > 0
            },
            valid_until=datetime.now() + timedelta(minutes=30)
        )

    def _check_long_gap(
        self,
        price: float,
        gap_pct: float,
        vwap: float,
        rsi: float,
        ema_9: float,
        ema_21: float,
        rvol: float,
        params: Dict
    ) -> Dict:
        """Check conditions for long gap-up trade"""
        score = 0
        reasons = []

        # Gap confirmation
        if gap_pct < params.get('min_gap_pct', 4.0):
            return {'valid': False, 'direction': None, 'score': 0, 'reasoning': ''}

        score += 20
        reasons.append(f"Gap up {gap_pct:.1f}%")

        # Price above VWAP (holding gap)
        if price > vwap:
            score += 20
            reasons.append(f"Price above VWAP ({price:.2f} > {vwap:.2f})")
        else:
            score -= 20
            reasons.append("Warning: Below VWAP, gap fill risk")

        # RSI range
        rsi_min = params.get('rsi_long_min', 50)
        rsi_max = params.get('rsi_long_max', 75)
        if rsi_min <= rsi <= rsi_max:
            score += 15
            reasons.append(f"RSI momentum ({rsi:.1f})")
        elif rsi > rsi_max:
            score -= 10
            reasons.append(f"RSI overbought ({rsi:.1f})")

        # EMA trend
        if ema_9 > ema_21:
            score += 15
            reasons.append("EMAs bullish aligned")
        if price > ema_9:
            score += 10
            reasons.append("Price above EMA 9")

        # Volume
        if rvol > 3.0:
            score += 15
            reasons.append(f"High volume (RVOL: {rvol:.1f})")
        elif rvol > 2.0:
            score += 10

        # Strong gap bonus
        if gap_pct > 7:
            score += 10
            reasons.append("Strong gap")

        valid = score >= 30  # Lowered from 55 - AGGRESSIVE

        return {
            'valid': valid,
            'direction': SignalDirection.LONG,
            'score': score,
            'reasoning': "; ".join(reasons)
        }

    def _check_short_gap(
        self,
        price: float,
        gap_pct: float,
        vwap: float,
        rsi: float,
        ema_9: float,
        ema_21: float,
        rvol: float,
        params: Dict
    ) -> Dict:
        """Check conditions for short gap-down trade"""
        score = 0
        reasons = []

        # Gap confirmation (gap_pct is negative)
        if gap_pct > -params.get('min_gap_pct', 4.0):
            return {'valid': False, 'direction': None, 'score': 0, 'reasoning': ''}

        score += 20
        reasons.append(f"Gap down {gap_pct:.1f}%")

        # Price below VWAP (holding gap)
        if price < vwap:
            score += 20
            reasons.append(f"Price below VWAP ({price:.2f} < {vwap:.2f})")
        else:
            score -= 20
            reasons.append("Warning: Above VWAP, gap fill risk")

        # RSI range
        rsi_min = params.get('rsi_short_min', 25)
        rsi_max = params.get('rsi_short_max', 50)
        if rsi_min <= rsi <= rsi_max:
            score += 15
            reasons.append(f"RSI momentum ({rsi:.1f})")
        elif rsi < rsi_min:
            score -= 10
            reasons.append(f"RSI oversold ({rsi:.1f})")

        # EMA trend
        if ema_9 < ema_21:
            score += 15
            reasons.append("EMAs bearish aligned")
        if price < ema_9:
            score += 10
            reasons.append("Price below EMA 9")

        # Volume
        if rvol > 3.0:
            score += 15
            reasons.append(f"High volume (RVOL: {rvol:.1f})")
        elif rvol > 2.0:
            score += 10

        # Strong gap bonus
        if gap_pct < -7:
            score += 10
            reasons.append("Strong gap")

        valid = score >= 30  # Lowered from 55 - AGGRESSIVE

        return {
            'valid': valid,
            'direction': SignalDirection.SHORT,
            'score': score,
            'reasoning': "; ".join(reasons)
        }
