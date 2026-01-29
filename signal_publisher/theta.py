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
    
    # Identity
    id: str
    symbol: str
    action: str = "SELL_TO_OPEN"
    
    # Option details
    strike: float
    expiration: str  # ISO format date
    dte: int
    
    # Pricing
    entry_price: float  # Bid price we're selling at
    ask: float
    mid: float
    
    # Greeks
    delta: float
    theta: float
    vega: float
    iv: float  # Implied volatility
    
    # Risk metrics
    confidence: float  # 0-100 score
    probability_otm: float  # Probability of expiring OTM
    expected_premium: float
    capital_required: float
    
    # Position sizing
    contracts: int
    total_premium: float
    total_capital_required: float
    
    # Metadata
    created_at: datetime
    status: str = "pending"
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert datetime to ISO format
        if isinstance(data['created_at'], datetime):
            data['created_at'] = data['created_at'].isoformat()
        return data


@dataclass
class ThetaExitSignal:
    """Signal for closing a theta position (buy back the put)."""
    
    # Identity
    id: str
    position_id: str  # ID of the entry signal
    symbol: str
    action: str = "BUY_TO_CLOSE"
    
    # Option details
    strike: float
    expiration: str
    
    # Exit details
    exit_price: float  # Ask price we're buying at
    exit_reason: str  # "profit_target", "stop_loss", "time_decay", "manual"
    
    # P&L
    entry_price: float
    pnl: float
    pnl_percent: float
    
    # Position info
    contracts: int
    days_held: int
    
    # Metadata
    created_at: datetime
    status: str = "pending"
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if isinstance(data['created_at'], datetime):
            data['created_at'] = data['created_at'].isoformat()
        return data


def publish_theta_entry_signal(signal: ThetaEntrySignal) -> bool:
    """
    Publish theta entry signal to WebSocket channels.
    
    Args:
        signal: ThetaEntrySignal dataclass
        
    Returns:
        True if broadcast to at least one channel succeeded
    """
    try:
        data = signal.to_dict()
        data['strategy'] = 'theta'
        data['signal_type'] = 'entry'
        
        # Broadcast to multiple channels
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
