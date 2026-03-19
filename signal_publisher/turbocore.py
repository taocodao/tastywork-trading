from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict
import pytz

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

        # TurboCore signals expire at 3:00 PM ET the next trading day
        # (the scheduler runs at 3PM, so the next scan replaces this signal)
        et = pytz.timezone('US/Eastern')
        now_et = datetime.now(et)
        next_day = now_et + timedelta(days=1)
        # Skip to Monday if next day is a weekend
        while next_day.weekday() >= 5:
            next_day += timedelta(days=1)
        expires_at_et = next_day.replace(hour=15, minute=0, second=0, microsecond=0)
        expires_at_utc = expires_at_et.astimezone(pytz.utc)

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
            "expires_at": expires_at_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),

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
    sma200_gate: bool,
    strategy: str = "TQQQ_TURBOCORE"
):
    import logging
    logger = logging.getLogger(__name__)
    
    sig = TurboCoreEntrySignal(
        timestamp=datetime.utcnow().isoformat() + "Z",
        symbol="TQQQ_PORT",
        action="REBALANCE",
        strategy=strategy,
        ml_regime=regime,
        ml_confidence=confidence,
        allocation_qqq=alloc_dict.get("QQQ", 0.0),
        allocation_qld=alloc_dict.get("QLD", 0.0),
        allocation_tqqq=alloc_dict.get("QQQ_LEAPS", alloc_dict.get("TQQQ", 0.0)),
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
