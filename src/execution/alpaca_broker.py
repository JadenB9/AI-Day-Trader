"""
Alpaca broker integration for order execution.
Uses alpaca-py SDK.
"""
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime
from enum import Enum
import structlog

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
    GetOrdersRequest
)
from alpaca.trading.enums import (
    OrderSide as AlpacaOrderSide,
    TimeInForce,
    OrderStatus as AlpacaOrderStatus,
    OrderType as AlpacaOrderType,
    QueryOrderStatus
)

from config.settings import get_settings
from src.core.exceptions import OrderError, OrderRejected, InsufficientFunds
from src.strategies.base import SignalDirection

logger = structlog.get_logger()
settings = get_settings()


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIAL = "partial_fill"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AlpacaBroker:
    """
    Alpaca trading client wrapper.
    Handles order submission, modification, and cancellation.
    """

    def __init__(self):
        self._client = TradingClient(
            api_key=settings.alpaca.api_key,
            secret_key=settings.alpaca.secret_key,
            paper=settings.alpaca.trading_mode.value == "paper"
        )

        self._order_count = 0
        self._fill_count = 0

    async def get_account(self) -> Dict[str, Any]:
        """Get account information"""
        loop = asyncio.get_event_loop()
        account = await loop.run_in_executor(
            None,
            self._client.get_account
        )

        return {
            'equity': float(account.equity),
            'cash': float(account.cash),
            'buying_power': float(account.buying_power),
            'portfolio_value': float(account.portfolio_value),
            'day_trade_count': account.daytrade_count,
            'pattern_day_trader': account.pattern_day_trader,
            'trading_blocked': account.trading_blocked,
            'account_blocked': account.account_blocked
        }

    async def get_positions(self) -> Dict[str, Dict]:
        """Get all open positions"""
        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(
            None,
            self._client.get_all_positions
        )

        result = {}
        for pos in positions:
            result[pos.symbol] = {
                'symbol': pos.symbol,
                'qty': int(pos.qty),
                'side': 'long' if int(pos.qty) > 0 else 'short',
                'avg_entry_price': float(pos.avg_entry_price),
                'market_value': float(pos.market_value),
                'current_price': float(pos.current_price),
                'unrealized_pl': float(pos.unrealized_pl),
                'unrealized_plpc': float(pos.unrealized_plpc),
                'change_today': float(pos.change_today) if pos.change_today else 0
            }

        return result

    async def get_position(self, symbol: str) -> Optional[Dict]:
        """Get specific position"""
        try:
            loop = asyncio.get_event_loop()
            pos = await loop.run_in_executor(
                None,
                lambda: self._client.get_open_position(symbol)
            )

            return {
                'symbol': pos.symbol,
                'qty': int(pos.qty),
                'side': 'long' if int(pos.qty) > 0 else 'short',
                'avg_entry_price': float(pos.avg_entry_price),
                'market_value': float(pos.market_value),
                'current_price': float(pos.current_price),
                'unrealized_pl': float(pos.unrealized_pl),
                'unrealized_plpc': float(pos.unrealized_plpc)
            }
        except Exception:
            return None

    async def submit_order(
        self,
        symbol: str,
        qty: int,
        side: SignalDirection,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float = None,
        stop_price: float = None,
        time_in_force: str = "day",
        extended_hours: bool = False,
        client_order_id: str = None
    ) -> Dict[str, Any]:
        """
        Submit a new order.

        Args:
            symbol: Stock symbol
            qty: Number of shares
            side: LONG (buy) or SHORT (sell)
            order_type: Market, limit, stop, stop_limit
            limit_price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)
            time_in_force: day, gtc, ioc, fok
            extended_hours: Allow extended hours trading
            client_order_id: Custom order ID

        Returns:
            Order details dict
        """
        alpaca_side = AlpacaOrderSide.BUY if side == SignalDirection.LONG else AlpacaOrderSide.SELL

        # Time in force mapping
        tif_map = {
            'day': TimeInForce.DAY,
            'gtc': TimeInForce.GTC,
            'ioc': TimeInForce.IOC,
            'fok': TimeInForce.FOK
        }
        tif = tif_map.get(time_in_force.lower(), TimeInForce.DAY)

        try:
            # Build order request based on type
            if order_type == OrderType.MARKET:
                request = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=tif,
                    extended_hours=extended_hours,
                    client_order_id=client_order_id
                )
            elif order_type == OrderType.LIMIT:
                if limit_price is None:
                    raise OrderError("Limit price required for limit orders")
                request = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=tif,
                    limit_price=limit_price,
                    extended_hours=extended_hours,
                    client_order_id=client_order_id
                )
            elif order_type == OrderType.STOP:
                if stop_price is None:
                    raise OrderError("Stop price required for stop orders")
                request = StopOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=tif,
                    stop_price=stop_price,
                    extended_hours=extended_hours,
                    client_order_id=client_order_id
                )
            elif order_type == OrderType.STOP_LIMIT:
                if stop_price is None or limit_price is None:
                    raise OrderError("Stop and limit prices required")
                request = StopLimitOrderRequest(
                    symbol=symbol,
                    qty=qty,
                    side=alpaca_side,
                    time_in_force=tif,
                    stop_price=stop_price,
                    limit_price=limit_price,
                    extended_hours=extended_hours,
                    client_order_id=client_order_id
                )
            else:
                raise OrderError(f"Unknown order type: {order_type}")

            # Submit order
            loop = asyncio.get_event_loop()
            order = await loop.run_in_executor(
                None,
                lambda: self._client.submit_order(request)
            )

            self._order_count += 1

            result = {
                'order_id': order.id,
                'client_order_id': order.client_order_id,
                'symbol': order.symbol,
                'qty': int(order.qty),
                'side': side.value,
                'type': order_type.value,
                'status': self._map_status(order.status),
                'limit_price': float(order.limit_price) if order.limit_price else None,
                'stop_price': float(order.stop_price) if order.stop_price else None,
                'filled_qty': int(order.filled_qty) if order.filled_qty else 0,
                'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
                'created_at': order.created_at,
                'extended_hours': order.extended_hours
            }

            logger.info(
                "order_submitted",
                order_id=order.id,
                symbol=symbol,
                side=side.value,
                qty=qty,
                type=order_type.value
            )

            return result

        except Exception as e:
            error_msg = str(e)

            if "insufficient" in error_msg.lower():
                raise InsufficientFunds(error_msg)
            elif "rejected" in error_msg.lower():
                raise OrderRejected(error_msg)
            else:
                raise OrderError(f"Order failed: {error_msg}")

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._client.cancel_order_by_id(order_id)
            )
            logger.info("order_cancelled", order_id=order_id)
            return True
        except Exception as e:
            logger.error("cancel_failed", order_id=order_id, error=str(e))
            return False

    async def cancel_all_orders(self) -> int:
        """Cancel all open orders"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._client.cancel_orders
        )
        count = len(result) if result else 0
        logger.info("all_orders_cancelled", count=count)
        return count

    async def get_order(self, order_id: str) -> Optional[Dict]:
        """Get order by ID"""
        try:
            loop = asyncio.get_event_loop()
            order = await loop.run_in_executor(
                None,
                lambda: self._client.get_order_by_id(order_id)
            )

            return {
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': int(order.qty),
                'side': 'buy' if order.side == AlpacaOrderSide.BUY else 'sell',
                'type': order.order_type.value,
                'status': self._map_status(order.status),
                'filled_qty': int(order.filled_qty) if order.filled_qty else 0,
                'filled_avg_price': float(order.filled_avg_price) if order.filled_avg_price else None,
                'created_at': order.created_at,
                'filled_at': order.filled_at
            }
        except Exception:
            return None

    async def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """Get open orders, optionally filtered by symbol"""
        request = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[symbol] if symbol else None
        )

        loop = asyncio.get_event_loop()
        orders = await loop.run_in_executor(
            None,
            lambda: self._client.get_orders(request)
        )

        return [
            {
                'order_id': o.id,
                'symbol': o.symbol,
                'qty': int(o.qty),
                'side': 'buy' if o.side == AlpacaOrderSide.BUY else 'sell',
                'type': o.order_type.value,
                'status': self._map_status(o.status),
                'limit_price': float(o.limit_price) if o.limit_price else None,
                'stop_price': float(o.stop_price) if o.stop_price else None
            }
            for o in orders
        ]

    async def close_position(self, symbol: str) -> Optional[Dict]:
        """Close entire position for symbol"""
        try:
            loop = asyncio.get_event_loop()
            order = await loop.run_in_executor(
                None,
                lambda: self._client.close_position(symbol)
            )

            logger.info("position_closed", symbol=symbol)
            return {
                'order_id': order.id,
                'symbol': symbol,
                'qty': int(order.qty),
                'status': self._map_status(order.status)
            }
        except Exception as e:
            logger.error("close_position_failed", symbol=symbol, error=str(e))
            return None

    async def close_all_positions(self) -> int:
        """Close all positions"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._client.close_all_positions
        )
        count = len(result) if result else 0
        logger.info("all_positions_closed", count=count)
        return count

    def _map_status(self, alpaca_status: AlpacaOrderStatus) -> str:
        """Map Alpaca status to our status"""
        status_map = {
            AlpacaOrderStatus.NEW: OrderStatus.SUBMITTED.value,
            AlpacaOrderStatus.ACCEPTED: OrderStatus.ACCEPTED.value,
            AlpacaOrderStatus.PENDING_NEW: OrderStatus.PENDING.value,
            AlpacaOrderStatus.FILLED: OrderStatus.FILLED.value,
            AlpacaOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIAL.value,
            AlpacaOrderStatus.CANCELED: OrderStatus.CANCELLED.value,
            AlpacaOrderStatus.REJECTED: OrderStatus.REJECTED.value,
            AlpacaOrderStatus.EXPIRED: OrderStatus.EXPIRED.value
        }
        return status_map.get(alpaca_status, alpaca_status.value)

    @property
    def stats(self) -> Dict:
        """Get broker statistics"""
        return {
            'orders_submitted': self._order_count,
            'orders_filled': self._fill_count
        }


# Singleton
_broker: Optional[AlpacaBroker] = None


def get_broker() -> AlpacaBroker:
    """Get or create broker singleton"""
    global _broker
    if _broker is None:
        _broker = AlpacaBroker()
    return _broker
