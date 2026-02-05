"""
Momentum Burst Strategy for HFT mode.
Detects sudden price spikes and rides the momentum with tight stops.
Designed for 1-second cycle times.
"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from src.strategies.base import Strategy, Signal, SignalDirection, SignalType, SignalStrength, StrategyConfig
from src.data.models.market_snapshot import MarketSnapshot


class MomentumBurstStrategy(Strategy):
    """
    HFT strategy that detects momentum bursts.

    Entry conditions:
    - Price moved > threshold % in last N bars
    - Volume spike (current > 2x average)
    - RSI not extreme (30-70 range)
    - MACD histogram positive/negative for direction

    Exit:
    - Quick profit targets (0.3-0.5%)
    - Tight stops (0.2%)
    - Time stop (30 seconds)
    """

    def __init__(self, config: StrategyConfig = None):
        default_config = StrategyConfig(
            name="momentum_burst",
            min_confidence=0.40,  # Lowered from 0.65 - AGGRESSIVE
            ai_threshold=0.9,  # Skip AI for speed
            max_position_pct=0.04,  # Increased from 0.015 - AGGRESSIVE
            default_stop_atr_mult=1.5,  # Slightly wider
            default_target_atr_mult=2.0,
            params={
                "burst_threshold_pct": 0.15,  # Lowered from 0.3 - detect smaller moves
                "lookback_bars": 3,  # Reduced from 5 - faster detection
                "volume_spike_mult": 1.2,  # Lowered from 2.0 - AGGRESSIVE
                "min_volume": 5000,  # Lowered from 10000
                "profit_target_pct": 0.6,  # Increased from 0.4
                "stop_loss_pct": 0.4,  # Increased from 0.2
                "max_hold_seconds": 60,  # Increased from 30
            }
        )
        super().__init__(config or default_config)

    @property
    def name(self) -> str:
        return "momentum_burst"

    @property
    def description(self) -> str:
        return "HFT momentum burst detector with tight stops"

    def get_required_indicators(self) -> List[str]:
        return ['rsi_14', 'macd_hist', 'atr_14', 'volume_sma_20']

    def generate_signal(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        indicators: Dict[str, float]
    ) -> Optional[Signal]:
        if not self.validate_conditions(symbol, snapshot):
            return None

        params = self.config.params
        bars = snapshot.bars_1m[-params["lookback_bars"]:]

        if len(bars) < params["lookback_bars"]:
            return None

        # Calculate price move
        start_price = bars[0].close
        end_price = bars[-1].close
        price_change_pct = ((end_price - start_price) / start_price) * 100

        # Check for burst
        if abs(price_change_pct) < params["burst_threshold_pct"]:
            return None

        # Volume check
        current_volume = bars[-1].volume
        avg_volume = indicators.get('volume_sma_20', current_volume)

        if current_volume < params["min_volume"]:
            return None

        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
        if volume_ratio < params["volume_spike_mult"]:
            return None

        # RSI filter (avoid extremes)
        rsi = indicators.get('rsi_14', 50)
        if rsi < 25 or rsi > 75:
            return None  # Too extreme

        # Direction from price move
        direction = SignalDirection.LONG if price_change_pct > 0 else SignalDirection.SHORT

        # MACD confirmation
        macd_hist = indicators.get('macd_hist', 0)
        if direction == SignalDirection.LONG and macd_hist < 0:
            return None  # MACD disagrees
        if direction == SignalDirection.SHORT and macd_hist > 0:
            return None

        # Calculate confidence
        confidence = 0.65
        confidence += min(abs(price_change_pct) / params["burst_threshold_pct"] * 0.1, 0.15)
        confidence += min((volume_ratio - params["volume_spike_mult"]) * 0.05, 0.1)
        confidence = min(confidence, 0.95)

        # Entry, stop, target
        entry = snapshot.mid_price
        atr = indicators.get('atr_14', entry * 0.01)

        if direction == SignalDirection.LONG:
            stop = entry * (1 - params["stop_loss_pct"] / 100)
            target = entry * (1 + params["profit_target_pct"] / 100)
        else:
            stop = entry * (1 + params["stop_loss_pct"] / 100)
            target = entry * (1 - params["profit_target_pct"] / 100)

        return Signal(
            symbol=symbol,
            direction=direction,
            signal_type=SignalType.ENTRY,
            strategy=self.name,
            confidence=confidence,
            strength=SignalStrength.STRONG if confidence > 0.8 else SignalStrength.MODERATE,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
            suggested_size_pct=self.config.max_position_pct,
            reasoning=f"Momentum burst: {price_change_pct:.2f}% in {params['lookback_bars']} bars, volume {volume_ratio:.1f}x avg",
            indicators_used={
                'price_change_pct': price_change_pct,
                'volume_ratio': volume_ratio,
                'rsi': rsi,
                'macd_hist': macd_hist
            },
            valid_until=datetime.now() + timedelta(seconds=params["max_hold_seconds"])
        )
