from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict

@dataclass
class TurboCoreEntrySignal:
    timestamp: str
    symbol: str
    action: str  # e.g., 'REBALANCE'
    strategy: str = "TQQQ_TURBOCORE"
    
    # ML Outputs
    ml_regime: str = "SIDEWAYS"
    ml_confidence: float = 0.5
    
    # Base Triggers
    ema_signal: int = 0
    sma200_gate: bool = True
    
    # Portfolio Allocation Matrix (%)
    allocation_qqq: float = 0.0
    allocation_qld: float = 0.0
    allocation_tqqq: float = 0.0
    allocation_sgov: float = 1.0
    
    # Optional metadata
    rationale: str = ""
    
    def to_dict(self) -> dict:
        import uuid
        return {
            "id": str(uuid.uuid4()),
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "action": self.action,
            "strategy": self.strategy,
            "type": "REBALANCE",  # Standardized for DB schema
            "direction": "LONG",  # We are always long something
            "confidence": self.ml_confidence,
            "rationale": self.rationale,
            
            # Pack custom TurboCore fields into JSON structure
            # (Matches DB schema 'legs' or dynamic 'cost' fields on Vercel)
            "legs": [
                {"symbol": "QQQ", "target_pct": self.allocation_qqq},
                {"symbol": "QLD", "target_pct": self.allocation_qld},
                {"symbol": "TQQQ", "target_pct": self.allocation_tqqq},
                {"symbol": "SGOV", "target_pct": self.allocation_sgov}
            ],
            "cost": 0.0,
            "capital_required": 1000.0, # Dummy for UI compatibility initially
            "regime": self.ml_regime,
            "ema_signal": self.ema_signal,
            "sma200_gate": self.sma200_gate
        }

def publish_turbocore_rebalance_signal(
    regime: str,
    confidence: float,
    alloc_dict: Dict[str, float],
    rationale: str,
    ema_signal: int,
    sma200_gate: bool
):
    import logging
    logger = logging.getLogger(__name__)
    
    sig = TurboCoreEntrySignal(
        timestamp=datetime.utcnow().isoformat() + "Z",
        symbol="TQQQ_PORT",
        action="REBALANCE",
        ml_regime=regime,
        ml_confidence=confidence,
        allocation_qqq=alloc_dict.get("QQQ", 0.0),
        allocation_qld=alloc_dict.get("QLD", 0.0),
        allocation_tqqq=alloc_dict.get("TQQQ", 0.0),
        allocation_sgov=alloc_dict.get("SGOV", 1.0),
        rationale=rationale,
        ema_signal=ema_signal,
        sma200_gate=sma200_gate
    )
    
    data = sig.to_dict()
    logger.info(f"Publishing TurboCore Signal: {regime} | Conf: {confidence:.2f} | TQQQ: {sig.allocation_tqqq*100}%")
    
    # Save to PostgreSQL Base
    try:
        from src.earnings_intelligence.database import SignalRepository
        repo = SignalRepository()
        try:
            repo.save_signal(data)
            logger.info("DB Save success: TurboCore Rebalance")
        finally:
            repo.session.close()
    except Exception as e:
        logger.error(f"DB Save failed for TurboCore: {e}")
        
    return data
