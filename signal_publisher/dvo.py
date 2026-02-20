
"""
DVO Signal Publisher
====================
Signal publishing for Deep Value Overlay strategy.
Channels:
- dvo_entry
- dvo_exit
- dvo_all
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any
import logging

from .websocket_client import broadcast_to_channel

logger = logging.getLogger(__name__)

@dataclass
class DVOEntrySignal:
    id: str # UUID
    symbol: str
    strategy_type: str # SHORT_PUT | LEAPS_CALL
    
    # Trade details
    action: str
    quantity: int
    limit_price: float
    expiration: str
    strike: float
    option_type: str
    dte: int
    
    # Fundamental Context
    current_price: float
    fair_value: float
    margin_of_safety: float
    regime: str
    
    # Metadata
    reasoning: str = ""
    status: str = "pending"
    created_at: str = ""
    
    def to_dict(self):
        return asdict(self)

@dataclass
class DVOExitSignal:
    id: str
    position_id: str
    symbol: str
    strategy_type: str
    
    action: str = "CLOSE"
    quantity: int = 0
    limit_price: float = 0.0
    
    reason: str = "" # VELOCITY, THESIS, etc.
    pnl_pct: float = 0.0
    
    status: str = "pending"
    created_at: str = ""
    
    def to_dict(self):
        return asdict(self)

def publish_dvo_entry_signal(signal: DVOEntrySignal) -> bool:
    """Publish Entry Signal."""
    try:
        data = signal.to_dict()
        
        # 1. Save to DB
        try:
            repo = SignalRepository()
            repo.save_signal(data) # Generic save, might need DVO specific table if structure differs heavily
        except Exception:
            pass # Ignore if generic schema mismatch, we have DVO specific tables too
            
        # 2. Auto-Approve Check (via auto_approve.py logic invoked here or by subscriber)
        # In ZEBRA pattern, we call `auto_approve_signal(data)` here.
        try:
            from auto_approve import auto_approve_signal
            result = auto_approve_signal(data)
            if result:
                 data['status'] = 'executed'
                 data['autoApproved'] = True
                 data['orderId'] = result.get('orderId')
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Auto-approve error: {e}")

        # 3. Broadcast
        broadcast_to_channel('dvo_entry', data)
        broadcast_to_channel('dvo_all', data)
        return True
    except Exception as e:
        logger.error(f"Failed to publish DVO entry: {e}")
        return False

def publish_dvo_exit_signal(signal: DVOExitSignal) -> bool:
    """Publish Exit Signal."""
    try:
        data = signal.to_dict()
        broadcast_to_channel('dvo_exit', data)
        broadcast_to_channel('dvo_all', data)
        return True
    except Exception as e:
        logger.error(f"Failed to publish DVO exit: {e}")
        return False
