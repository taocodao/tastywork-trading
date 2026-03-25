
from sqlalchemy import Column, String, Boolean, DateTime, Float, Integer
from datetime import datetime
import uuid
from .db import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=True)
    name = Column(String, nullable=True)
    
    # Tastytrade Credentials (Encrypted)
    tt_refresh_token = Column(String, nullable=True)
    tt_account_number = Column(String, nullable=True)
    
    # Risk Profile (kept for backwards compatibility with other strategies)
    risk_level = Column(String, default="MEDIUM") # LOW, MEDIUM, HIGH
    investment_amount = Column(Float, default=10000.0)
    current_nav = Column(Float, nullable=True)  # Updated daily from TT API
    max_daily_trades = Column(Integer, default=5)
    auto_approve_enabled = Column(Boolean, default=False)
    
    # Strategy settings
    zebra_enabled = Column(Boolean, default=True)
    iv_strategy_enabled = Column(Boolean, default=False)  # IV-Switching Composite Strategy
    
    # Metadata
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_trade_at = Column(DateTime, nullable=True)
