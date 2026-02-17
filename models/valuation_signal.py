from sqlalchemy import Column, Integer, String, Float, Date, DateTime
from datetime import datetime
from .db import Base

class ValuationSignal(Base):
    """
    Stores daily fundamental valuation signals from GravityEngine.
    Used for audit trails and historical 'Gravity Line' visualization.
    """
    __tablename__ = "valuation_signals"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    analysis_date = Column(Date, nullable=False)
    
    # Market Data
    current_price = Column(Float, nullable=False)
    iv_percentile = Column(Float)
    
    # Fundamental Gravity Metrics
    fair_value_price = Column(Float, nullable=False)  # The "EPS Gravity Line"
    margin_of_safety_pct = Column(Float)              # (FV - Price) / FV
    
    # Details
    trailing_eps = Column(Float)
    forward_eps_estimate = Column(Float)
    sector = Column(String(50))
    
    # AI Context
    regime_tag = Column(String(20))     # UNDERVALUED | FAIR | OVERVALUED | BUBBLE
    confidence_score = Column(Float)    # 0.0 - 1.0
    
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ValuationSignal(symbol={self.symbol}, date={self.analysis_date}, mos={self.margin_of_safety_pct:.2%})>"
