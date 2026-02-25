"""
Diagonal Signal Publisher
=========================
Publishes Active Diagonal Strategy entry signals.

Uses the same pattern as PMCC/ZEBRA:
  1. broadcast_to_channel  -> WebSocket server (port 8004)
  2. SignalRepository       -> database persistence
"""
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict

import pytz

from signal_publisher.websocket_client import broadcast_to_channel

logger = logging.getLogger(__name__)


@dataclass
class DiagonalEntrySignal:
    """Signal data for a new Active Diagonal entry opportunity."""
    symbol: str
    strategy: str
    dip_score: float
    ml_direction: str
    ml_confidence: float
    regime: str
    current_price: float
    status: str = "pending"
    signal_type: str = "entry"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def publish_diagonal_entry_signal(signal: DiagonalEntrySignal) -> bool:
    """
    Broadcast diagonal entry signal to WebSocket + save to database.
    """
    try:
        data = signal.to_dict()

        # Add expires_at (market close in ET, converted to UTC)
        try:
            ny_tz = pytz.timezone('US/Eastern')
            now_ny = datetime.now(ny_tz)
            market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
            market_close_utc = market_close.astimezone(pytz.UTC).replace(tzinfo=None)
            data['expires_at'] = market_close_utc.isoformat()
        except Exception:
            data['expires_at'] = (datetime.utcnow() + timedelta(hours=4)).isoformat()

        # 1. Broadcast to WebSocket
        ws_ok = broadcast_to_channel('diagonal_entry', data)
        broadcast_to_channel('diagonal_all', data)

        # 2. Persist to database
        try:
            from src.earnings_intelligence.database import SignalRepository
            repo = SignalRepository()
            repo.save_signal(data)
            logger.info(f"✅ Diagonal signal saved to DB: {signal.symbol} (Regime={signal.regime}, Dip={signal.dip_score:.2f})")
        except Exception as db_err:
            logger.warning(f"⚠️ DB save failed (signal still broadcast): {db_err}")

        return ws_ok

    except Exception as e:
        logger.error(f"Error publishing Diagonal entry signal: {e}")
        return False
