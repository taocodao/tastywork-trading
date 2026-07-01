"""
EMA-CCI-MACD Types
===================
Data structures for the ML-enhanced hybrid architecture.
Separates the deterministic setup candidate from the ML score.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class SignalCandidate:
    """A technical setup emitted by the deterministic rules engine."""
    symbol: str
    timeframe: str
    direction: str          # "BUY" or "SELL"
    timestamp: str          # ISO format string
    entry_price: float
    stop_loss: float
    ema1_value: float
    ema2_value: float
    ema3_value: float
    cci_value: float
    macd_hist: float
    conditions_met: int = 5
    
    # ML & Context (populated downstream)
    features: Optional[Dict[str, Any]] = None
    ml_score: Optional[float] = None
    regime: Optional[str] = None
    publish_decision: Optional[bool] = None
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "timestamp": self.timestamp,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "ema1_value": self.ema1_value,
            "ema2_value": self.ema2_value,
            "ema3_value": self.ema3_value,
            "cci_value": self.cci_value,
            "macd_hist": self.macd_hist,
            "features": self.features,
            "ml_score": self.ml_score,
            "regime": self.regime,
            "publish_decision": self.publish_decision
        }
