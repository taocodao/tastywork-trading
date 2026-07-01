"""
EMA-CCI-MACD Signal Publisher
=============================
Publishes signals to the RDS database and notifies TradeMind frontend.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import uuid
import logging
from typing import Optional

# Import base signal structures from the publisher module
from .base import BaseSignal

logger = logging.getLogger(__name__)

@dataclass
class EMACCIMACDEntrySignal(BaseSignal):
    direction: str
    entry_price: float
    stop_loss: float
    cci_value: float
    macd_hist: float
    ema1_value: float
    timeframe: str
    ml_score: Optional[float] = None
    regime: Optional[str] = None
    model_version: Optional[str] = None

def publish_ema_cci_macd_signal(candidate, config) -> str:
    """
    Converts a SignalCandidate to a Publisher Signal and saves it.
    """
    signal_id = f"ema-{candidate.symbol}-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
    
    # Calculate expiration (e.g. 3 bars from now)
    try:
        minutes = int(candidate.timeframe.replace('m', '')) if 'm' in candidate.timeframe else 60
    except ValueError:
        minutes = 60
        
    expires = datetime.utcnow() + timedelta(minutes=minutes * 3)
    
    signal = EMACCIMACDEntrySignal(
        id=signal_id,
        symbol=candidate.symbol,
        strategy="EMA_CCI_MACD",
        status="active",
        created_at=datetime.utcnow(),
        expires_at=expires,
        metadata={
            "conditions_met": candidate.conditions_met,
            "ema2_value": candidate.ema2_value,
            "ema3_value": candidate.ema3_value,
        },
        direction=candidate.direction,
        entry_price=candidate.entry_price,
        stop_loss=candidate.stop_loss,
        cci_value=candidate.cci_value,
        macd_hist=candidate.macd_hist,
        ema1_value=candidate.ema1_value,
        timeframe=candidate.timeframe,
        ml_score=candidate.ml_score,
        regime=candidate.regime,
        model_version="v1" if candidate.ml_score is not None else None
    )
    
    # TODO: In the real environment, this connects to your RDS/Supabase database.
    # We will log it here so we know the publisher is triggered.
    logger.info(f"[RDS PUBLISH] Generated signal ID: {signal.id} for {signal.symbol} {signal.direction}")
    logger.info(f"  ML Confidence: {signal.ml_score} | Regime: {signal.regime}")
    
    # TODO: Make the HTTP POST call to config.alerts.trademind_endpoint 
    # to trigger the SSE in TradeMind.
    
    return signal.id
