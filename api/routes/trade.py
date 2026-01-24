"""
Trade Execution Routes
======================
Submit trades to Tastytrade API.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import logging

from ..services.tastytrade import TastytradeService, get_tastytrade_service

router = APIRouter()
logger = logging.getLogger(__name__)


class CalendarSpreadRequest(BaseModel):
    """Calendar spread trade request."""
    underlying: str
    strike: float
    front_expiry: str  # YYYY-MM-DD
    back_expiry: str   # YYYY-MM-DD
    quantity: int = 1
    order_type: str = "limit"  # limit/market
    limit_price: Optional[float] = None


class ClosePositionRequest(BaseModel):
    """Close position request."""
    position_id: str
    order_type: str = "market"
    limit_price: Optional[float] = None


class TradeResponse(BaseModel):
    """Trade execution response."""
    order_id: str
    status: str
    symbol: str
    message: str


class StopLossRequest(BaseModel):
    """Set stop-loss request."""
    position_id: str
    stop_price: float
    stop_percent: Optional[float] = None


@router.post("/calendar-spread", response_model=TradeResponse)
async def execute_calendar_spread(
    trade: CalendarSpreadRequest,
    service: TastytradeService = Depends(get_tastytrade_service)
):
    """
    Execute a calendar spread trade on Tastytrade.
    
    Buys the back-month option and sells the front-month option.
    """
    try:
        result = await service.place_calendar_spread(
            underlying=trade.underlying,
            strike=trade.strike,
            front_expiry=trade.front_expiry,
            back_expiry=trade.back_expiry,
            quantity=trade.quantity,
            order_type=trade.order_type,
            limit_price=trade.limit_price,
        )
        
        logger.info(f"Calendar spread placed: {result}")
        return TradeResponse(
            order_id=result["order_id"],
            status=result["status"],
            symbol=trade.underlying,
            message="Calendar spread order submitted"
        )
        
    except Exception as e:
        logger.error(f"Trade execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/close", response_model=TradeResponse)
async def close_position(
    request: ClosePositionRequest,
    service: TastytradeService = Depends(get_tastytrade_service)
):
    """
    Close an existing position.
    """
    try:
        result = await service.close_position(
            position_id=request.position_id,
            order_type=request.order_type,
            limit_price=request.limit_price,
        )
        
        logger.info(f"Position closed: {result}")
        return TradeResponse(
            order_id=result["order_id"],
            status=result["status"],
            symbol=result["symbol"],
            message="Position close order submitted"
        )
        
    except Exception as e:
        logger.error(f"Close position failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop-loss")
async def set_stop_loss(
    request: StopLossRequest,
    service: TastytradeService = Depends(get_tastytrade_service)
):
    """
    Set or update stop-loss for a position.
    """
    try:
        result = await service.set_stop_loss(
            position_id=request.position_id,
            stop_price=request.stop_price,
        )
        
        return {
            "status": "active",
            "position_id": request.position_id,
            "stop_price": request.stop_price,
            "message": "Stop-loss set"
        }
        
    except Exception as e:
        logger.error(f"Set stop-loss failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders")
async def get_pending_orders(
    service: TastytradeService = Depends(get_tastytrade_service)
):
    """Get all pending orders."""
    try:
        orders = await service.get_pending_orders()
        return {"orders": orders}
    except Exception as e:
        logger.error(f"Get orders failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
