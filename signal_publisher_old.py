"""
Signal Publisher
=================
Converts scanner SpreadSetup objects to frontend Signal format
and publishes to WebSocket server for real-time delivery.
"""

import uuid
import requests
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import asdict

# Import scanner types
try:
    from scanner import SpreadSetup
except ImportError:
    SpreadSetup = None

logger = logging.getLogger(__name__)

# Add current directory to path to allow 'src' imports
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# WebSocket HTTP broadcast endpoint
WEBSOCKET_BROADCAST_URL = "http://localhost:8004/"

# In-memory signal storage (pending signals for API)
_pending_signals: List[Dict[str, Any]] = []


def spread_setup_to_signal(setup) -> Dict[str, Any]:
    """Convert a SpreadSetup to frontend Signal format."""
    from datetime import timedelta
    
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


def publish_signal(setup, channel: str = "calendar_spread") -> bool:
    """
    Publish a signal to the WebSocket server for broadcast.
    
    Args:
        setup: SpreadSetup object from scanner
        channel: WebSocket channel to broadcast on
        
    Returns:
        True if broadcast succeeded
    """
    try:
        signal = spread_setup_to_signal(setup)
        
        # Add to pending signals for API
        _pending_signals.append(signal)
        
        # Broadcast via WebSocket HTTP endpoint
        response = requests.post(
            WEBSOCKET_BROADCAST_URL,
            json={"channel": channel, "signal": signal},
            timeout=5
        )
        
        if response.ok:
            logger.info(f"📡 Published signal: {signal['symbol']} @ ${signal['strike']}")
            return True
        else:
            logger.warning(f"Broadcast failed: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.warning("WebSocket server not running, signal queued locally only")
        return False
    except Exception as e:
        logger.error(f"Failed to publish signal: {e}")
        return False
    finally:
        # Persist to disk for API server to pick up (now via DB)
        save_signal_to_db(signal)


def save_signal_to_db(signal_data: Dict[str, Any]):
    """Save signal to database with expiration info and trigger auto-approve if eligible."""
    try:
        import sys
        import os
        import traceback
        
        # Ensure project root is in path
        if os.getcwd() not in sys.path:
            sys.path.append(os.getcwd())
            
        from src.earnings_intelligence.database import SignalRepository, Signal, init_db
        from datetime import datetime as dt
        
        # Ensure database tables exist
        init_db()
        
        repo = SignalRepository()
        
        # Parse expiration from signal data
        expires_at = None
        if 'expiresAt' in signal_data:
            try:
                expires_at = dt.fromisoformat(signal_data['expiresAt'])
            except:
                pass
        
        front_expiry = None
        if 'frontExpiry' in signal_data:
            try:
                front_expiry = dt.fromisoformat(signal_data['frontExpiry'])
            except:
                pass
        
        # Save with expiration fields
        signal = repo.save_signal(signal_data)
        
        # Update expiration fields directly on the model
        if expires_at:
            signal.expires_at = expires_at
        if front_expiry:
            signal.front_expiry = front_expiry
        repo.session.commit()
        
        logger.info(f"✅ Signal {signal_data.get('id')} saved to DB (expires: {expires_at})")
        
        # ✅ AUTO-APPROVE: Check if signal should be automatically executed
        try:
            from auto_approve import auto_approve_signal
            result = auto_approve_signal(signal_data)
            if result:
                logger.info(f"🤖 Auto-approved: {result.get('orderId')}")
                # Update signal status in database
                signal.status = 'executed'
                signal.data = signal.data or {}
                signal.data['autoApproved'] = True
                signal.data['orderId'] = result.get('orderId')
                repo.session.commit()
        except Exception as auto_err:
            logger.debug(f"Auto-approve skipped: {auto_err}")
        
        return True
        
    except Exception as e:
        import traceback
        logger.error(f"❌ Failed to save signal to DB: {e}")
        logger.error(traceback.format_exc())
        return False


def publish_alert(alert_data: Dict[str, Any], channel: str = "position_alerts") -> bool:
    """
    Publish a position alert to the WebSocket server for broadcast.
    
    Args:
        alert_data: Alert data dict containing:
            - type: alert type (e.g., 'position_alert')
            - position_id: Position ID
            - symbol: Underlying symbol
            - rule: Exit rule that triggered
            - reason: Exit reason
            - action: Recommended action
            - pnl_percent: P&L percentage
            - urgency: 'high' or 'medium'
            - timestamp: ISO timestamp
        channel: WebSocket channel to broadcast on
        
    Returns:
        True if broadcast succeeded
    """
    try:
        # Broadcast via WebSocket HTTP endpoint
        response = requests.post(
            WEBSOCKET_BROADCAST_URL,
            json={"channel": channel, "alert": alert_data},
            timeout=5
        )
        
        if response.ok:
            logger.info(f"📢 Published alert: {alert_data.get('symbol')} - {alert_data.get('rule')}")
            return True
        else:
            logger.warning(f"Alert broadcast failed: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.warning("WebSocket server not running, alert not broadcast")
        return False
    except Exception as e:
        logger.error(f"Failed to publish alert: {e}")
        return False

def save_signals_to_disk(filename=None):
    """Deprecated - using DB now."""
    pass

def load_signals_from_disk(filename=None) -> List[Dict[str, Any]]:
    """Load signals from database (backward compatibility wrapper)."""
    try:
        from src.earnings_intelligence.database import SignalRepository
        repo = SignalRepository()
        signals = repo.get_all_signals()
        return [s.to_dict() for s in signals]
    except Exception as e:
        logger.error(f"Failed to load signals from DB: {e}")
    return []


def publish_signals(setups: List, max_signals: int = 5) -> int:
    """
    Publish multiple signals (top N by score).
    
    Args:
        setups: List of SpreadSetup objects
        max_signals: Maximum signals to publish
        
    Returns:
        Number of successfully published signals
    """
    published = 0
    
    # Take top N by score (already sorted by scanner)
    for setup in setups[:max_signals]:
        if publish_signal(setup):
            published += 1
    
    logger.info(f"Published {published}/{len(setups[:max_signals])} signals")
    return published


def get_pending_signals() -> List[Dict[str, Any]]:
    """Get all pending signals for the API."""
    return [s for s in _pending_signals if s['status'] == 'pending']


def clear_old_signals(max_age_hours: int = 24) -> int:
    """Remove signals older than max_age_hours."""
    global _pending_signals
    cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
    
    original_count = len(_pending_signals)
    _pending_signals = [
        s for s in _pending_signals
        if datetime.fromisoformat(s['createdAt']).timestamp() > cutoff
    ]
    
    removed = original_count - len(_pending_signals)
    if removed:
        logger.info(f"Cleared {removed} old signals")
    return removed


def mark_signal_executed(signal_id: str) -> Optional[Dict[str, Any]]:
    """Mark a signal as executed."""
    for signal in _pending_signals:
        if signal['id'] == signal_id:
            signal['status'] = 'executed'
            signal['executedAt'] = datetime.now().isoformat()
            return signal
    return None


# =============================================================================
# EARNINGS SCANNER SIGNAL PUBLISHING
# =============================================================================

def earnings_opportunity_to_signal(opportunity) -> Dict[str, Any]:
    """
    Convert an EarningsOpportunity to frontend Signal format.
    
    Args:
        opportunity: EarningsOpportunity from earnings scanner
        
    Returns:
        Dict formatted for frontend consumption
    """
    # Determine risk level based on prediction
    if opportunity.predicted_class == "SEVERE":
        risk_level = "High"
    elif opportunity.predicted_class == "NORMAL":
        risk_level = "Medium"
    else:
        risk_level = "Low"
    
    # Calculate potential return based on strategy
    if opportunity.decision == "APPROVE":
        potential_return_pct = 8.0  # Target 8% for approved
    elif opportunity.decision == "REDUCE_SIZE":
        potential_return_pct = 5.0  # Lower target for reduced size
    else:
        potential_return_pct = 0.0  # Skip trades
    
    # Estimate cost based on average calendar spread
    estimated_cost = 250.0  # Average calendar spread cost
    potential_return = estimated_cost * (potential_return_pct / 100)
    
    signal = {
        "id": str(uuid.uuid4()),
        "symbol": opportunity.symbol,
        "strategy": opportunity.strategy or "Calendar Spread",
        "strategyType": "earnings",  # Distinguish from regular calendars
        "direction": "neutral",  # Calendar spreads are neutral
        "daysToEarnings": opportunity.days_to_earnings,
        "earningsDate": opportunity.earnings_date,
        "predictedClass": opportunity.predicted_class,
        "confidence": round(opportunity.confidence, 1),
        "predictedCrush": round(opportunity.predicted_crush_pct, 1),
        "currentIV": round(opportunity.current_iv, 1),
        "ivPercentile": round(opportunity.iv_percentile, 0),
        "currentPrice": round(opportunity.current_price, 2) if opportunity.current_price else 0,
        "cost": round(estimated_cost, 2),
        "potentialReturn": round(potential_return, 2),
        "returnPercent": round(potential_return_pct, 1),
        "winRate": int(60 + (opportunity.confidence * 0.15)),  # Base 60% + confidence bonus
        "riskLevel": risk_level,
        "decision": opportunity.decision,
        "status": "pending",
        "createdAt": datetime.now().isoformat(),
        "score": round(opportunity.score, 1),
        "reason": opportunity.reason,
        "rationale": f"{opportunity.predicted_class} crush ({opportunity.confidence:.0f}% conf), IV {opportunity.current_iv:.0f}%",
        # Analyst ratings
        "analystConsensus": getattr(opportunity, 'analyst_consensus', ''),
        "analystPriceTarget": getattr(opportunity, 'analyst_price_target', 0),
        "recentAnalystChanges": getattr(opportunity, 'recent_analyst_changes', ''),
        # Significant news
        "significantNews": getattr(opportunity, 'significant_news', ''),
        "newsSentiment": getattr(opportunity, 'news_sentiment', 'neutral'),
    }
    
    return signal


def publish_earnings_signal(opportunity, channel: str = "earnings") -> bool:
    """
    Publish an earnings scanner signal to WebSocket.
    
    Args:
        opportunity: EarningsOpportunity from scanner
        channel: WebSocket channel (default: 'earnings')
        
    Returns:
        True if broadcast succeeded
    """
    try:
        signal = earnings_opportunity_to_signal(opportunity)
        
        # Add to pending signals
        _pending_signals.append(signal)
        
        # Broadcast via WebSocket
        response = requests.post(
            WEBSOCKET_BROADCAST_URL,
            json={"channel": channel, "signal": signal},
            timeout=5
        )
        
        if response.ok:
            logger.info(f"📡 Published earnings signal: {signal['symbol']} ({signal['predictedClass']})")
            return True
        else:
            logger.warning(f"Broadcast failed: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.warning("WebSocket server not running, signal queued locally only")
        return False
    except Exception as e:
        logger.error(f"Failed to publish earnings signal: {e}")
        return False
    finally:
        # Persist to database (same as calendar spreads)
        save_signal_to_db(signal)


def publish_earnings_signals(opportunities: List, max_signals: int = 10) -> int:
    """
    Publish multiple earnings signals.
    
    Args:
        opportunities: List of EarningsOpportunity objects
        max_signals: Maximum to publish (default: 10)
        
    Returns:
        Number of successfully published signals
    """
    published = 0
    
    for opp in opportunities[:max_signals]:
        # Only publish APPROVE or REDUCE_SIZE decisions
        if opp.decision in ["APPROVE", "REDUCE_SIZE"]:
            if publish_earnings_signal(opp):
                published += 1
    
    logger.info(f"📡 Published {published}/{len(opportunities[:max_signals])} earnings signals")
    return published


def get_earnings_signals(status: str = None) -> List[Dict[str, Any]]:
    """
    Get earnings signals filtered by status.
    
    Args:
        status: Optional filter ('pending', 'approved', 'executed')
        
    Returns:
        List of matching signals
    """
    earnings_signals = [s for s in _pending_signals if s.get('strategyType') == 'earnings']
    
    if status:
        earnings_signals = [s for s in earnings_signals if s.get('status') == status]
    
    return earnings_signals


# =============================================================================
# VERTICAL SPREAD SIGNAL PUBLISHING
# =============================================================================

# Signal types for vertical spreads
class SignalType:
    BUY = "BUY"           # New position entry signal
    SELL = "SELL"         # Exit/close position signal
    WARNING = "WARNING"   # Risk alert (no action required)


def vertical_spread_to_signal(spread_setup, signal_type: str = SignalType.BUY) -> Dict[str, Any]:
    """
    Convert a VerticalSpreadSignal or VerticalSpreadSetup to frontend format.
    
    Args:
        spread_setup: VerticalSpreadSignal or VerticalSpreadSetup object
        signal_type: BUY, SELL, or WARNING
        
    Returns:
        Dict formatted for frontend consumption
    """
    # Handle both VerticalSpreadSignal and VerticalSpreadSetup
    if hasattr(spread_setup, 'to_dict'):
        data = spread_setup.to_dict()
    elif hasattr(spread_setup, '__dataclass_fields__'):
        from dataclasses import asdict
        data = asdict(spread_setup)
    else:
        # Assume it's already a dict or has the needed attributes
        data = {
            "id": getattr(spread_setup, 'id', str(uuid.uuid4())),
            "symbol": getattr(spread_setup, 'symbol', ''),
            "strategy": getattr(spread_setup, 'strategy', ''),
            "direction": getattr(spread_setup, 'direction', ''),
            "buyStrike": getattr(spread_setup, 'buy_strike', 0),
            "sellStrike": getattr(spread_setup, 'sell_strike', 0),
            "optionType": getattr(spread_setup, 'option_type', 'C'),
            "expiration": str(getattr(spread_setup, 'expiration', '')),
            "dte": getattr(spread_setup, 'dte', 0),
            "cost": getattr(spread_setup, 'cost', getattr(spread_setup, 'net_debit', 0) * 100),
            "maxProfit": getattr(spread_setup, 'max_profit', 0),
            "maxLoss": getattr(spread_setup, 'max_loss', 0),
            "contracts": getattr(spread_setup, 'contracts', 1),
            "totalRisk": getattr(spread_setup, 'total_at_risk', getattr(spread_setup, 'total_risk', 0)),
            "confidence": getattr(spread_setup, 'confidence', 0),
            "returnPercent": getattr(spread_setup, 'return_percent', 0),
            "riskLevel": getattr(spread_setup, 'risk_level', 'Medium'),
            "rationale": getattr(spread_setup, 'rationale', ''),
        }
    
    # Add signal metadata
    signal = {
        "id": data.get('id') or str(uuid.uuid4()),
        "signalType": signal_type,
        "symbol": data.get('symbol', ''),
        "strategy": data.get('strategy', ''),
        "direction": data.get('direction', ''),
        "buyStrike": data.get('buyStrike', data.get('buy_strike', 0)),
        "sellStrike": data.get('sellStrike', data.get('sell_strike', 0)),
        "optionType": data.get('optionType', data.get('option_type', 'C')),
        "expiration": str(data.get('expiration', '')),
        "dte": data.get('dte', 0),
        "cost": round(float(data.get('cost', 0)), 2),
        "maxProfit": round(float(data.get('maxProfit', data.get('max_profit', 0))), 2),
        "maxLoss": round(float(data.get('maxLoss', data.get('max_loss', 0))), 2),
        "contracts": data.get('contracts', 1),
        "totalRisk": round(float(data.get('totalRisk', data.get('total_risk', 0))), 2),
        "confidence": data.get('confidence', 0),
        "returnPercent": round(float(data.get('returnPercent', data.get('return_percent', 0))), 1),
        "riskLevel": data.get('riskLevel', data.get('risk_level', 'Medium')),
        "rationale": data.get('rationale', ''),
        "status": "pending",
        "createdAt": datetime.now().isoformat(),
    }
    
    return signal


def publish_vertical_spread_signal(
    spread_setup, 
    signal_type: str = SignalType.BUY,
    include_parent_channel: bool = True
) -> bool:
    """
    Publish a vertical spread signal to WebSocket subscribers.
    
    Args:
        spread_setup: VerticalSpreadSignal, VerticalSpreadSetup, or dict
        signal_type: BUY, SELL, or WARNING
        include_parent_channel: Also broadcast to 'vertical_spread' parent channel
        
    Returns:
        True if broadcast succeeded
    """
    try:
        signal = vertical_spread_to_signal(spread_setup, signal_type)
        
        # Add to pending signals for API
        _pending_signals.append(signal)
        
        # Determine channel based on signal type
        specific_channel = f"vertical_spread.{signal_type.lower()}"
        
        # Broadcast to specific channel
        response = requests.post(
            WEBSOCKET_BROADCAST_URL,
            json={"channel": specific_channel, "signal": signal},
            timeout=5
        )
        
        # Also broadcast to parent channel if requested
        if include_parent_channel:
            requests.post(
                WEBSOCKET_BROADCAST_URL,
                json={"channel": "vertical_spread", "signal": signal},
                timeout=5
            )
        
        if response.ok:
            logger.info(f"📡 Published {signal_type} signal: {signal['symbol']} {signal['strategy']}")
            return True
        else:
            logger.warning(f"Broadcast failed: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.warning("WebSocket server not running, signal queued locally only")
        return False
    except Exception as e:
        logger.error(f"Failed to publish vertical spread signal: {e}")
        return False
    finally:
        # Persist to database (same as calendar spreads)
        save_signal_to_db(signal)


def publish_buy_signal(spread_setup) -> bool:
    """Publish a BUY signal for a new vertical spread opportunity."""
    return publish_vertical_spread_signal(spread_setup, SignalType.BUY)


def publish_sell_signal(spread_setup, reason: str = "") -> bool:
    """
    Publish a SELL signal to close a position.
    
    Args:
        spread_setup: Position data or signal to close
        reason: Why the position should be closed (e.g., "Profit target reached")
    """
    if hasattr(spread_setup, 'rationale'):
        spread_setup.rationale = reason or spread_setup.rationale
    elif isinstance(spread_setup, dict):
        spread_setup['rationale'] = reason or spread_setup.get('rationale', '')
    
    return publish_vertical_spread_signal(spread_setup, SignalType.SELL)


def publish_warning_signal(symbol: str, warning_message: str, data: Dict[str, Any] = None) -> bool:
    """
    Publish a WARNING signal (risk alert, no action required).
    
    Args:
        symbol: Stock symbol
        warning_message: Human-readable warning
        data: Optional additional data
    """
    warning_signal = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "strategy": "WARNING",
        "direction": "",
        "rationale": warning_message,
        "riskLevel": "High",
        "confidence": 0,
        **(data or {})
    }
    
    return publish_vertical_spread_signal(warning_signal, SignalType.WARNING)


def get_vertical_spread_signals(signal_type: str = None) -> List[Dict[str, Any]]:
    """
    Get pending vertical spread signals.
    
    Args:
        signal_type: Optional filter by BUY, SELL, or WARNING
        
    Returns:
        List of matching signals
    """
    signals = [s for s in _pending_signals if s.get('strategy', '').endswith('SPREAD') or s.get('signalType')]
    
    if signal_type:
        signals = [s for s in signals if s.get('signalType') == signal_type]
    
    return signals


# =============================================================================
# THETA STRATEGY SIGNAL PUBLISHING (Cash-Secured Puts)
# =============================================================================

def theta_put_to_signal(put_signal, signal_type: str = "ENTRY") -> Dict[str, Any]:
    """
    Convert Theta put signal (entry or exit) to frontend Signal format.
    
    Args:
        put_signal: ThetaEntrySignal or ThetaExitSignal object
        signal_type: "ENTRY" or "EXIT"
        
    Returns:
        Dict formatted for frontend consumption
    """
    # Handle both entry and exit signals
    if signal_type == "ENTRY":
        signal = {
            "id": getattr(put_signal, 'id', str(uuid.uuid4())),
            "signalType": "ENTRY",
            "action": "SELL_TO_OPEN",
            "symbol": getattr(put_signal, 'symbol', ''),
            "strategy": "Theta Cash-Secured Put",
            "strategyType": "theta",
            "direction": "neutral",  # Selling puts is neutral-to-bullish
            "strike": getattr(put_signal, 'strike', 0),
            "expiration": str(getattr(put_signal, 'expiration', '')),
            "dte": getattr(put_signal, 'dte', 0),
            "entryPrice": round(float(getattr(put_signal, 'entry_price', 0)), 2),
            "delta": round(float(getattr(put_signal, 'delta', 0)), 3),
            "theta": round(float(getattr(put_signal, 'theta', 0)), 3),
            "vega": round(float(getattr(put_signal, 'vega', 0)), 3),
            "iv": round(float(getattr(put_signal, 'iv', 0)) * 100, 1),
            "confidence": getattr(put_signal, 'confidence', 0),
            "probabilityOTM": round(float(getattr(put_signal, 'probability_otm', 0)), 1),
            "contracts": getattr(put_signal, 'contracts', 1),
            "totalPremium": round(float(getattr(put_signal, 'total_premium', 0)), 2),
            "capitalRequired": round(float(getattr(put_signal, 'total_capital_required', 0)), 2),
            "cost": round(float(getattr(put_signal, 'total_capital_required', 0)), 2),  # For consistency
            "potentialReturn": round(float(getattr(put_signal, 'total_premium', 0)), 2),
            "returnPercent": round((float(getattr(put_signal, 'total_premium', 0)) / 
                                   float(getattr(put_signal, 'total_capital_required', 1))) * 100, 2),
            "riskLevel": _theta_risk_level(put_signal),
            "rationale": f"30-delta put | {getattr(put_signal, 'confidence', 0)}% confidence | "
                        f"Premium ${getattr(put_signal, 'total_premium', 0):.0f}",
            "status": "pending",
            "createdAt": datetime.now().isoformat(),
        }
    else:  # EXIT
        signal = {
            "id": getattr(put_signal, 'id', str(uuid.uuid4())),
            "signalType": "EXIT",
            "action": "BUY_TO_CLOSE",
            "positionId": getattr(put_signal, 'position_id', ''),
            "symbol": getattr(put_signal, 'symbol', ''),
            "strategy": "Theta Cash-Secured Put",
            "strategyType": "theta",
            "strike": getattr(put_signal, 'strike', 0),
            "exitPrice": round(float(getattr(put_signal, 'exit_price', 0)), 2),
            "entryPrice": round(float(getattr(put_signal, 'entry_price', 0)), 2),
            "unrealizedPnL": round(float(getattr(put_signal, 'unrealized_pnl', 0)), 2),
            "unrealizedPnLPct": round(float(getattr(put_signal, 'unrealized_pnl_pct', 0)), 1),
            "reason": str(getattr(put_signal, 'reason', '')).split('.')[-1],  # Remove enum prefix
            "urgency": getattr(put_signal, 'urgency', 'MEDIUM'),
            "daysInTrade": getattr(put_signal, 'days_in_trade', 0),
            "targetProfitPct": round(float(getattr(put_signal, 'target_profit_pct', 0)), 1),
            "contracts": getattr(put_signal, 'contracts', 1),
            "capitalToRelease": round(float(getattr(put_signal, 'capital_to_release', 0)), 2),
            "rationale": _theta_exit_rationale(put_signal),
            "status": "pending",
            "createdAt": datetime.now().isoformat(),
        }
    
    return signal


def _theta_risk_level(put_signal) -> str:
    """Determine risk level for Theta entry signal."""
    delta = float(getattr(put_signal, 'delta', 0.30))
    dte = getattr(put_signal, 'dte', 30)
    confidence = getattr(put_signal, 'confidence', 60)
    
    if delta > 0.35 or dte < 21 or confidence < 60:
        return "High"
    elif delta < 0.28 and dte > 28 and confidence > 70:
        return "Low"
    else:
        return "Medium"


def _theta_exit_rationale(put_signal) -> str:
    """Build rationale for Theta exit signal."""
    reason = str(getattr(put_signal, 'reason', '')).split('.')[-1]
    pnl_pct = float(getattr(put_signal, 'unrealized_pnl_pct', 0))
    target_pct = float(getattr(put_signal, 'target_profit_pct', 0))
    days = getattr(put_signal, 'days_in_trade', 0)
    
    if reason == "PROFIT_TARGET":
        week = (days - 1) // 7 + 1  # Week 1-4
        return f"Time-based exit: Week {week} target ({target_pct:.0f}%) reached @ {pnl_pct:.1f}% profit"
    elif reason == "EXPIRATION_IMMINENT":
        return f"Close to expiration ({days} days in trade)"
    elif reason == "DEFENSIVE_CLOSE":
        return f"Underlying breached strike threshold ({pnl_pct:.1f}% P&L)"
    else:
        return f"{reason} | P&L: {pnl_pct:.1f}% | Days: {days}"


def publish_theta_signal(
    put_signal,
    signal_type: str = "ENTRY",
    channel: str = "theta_puts"
) -> bool:
    """
    Publish a Theta strategy signal to WebSocket subscribers.
    
    Args:
        put_signal: ThetaEntrySignal or ThetaExitSignal object
        signal_type: "ENTRY" or "EXIT"
        channel: WebSocket channel (default: 'theta_puts')
        
    Returns:
        True if broadcast succeeded
    """
    try:
        signal = theta_put_to_signal(put_signal, signal_type)
        
        # Add to pending signals for API
        _pending_signals.append(signal)
        
        # Determine channel based on signal type
        specific_channel = f"theta_{signal_type.lower()}"
        
        # Broadcast to specific channel
        response = requests.post(
            WEBSOCKET_BROADCAST_URL,
            json={"channel": specific_channel, "signal": signal},
            timeout=5
        )
        
        # Also broadcast to parent channel
        requests.post(
            WEBSOCKET_BROADCAST_URL,
            json={"channel": channel, "signal": signal},
            timeout=5
        )
        
        if response.ok:
            logger.info(f"📡 Published Theta {signal_type}: {signal['symbol']} {signal.get('strike')}P")
            return True
        else:
            logger.warning(f"Broadcast failed: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.warning("WebSocket server not running, signal queued locally only")
        return False
    except Exception as e:
        logger.error(f"Failed to publish Theta signal: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    finally:
        # Persist to database
        save_signal_to_db(signal)


def publish_theta_entry_signal(put_signal) -> bool:
    """Publish a Theta entry signal (SELL_TO_OPEN)."""
    return publish_theta_signal(put_signal, "ENTRY", "theta_puts")


def publish_theta_exit_signal(put_signal) -> bool:
    """Publish a Theta exit signal (BUY_TO_CLOSE)."""
    return publish_theta_signal(put_signal, "EXIT", "theta_puts")


def get_theta_signals(signal_type: str = None) -> List[Dict[str, Any]]:
    """
    Get pending Theta strategy signals.
    
    Args:
        signal_type: Optional filter by "ENTRY" or "EXIT"
        
    Returns:
        List of matching signals
    """
    theta_signals = [s for s in _pending_signals if s.get('strategyType') == 'theta']
    
    if signal_type:
        theta_signals = [s for s in theta_signals if s.get('signalType') == signal_type]
    
    return theta_signals




# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create a mock setup for testing
    from datetime import date
    
    class MockSetup:
        symbol = "SPY"
        strike = 485.0
        stock_price = 484.50
        short_expiry = date(2026, 1, 24)
        long_expiry = date(2026, 2, 21)
        net_debit = 2.50
        iv = 0.18
        score = 45.5
        theta_edge = 0.08
    
    setup = MockSetup()
    signal = spread_setup_to_signal(setup)
    print(f"Signal: {signal}")
    
    # Try to publish
    result = publish_signal(setup)
    print(f"Published: {result}")
