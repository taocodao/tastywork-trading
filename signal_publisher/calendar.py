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
        risk_level = "low"
    elif setup.iv > 0.35 or cost > 500:
        risk_level = "high"
    else:
        risk_level = "medium"
    
    now = datetime.now()
    
    # Calculate expiration: Market close today (16:00 ET)
    try:
        import pytz
        ny_tz = pytz.timezone('US/Eastern')
        now_ny = datetime.now(ny_tz)
        
        # Market close is 16:00 ET
        market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        
        # Convert to UTC naive for DB consistency with datetime.utcnow()
        expires_at = market_close.astimezone(pytz.UTC).replace(tzinfo=None)
    except Exception:
        # Fallback if pytz not available or error
        expires_at = datetime.utcnow().replace(hour=20, minute=0, second=0, microsecond=0)
    
    # Frontend expects snake_case keys fitting DiagonalSignal interface
    signal = {
        "id": str(uuid.uuid4()),
        "symbol": setup.symbol,
        "strategy": "calendar",  # Lowercase for interface matching
        "direction": "neutral",
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        
        # Core Params
        "short_strike": setup.strike,
        "short_expiry": setup.short_expiry.isoformat(),
        "long_strike": setup.strike,
        "long_expiry": setup.long_expiry.isoformat(),
        
        # Pricing & Metrics
        "capital_required": round(cost, 2),
        "expected_return": potential_return,
        "return_percent": round((potential_return / cost) * 100, 1) if cost > 0 else 0,
        "confidence": win_rate,
        "risk_level": risk_level,
        "score": round(setup.score, 2),
        "iv": round(setup.iv * 100, 1),
        "theta_edge": round(setup.theta_edge, 2) if hasattr(setup, 'theta_edge') else 0,
        
        # Aliases / Legacy (for components using old keys)
        "strike": setup.strike,
        "frontExpiry": setup.short_expiry.isoformat(),
        "backExpiry": setup.long_expiry.isoformat(),
        "cost": round(cost, 2),
        "potentialReturn": potential_return,
        "returnPercent": round((potential_return / cost) * 100, 1) if cost > 0 else 0,
        "riskLevel": risk_level.capitalize(),
        "winRate": win_rate,
        "createdAt": now.isoformat(),
        "expiresAt": expires_at,
        "rationale": f"Theta edge ${setup.theta_edge:.2f}/day, IV {setup.iv*100:.0f}%, Score {setup.score:.1f}",
        
        "contracts": 1, # Default
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
        
        # AUTO-APPROVE: Check if signal should be automatically executed
        try:
            from auto_approve import auto_approve_signal
            result = auto_approve_signal(signal)
            if result:
                logger.info(f"🤖 Auto-approved calendar signal: {signal['symbol']} → Order {result.get('orderId')}")
                signal['status'] = 'executed'
                signal['autoApproved'] = True
                signal['orderId'] = result.get('orderId')
                # Update DB status
                try:
                    repo = SignalRepository()
                    repo.save_signal(signal)
                except Exception:
                    pass
        except Exception as auto_err:
            logger.debug(f"Auto-approve skipped for {signal['symbol']}: {auto_err}")
        
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
