"""
Positions router - View and manage trading positions.
"""
from fastapi import APIRouter, HTTPException

from src.execution.alpaca_broker import get_broker
from api.schemas.models import PositionResponse, PositionsResponse

router = APIRouter()


@router.get("", response_model=PositionsResponse)
async def get_all_positions():
    """Get all open positions"""
    broker = get_broker()
    positions = await broker.get_positions()

    pos_list = []
    total_value = 0
    total_pl = 0

    for symbol, pos in positions.items():
        pos_list.append(PositionResponse(
            symbol=pos['symbol'],
            qty=pos['qty'],
            side=pos['side'],
            avg_entry_price=pos['avg_entry_price'],
            market_value=pos['market_value'],
            current_price=pos['current_price'],
            unrealized_pl=pos['unrealized_pl'],
            unrealized_plpc=pos['unrealized_plpc'],
            change_today=pos.get('change_today', 0),
            asset_class=pos.get('asset_class', 'us_equity')
        ))
        total_value += pos['market_value']
        total_pl += pos['unrealized_pl']

    return PositionsResponse(
        positions=pos_list,
        total_value=total_value,
        total_unrealized_pl=total_pl
    )


@router.get("/{symbol}", response_model=PositionResponse)
async def get_position(symbol: str):
    """Get position for specific symbol"""
    broker = get_broker()
    pos = await broker.get_position(symbol.upper())

    if not pos:
        raise HTTPException(status_code=404, detail=f"No position for {symbol}")

    return PositionResponse(
        symbol=pos['symbol'],
        qty=pos['qty'],
        side=pos['side'],
        avg_entry_price=pos['avg_entry_price'],
        market_value=pos['market_value'],
        current_price=pos['current_price'],
        unrealized_pl=pos['unrealized_pl'],
        unrealized_plpc=pos['unrealized_plpc'],
        asset_class=pos.get('asset_class', 'us_equity')
    )


@router.delete("/{symbol}")
async def close_position(symbol: str):
    """Close position for specific symbol"""
    broker = get_broker()
    result = await broker.close_position(symbol.upper())

    if not result:
        raise HTTPException(status_code=400, detail=f"Failed to close position for {symbol}")

    return {
        "status": "closing",
        "symbol": symbol,
        "order_id": result.get('order_id')
    }


@router.delete("")
async def close_all_positions():
    """Close all positions (panic button)"""
    broker = get_broker()
    count = await broker.close_all_positions()

    return {
        "status": "closing_all",
        "positions_closed": count
    }


@router.get("/history/equity")
async def get_equity_history(period: str = "1D", timeframe: str = "5Min"):
    """
    Get real portfolio equity history from Alpaca.

    Args:
        period: 1D, 1W, 1M, 3M, 1A, all
        timeframe: 1Min, 5Min, 15Min, 1H, 1D
    """
    broker = get_broker()

    try:
        history = await broker.get_portfolio_history(period=period, timeframe=timeframe)

        if not history:
            return {"data": [], "message": "No trading history yet"}

        return {
            "data": history,
            "period": period,
            "timeframe": timeframe
        }
    except Exception as e:
        return {"data": [], "error": str(e)}
