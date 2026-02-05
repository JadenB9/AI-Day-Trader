"""
Risk router - View and manage risk metrics.
"""
from fastapi import APIRouter

from config.settings import get_settings
from src.execution.alpaca_broker import get_broker
from src.risk.daily_limits import get_limits_manager
from api.schemas.models import RiskMetrics

router = APIRouter()
settings = get_settings()


@router.get("/metrics", response_model=RiskMetrics)
async def get_risk_metrics():
    """Get current risk metrics"""
    broker = get_broker()
    account = await broker.get_account()
    positions = await broker.get_positions()

    equity = account['equity']

    # Get limits manager if initialized
    limits_mgr = get_limits_manager()

    # Calculate portfolio heat (total risk exposure)
    open_risk = 0
    for symbol, pos in positions.items():
        entry = pos.get('avg_entry_price', 0)
        current = pos.get('current_price', entry)
        qty = abs(pos.get('qty', 0))
        risk_per_share = abs(current - entry) if entry != 0 else current * 0.02
        open_risk += qty * risk_per_share

    portfolio_heat = (open_risk / equity * 100) if equity > 0 else 0

    # Get daily P&L from limits manager stats
    daily_pnl = 0
    weekly_pnl = 0
    consecutive_losses = 0

    if limits_mgr:
        today_stats = limits_mgr.today_stats
        if today_stats:
            daily_pnl = today_stats.realized_pnl
            consecutive_losses = today_stats.consecutive_losses
        # Calculate weekly P&L from weekly stats
        if hasattr(limits_mgr, '_weekly_stats'):
            weekly_pnl = sum(s.realized_pnl for s in limits_mgr._weekly_stats.values())

    daily_pnl_pct = (daily_pnl / equity * 100) if equity > 0 else 0
    weekly_pnl_pct = (weekly_pnl / equity * 100) if equity > 0 else 0

    # Risk limits from settings
    max_daily = settings.portfolio.max_daily_loss * 100
    max_weekly = settings.portfolio.max_weekly_loss * 100

    return RiskMetrics(
        portfolio_heat=portfolio_heat,
        daily_pnl=daily_pnl,
        daily_pnl_pct=daily_pnl_pct,
        weekly_pnl=weekly_pnl,
        weekly_pnl_pct=weekly_pnl_pct,
        max_daily_loss=max_daily,
        max_weekly_loss=max_weekly,
        daily_limit_remaining=max_daily - abs(daily_pnl_pct) if daily_pnl_pct < 0 else max_daily,
        weekly_limit_remaining=max_weekly - abs(weekly_pnl_pct) if weekly_pnl_pct < 0 else max_weekly,
        position_count=len(positions),
        max_positions=settings.portfolio.max_positions,
        consecutive_losses=consecutive_losses,
        is_halted=limits_mgr.is_halted if limits_mgr else False,
        halt_reason=limits_mgr.halt_reason if limits_mgr and limits_mgr.is_halted else None
    )


@router.post("/halt")
async def halt_trading():
    """Emergency halt - stop all trading"""
    limits_mgr = get_limits_manager()

    if limits_mgr:
        limits_mgr.force_halt("Manual halt via API", duration_hours=24)

    return {
        "status": "halted",
        "message": "Trading has been halted"
    }


@router.post("/resume")
async def resume_trading():
    """Resume trading after halt"""
    limits_mgr = get_limits_manager()

    if limits_mgr:
        limits_mgr.resume_trading()

    return {
        "status": "resumed",
        "message": "Trading has been resumed"
    }


@router.get("/limits")
async def get_risk_limits():
    """Get configured risk limits"""
    return {
        "max_positions": settings.portfolio.max_positions,
        "max_portfolio_heat": settings.portfolio.max_portfolio_heat * 100,
        "max_daily_loss": settings.portfolio.max_daily_loss * 100,
        "max_weekly_loss": settings.portfolio.max_weekly_loss * 100,
        "max_sector_exposure": settings.portfolio.max_sector_exposure * 100,
        "risk_per_trade": settings.position_sizing.risk_per_trade * 100,
        "max_position_pct": settings.position_sizing.max_position_pct * 100
    }
