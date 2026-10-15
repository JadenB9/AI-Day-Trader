"""
Order lifecycle management.
Tracks orders from signal to fill.
"""
from typing import Optional, Dict, List
from datetime import datetime
from dataclasses import dataclass
import structlog

from src.execution.alpaca_broker import get_broker, AlpacaBroker, OrderType
from src.strategies.base import Signal, SignalDirection
from src.risk.position_sizer import PositionSizer
from src.risk.stop_manager import get_stop_manager
from src.risk.validators import get_validator, PortfolioState
from src.core.event_bus import get_event_bus, EventType, Event

logger = structlog.get_logger()


@dataclass
class OrderContext:
    """Full context for an order"""
    signal: Signal
    order_id: str
    alpaca_order_id: str = ""
    symbol: str = ""
    side: SignalDirection = SignalDirection.LONG
    quantity: int = 0
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None

    status: str = "pending"
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    filled_qty: int = 0
    filled_price: float = 0.0

    stop_order_id: Optional[str] = None
    target_order_id: Optional[str] = None

    error_message: str = ""
    correlation_id: str = ""


class OrderManager:
    """
    Manages the full lifecycle of orders.
    From signal validation to execution and fill tracking.
    """

    def __init__(
        self,
        broker: AlpacaBroker = None,
        dry_run: bool = False
    ):
        self._broker = broker or get_broker()
        self._validator = get_validator()
        self._stop_manager = get_stop_manager()
        self._event_bus = get_event_bus()
        self._dry_run = dry_run

        # Active orders
        self._orders: Dict[str, OrderContext] = {}
        self._pending_stops: Dict[str, str] = {}  # symbol -> stop order id

        # Stats
        self._submitted_count = 0
        self._filled_count = 0
        self._rejected_count = 0

    async def execute_signal(
        self,
        signal: Signal,
        portfolio_state: PortfolioState,
        use_limit: bool = False,
        extended_hours: bool = False
    ) -> Optional[OrderContext]:
        """
        Execute a trading signal.

        Args:
            signal: Signal to execute
            portfolio_state: Current portfolio state
            use_limit: Use limit order instead of market
            extended_hours: Allow extended hours

        Returns:
            OrderContext if successful, None if rejected
        """
        # Validate signal
        validation = self._validator.validate(
            signal,
            current_price=signal.entry_price,
            spread=None  # Would get from snapshot
        )

        if not validation.approved:
            logger.warning(
                "signal_rejected",
                symbol=signal.symbol,
                reason=validation.rejection_reason.value if validation.rejection_reason else "unknown"
            )
            self._rejected_count += 1
            return None

        # Calculate position size
        sizer = PositionSizer(portfolio_state.equity)
        shares = sizer.calculate(
            entry_price=signal.entry_price,
            stop_price=signal.stop_loss
        )

        if shares <= 0:
            logger.warning("zero_shares", symbol=signal.symbol)
            return None

        # Create order context
        order_id = f"ord_{signal.symbol}_{datetime.now().strftime('%H%M%S')}"
        ctx = OrderContext(
            signal=signal,
            order_id=order_id,
            symbol=signal.symbol,
            side=signal.direction,
            quantity=shares,
            order_type=OrderType.LIMIT if use_limit else OrderType.MARKET,
            limit_price=signal.entry_price if use_limit else None,
            stop_price=signal.stop_loss,
            correlation_id=signal.correlation_id or ""
        )

        # Dry run mode
        if self._dry_run:
            ctx.status = "filled"
            ctx.filled_qty = shares
            ctx.filled_price = signal.entry_price
            ctx.filled_at = datetime.now()
            logger.info("dry_run_order", symbol=signal.symbol, shares=shares)
            return ctx

        try:
            # Submit entry order
            result = await self._broker.submit_order(
                symbol=signal.symbol,
                qty=shares,
                side=signal.direction,
                order_type=ctx.order_type,
                limit_price=ctx.limit_price,
                extended_hours=extended_hours,
                client_order_id=order_id
            )

            ctx.alpaca_order_id = result['order_id']
            ctx.status = result['status']
            ctx.submitted_at = datetime.now()

            # Store order
            self._orders[order_id] = ctx
            self._submitted_count += 1

            # Emit event
            await self._emit_order_event(EventType.ORDER_SUBMITTED, ctx)

            logger.info(
                "order_submitted",
                order_id=order_id,
                symbol=signal.symbol,
                shares=shares,
                direction=signal.direction.value
            )

            # Register stop with stop manager
            if signal.stop_loss:
                self._stop_manager.register_position(
                    symbol=signal.symbol,
                    entry_price=signal.entry_price,
                    direction=signal.direction,
                    stop_price=signal.stop_loss
                )

            return ctx

        except Exception as e:
            ctx.status = "error"
            ctx.error_message = str(e)
            logger.error(
                "order_submission_failed",
                symbol=signal.symbol,
                error=str(e)
            )
            return None

    async def check_order_status(self, order_id: str) -> Optional[OrderContext]:
        """Check and update order status"""
        if order_id not in self._orders:
            return None

        ctx = self._orders[order_id]

        if not ctx.alpaca_order_id:
            return ctx

        # Get status from broker
        order_info = await self._broker.get_order(ctx.alpaca_order_id)

        if order_info:
            old_status = ctx.status
            ctx.status = order_info['status']
            ctx.filled_qty = order_info.get('filled_qty', 0)
            ctx.filled_price = order_info.get('filled_avg_price', 0)

            if order_info.get('filled_at'):
                ctx.filled_at = order_info['filled_at']

            # Check for fill
            if ctx.status == 'filled' and old_status != 'filled':
                self._filled_count += 1
                await self._emit_order_event(EventType.ORDER_FILLED, ctx)
                logger.info(
                    "order_filled",
                    order_id=order_id,
                    symbol=ctx.symbol,
                    filled_qty=ctx.filled_qty,
                    filled_price=ctx.filled_price
                )

        return ctx

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if order_id not in self._orders:
            return False

        ctx = self._orders[order_id]

        if not ctx.alpaca_order_id:
            return False

        result = await self._broker.cancel_order(ctx.alpaca_order_id)

        if result:
            ctx.status = 'cancelled'
            await self._emit_order_event(EventType.ORDER_CANCELLED, ctx)

        return result

    async def close_position(self, symbol: str) -> Optional[Dict]:
        """Close entire position for symbol"""
        # Cancel any pending orders for this symbol
        for order_id, ctx in self._orders.items():
            if ctx.symbol == symbol and ctx.status in ['pending', 'submitted', 'accepted']:
                await self.cancel_order(order_id)

        # Remove stop tracking
        self._stop_manager.remove_position(symbol)

        # Close position
        return await self._broker.close_position(symbol)

    async def check_stops(self, symbol: str, current_price: float) -> bool:
        """
        Check if stop should trigger for a position.
        Returns True if stopped out.
        """
        # Check time stop
        if self._stop_manager.check_time_stop(symbol):
            logger.info("time_stop_triggered", symbol=symbol)
            await self.close_position(symbol)
            return True

        # Check price stop
        if self._stop_manager.should_stop_out(symbol, current_price):
            logger.info(
                "stop_triggered",
                symbol=symbol,
                price=current_price,
                stop=self._stop_manager.get_stop(symbol)
            )
            await self.close_position(symbol)
            return True

        # Update trailing stop
        self._stop_manager.update(symbol, current_price)

        return False

    async def _emit_order_event(self, event_type: EventType, ctx: OrderContext) -> None:
        """Emit order event"""
        await self._event_bus.publish(Event(
            type=event_type,
            data={
                'order_id': ctx.order_id,
                'alpaca_order_id': ctx.alpaca_order_id,
                'symbol': ctx.symbol,
                'side': ctx.side.value,
                'quantity': ctx.quantity,
                'status': ctx.status,
                'filled_qty': ctx.filled_qty,
                'filled_price': ctx.filled_price
            },
            source="order_manager",
            correlation_id=ctx.correlation_id
        ))

    def get_order(self, order_id: str) -> Optional[OrderContext]:
        """Get order by ID"""
        return self._orders.get(order_id)

    def get_orders_for_symbol(self, symbol: str) -> List[OrderContext]:
        """Get all orders for a symbol"""
        return [ctx for ctx in self._orders.values() if ctx.symbol == symbol]

    @property
    def active_orders(self) -> List[OrderContext]:
        """Get active (non-terminal) orders"""
        return [
            ctx for ctx in self._orders.values()
            if ctx.status in ['pending', 'submitted', 'accepted', 'partial_fill']
        ]

    @property
    def stats(self) -> Dict:
        """Get manager statistics"""
        return {
            'submitted': self._submitted_count,
            'filled': self._filled_count,
            'rejected': self._rejected_count,
            'active_orders': len(self.active_orders)
        }


# Singleton
_manager: Optional[OrderManager] = None


def get_order_manager(dry_run: bool = False) -> OrderManager:
    """Get or create order manager singleton"""
    global _manager
    if _manager is None:
        _manager = OrderManager(dry_run=dry_run)
    return _manager
