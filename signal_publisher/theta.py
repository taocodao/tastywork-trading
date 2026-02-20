"""
Theta Strategy Signals
=======================
Signal publishing for cash-secured put (theta) strategy.

Channels:
- theta_puts: All theta signals
- theta_entry: Entry signals (SELL_TO_OPEN)
- theta_exit: Exit signals (BUY_TO_CLOSE)
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional
import logging

from .websocket_client import broadcast_to_channel

logger = logging.getLogger(__name__)


@dataclass
class ThetaEntrySignal:
    """Signal for opening a theta position (cash-secured put)."""
    
    # Identity (required)
    id: str
    symbol: str
    
    # Option details (required)
    strike: float
    expiration: 'str | date'  # ISO format date string OR date object
    dte: int
    
    # Pricing (required)
    entry_price: float  # Bid price we're selling at
    ask: float
    mid: float
    
    # Greeks (required)
    delta: float
    theta: float
    vega: float
    iv: float  # Implied volatility
    
    # Risk metrics (required)
    confidence: float  # 0-100 score
    probability_otm: float  # Probability of expiring OTM
    expected_premium: float
    capital_required: float
    
    # Position sizing (required)
    contracts: int
    total_premium: float
    total_capital_required: float
    
    # Metadata (required)
    created_at: datetime
    
    # Fields with default values must come last
    action: str = "SELL_TO_OPEN"
    status: str = "pending"
    expires_at: 'datetime | None' = None  # Optional signal expiration
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert datetime to ISO format
        if isinstance(data['created_at'], datetime):
            data['created_at'] = data['created_at'].isoformat()
        if isinstance(data.get('expires_at'), datetime):
            data['expires_at'] = data['expires_at'].isoformat()
        # Convert date to ISO format (for expiration)
        from datetime import date
        if isinstance(data['expiration'], date):
            data['expiration'] = data['expiration'].isoformat()
        return data


@dataclass
class ThetaExitSignal:
    """Signal for closing a theta position (buy back the put)."""
    
    # Identity (required)
    id: str
    position_id: str  # ID of the entry signal
    symbol: str
    
    # Option details (required)
    strike: float
    expiration: str
    
    # Exit details (required)
    exit_price: float  # Ask price we're buying at
    exit_reason: str  # "profit_target", "stop_loss", "time_decay", "manual"
    
    # P&L (required)
    entry_price: float
    pnl: float
    pnl_percent: float
    
    # Position info (required)
    contracts: int
    days_held: int
    
    # Metadata (required)
    created_at: datetime
    
    # Fields with default values must come last
    action: str = "BUY_TO_CLOSE"
    status: str = "pending"
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if isinstance(data['created_at'], datetime):
            data['created_at'] = data['created_at'].isoformat()
        return data


def publish_theta_entry_signal(signal: ThetaEntrySignal) -> bool:
    """
    Publish theta entry signal to WebSocket channels AND save to database.
    
    Args:
        signal: ThetaEntrySignal dataclass
        
    Returns:
        True if broadcast to at least one channel succeeded
    """
    try:
        data = signal.to_dict()
        data['strategy'] = 'theta'
        data['signal_type'] = 'entry'
        
        # Calculate expiration: Market close today (16:00 ET)
        try:
            import pytz
            ny_tz = pytz.timezone('US/Eastern')
            now_ny = datetime.now(ny_tz)
            market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
            data['expires_at'] = market_close.astimezone(pytz.UTC).replace(tzinfo=None).isoformat()
        except ImportError:
            pass
        
        # STEP 1: Save to database for persistence
        try:
            from src.earnings_intelligence.database import SignalRepository
            repo = SignalRepository()
            repo.save_signal(data)
            logger.info(f"✅ Theta signal saved to database: {signal.symbol}")
        except Exception as db_error:
            logger.warning(f"⚠️ Failed to save to DB (signal will still broadcast): {db_error}")
        
        # STEP 2: Auto-approve if criteria met
        try:
            from auto_approve import auto_approve_signal
            result = auto_approve_signal(data)
            if result:
                logger.info(f"🤖 Auto-approved theta signal: {signal.symbol} → Order {result.get('orderId')}")
                data['status'] = 'executed'
                data['autoApproved'] = True
                data['orderId'] = result.get('orderId')
                # Update DB status
                try:
                    repo = SignalRepository()
                    repo.save_signal(data)
                except Exception:
                    pass
        except Exception as auto_err:
            logger.debug(f"Auto-approve skipped for {signal.symbol}: {auto_err}")
        
        # STEP 3: Broadcast to WebSocket channels
        success_puts = broadcast_to_channel('theta_puts', data)
        success_entry = broadcast_to_channel('theta_entry', data)
        
        # Return True if at least one succeeded
        return success_puts or success_entry
        
    except Exception as e:
        logger.error(f"Failed to publish theta entry signal: {e}")
        return False


def publish_theta_exit_signal(signal: ThetaExitSignal) -> bool:
    """
    Publish theta exit signal to WebSocket channels.
    
    Args:
        signal: ThetaExitSignal dataclass
        
    Returns:
        True if broadcast to at least one channel succeeded
    """
    try:
        data = signal.to_dict()
        data['strategy'] = 'theta'
        data['signal_type'] = 'exit'
        
        # Broadcast to multiple channels
        success_puts = broadcast_to_channel('theta_puts', data)
        success_exit = broadcast_to_channel('theta_exit', data)
        
        return success_puts or success_exit
        
    except Exception as e:
        logger.error(f"Failed to publish theta exit signal: {e}")
        return False
