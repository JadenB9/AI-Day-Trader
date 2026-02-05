"""
Strategy registry - plugin discovery and management.
"""
from typing import Dict, List, Type, Optional, Set
import structlog

from src.strategies.base import Strategy, StrategyConfig, Signal
from src.data.models.market_snapshot import MarketSnapshot

logger = structlog.get_logger()


class StrategyRegistry:
    """
    Registry for managing and discovering strategies.
    Strategies register themselves here.
    """

    def __init__(self):
        self._strategies: Dict[str, Strategy] = {}
        self._enabled: Set[str] = set()

    def register(self, strategy: Strategy) -> None:
        """Register a strategy instance"""
        name = strategy.name
        if name in self._strategies:
            logger.warning("strategy_overwrite", name=name)

        self._strategies[name] = strategy

        if strategy.config.enabled:
            self._enabled.add(name)

        logger.info("strategy_registered", name=name, enabled=strategy.config.enabled)

    def register_class(self, strategy_class: Type[Strategy], config: StrategyConfig = None) -> Strategy:
        """Register a strategy by class, instantiate it"""
        instance = strategy_class(config)
        self.register(instance)
        return instance

    def unregister(self, name: str) -> None:
        """Remove strategy from registry"""
        self._strategies.pop(name, None)
        self._enabled.discard(name)

    def get(self, name: str) -> Optional[Strategy]:
        """Get strategy by name"""
        return self._strategies.get(name)

    def get_all(self) -> List[Strategy]:
        """Get all registered strategies"""
        return list(self._strategies.values())

    def get_enabled(self) -> List[Strategy]:
        """Get all enabled strategies"""
        return [s for name, s in self._strategies.items() if name in self._enabled]

    def enable(self, name: str) -> bool:
        """Enable a strategy"""
        if name in self._strategies:
            self._enabled.add(name)
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a strategy"""
        self._enabled.discard(name)
        return True

    def is_enabled(self, name: str) -> bool:
        """Check if strategy is enabled"""
        return name in self._enabled

    @property
    def names(self) -> List[str]:
        """List all strategy names"""
        return list(self._strategies.keys())

    @property
    def enabled_count(self) -> int:
        return len(self._enabled)


# Global registry singleton
_registry: Optional[StrategyRegistry] = None


def get_registry() -> StrategyRegistry:
    """Get or create strategy registry"""
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
    return _registry


def register_strategy(strategy: Strategy) -> None:
    """Convenience function to register strategy"""
    get_registry().register(strategy)


class StrategyEngine:
    """
    Runs all enabled strategies against market data.
    Collects and routes signals.
    """

    def __init__(self, registry: StrategyRegistry = None):
        self.registry = registry or get_registry()
        self._signal_count = 0

    async def process_snapshot(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        indicators: Dict[str, float]
    ) -> List[Signal]:
        """
        Run all enabled strategies on a market snapshot.

        Args:
            symbol: Stock symbol
            snapshot: Market data snapshot
            indicators: Pre-calculated indicators

        Returns:
            List of signals generated
        """
        signals = []

        for strategy in self.registry.get_enabled():
            try:
                # Validate basic conditions
                if not strategy.validate_conditions(symbol, snapshot):
                    continue

                # Check if required indicators are available
                required = strategy.get_required_indicators()
                missing = [r for r in required if r not in indicators]
                if missing:
                    logger.debug(
                        "missing_indicators",
                        strategy=strategy.name,
                        symbol=symbol,
                        missing=missing
                    )
                    continue

                # Generate signal
                signal = strategy.generate_signal(symbol, snapshot, indicators)

                if signal is not None:
                    signals.append(signal)
                    self._signal_count += 1
                    logger.info(
                        "signal_generated",
                        strategy=strategy.name,
                        symbol=symbol,
                        direction=signal.direction.value,
                        confidence=signal.confidence
                    )

            except Exception as e:
                logger.error(
                    "strategy_error",
                    strategy=strategy.name,
                    symbol=symbol,
                    error=str(e)
                )

        return signals

    @property
    def signal_count(self) -> int:
        return self._signal_count


def register_all_strategies() -> None:
    """
    Import and register all built-in strategies.
    Call this at startup.
    """
    registry = get_registry()

    # Import strategies - they self-register via decorators or explicit registration
    try:
        from src.strategies.scalping.one_minute_scalp import OneMinuteScalp
        registry.register(OneMinuteScalp())
    except ImportError as e:
        logger.warning("strategy_import_failed", strategy="one_minute_scalp", error=str(e))

    try:
        from src.strategies.scalping.vwap_bounce import VWAPBounce
        registry.register(VWAPBounce())
    except ImportError as e:
        logger.warning("strategy_import_failed", strategy="vwap_bounce", error=str(e))

    try:
        from src.strategies.momentum.gap_and_go import GapAndGo
        registry.register(GapAndGo())
    except ImportError as e:
        logger.warning("strategy_import_failed", strategy="gap_and_go", error=str(e))

    try:
        from src.strategies.mean_reversion.bollinger_bounce import BollingerBounce
        registry.register(BollingerBounce())
    except ImportError as e:
        logger.warning("strategy_import_failed", strategy="bollinger_bounce", error=str(e))

    try:
        from src.strategies.mean_reversion.rsi_reversal import RSIReversal
        registry.register(RSIReversal())
    except ImportError as e:
        logger.warning("strategy_import_failed", strategy="rsi_reversal", error=str(e))

    logger.info("strategies_registered", count=registry.enabled_count)
