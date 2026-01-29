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
        return {
            'id': self.id,
            'symbol': self.symbol,
            'strategy': self.strategy,
            'status': self.status,
            'created_at': self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            'expires_at': self.expires_at.isoformat() if isinstance(self.expires_at, datetime) else self.expires_at,
            'metadata': self.metadata or {}
        }
