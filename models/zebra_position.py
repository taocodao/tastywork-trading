
from sqlalchemy import Column, String, Boolean, DateTime, Float, Integer, ForeignKey
from datetime import datetime
import uuid
from .db import Base

class ZebraPosition(Base):
    __tablename__ = "zebra_positions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"))
    
    # Signal Context
    signal_id = Column(String) # Link back to original signal
    symbol = Column(String)
    direction = Column(String) # LONG or SHORT
    strategy = Column(String, default="ZEBRA")
    
    # Entry
    entry_date = Column(DateTime, default=datetime.utcnow)
    entry_price = Column(Float) # Net Debit per contract
    contracts = Column(Integer)
    capital_deployed = Column(Float) # contracts * entry_price * 100
    
    # Live State
    current_price = Column(Float, nullable=True)
    high_watermark = Column(Float, nullable=True)
    unrealized_pnl = Column(Float, default=0.0)
    status = Column(String, default="OPEN") # OPEN, CLOSED, PENDING_EXIT
    
    # Exit
    exit_date = Column(DateTime, nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True) # TAKE_PROFIT, STOP_LOSS, TIME_EXIT, REGIME_CHANGE
    realized_pnl = Column(Float, nullable=True)
