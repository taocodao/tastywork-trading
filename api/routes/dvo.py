
"""
DVO API Routes
==============
Rest API for Deep Value Overlay strategy.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import logging

from models.db import get_db
from models.user import User
from models.valuation_signal import ValuationSignal
from models.dvo_position import DVOPosition

from src.dvo.gravity_engine import GravityEngine
from src.dvo.signal_generator import DVOSignalGenerator
from src.dvo.trade_constructor import TradeConstructor
from src.dvo.client import DVOClient
from src.dvo.risk_guardian import RiskGuardian, DVO_RISK_PROFILES
from signal_publisher.dvo import publish_dvo_entry_signal, DVOEntrySignal

router = APIRouter(prefix="/api/dvo", tags=["dvo"])
logger = logging.getLogger(__name__)

# --- Dependencies ---
# Assuming auth dependency to get current user
def get_current_user_stub():
    # Placeholder for real auth dependency
    return User(id=1, username="trademind_user") 

# --- Endpoints ---

@router.get("/valuations")
def get_valuations(symbol: Optional[str] = None, db: Session = Depends(get_db)):
    """Get latest valuation signals."""
    query = db.query(ValuationSignal)
    if symbol:
        query = query.filter(ValuationSignal.symbol == symbol)
    return query.order_by(ValuationSignal.analysis_date.desc()).limit(50).all()

@router.post("/scan")
def run_scan(symbols: List[str]):
    """Run on-demand Gravity Scan for list of symbols."""
    engine = GravityEngine()
    results = []
    for sym in symbols:
        res = engine.analyze(sym)
        if res:
            results.append(res)
    return results

@router.get("/candidates")
def get_candidates(risk_level: str = "MEDIUM"):
    """
    Generate DVO trade candidates based on current market data.
    """
    # Define universe (mock for now, or fetch from config)
    universe = ["SPY", "QQQ", "IWM", "META", "GOOGL", "AMZN", "MSFT", "NVDA", "TSM", "JPM"]
    
    gen = DVOSignalGenerator(risk_level)
    signals = gen.generate_signals(universe)
    return signals

@router.post("/order")
async def execute_order(signal: dict, dry_run: bool = True, user: User = Depends(get_current_user_stub)):
    """
    Execute a DVO order (Short Put or LEAPS).
    """
    try:
        # 1. Validate Risk
        guardian = RiskGuardian(risk_level="MEDIUM") # Should fetch user setting
        # ... checks ...
        
        # 2. Construct Ticket
        constructor = TradeConstructor(risk_level="MEDIUM")
        
        # 3. Execute via Client
        client = DVOClient(user_id=str(user.id))
        
        if signal.get('suggested_structure') == "PORTFOLIO_SECURED_PUT_ONLY":
            # Logic to find chain and fill details not in raw signal
            # For this endpoint, we assume 'signal' contains the specific trade details 
            # OR we re-run construction.
            # Ideally the frontend confirms the "Candidate" which lacks specific option details,
            # so we need to Constructor to "Find Best Put" now.
            
            chain = await client.fetch_option_chain(signal['symbol'])
            trade = constructor.find_short_put_candidate(
                chain, 
                signal['fair_value'], 
                signal['current_price']
            )
            
            if not trade:
                raise HTTPException(status_code=400, detail="No suitable option found")
                
            res = await client.execute_short_put(
                trade.symbol,
                trade.quantity,
                trade.expiration,
                trade.strike,
                trade.limit_price,
                dry_run=dry_run
            )
            
            # Publish Signal
            # ...
            
            return {"status": "success", "trade": trade, "execution": res}
            
        return {"status": "error", "message": "Structure not supported yet"}
        
    except Exception as e:
        logger.error(f"Order Execution Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/positions")
def get_positions(db: Session = Depends(get_db), user: User = Depends(get_current_user_stub)):
    """Get active DVO positions."""
    return db.query(DVOPosition).filter(DVOPosition.status == "OPEN").all()

@router.get("/risk")
def get_risk_metrics():
    """Get current portfolio risk metrics relevant to DVO."""
    # Mock data for now until linked to real portfolio
    return {
        "portfolio_leverage": 0.30,
        "dvo_allocation_pct": 0.15,
        "regime": "UPTREND",
        "kill_switch_active": False
    }
