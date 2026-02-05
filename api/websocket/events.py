"""
WebSocket event types and helpers.
"""
from datetime import datetime
from typing import Dict, Any


class WSEventType:
    """WebSocket event type constants"""
    POSITION_UPDATE = "position_update"
    ORDER_UPDATE = "order_update"
    SIGNAL = "signal"
    RISK_ALERT = "risk_alert"
    HEARTBEAT = "heartbeat"
    SYSTEM_STATUS = "system_status"
    FULL_STATE = "full_state"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    ACTIVITY = "activity"  # New: activity log events


async def create_heartbeat_event() -> Dict[str, Any]:
    """Create heartbeat event with current system stats"""
    from src.execution.alpaca_broker import get_broker
    from api.routers.system import get_engine_state

    try:
        broker = get_broker()
        account = await broker.get_account()
        positions = await broker.get_positions()
    except Exception:
        account = {"equity": 0, "cash": 0}
        positions = {}

    engine_state = get_engine_state()

    # Calculate P&L
    total_pl = sum(p.get('unrealized_pl', 0) for p in positions.values())

    return {
        "equity": account.get('equity', 0),
        "cash": account.get('cash', 0),
        "daily_pnl": total_pl,
        "position_count": len(positions),
        "cycle_count": engine_state.get("cycle_count", 0),
        "running": engine_state.get("running", False),
        "timestamp": datetime.now().isoformat()
    }


def create_position_event(symbol: str, position_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create position update event"""
    return {
        "symbol": symbol,
        "qty": position_data.get('qty'),
        "side": position_data.get('side'),
        "entry_price": position_data.get('avg_entry_price'),
        "current_price": position_data.get('current_price'),
        "unrealized_pl": position_data.get('unrealized_pl'),
        "unrealized_plpc": position_data.get('unrealized_plpc'),
        "market_value": position_data.get('market_value'),
        "asset_class": position_data.get('asset_class', 'us_equity'),
        "timestamp": datetime.now().isoformat()
    }


def create_order_event(order_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create order update event"""
    return {
        "order_id": order_data.get('order_id'),
        "symbol": order_data.get('symbol'),
        "side": order_data.get('side'),
        "qty": order_data.get('qty'),
        "type": order_data.get('type'),
        "status": order_data.get('status'),
        "filled_qty": order_data.get('filled_qty', 0),
        "filled_avg_price": order_data.get('filled_avg_price'),
        "timestamp": datetime.now().isoformat()
    }


def create_signal_event(signal) -> Dict[str, Any]:
    """Create signal event from Signal object"""
    if hasattr(signal, 'to_dict'):
        return signal.to_dict()

    return {
        "symbol": signal.symbol,
        "direction": signal.direction.value,
        "strategy": signal.strategy,
        "confidence": signal.confidence,
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "reasoning": signal.reasoning,
        "timestamp": datetime.now().isoformat()
    }


def create_risk_alert(alert_type: str, message: str, metrics: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create risk alert event"""
    return {
        "alert_type": alert_type,
        "message": message,
        "metrics": metrics or {},
        "timestamp": datetime.now().isoformat()
    }
