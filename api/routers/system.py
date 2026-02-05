"""
System router - Start/stop trading engine, get system status.
"""
import asyncio
import uuid
from datetime import datetime
from typing import Optional, List, Dict
from collections import deque
from fastapi import APIRouter, HTTPException

from config.settings import get_settings
from src.execution.alpaca_broker import get_broker
from api.schemas.models import SystemStatus, SystemAction

router = APIRouter()
settings = get_settings()

# Activity log storage (in-memory, last 500 entries)
_activity_log: deque = deque(maxlen=500)


def log_activity(
    log_type: str,
    title: str,
    message: str,
    details: Dict = None
):
    """Add an activity log entry and broadcast via WebSocket"""
    entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now().isoformat(),
        "type": log_type,
        "title": title,
        "message": message,
        "details": details
    }
    _activity_log.append(entry)

    # Broadcast to WebSocket clients
    try:
        import asyncio
        from api.websocket.manager import get_manager
        from api.websocket.events import WSEventType

        manager = get_manager()
        if manager.active_connections:
            # Run broadcast in background
            asyncio.create_task(manager.broadcast(WSEventType.ACTIVITY, entry))
    except Exception:
        pass  # WebSocket not available

    return entry


def get_activity_logs(limit: int = 100, log_type: str = None) -> List[Dict]:
    """Get recent activity logs"""
    logs = list(_activity_log)
    if log_type:
        logs = [l for l in logs if l["type"] == log_type]
    return logs[-limit:]

# Global engine state
_engine_state = {
    "running": False,
    "start_time": None,
    "cycle_count": 0,
    "last_cycle_ms": 0,
    "engine_task": None
}


def get_engine_state():
    return _engine_state


@router.get("/status", response_model=SystemStatus)
async def get_system_status():
    """Get current system status"""
    broker = get_broker()

    try:
        account = await broker.get_account()
        positions = await broker.get_positions()
        open_orders = await broker.get_open_orders()
    except Exception as e:
        # Broker not connected
        account = {"equity": 0, "cash": 0, "buying_power": 0}
        positions = {}
        open_orders = []

    uptime = 0
    if _engine_state["running"] and _engine_state["start_time"]:
        uptime = (datetime.now() - _engine_state["start_time"]).total_seconds()

    mode = "paper" if settings.alpaca.trading_mode.value == "paper" else "live"
    if settings.dry_run:
        mode = "dry_run"

    return SystemStatus(
        running=_engine_state["running"],
        mode=mode,
        uptime_seconds=uptime,
        cycle_count=_engine_state["cycle_count"],
        last_cycle_time_ms=_engine_state["last_cycle_ms"],
        equity=account.get('equity', 0),
        cash=account.get('cash', 0),
        buying_power=account.get('buying_power', 0),
        position_count=len(positions),
        open_orders=len(open_orders),
        crypto_enabled=settings.crypto.enabled,
        hft_enabled=settings.hft.enabled
    )


@router.post("/start")
async def start_trading():
    """Start the trading engine"""
    if _engine_state["running"]:
        return {"status": "already_running"}

    # Import here to avoid circular imports
    from scripts.run_trader import TradingEngine

    # Create engine
    engine = TradingEngine(
        dry_run=settings.dry_run,
        single_cycle=False
    )

    # Start in background
    async def run_engine():
        try:
            await engine.start()
        except Exception as e:
            _engine_state["running"] = False
            raise

    _engine_state["engine_task"] = asyncio.create_task(run_engine())
    _engine_state["running"] = True
    _engine_state["start_time"] = datetime.now()

    return {
        "status": "started",
        "mode": "paper" if settings.alpaca.trading_mode.value == "paper" else "live"
    }


@router.post("/stop")
async def stop_trading():
    """Stop the trading engine"""
    if not _engine_state["running"]:
        return {"status": "not_running"}

    # Cancel engine task
    if _engine_state["engine_task"]:
        _engine_state["engine_task"].cancel()
        try:
            await _engine_state["engine_task"]
        except asyncio.CancelledError:
            pass

    _engine_state["running"] = False
    _engine_state["engine_task"] = None

    return {"status": "stopped"}


@router.get("/watchlist")
async def get_watchlist():
    """Get current watchlist symbols"""
    try:
        from src.data.scanner.watchlist import get_watchlist
        wl = get_watchlist()
        return {
            "symbols": list(wl.symbols) if wl else [],
            "crypto_symbols": list(settings.crypto.symbols) if settings.crypto.enabled else []
        }
    except Exception:
        return {
            "symbols": list(settings.default_symbols),
            "crypto_symbols": list(settings.crypto.symbols) if settings.crypto.enabled else []
        }


@router.post("/watchlist/add")
async def add_to_watchlist(symbol: str):
    """Add symbol to watchlist"""
    try:
        from src.data.scanner.watchlist import get_watchlist
        wl = get_watchlist()
        if wl:
            wl.add_symbol(symbol.upper())
            return {"status": "added", "symbol": symbol.upper()}
    except Exception:
        pass
    return {"status": "failed", "message": "Watchlist not initialized"}


@router.post("/watchlist/remove")
async def remove_from_watchlist(symbol: str):
    """Remove symbol from watchlist"""
    try:
        from src.data.scanner.watchlist import get_watchlist
        wl = get_watchlist()
        if wl:
            wl.remove_symbol(symbol.upper())
            return {"status": "removed", "symbol": symbol.upper()}
    except Exception:
        pass
    return {"status": "failed", "message": "Watchlist not initialized"}


@router.get("/test-connections")
async def test_connections():
    """Test Alpaca and Claude API connections"""
    from src.utils.connection_test import test_all_connections
    results = await test_all_connections()
    return results


@router.get("/test-alpaca")
async def test_alpaca():
    """Test Alpaca connection only"""
    from src.utils.connection_test import test_alpaca_connection
    success, result = await test_alpaca_connection()
    return result


@router.get("/test-claude")
async def test_claude():
    """Test Claude API connection"""
    from src.utils.connection_test import test_claude_connection
    success, result = await test_claude_connection()
    return result


@router.get("/test-claude-websearch")
async def test_claude_websearch():
    """Test Claude API with web search"""
    from src.utils.connection_test import test_claude_web_search
    success, result = await test_claude_web_search()
    return result


@router.get("/capital")
async def get_capital_status():
    """Get trading capital status (virtual vs actual)"""
    from src.execution.alpaca_broker import get_broker
    from src.utils.helpers import get_trading_capital, get_available_capital, is_capital_depleted

    broker = get_broker()
    account = await broker.get_account()

    actual_equity = account['equity']
    trading_capital = get_trading_capital(actual_equity)
    available_capital = get_available_capital(actual_equity)

    return {
        "actual_equity": actual_equity,
        "trading_capital": trading_capital,
        "available_capital": available_capital,
        "capital_reserve": settings.portfolio.capital_reserve,
        "virtual_mode": settings.portfolio.virtual_capital > 0,
        "is_depleted": is_capital_depleted(actual_equity),
        "utilization_pct": ((trading_capital - available_capital) / trading_capital * 100) if trading_capital > 0 else 0
    }


@router.get("/research")
async def get_research_status():
    """Get market research status and results"""
    try:
        from src.ai.market_research import get_researcher
        researcher = get_researcher()

        stats = researcher.stats
        cached = {}

        for symbol, research in researcher._cache.data.items():
            cached[symbol] = {
                "sentiment": research.sentiment,
                "confidence": research.confidence,
                "key_findings": research.key_findings[:3],
                "timestamp": research.timestamp.isoformat()
            }

        return {
            "stats": stats,
            "cached_research": cached,
            "last_overview": researcher._last_market_overview[:500] if researcher._last_market_overview else None
        }
    except Exception as e:
        return {"error": str(e), "message": "Research not yet initialized"}


@router.post("/research/run")
async def trigger_research(symbol: str = None):
    """Manually trigger market research"""
    try:
        from src.ai.market_research import get_researcher, run_hourly_research

        researcher = get_researcher()

        if symbol:
            # Research single symbol
            result = await researcher.research_symbol(symbol.upper(), force=True)
            return {
                "symbol": symbol.upper(),
                "sentiment": result.sentiment,
                "confidence": result.confidence,
                "key_findings": result.key_findings,
                "news_summary": result.news_summary,
                "recommendation": result.recommendation
            }
        else:
            # Research all watchlist symbols
            symbols = list(settings.default_symbols)
            results = await run_hourly_research(symbols)
            return results

    except Exception as e:
        return {"error": str(e)}


@router.get("/activity")
async def get_activity(limit: int = 100, log_type: str = None):
    """Get recent activity logs"""
    logs = get_activity_logs(limit=limit, log_type=log_type)

    # Add some system status info
    try:
        broker = get_broker()
        account = await broker.get_account()
        positions = await broker.get_positions()

        # Log current state if no recent logs
        if len(logs) == 0:
            log_activity(
                "info",
                "System Status",
                f"Connected to Alpaca. Equity: ${account['equity']:,.2f}, Positions: {len(positions)}",
                {"equity": account["equity"], "positions": len(positions)}
            )
            logs = get_activity_logs(limit=1)

    except Exception:
        pass

    return {
        "logs": logs,
        "total": len(_activity_log)
    }


@router.post("/activity/log")
async def add_activity_log(log_type: str, title: str, message: str, details: dict = None):
    """Manually add an activity log entry (for testing)"""
    entry = log_activity(log_type, title, message, details)
    return entry
