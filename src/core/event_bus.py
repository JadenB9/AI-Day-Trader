"""
Async event bus for decoupled component communication.
Central pub/sub system for the trading architecture.
"""
import asyncio
from typing import Callable, Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
import structlog

logger = structlog.get_logger()


class EventType(Enum):
    """All event types in the system"""
    # Market data events
    QUOTE_UPDATE = auto()
    TRADE_TICK = auto()
    BAR_COMPLETE = auto()
    ORDERBOOK_UPDATE = auto()

    # Scanner events
    SCANNER_RESULT = auto()
    WATCHLIST_UPDATED = auto()

    # Strategy events
    SIGNAL_GENERATED = auto()
    SIGNAL_EXPIRED = auto()

    # AI events
    AI_DECISION_REQUEST = auto()
    AI_DECISION_RESPONSE = auto()

    # Order events
    ORDER_SUBMITTED = auto()
    ORDER_FILLED = auto()
    ORDER_PARTIAL = auto()
    ORDER_CANCELLED = auto()
    ORDER_REJECTED = auto()

    # Position events
    POSITION_OPENED = auto()
    POSITION_UPDATED = auto()
    POSITION_CLOSED = auto()

    # Risk events
    RISK_ALERT = auto()
    DAILY_LIMIT_WARNING = auto()
    DAILY_LIMIT_HIT = auto()

    # System events
    SYSTEM_START = auto()
    SYSTEM_SHUTDOWN = auto()
    HEARTBEAT = auto()
    ERROR = auto()


@dataclass
class Event:
    """Event container"""
    type: EventType
    data: Any
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    correlation_id: Optional[str] = None

    def __repr__(self):
        return f"Event({self.type.name}, source={self.source})"


# Type alias for handlers
EventHandler = Callable[[Event], Any]


class EventBus:
    """
    Async event bus with pub/sub pattern.
    Supports both sync and async handlers.
    """

    def __init__(self):
        self._handlers: Dict[EventType, List[EventHandler]] = {}
        self._all_handlers: List[EventHandler] = []  # handlers for all events
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._processed_count = 0
        self._subscribers: Dict[EventType, Set[str]] = {}

    def subscribe(self, event_type: EventType, handler: EventHandler, name: str = "") -> None:
        """Subscribe handler to event type"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
            self._subscribers[event_type] = set()

        self._handlers[event_type].append(handler)
        if name:
            self._subscribers[event_type].add(name)
        logger.debug("handler_subscribed", event_type=event_type.name, handler=name or str(handler))

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe handler to all events"""
        self._all_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove handler from event type"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    async def publish(self, event: Event) -> None:
        """Publish event to queue"""
        await self._queue.put(event)

    def publish_sync(self, event: Event) -> None:
        """Publish event synchronously (for non-async contexts)"""
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self._queue.put_nowait, event)
        except RuntimeError:
            # No running loop, create task
            asyncio.create_task(self._queue.put(event))

    async def _process_event(self, event: Event) -> None:
        """Process single event through handlers"""
        handlers = self._handlers.get(event.type, []) + self._all_handlers

        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    "handler_error",
                    event_type=event.type.name,
                    error=str(e),
                    exc_info=True
                )

        self._processed_count += 1

    async def _run_loop(self) -> None:
        """Main event processing loop"""
        logger.info("event_bus_started")

        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._process_event(event)
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("event_loop_error", error=str(e))

        logger.info("event_bus_stopped", processed=self._processed_count)

    async def start(self) -> None:
        """Start the event bus"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        """Stop the event bus gracefully"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def wait_for_event(
        self,
        event_type: EventType,
        timeout: float = 30.0,
        predicate: Callable[[Event], bool] = None
    ) -> Optional[Event]:
        """
        Wait for specific event type, optionally with predicate filter.
        Useful for request-response patterns.
        """
        result_event: Optional[Event] = None
        event_received = asyncio.Event()

        def handler(event: Event):
            nonlocal result_event
            if predicate is None or predicate(event):
                result_event = event
                event_received.set()

        self.subscribe(event_type, handler)

        try:
            await asyncio.wait_for(event_received.wait(), timeout=timeout)
            return result_event
        except asyncio.TimeoutError:
            return None
        finally:
            self.unsubscribe(event_type, handler)

    @property
    def stats(self) -> Dict[str, Any]:
        """Get event bus statistics"""
        return {
            "running": self._running,
            "queue_size": self._queue.qsize(),
            "processed_count": self._processed_count,
            "subscribed_events": list(self._handlers.keys()),
            "handler_counts": {
                et.name: len(handlers) for et, handlers in self._handlers.items()
            }
        }


# Singleton instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


async def emit(event_type: EventType, data: Any, source: str = "", correlation_id: str = None) -> None:
    """Convenience function to emit events"""
    bus = get_event_bus()
    event = Event(
        type=event_type,
        data=data,
        source=source,
        correlation_id=correlation_id
    )
    await bus.publish(event)
