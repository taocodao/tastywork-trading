from sqlalchemy import Column, String, Integer, Float, Date, DateTime, ForeignKey, Boolean
from datetime import datetime
from .db import Base

class DVOPosition(Base):
    """
    Tracks Deep Value Overlay (DVO) positions.
    Includes both Short Puts (Portfolio-Secured) and Long LEAPS (Premium Recycling).
    """
    __tablename__ = "dvo_positions"
    
    id = Column(String, primary_key=True)  # Broker ID or generated UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Optional for now if single-user
    symbol = Column(String(10), nullable=False)
    strategy_type = Column(String(20), nullable=False) # 'SHORT_PUT' | 'LONG_LEAPS'
    
    # Option Details
    expiration_date = Column(Date, nullable=False)
    strike_price = Column(Float, nullable=False)
    option_type = Column(String(4), nullable=False) # 'PUT' | 'CALL'
    dte_at_entry = Column(Integer)
    
    # Entry Data
    entry_date = Column(DateTime, default=datetime.utcnow)
    entry_price = Column(Float)             # Premium received (credit) or paid (debit)
    underlying_at_entry = Column(Float)
    fair_value_at_entry = Column(Float)     # From GravityEngine
    margin_of_safety_at_entry = Column(Float)
    quantity = Column(Integer, default=1)
    
    # Management
    status = Column(String(20), default="OPEN") # OPEN | CLOSED | ASSIGNED | ROLLED
    current_value = Column(Float)
    unrealized_pnl = Column(Float)
    realized_pnl = Column(Float, default=0.0)
    
    # Exit Data
    exit_date = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_reason = Column(String(50), nullable=True)
    
    # Linked Logic
    parent_position_id = Column(String, nullable=True) # For LEAPS bought with Put premium
    
    def __repr__(self):
        return f"<DVOPosition(symbol={self.symbol}, type={self.strategy_type}, strike={self.strike_price}, status={self.status})>"
