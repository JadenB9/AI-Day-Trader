"""
WebSocket connection manager for real-time updates.
"""
import asyncio
from datetime import datetime
from typing import Dict, Set, List, Any
import structlog

from fastapi import WebSocket, WebSocketDisconnect

from config.settings import get_settings
from src.core.event_bus import get_event_bus, EventType, Event
from api.websocket.events import WSEventType, create_heartbeat_event

logger = structlog.get_logger()
settings = get_settings()


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.subscriptions: Dict[WebSocket, Set[str]] = {}  # symbol subscriptions
        self._event_bus = get_event_bus()
        self._setup_event_handlers()

    def _setup_event_handlers(self):
        """Subscribe to event bus for broadcasting"""
        bus = self._event_bus

        # Position events
        bus.subscribe(EventType.POSITION_OPENED, self._handle_position_event, "ws_manager")
        bus.subscribe(EventType.POSITION_UPDATED, self._handle_position_event, "ws_manager")
        bus.subscribe(EventType.POSITION_CLOSED, self._handle_position_event, "ws_manager")

        # Order events
        bus.subscribe(EventType.ORDER_SUBMITTED, self._handle_order_event, "ws_manager")
        bus.subscribe(EventType.ORDER_FILLED, self._handle_order_event, "ws_manager")
        bus.subscribe(EventType.ORDER_CANCELLED, self._handle_order_event, "ws_manager")
        bus.subscribe(EventType.ORDER_REJECTED, self._handle_order_event, "ws_manager")

        # Signal events
        bus.subscribe(EventType.SIGNAL_GENERATED, self._handle_signal_event, "ws_manager")

        # Risk events
        bus.subscribe(EventType.RISK_ALERT, self._handle_risk_event, "ws_manager")
        bus.subscribe(EventType.DAILY_LIMIT_WARNING, self._handle_risk_event, "ws_manager")
        bus.subscribe(EventType.DAILY_LIMIT_HIT, self._handle_risk_event, "ws_manager")

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        self.subscriptions[websocket] = set()
        logger.info("ws_connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        """Remove disconnected client"""
        self.active_connections.discard(websocket)
        self.subscriptions.pop(websocket, None)
        logger.info("ws_disconnected", total=len(self.active_connections))

    async def broadcast(self, event_type: str, data: Dict[str, Any]):
        """Broadcast event to all connected clients"""
        if not self.active_connections:
            return

        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }

        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.debug("ws_send_error", error=str(e))
                disconnected.add(connection)

        # Clean up disconnected
        for conn in disconnected:
            self.disconnect(conn)

    async def send_to_subscribers(self, symbol: str, event_type: str, data: Dict[str, Any]):
        """Send event only to clients subscribed to symbol"""
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }

        disconnected = set()
        for connection, symbols in self.subscriptions.items():
            if symbol in symbols or not symbols:  # Empty = all symbols
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.add(connection)

        for conn in disconnected:
            self.disconnect(conn)

    def subscribe(self, websocket: WebSocket, symbols: List[str]):
        """Subscribe client to specific symbols"""
        if websocket in self.subscriptions:
            self.subscriptions[websocket].update(symbols)

    def unsubscribe(self, websocket: WebSocket, symbols: List[str]):
        """Unsubscribe client from symbols"""
        if websocket in self.subscriptions:
            self.subscriptions[websocket] -= set(symbols)

    # Event handlers
    async def _handle_position_event(self, event: Event):
        data = event.data if isinstance(event.data, dict) else event.data.to_dict() if hasattr(event.data, 'to_dict') else {"data": str(event.data)}
        await self.broadcast(WSEventType.POSITION_UPDATE, data)

    async def _handle_order_event(self, event: Event):
        data = event.data if isinstance(event.data, dict) else {"data": str(event.data)}
        await self.broadcast(WSEventType.ORDER_UPDATE, data)

    async def _handle_signal_event(self, event: Event):
        data = event.data.to_dict() if hasattr(event.data, 'to_dict') else {"data": str(event.data)}
        await self.broadcast(WSEventType.SIGNAL, data)

    async def _handle_risk_event(self, event: Event):
        data = event.data if isinstance(event.data, dict) else {"data": str(event.data)}
        data["alert_type"] = event.type.name
        await self.broadcast(WSEventType.RISK_ALERT, data)


# Singleton manager
_manager: ConnectionManager = None


def get_manager() -> ConnectionManager:
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint handler"""
    manager = get_manager()
    await manager.connect(websocket)

    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_json()

            # Handle client commands
            if data.get("action") == "subscribe":
                symbols = data.get("symbols", [])
                manager.subscribe(websocket, symbols)
                await websocket.send_json({
                    "type": "subscribed",
                    "symbols": symbols
                })

            elif data.get("action") == "unsubscribe":
                symbols = data.get("symbols", [])
                manager.unsubscribe(websocket, symbols)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "symbols": symbols
                })

            elif data.get("action") == "refresh":
                # Send current state
                await send_full_state(websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("ws_error", error=str(e))
        manager.disconnect(websocket)


async def send_full_state(websocket: WebSocket):
    """Send full system state to client"""
    from src.execution.alpaca_broker import get_broker

    try:
        broker = get_broker()
        account = await broker.get_account()
        positions = await broker.get_positions()

        await websocket.send_json({
            "type": "full_state",
            "data": {
                "account": account,
                "positions": positions
            },
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logger.error("send_state_error", error=str(e))


async def start_heartbeat():
    """Send periodic heartbeat with system stats"""
    manager = get_manager()

    while True:
        try:
            await asyncio.sleep(settings.dashboard.websocket_heartbeat_sec)

            if not manager.active_connections:
                continue

            # Build heartbeat data
            heartbeat = await create_heartbeat_event()
            await manager.broadcast(WSEventType.HEARTBEAT, heartbeat)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("heartbeat_error", error=str(e))
