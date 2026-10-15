"""
Strategies router - View and manage trading strategies.
"""
from fastapi import APIRouter, HTTPException

from src.strategies.registry import get_registry
from api.schemas.models import StrategyStatus, StrategyToggle, StrategyParamsUpdate, StrategiesResponse

router = APIRouter()


@router.get("", response_model=StrategiesResponse)
async def get_all_strategies():
    """Get all registered strategies with their status"""
    registry = get_registry()
    strategies = []

    # get_all() returns a list, not a dict
    for strategy in registry.get_all():
        strategies.append(StrategyStatus(
            name=strategy.name,
            enabled=strategy.config.enabled,
            description=strategy.description,
            signals_generated=getattr(strategy, '_signal_count', 0),
            win_rate=getattr(strategy, '_win_rate', 0.0),
            params=strategy.config.params
        ))

    return StrategiesResponse(strategies=strategies)


@router.get("/{name}", response_model=StrategyStatus)
async def get_strategy(name: str):
    """Get specific strategy status"""
    registry = get_registry()
    strategy = registry.get(name)

    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy {name} not found")

    return StrategyStatus(
        name=name,
        enabled=strategy.config.enabled,
        description=strategy.description,
        signals_generated=getattr(strategy, '_signal_count', 0),
        win_rate=getattr(strategy, '_win_rate', 0.0),
        params=strategy.config.params
    )


@router.post("/{name}/toggle")
async def toggle_strategy(name: str, toggle: StrategyToggle):
    """Enable or disable a strategy"""
    registry = get_registry()
    strategy = registry.get(name)

    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy {name} not found")

    strategy.config.enabled = toggle.enabled

    return {
        "status": "updated",
        "strategy": name,
        "enabled": toggle.enabled
    }


@router.patch("/{name}/params")
async def update_strategy_params(name: str, update: StrategyParamsUpdate):
    """Update strategy parameters"""
    registry = get_registry()
    strategy = registry.get(name)

    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy {name} not found")

    # Update params
    strategy.config.params.update(update.params)

    return {
        "status": "updated",
        "strategy": name,
        "params": strategy.config.params
    }


@router.get("/{name}/signals")
async def get_strategy_signals(name: str, limit: int = 50):
    """Get recent signals from a strategy"""
    # TODO: Implement signal history from database
    return {
        "strategy": name,
        "signals": [],
        "message": "Signal history not yet implemented"
    }
