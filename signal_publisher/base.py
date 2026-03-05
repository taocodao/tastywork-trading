"""
Base Signal Classes
===================
Common base classes for all trading signals.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any


@dataclass
class BaseSignal:
    """Base class for all trading signals."""
    
    id: str
    symbol: str
    strategy: str  # "theta", "calendar", "vertical"
    status: str    # "pending", "active", "filled", "cancelled"
    created_at: datetime
    expires_at: datetime
    
    # Strategy-specific metadata
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary for JSON serialization."""
        def _format_date(dt):
            if not isinstance(dt, datetime):
                return dt
            # If naive, assume UTC and append Z. If aware, isoformat() already includes offset.
            return dt.isoformat() + ('Z' if dt.tzinfo is None else '')

        return {
            'id': self.id,
            'symbol': self.symbol,
            'strategy': self.strategy,
            'status': self.status,
            'created_at': _format_date(self.created_at),
            'expires_at': _format_date(self.expires_at),
            'metadata': self.metadata or {}
        }
