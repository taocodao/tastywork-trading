"""
TurboBounce Options: Signal Publisher
=====================================
Unified signal publishing for the TurboBounce Multi-Ticker Strategy.
Formats scanner/router outputs, saves to PostgreSQL, and broadcasts via WebSocket.
"""

import uuid
import logging
import os
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from signal_publisher.base import BaseSignal
from signal_publisher.websocket_client import broadcast_to_channel

logger = logging.getLogger(__name__)

@dataclass
class TurboBounceEntrySignal(BaseSignal):
    """Signal for opening a TurboBounce multi-ticker trade."""
    
    # Core fields defined in BaseSignal:
    # id, symbol, strategy, status, created_at, expires_at, metadata
    
    # TurboBounce specific fields
    type: str = ""
    strategy_name: str = "TurboBounce Multi-Ticker"
    pool: str = "MULTI_TICKER"
    direction: str = ""
    scanner_rank: int = 0
    total_score: float = 0.0
    confidence: float = 0.0  # 0-100 quality score; maps from total_score
    rsi_2: float = 0.0
    iv_rank: float = 0.0
    category: str = ""
    rationale: str = ""
    
    # Trade parameters for execution engine
    target_anchor_dte: Optional[int] = None
    target_hedge_dte: Optional[int] = None
    target_delta: Optional[float] = None
    cost: float = 1.0  # Estimated debit/credit per spread
    capital_required: float = 500.0  # Estimated capital block per contract

    # Actual executable Option Legs derived from StrategyBuilder
    legs: Optional[List[Dict[str, Any]]] = None
    frontExpiry: Optional[str] = None
    backExpiry: Optional[str] = None
    strike: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/DB serialization. Matches prior schema."""
        base = super().to_dict()
        
        # Merge the structural fields
        base.update({
            "timestamp": base.get("created_at"), # Frontend backward compatibility
            "type": self.type,
            "strategy_name": self.strategy_name,
            "pool": self.pool,
            "direction": self.direction,
            "scanner_rank": self.scanner_rank,
            "total_score": self.total_score,
            # Confidence aliases — all three needed for frontend normalizeSignal() compat
            "confidence": self.confidence,
            "win_rate": self.confidence,
            "winRate": self.confidence,
            "rsi_2": self.rsi_2,
            "iv_rank": self.iv_rank,
            "category": self.category,
            "rationale": self.rationale,
            "target_anchor_dte": self.target_anchor_dte,
            "target_hedge_dte": self.target_hedge_dte,
            "target_delta": self.target_delta,
            "cost": self.cost,
            "capital_required": self.capital_required,
            "capitalRequired": self.capital_required,  # Frontend camelCase compat
            "legs": self.legs,
            "frontExpiry": self.frontExpiry,
            "backExpiry": self.backExpiry,
            "strike": self.strike,
        })
        return base


def _next_market_open() -> datetime:
    """Calculate next market open (9:30 AM ET on next trading day)."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    now_et = datetime.now(et)
    
    # Next market open = 9:30 AM ET on the next trading day
    tomorrow = now_et + timedelta(days=1)
    target = tomorrow.replace(hour=9, minute=30, second=0, microsecond=0)
    
    # Skip weekends (Sat=5, Sun=6)
    while target.weekday() >= 5:
        target += timedelta(days=1)
    
    # Return as naive UTC for DB storage
    return target.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def publish_turbobounce_entry_signal(
    symbol: str,
    action_type: str,
    direction: str,
    scanner_rank: int,
    total_score: float,
    rsi_2: float,
    iv_rank: float,
    category: str,
    rationale: str,
    target_anchor_dte: Optional[int],
    target_hedge_dte: Optional[int],
    target_delta: Optional[float],
    leg_data: Optional[Dict[str, Any]] = None
) -> "TurboBounceEntrySignal":
    """
    Creates the TurboBounce signal, saves to DB, broadcasts via WebSocket, 
    and appends to legacy JSON file.
    """
    # Expire at next market open (9:30 AM ET next trading day)
    expires = _next_market_open()
    
    sig = TurboBounceEntrySignal(
        id=str(uuid.uuid4()),
        symbol=symbol,
        strategy="turbobounce",
        status="pending",  # Normalizing to lowercase
        created_at=datetime.utcnow(),
        expires_at=expires,
        type=action_type,
        direction=direction,
        scanner_rank=scanner_rank,
        total_score=total_score,
        confidence=round(total_score, 1),  # Map total_score → confidence for frontend auto-approve
        rsi_2=rsi_2,
        iv_rank=iv_rank,
        category=category,
        rationale=rationale,
        target_anchor_dte=target_anchor_dte,
        target_hedge_dte=target_hedge_dte,
        target_delta=target_delta,
        cost=1.50 if action_type == 'DIAGONAL' else 1.0,  # Realistic defaults
        capital_required=1000.0 if action_type == 'DIAGONAL' else 500.0,
    )
    
    if leg_data:
        sig.legs = leg_data.get("legs")
        sig.cost = round(leg_data.get("cost", sig.cost), 2)
        sig.frontExpiry = leg_data.get("frontExpiry")
        sig.backExpiry = leg_data.get("backExpiry")
        sig.strike = leg_data.get("strike")
    
    data = sig.to_dict()
    
    # 1. Save to Database
    try:
        from src.earnings_intelligence.database import SignalRepository
        repo = SignalRepository()
        try:
            repo.save_signal(data)
            logger.info(f"DB Save success: TurboBounce {symbol} ({action_type})")
        finally:
            repo.session.close()  # CRITICAL: return connection to pool
    except Exception as e:
        logger.error(f"DB Save failed for {symbol}: {e}")

    # 2. Auto-approve if criteria met
    try:
        from auto_approve import auto_approve_signal
        result = auto_approve_signal(data)
        if result:
            logger.info(f"🤖 Auto-approved TurboBounce signal: {symbol} → Order {result.get('order_id')}")
            # Update status to executed
            data['status'] = 'executed'
            data['autoApproved'] = True
            data['orderId'] = result.get('order_id')
            try:
                from src.earnings_intelligence.database import SignalRepository
                repo2 = SignalRepository()
                try:
                    repo2.save_signal(data)
                finally:
                    repo2.session.close()
            except Exception:
                pass
    except Exception as auto_err:
        logger.debug(f"Auto-approve skipped for {symbol}: {auto_err}")

    return sig
