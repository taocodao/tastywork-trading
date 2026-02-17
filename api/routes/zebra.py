from fastapi import APIRouter, HTTPException, Depends, Body
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import logging

from models.db import get_db
from models.user import User
from models.zebra_position import ZebraPosition
from sqlalchemy.orm import Session

from src.zebra.client import ZebraClient
from src.zebra.construction_engine import ZebraConstructionEngine
from src.zebra.position_monitor import ZebraPositionMonitor
from src.earnings_intelligence.database import SignalRepository
from tastytrade_utils import create_user_session, get_user_account

router = APIRouter()
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# CANDIDATES & CONSTRUCTION
# ----------------------------------------------------------------------------

@router.get("/candidates")
async def get_zebra_candidates():
    """Get pending ZEBRA strategy signals."""
    try:
        repo = SignalRepository()
        all_signals = repo.get_all_signals()
        
        # Filter for ZEBRA strategy and pending status
        # Note: repo.get_all_signals returns Signal objects, need to check attributes
        zebra_signals = [
            s.to_dict() for s in all_signals 
            if s.strategy.lower() == 'zebra' and s.status == 'pending'
        ]
        
        return {
            "candidates": zebra_signals,
            "total": len(zebra_signals),
            "source": "database"
        }
    except Exception as e:
        logger.error(f"Error fetching ZEBRA candidates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/construct")
async def construct_zebra_structure(
    symbol: str = Body(..., embed=True),
    direction: str = Body("LONG", embed=True),
    horizon: int = Body(30, embed=True)
):
    """Construct ZEBRA trade structures for a given symbol."""
    try:
        # We need a session for market data. 
        # For public construction, we can use a system session or user session.
        # Here we'll try to use system session (env vars) via ZebraClient default init
        # OR better, if we have a user token, use that.
        # For now, let's assume system session for general construction.
        
        client = ZebraClient() # Uses env vars
        
        price = client.get_stock_price(symbol)
        if price <= 0:
            raise HTTPException(status_code=404, detail=f"Could not fetch price for {symbol}")
            
        engine = ZebraConstructionEngine(client)
        
        structures = engine.construct(
            symbol=symbol,
            stock_price=price,
            thesis_horizon_days=horizon,
            direction=direction
        )
        
        serialized = []
        for s in structures:
            serialized.append({
                'symbol': s.symbol,
                'direction': s.direction,
                'expiry': s.expiry.isoformat(),
                'dte': s.dte,
                'net_debit': float(s.net_debit),
                'max_loss': float(s.max_loss),
                'breakeven': float(s.breakeven),
                'net_delta': float(s.net_delta),
                'net_theta': float(s.net_theta),
                'net_eval': float(s.net_extrinsic),
                'construction_score': float(s.construction_score),
                'legs': [
                    {
                        'side': 'md_long',
                        'strike': float(s.long_leg.strike),
                        'option_type': s.long_leg.option_type,
                        'quantity': 2,
                        'delta': float(s.long_leg.delta or 0)
                    },
                    {
                        'side': 'md_short',
                        'strike': float(s.short_leg.strike),
                        'option_type': s.short_leg.option_type,
                        'quantity': 1,
                        'delta': float(s.short_leg.delta or 0)
                    }
                ]
            })
            
        return {
            "symbol": symbol,
            "price": price,
            "count": len(serialized),
            "structures": serialized
        }
        
    except Exception as e:
        logger.error(f"Error constructing ZEBRA: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------------------------------------------------------------
# ORDER EXECUTION
# ----------------------------------------------------------------------------

@router.post("/order")
async def execute_zebra_order(
    payload: Dict[str, Any] = Body(...)
):
    """
    Execute a ZEBRA trade.
    Expects payload: {
        refreshToken, accountNumber, 
        symbol, longStrike, shortStrike, expiry, 
        direction, quantity, limitPrice
    }
    """
    try:
        user_refresh_token = payload.get('refreshToken')
        account_number = payload.get('accountNumber')
        
        if not user_refresh_token:
            raise HTTPException(status_code=401, detail="Missing user credentials")
            
        symbol = payload.get('symbol')
        long_strike = float(payload.get('longStrike', 0))
        short_strike = float(payload.get('shortStrike', 0))
        expiry_str = payload.get('expiry')
        direction = payload.get('direction', 'LONG')
        quantity = int(payload.get('quantity', 1))
        limit_price = payload.get('limitPrice')
        if limit_price:
            limit_price = float(limit_price)
            
        if not (symbol and long_strike and short_strike and expiry_str):
            raise HTTPException(status_code=400, detail="Missing trade parameters")
            
        expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        
        # Create session for user
        try:
            user_session = create_user_session(user_refresh_token)
            account = get_user_account(user_session, account_number)
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")
            
        # Execute
        client = ZebraClient()
        client._session = user_session
        client._account = account
        
        logger.info(f"Executing ZEBRA {symbol} {direction} for account {account.account_number}")
        
        order_response = client.execute_zebra_entry(
            symbol=symbol,
            long_strike=long_strike,
            short_strike=short_strike,
            expiry=expiry,
            direction=direction,
            quantity=quantity,
            limit_price=limit_price,
            dry_run=False
        )
        
        order_id = None
        if hasattr(order_response, 'id'):
            order_id = str(order_response.id)
        elif isinstance(order_response, dict) and 'id' in order_response:
            order_id = str(order_response['id'])
            
        return {
            "status": "submitted",
            "symbol": symbol,
            "order_id": order_id,
            "message": "ZEBRA order submitted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ZEBRA execution error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# ----------------------------------------------------------------------------
# POSITIONS
# ----------------------------------------------------------------------------

@router.get("/positions")
async def get_zebra_positions(
    db: Session = Depends(get_db)  # Only needed if we query DB for all positions
):
    """
    Get monitored ZEBRA positions.
    For now, return all tracked positions from the database.
    In future, we might filter by user_id if authentication is strictly enforced here.
    """
    try:
        positions = db.query(ZebraPosition).filter(ZebraPosition.status == 'OPEN').all()
        
        results = []
        for pos in positions:
            # We can also fetch live updates if we want, but for speed just return DB state
            # The background monitor updates the DB state.
            
            results.append({
                "id": pos.id,
                "user_id": pos.user_id,
                "symbol": pos.symbol,
                "direction": pos.direction,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": pos.unrealized_pnl,
                "unrealized_pnl_pct": pos.unrealized_pnl_pct,
                "days_held": (datetime.utcnow() - pos.entry_date).days if pos.entry_date else 0,
                "entry_date": pos.entry_date.isoformat() if pos.entry_date else None,
                "expiry": pos.expiry.isoformat() if pos.expiry else None,
                "status": pos.status
            })
            
        return {"positions": results}
        
    except Exception as e:
        logger.error(f"Error fetching ZEBRA positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
