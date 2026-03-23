"""
models/iv_switching_position.py
================================
SQLAlchemy ORM model for the iv_switching_positions table.
Tracks virtual options positions for all IV-Switching modes per user.
Used by daily_order_generator.py to read existing positions without
making live TastyTrade API calls during signal generation.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Date, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from models.db import Base


class IVSwitchingPosition(Base):
    __tablename__ = "iv_switching_positions"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id         = Column(String, nullable=False, index=True)

    # Strategy context
    mode            = Column(String(8),  nullable=False)   # A / B / C / D2 / D3
    signal_type     = Column(String(32), nullable=False)   # OPEN_ZEBRA / OPEN_CSP / etc.

    # Position details
    symbol          = Column(String(16))
    option_type     = Column(String(16))    # ZEBRA / CSP / CCS / EQUITY
    contracts       = Column(Integer, default=0)

    # Strikes & expiry
    long_strike     = Column(Float)
    short_strike    = Column(Float)
    expiry_date     = Column(Date)

    # Pricing
    entry_price     = Column(Float)         # net debit / premium at fill
    fill_price      = Column(Float)         # actual fill price from TT
    current_price   = Column(Float)         # last mark price

    # P&L
    unrealized_pnl  = Column(Float, default=0)
    realized_pnl    = Column(Float, default=0)

    # Lifecycle
    status          = Column(String(16), default='OPEN', index=True)
    #   'OPEN' | 'CLOSED_PROFIT' | 'CLOSED_STOP' | 'CLOSED_EXPIRY' | 'CLOSED_REGIME'
    tt_order_id     = Column(Text)          # TastyTrade order ID for polling
    opened_at       = Column(DateTime, default=datetime.utcnow)
    closed_at       = Column(DateTime)

    # Metadata
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return (
            f"<IVSwitchingPosition user={self.user_id[:8]} mode={self.mode} "
            f"type={self.option_type} contracts={self.contracts} status={self.status}>"
        )

    @property
    def is_open(self) -> bool:
        return self.status == 'OPEN'

    def close(self, reason: str = 'CLOSED_REGIME', realized_pnl: float = 0):
        """Mark the position as closed."""
        self.status = reason
        self.realized_pnl = realized_pnl
        self.closed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
