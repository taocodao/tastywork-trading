"""
TQQQ Signal Publisher
=====================
Publishing signals for the VIX-Adaptive TQQQ Spread Strategy.
Three signal types:
  - TQQQSpreadEntrySignal  : open a new put credit spread
  - TQQQLegOutSignal       : buy back the short put, retain the long
  - TQQQLongPutSellSignal  : take profit or abandon the retained long put

All classes extend BaseSignal for compatibility with the unified signal router.
"""

import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from signal_publisher.base import BaseSignal

logger = logging.getLogger(__name__)

# ── Re-export convenience functions ──────────────────────────────────────────

def publish_tqqq_entry_signal(
    short_strike: float,
    long_strike: float,
    expiration: str,
    credit: float,
    regime: str,
    vix_direction: str,
    confidence: float,
    quantity: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
) -> "TQQQSpreadEntrySignal":
    sig = TQQQSpreadEntrySignal(
        id=str(uuid.uuid4()),
        symbol="TQQQ",
        strategy="tqqq_vix_adaptive",
        status="pending",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=6),
        short_strike=short_strike,
        long_strike=long_strike,
        expiration=expiration,
        credit=credit,
        regime=regime,
        vix_direction=vix_direction,
        confidence=confidence,
        quantity=quantity,
        metadata=metadata or {},
    )
    logger.info(
        f"[TQQQ ENTRY] Short:{short_strike}P / Long:{long_strike}P "
        f"| Credit:${credit:.2f} | Conf:{confidence:.0%} | {expiration}"
    )
    return sig


def publish_tqqq_legout_signal(
    position_id: str,
    short_strike: float,
    expiration: str,
    short_put_buyback_price: float,
    long_put_value: float,
    regime: str,
    vix_direction: str,
    confidence: float,
) -> "TQQQLegOutSignal":
    sig = TQQQLegOutSignal(
        id=str(uuid.uuid4()),
        symbol="TQQQ",
        strategy="tqqq_vix_adaptive",
        status="pending",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=2),
        position_id=position_id,
        short_strike=short_strike,
        expiration=expiration,
        short_put_buyback_price=short_put_buyback_price,
        long_put_value_at_legout=long_put_value,
        regime=regime,
        vix_direction=vix_direction,
        confidence=confidence,
    )
    logger.info(
        f"[TQQQ LEG-OUT] {short_strike}P buyback @ ${short_put_buyback_price:.2f} "
        f"| Long put value: ${long_put_value:.2f} | Regime: {regime}"
    )
    return sig


def publish_tqqq_long_put_signal(
    position_id: str,
    long_strike: float,
    expiration: str,
    current_value: float,
    action: str,         # "SELL" or "ABANDON"
    reason: str,
) -> "TQQQLongPutSellSignal":
    sig = TQQQLongPutSellSignal(
        id=str(uuid.uuid4()),
        symbol="TQQQ",
        strategy="tqqq_vix_adaptive",
        status="pending",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=2),
        position_id=position_id,
        long_strike=long_strike,
        expiration=expiration,
        current_value=current_value,
        action=action,
        reason=reason,
    )
    logger.info(
        f"[TQQQ LONG-PUT {action}] {long_strike}P @ ${current_value:.2f} | Reason: {reason}"
    )
    return sig


# ── Signal dataclasses ────────────────────────────────────────────────────────

@dataclass
class TQQQSpreadEntrySignal(BaseSignal):
    """Signal to open a new TQQQ vertical put credit spread."""
    short_strike: float = 0.0
    long_strike:  float = 0.0
    expiration:   str   = ""
    credit:       float = 0.0
    regime:       str   = ""
    vix_direction: str  = ""
    confidence:   float = 0.0
    quantity:     int   = 1

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "short_strike": self.short_strike,
            "long_strike":  self.long_strike,
            "expiration":   self.expiration,
            "credit":       self.credit,
            "regime":       self.regime,
            "vix_direction": self.vix_direction,
            "confidence":   self.confidence,
            "quantity":     self.quantity,
        })
        return base


@dataclass
class TQQQLegOutSignal(BaseSignal):
    """Signal to buy back the short put and retain the long put."""
    position_id:               str   = ""
    short_strike:              float = 0.0
    expiration:                str   = ""
    short_put_buyback_price:   float = 0.0
    long_put_value_at_legout:  float = 0.0
    regime:                    str   = ""
    vix_direction:             str   = ""
    confidence:                float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "position_id":              self.position_id,
            "short_strike":             self.short_strike,
            "expiration":               self.expiration,
            "short_put_buyback_price":  self.short_put_buyback_price,
            "long_put_value_at_legout": self.long_put_value_at_legout,
            "regime":                   self.regime,
            "vix_direction":            self.vix_direction,
            "confidence":               self.confidence,
        })
        return base


@dataclass
class TQQQLongPutSellSignal(BaseSignal):
    """Signal to sell (profit) or abandon (theta decay) the retained long put."""
    position_id:   str   = ""
    long_strike:   float = 0.0
    expiration:    str   = ""
    current_value: float = 0.0
    action:        str   = "SELL"   # "SELL" | "ABANDON"
    reason:        str   = ""

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "position_id":   self.position_id,
            "long_strike":   self.long_strike,
            "expiration":    self.expiration,
            "current_value": self.current_value,
            "action":        self.action,
            "reason":        self.reason,
        })
        return base
