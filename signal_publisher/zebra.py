"""
ZEBRA Strategy Signals
=======================
Signal publishing for ZEBRA (Zero Extrinsic Back Ratio) strategy.
Supports both LONG (Call) and SHORT (Put) ZEBRAs.

Channels:
- zebra_entry: Entry signals (OPEN)
- zebra_exit: Exit signals (CLOSE/ROLL)
- zebra_all: All ZEBRA signals
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, List
import logging

from .websocket_client import broadcast_to_channel

logger = logging.getLogger(__name__)


@dataclass
class ZebraEntrySignal:
    """Signal for opening a ZEBRA position."""
    
    # Identity (required)
    id: str
    symbol: str
    
    # Direction
    direction: str  # "LONG" or "SHORT"
    
    # Structure - 3 legs
    long_strike: float       # ITM strike (Buy 2)
    long_delta: float        # Delta of each long leg
    short_strike: float      # ATM strike (Sell 1)
    short_delta: float       # Delta of short leg
    expiry: str              # YYYY-MM-DD
    dte: int
    
    # Pricing
    net_debit: float         # Total cost to open
    max_loss: float          # Defined risk (debit paid)
    breakeven: float         # Price where P&L = 0
    
    # Greeks (net position)
    net_delta: float         # Target ≈ 0.90-1.10
    net_theta: float         # Should be ≈ 0
    net_vega: float
    net_extrinsic: float     # Target: as close to $0 as possible
    
    # Scoring
    construction_score: float     # 0-100
    directional_confidence: float # 0-100
    capital_efficiency: float     # delta per dollar vs 100 shares
    anti_crowding_score: float    # 0-100
    composite_score: float        # Weighted ranking score
    
    # Individual leg market data (for order construction)
    long_leg_bid: float = 0.0
    long_leg_ask: float = 0.0
    short_leg_bid: float = 0.0
    short_leg_ask: float = 0.0
    
    # Risk context
    capital_required: float = 0.0      # = net_debit * contracts * 100
    expected_move_pct: float = 0.0     # ML predicted move
    thesis_horizon_days: int = 30
    
    # Metadata
    contracts: int = 1
    rationale: str = ""
    strategy: str = "zebra"
    signal_type: str = "entry"
    action: str = "OPEN"
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if isinstance(data['created_at'], datetime):
            data['created_at'] = data['created_at'].isoformat()
        if isinstance(data.get('expires_at'), datetime):
            data['expires_at'] = data['expires_at'].isoformat()
        return data


@dataclass
class ZebraExitSignal:
    """Signal for closing or adjusting a ZEBRA position."""
    
    # Identity
    id: str
    position_id: str  # ID of the entry signal/position
    symbol: str
    direction: str    # "LONG" or "SHORT"
    
    # Exit details
    exit_credit: float      # Credit received to close
    exit_reason: str        # PROFIT_TARGET, STOP_LOSS, TIME_EXIT, etc.
    
    # P&L
    entry_debit: float
    pnl: float
    pnl_percent: float
    
    # Position info
    contracts: int
    days_held: int
    
    # Metadata
    created_at: datetime
    strategy: str = "zebra"
    signal_type: str = "exit"
    action: str = "CLOSE"
    status: str = "pending"
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        if isinstance(data['created_at'], datetime):
            data['created_at'] = data['created_at'].isoformat()
        return data


def publish_zebra_entry_signal(signal: ZebraEntrySignal) -> bool:
    """
    Publish ZEBRA entry signal to WebSocket channels AND save to database.
    """
    try:
        data = signal.to_dict()
        
        # Calculate expiration: Market close today (16:00 ET)
        try:
            import pytz
            ny_tz = pytz.timezone('US/Eastern')
            now_ny = datetime.now(ny_tz)
            market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
            data['expires_at'] = market_close.astimezone(pytz.UTC).replace(tzinfo=None)
        except ImportError:
            pass
        
        
        # 1. Save to DB (Persistence)
        try:
            from src.earnings_intelligence.database import SignalRepository
            repo = SignalRepository()
            repo.save_signal(data)
            logger.info(f"✅ ZEBRA signal saved to DB: {signal.symbol}")
        except Exception as db_err:
            logger.warning(f"⚠️ Failed to save ZEBRA to DB: {db_err}")
            
        # 2. Auto-Approve check (if enabled)
        try:
            from auto_approve import auto_approve_signal
            result = auto_approve_signal(data)
            if result:
                logger.info(f"🤖 Auto-approved ZEBRA signal: {signal.symbol} -> Order {result.get('orderId')}")
                data['status'] = 'executed'
                data['autoApproved'] = True
                data['orderId'] = result.get('orderId')
                # Update DB
                try:
                    repo = SignalRepository()
                    repo.save_signal(data)
                except Exception:
                    pass
        except Exception as auto_err:
            logger.debug(f"Auto-approve skipped for {signal.symbol}: {auto_err}")

        # 3. Broadcast
        success_entry = broadcast_to_channel('zebra_entry', data)
        success_all = broadcast_to_channel('zebra_all', data)
        
        return success_entry or success_all

    except Exception as e:
        logger.error(f"Failed to publish ZEBRA entry signal: {e}")
        return False


def publish_zebra_exit_signal(signal: ZebraExitSignal) -> bool:
    """
    Publish ZEBRA exit signal to WebSocket channels.
    """
    try:
        data = signal.to_dict()
        
        success_exit = broadcast_to_channel('zebra_exit', data)
        success_all = broadcast_to_channel('zebra_all', data)
        
        return success_exit or success_all
        
    except Exception as e:
        logger.error(f"Failed to publish ZEBRA exit signal: {e}")
        return False
