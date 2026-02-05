"""
Orders router - View and manage orders.
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException

from src.execution.alpaca_broker import get_broker, OrderType as BrokerOrderType
from src.strategies.base import SignalDirection
from api.schemas.models import OrderRequest, OrderResponse, OrdersResponse

router = APIRouter()


@router.get("", response_model=OrdersResponse)
async def get_open_orders(symbol: Optional[str] = None):
    """Get all open orders, optionally filtered by symbol"""
    broker = get_broker()
    orders = await broker.get_open_orders(symbol.upper() if symbol else None)

    order_list = [
        OrderResponse(
            order_id=o['order_id'],
            client_order_id=o.get('client_order_id'),
            symbol=o['symbol'],
            qty=o['qty'],
            side=o['side'],
            type=o['type'],
            status=o['status'],
            limit_price=o.get('limit_price'),
            stop_price=o.get('stop_price'),
            filled_qty=o.get('filled_qty', 0),
            filled_avg_price=o.get('filled_avg_price'),
            created_at=o.get('created_at'),
            asset_class=o.get('asset_class', 'us_equity')
        )
        for o in orders
    ]

    return OrdersResponse(orders=order_list)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    """Get specific order by ID"""
    broker = get_broker()
    order = await broker.get_order(order_id)

    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

    return OrderResponse(
        order_id=order['order_id'],
        client_order_id=order.get('client_order_id'),
        symbol=order['symbol'],
        qty=order['qty'],
        side=order['side'],
        type=order['type'],
        status=order['status'],
        limit_price=order.get('limit_price'),
        stop_price=order.get('stop_price'),
        filled_qty=order.get('filled_qty', 0),
        filled_avg_price=order.get('filled_avg_price'),
        created_at=order.get('created_at'),
        asset_class=order.get('asset_class', 'us_equity')
    )


@router.post("", response_model=OrderResponse)
async def submit_order(order: OrderRequest):
    """Submit a new order"""
    broker = get_broker()

    # Map order type
    type_map = {
        'market': BrokerOrderType.MARKET,
        'limit': BrokerOrderType.LIMIT,
        'stop': BrokerOrderType.STOP,
        'stop_limit': BrokerOrderType.STOP_LIMIT
    }

    # Map side
    side = SignalDirection.LONG if order.side.value == 'buy' else SignalDirection.SHORT

    try:
        result = await broker.submit_order(
            symbol=order.symbol.upper(),
            qty=order.qty,
            side=side,
            order_type=type_map[order.order_type.value],
            limit_price=order.limit_price,
            stop_price=order.stop_price,
            time_in_force=order.time_in_force,
            extended_hours=order.extended_hours
        )

        return OrderResponse(
            order_id=result['order_id'],
            client_order_id=result.get('client_order_id'),
            symbol=result['symbol'],
            qty=result['qty'],
            side=result['side'],
            type=result['type'],
            status=result['status'],
            limit_price=result.get('limit_price'),
            stop_price=result.get('stop_price'),
            filled_qty=result.get('filled_qty', 0),
            filled_avg_price=result.get('filled_avg_price'),
            created_at=result.get('created_at'),
            asset_class=result.get('asset_class', 'us_equity')
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{order_id}")
async def cancel_order(order_id: str):
    """Cancel an open order"""
    broker = get_broker()
    success = await broker.cancel_order(order_id)

    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to cancel order {order_id}")

    return {"status": "cancelled", "order_id": order_id}


@router.delete("")
async def cancel_all_orders():
    """Cancel all open orders"""
    broker = get_broker()
    count = await broker.cancel_all_orders()

    return {"status": "cancelled_all", "orders_cancelled": count}
