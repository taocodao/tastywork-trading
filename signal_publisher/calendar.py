"""
Calendar Spread Signals
========================
Signal publishing for calendar spread strategy.

Channels:
- calendar_spread: All calendar spread signals
- calendar_entry: Entry signals
"""

import uuid
import logging
from typing import Dict, Any
from datetime import datetime, timedelta

from .websocket_client import broadcast_to_channel

logger = logging.getLogger(__name__)

# In-memory signal storage (for backward compatibility)
_pending_signals = []


def spread_setup_to_signal(setup) -> Dict[str, Any]:
    """
    Convert a SpreadSetup to frontend Signal format.
    
    Args:
        setup: SpreadSetup object from scanner
        
    Returns:
        Dictionary with signal data
    """
    # Calculate potential return (35% target)
    cost = setup.net_debit
    potential_return = round(cost * 0.35, 2)
    
    # Calculate win rate based on score (simplified)
    base_win_rate = 70
    score_bonus = min(setup.score / 10, 10)  # Max 10% bonus
    win_rate = int(base_win_rate + score_bonus)
    
    # Determine risk level based on IV and cost
    if setup.iv < 0.20 and cost < 300:
        risk_level = "Low"
    elif setup.iv > 0.35 or cost > 500:
        risk_level = "High"
    else:
        risk_level = "Medium"
    
    now = datetime.now()
    
    # Calculate expiration: earlier of (front_expiry - 1 day) or (now + 24 hours)
    front_expiry_dt = datetime.combine(setup.short_expiry, datetime.min.time())
    expiry_based = front_expiry_dt - timedelta(days=1)
    staleness_based = now + timedelta(hours=24)
    expires_at = min(expiry_based, staleness_based)
    
    signal = {
        "id": str(uuid.uuid4()),
        "symbol": setup.symbol,
        "strategy": "Calendar Spread",
        "direction": "neutral",
        "strike": setup.strike,
        "stockPrice": setup.stock_price,
        "frontExpiry": setup.short_expiry.isoformat(),
        "backExpiry": setup.long_expiry.isoformat(),
        "cost": round(cost, 2),
        "potentialReturn": potential_return,
        "returnPercent": round((potential_return / cost) * 100, 1) if cost > 0 else 0,
        "winRate": win_rate,
        "riskLevel": risk_level,
        "status": "pending",
        "createdAt": now.isoformat(),
        "expiresAt": expires_at.isoformat(),
        "score": round(setup.score, 2),
        "iv": round(setup.iv * 100, 1),  # Convert to percentage
        "thetaEdge": round(setup.theta_edge, 2) if hasattr(setup, 'theta_edge') else 0,
        "rationale": f"Theta edge ${setup.theta_edge:.2f}/day, IV {setup.iv*100:.0f}%, Score {setup.score:.1f}",
    }
    
    return signal


def publish_calendar_signal(setup, channel: str = "calendar_spread") -> bool:
    """
    Publish a calendar/diagonal spread signal to WebSocket channels AND save to database.
    
    Args:
        setup: SpreadSetup object from scanner
        channel: WebSocket channel to broadcast on
        
    Returns:
        True if broadcast succeeded
    """
    try:
        signal = spread_setup_to_signal(setup)
        
        # Add to pending signals for backward compatibility
        _pending_signals.append(signal)
        
        # SAVE TO DATABASE (so /api/signals endpoint returns it)
        try:
            from src.earnings_intelligence.database import SignalRepository
            repo = SignalRepository()
            repo.save_signal(signal)
            logger.info(f"💾 Saved signal to database: {signal['symbol']}")
        except Exception as db_err:
            logger.warning(f"⚠️ Could not save to database: {db_err}")
        
        # Broadcast to WebSocket channel
        success = broadcast_to_channel(channel, {"signal": signal})
        
        if success:
            logger.info(f"📡 Published calendar spread: {signal['symbol']} @ ${signal['strike']}")
        
        return success
        
    except Exception as e:
        logger.error(f"Failed to publish calendar signal: {e}")
        return False


def get_pending_signals() -> list:
    """Get list of pending signals (for backward compatibility with API)."""
    return _pending_signals.copy()


def clear_pending_signals():
    """Clear pending signals list."""
    global _pending_signals
    _pending_signals = []
