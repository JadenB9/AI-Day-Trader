from typing import Dict, List, Optional

from src.strategies.base import Strategy, StrategyConfig, Signal
from src.strategies.registry import StrategyRegistry, register_all_strategies, get_registry


class Dummy(Strategy):
    def __init__(self, name="dummy", enabled=True):
        self._name = name
        super().__init__(StrategyConfig(name=name, enabled=enabled))

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "test strategy"

    def get_required_indicators(self) -> List[str]:
        return []

    def generate_signal(self, symbol, snapshot, indicators: Dict[str, float]) -> Optional[Signal]:
        return None


def test_register_enable_disable():
    reg = StrategyRegistry()
    reg.register(Dummy("a"))
    reg.register(Dummy("b", enabled=False))
    assert reg.names == ["a", "b"]
    assert [s.name for s in reg.get_enabled()] == ["a"]
    assert reg.enable("b")
    assert reg.enabled_count == 2
    reg.disable("a")
    assert not reg.is_enabled("a")
    assert not reg.enable("missing")
    reg.unregister("a")
    assert reg.get("a") is None


def test_builtin_strategies_register_at_startup():
    register_all_strategies()
    names = set(get_registry().names)
    assert {"one_minute_scalp", "vwap_bounce", "gap_and_go", "bollinger_bounce", "rsi_reversal"} <= names
