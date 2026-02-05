"""
Crypto Scalping Strategy for HFT mode.
Optimized for 24/7 volatile crypto markets.
"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from src.strategies.base import Strategy, Signal, SignalDirection, SignalType, SignalStrength, StrategyConfig, AssetClass
from src.data.models.market_snapshot import MarketSnapshot


class CryptoScalpStrategy(Strategy):
    """
    HFT strategy optimized for crypto volatility.

    Entry conditions:
    - Mean reversion on short timeframe
    - Price touched Bollinger Band
    - RSI extreme (oversold/overbought)
    - High volume activity

    Features:
    - Works 24/7 (no market hours)
    - Wider stops for crypto volatility
    - Faster targets
    """

    def __init__(self, config: StrategyConfig = None):
        default_config = StrategyConfig(
            name="crypto_scalp",
            min_confidence=0.40,  # Lowered from 0.60 - AGGRESSIVE
            ai_threshold=0.95,  # Almost never AI
            max_position_pct=0.03,  # Increased from 0.01 - AGGRESSIVE
            default_stop_atr_mult=2.0,  # Wider for volatility
            default_target_atr_mult=2.5,
            params={
                "rsi_oversold": 35,  # Widened from 30
                "rsi_overbought": 65,  # Widened from 70
                "bb_touch_threshold": 0.05,  # Widened from 0.02 - AGGRESSIVE
                "min_volume_ratio": 0.8,  # Lowered from 1.5
                "profit_target_pct": 0.8,  # Increased from 0.5
                "stop_loss_pct": 0.5,  # Increased from 0.3
                "max_hold_seconds": 120,  # Increased from 60
            }
        )
        super().__init__(config or default_config)

    @property
    def name(self) -> str:
        return "crypto_scalp"

    @property
    def description(self) -> str:
        return "24/7 crypto scalping with mean reversion"

    def get_required_indicators(self) -> List[str]:
        return ['rsi_14', 'bb_upper', 'bb_lower', 'bb_mid', 'atr_14', 'volume_sma_20']

    def validate_conditions(self, symbol: str, snapshot: MarketSnapshot) -> bool:
        """Override to allow crypto symbols"""
        # Only trade crypto
        if "/" not in symbol and snapshot.asset_class != "crypto":
            return False

        if not snapshot.bars_1m or len(snapshot.bars_1m) < 20:
            return False

        return True

    def generate_signal(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        indicators: Dict[str, float]
    ) -> Optional[Signal]:
        if not self.validate_conditions(symbol, snapshot):
            return None

        params = self.config.params
        price = snapshot.mid_price

        if price <= 0:
            return None

        # Get indicators
        rsi = indicators.get('rsi_14', 50)
        bb_upper = indicators.get('bb_upper', price * 1.02)
        bb_lower = indicators.get('bb_lower', price * 0.98)
        bb_mid = indicators.get('bb_mid', price)
        atr = indicators.get('atr_14', price * 0.01)
        avg_volume = indicators.get('volume_sma_20', 1)

        # Current volume
        current_volume = snapshot.bars_1m[-1].volume if snapshot.bars_1m else 0
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

        # Volume filter
        if volume_ratio < params["min_volume_ratio"]:
            return None

        direction = None
        confidence = 0.60

        # Check for oversold bounce (long)
        if rsi <= params["rsi_oversold"]:
            # Price near lower BB
            distance_to_lower = (price - bb_lower) / price * 100
            if distance_to_lower <= params["bb_touch_threshold"]:
                direction = SignalDirection.LONG
                confidence += 0.15
                confidence += min((params["rsi_oversold"] - rsi) * 0.01, 0.1)

        # Check for overbought reversal (short)
        elif rsi >= params["rsi_overbought"]:
            distance_to_upper = (bb_upper - price) / price * 100
            if distance_to_upper <= params["bb_touch_threshold"]:
                direction = SignalDirection.SHORT
                confidence += 0.15
                confidence += min((rsi - params["rsi_overbought"]) * 0.01, 0.1)

        if direction is None:
            return None

        # Volume bonus
        confidence += min((volume_ratio - params["min_volume_ratio"]) * 0.05, 0.1)
        confidence = min(confidence, 0.95)

        # Price targets
        entry = price

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
            strength=SignalStrength.STRONG if confidence > 0.75 else SignalStrength.MODERATE,
            entry_price=entry,
            stop_loss=stop,
            take_profit=target,
            suggested_size_pct=self.config.max_position_pct,
            reasoning=f"Crypto scalp: RSI {rsi:.1f}, {'oversold' if direction == SignalDirection.LONG else 'overbought'}, vol {volume_ratio:.1f}x",
            indicators_used={
                'rsi': rsi,
                'bb_upper': bb_upper,
                'bb_lower': bb_lower,
                'volume_ratio': volume_ratio,
                'price': price
            },
            valid_until=datetime.now() + timedelta(seconds=params["max_hold_seconds"]),
            asset_class=AssetClass.CRYPTO
        )
