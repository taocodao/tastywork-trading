"""
Account Routes - Real Tastytrade Data
======================================
Fetches balance and positions from Tastytrade API.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
import logging

from ..services.tastytrade import TastytradeService, get_tastytrade_service

router = APIRouter()
logger = logging.getLogger(__name__)


class BalanceResponse(BaseModel):
    """Account balance response."""
    account_number: str
    cash_balance: float
    net_liquidating_value: float
    buying_power: float
    day_pnl: float
    day_pnl_percent: float


class PositionResponse(BaseModel):
    """Single position response."""
    symbol: str
    underlying: str
    instrument_type: str
    quantity: int
    entry_price: float
    current_price: float
    unrealized_pnl: float
    pnl_percent: float
    expiry: Optional[str] = None


class PositionsListResponse(BaseModel):
    """List of positions."""
    positions: List[PositionResponse]
    total_unrealized_pnl: float


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    service: TastytradeService = Depends(get_tastytrade_service)
):
    """
    Get account balance from Tastytrade.
    
    Returns cash balance, net liquidating value, buying power, and day P&L.
    """
    try:
        balance = await service.get_balance()
        return balance
    except Exception as e:
        logger.error(f"Failed to fetch balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions", response_model=PositionsListResponse)
async def get_positions(
    service: TastytradeService = Depends(get_tastytrade_service)
):
    """
    Get all open positions from Tastytrade.
    
    Returns list of positions with current P&L.
    """
    try:
        positions = await service.get_positions()
        total_pnl = sum(p.unrealized_pnl for p in positions)
        return PositionsListResponse(
            positions=positions,
            total_unrealized_pnl=total_pnl
        )
    except Exception as e:
        logger.error(f"Failed to fetch positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_trade_history(
    limit: int = 50,
    service: TastytradeService = Depends(get_tastytrade_service)
):
    """
    Get recent trade history from Tastytrade.
    """
    try:
        history = await service.get_trade_history(limit=limit)
        return {"trades": history}
    except Exception as e:
        logger.error(f"Failed to fetch trade history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
