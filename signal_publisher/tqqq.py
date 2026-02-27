"""
TQQQ Signal Publisher
=====================
Publishing signals for the VIX-Adaptive TQQQ Spread Strategy.
Signal types:
  - TQQQSpreadEntrySignal      : open a new put credit spread
  - TQQQCallSpreadEntrySignal  : open a new bear call credit spread
  - TQQQCallSpreadCloseSignal  : close a bear call credit spread
  - TQQQLegOutSignal           : buy back the short put, retain the long
  - TQQQLongPutSellSignal      : take profit or abandon the retained long put
  - TQQQDiagonalEntrySignal    : open a diagonal swing trade
  - TQQQDiagonalExitSignal     : close or roll a diagonal swing trade

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

@dataclass
class TQQQCallSpreadEntrySignal(BaseSignal):
    """Signal to open a new TQQQ bear call credit spread."""
    short_call_strike: float = 0.0
    long_call_strike:  float = 0.0
    expiration:        str   = ""
    credit:            float = 0.0
    regime:            str   = ""
    vix_direction:     str   = ""
    confidence:        float = 0.0
    quantity:          int   = 1
    tqqq_entry_price:  float = 0.0  # For rally circuit breaker

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "short_call_strike": self.short_call_strike,
            "long_call_strike":  self.long_call_strike,
            "expiration":        self.expiration,
            "credit":            self.credit,
            "regime":            self.regime,
            "vix_direction":     self.vix_direction,
            "confidence":        self.confidence,
            "quantity":          self.quantity,
            "tqqq_entry_price":  self.tqqq_entry_price,
        })
        return base


@dataclass
class TQQQCallSpreadCloseSignal(BaseSignal):
    """Signal to close (buy-to-close) a bear call credit spread."""
    position_id: str   = ""
    reason:      str   = ""   # PROFIT_TARGET | LOSS_LIMIT | RALLY_CIRCUIT_BREAKER | DTE_EXIT
    pnl:         float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "position_id": self.position_id,
            "reason":      self.reason,
            "pnl":         self.pnl,
        })
        return base


@dataclass
class TQQQDiagonalEntrySignal(BaseSignal):
    """Signal to open a new TQQQ put diagonal swing trade."""
    anchor_strike: float = 0.0
    anchor_expiration: str = ""
    hedge_strike: float = 0.0
    hedge_expiration: str = ""
    net_credit: float = 0.0
    rsi_2: float = 0.0
    ml_prob: float = 0.0
    regime_score: int = 0
    quantity: int = 1
    risk_level: str = "Medium"

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "anchor_strike": self.anchor_strike,
            "anchor_expiration": self.anchor_expiration,
            "hedge_strike": self.hedge_strike,
            "hedge_expiration": self.hedge_expiration,
            "net_credit": self.net_credit,
            "rsi_2": self.rsi_2,
            "ml_prob": self.ml_prob,
            "regime_score": self.regime_score,
            "quantity": self.quantity,
            "risk_level": self.risk_level,
        })
        return base

@dataclass
class TQQQDiagonalExitSignal(BaseSignal):
    """Signal to close or roll a TQQQ diagonal spread."""
    position_id: str = ""
    action: str = "" # "CLOSE_ALL" or "ROLL_HEDGE"
    reason: str = ""
    pnl: float = 0.0
    days_held: int = 0
    roll_count: int = 0
    risk_level: str = "Medium"
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "position_id": self.position_id,
            "action": self.action,
            "reason": self.reason,
            "pnl": self.pnl,
            "days_held": self.days_held,
            "roll_count": self.roll_count,
            "risk_level": self.risk_level,
        })
        return base

@dataclass
class TQQQBackspreadEntrySignal(BaseSignal):
    """Signal to open a new 1x2 TQQQ call ratio backspread (Deep tranche)."""
    short_strike: float = 0.0
    long_strike: float = 0.0
    expiration: str = ""
    net_cost: float = 0.0
    rsi_2: float = 0.0
    ml_prob: float = 0.0
    regime_score: int = 0
    quantity: int = 1
    risk_level: str = "Medium"

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "short_strike": self.short_strike,
            "long_strike": self.long_strike,
            "expiration": self.expiration,
            "net_cost": self.net_cost,
            "rsi_2": self.rsi_2,
            "ml_prob": self.ml_prob,
            "regime_score": self.regime_score,
            "quantity": self.quantity,
            "risk_level": self.risk_level,
        })
        return base

def publish_tqqq_call_entry_signal(
    short_call_strike: float,
    long_call_strike: float,
    expiration: str,
    credit: float,
    regime: str,
    vix_direction: str,
    confidence: float,
    tqqq_entry_price: float,
    quantity: int = 1,
    metadata: Optional[Dict[str, Any]] = None,
) -> "TQQQCallSpreadEntrySignal":
    sig = TQQQCallSpreadEntrySignal(
        id=str(uuid.uuid4()),
        symbol="TQQQ",
        strategy="tqqq_vix_adaptive_call",
        status="pending",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=6),
        short_call_strike=short_call_strike,
        long_call_strike=long_call_strike,
        expiration=expiration,
        credit=credit,
        regime=regime,
        vix_direction=vix_direction,
        confidence=confidence,
        quantity=quantity,
        tqqq_entry_price=tqqq_entry_price,
        metadata=metadata or {},
    )
    logger.info(
        f"[TQQQ CALL ENTRY] Short:{short_call_strike}C / Long:{long_call_strike}C "
        f"| Credit:${credit:.2f} | Conf:{confidence:.0%} | {expiration}"
    )
    return sig


def publish_tqqq_call_close_signal(
    position_id: str,
    reason: str,
    pnl: float,
) -> "TQQQCallSpreadCloseSignal":
    sig = TQQQCallSpreadCloseSignal(
        id=str(uuid.uuid4()),
        symbol="TQQQ",
        strategy="tqqq_vix_adaptive_call",
        status="pending",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=2),
        position_id=position_id,
        reason=reason,
        pnl=pnl,
    )
    logger.info(
        f"[TQQQ CALL CLOSE] Pos:{position_id[:8]} | P&L:${pnl:.2f} | Reason:{reason}"
    )
    return sig


def publish_tqqq_diagonal_entry_signal(
    anchor_strike: float,
    anchor_expiration: str,
    hedge_strike: float,
    hedge_expiration: str,
    net_credit: float,
    rsi_2: float,
    ml_prob: float,
    regime_score: int,
    quantity: int = 1,
    risk_level: str = "Medium",
    metadata: Optional[Dict[str, Any]] = None,
) -> "TQQQDiagonalEntrySignal":
    sig = TQQQDiagonalEntrySignal(
        id=str(uuid.uuid4()),
        symbol="TQQQ",
        strategy="tqqq_hybrid_swing",
        status="pending",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=6),
        anchor_strike=anchor_strike,
        anchor_expiration=anchor_expiration,
        hedge_strike=hedge_strike,
        hedge_expiration=hedge_expiration,
        net_credit=net_credit,
        rsi_2=rsi_2,
        ml_prob=ml_prob,
        regime_score=regime_score,
        quantity=quantity,
        risk_level=risk_level,
        metadata=metadata or {},
    )
    logger.info(
        f"[TQQQ DIAGONAL ENTRY] Anchor:{anchor_strike}P / Hedge:{hedge_strike}P "
        f"| Net Cred:${net_credit:.2f} | RSI:{rsi_2:.1f} | ML:{ml_prob:.0%}"
    )
    return sig

def publish_tqqq_diagonal_exit_signal(
    position_id: str,
    action: str,
    reason: str,
    pnl: float,
    days_held: int,
    roll_count: int,
    risk_level: str = "Medium",
) -> "TQQQDiagonalExitSignal":
    sig = TQQQDiagonalExitSignal(
        id=str(uuid.uuid4()),
        symbol="TQQQ",
        strategy="tqqq_hybrid_swing",
        status="pending",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=2),
        position_id=position_id,
        action=action,
        reason=reason,
        pnl=pnl,
        days_held=days_held,
        roll_count=roll_count,
        risk_level=risk_level,
    )
    logger.info(
        f"[TQQQ DIAGONAL {action}] Pos:{position_id[:8]} | ({risk_level}) P&L:${pnl:.2f} "
        f"| Days:{days_held} | Rolls:{roll_count} | Reason:{reason}"
    )
    return sig

def publish_tqqq_backspread_entry_signal(
    short_strike: float,
    long_strike: float,
    expiration: str,
    net_cost: float,
    rsi_2: float,
    ml_prob: float,
    regime_score: int,
    quantity: int = 1,
    risk_level: str = "Medium",
    metadata: Optional[Dict[str, Any]] = None,
) -> "TQQQBackspreadEntrySignal":
    sig = TQQQBackspreadEntrySignal(
        id=str(uuid.uuid4()),
        symbol="TQQQ",
        strategy="tqqq_hybrid_swing",
        status="pending",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=6),
        short_strike=short_strike,
        long_strike=long_strike,
        expiration=expiration,
        net_cost=net_cost,
        rsi_2=rsi_2,
        ml_prob=ml_prob,
        regime_score=regime_score,
        quantity=quantity,
        risk_level=risk_level,
        metadata=metadata or {},
    )
    logger.info(
        f"[TQQQ BACKSPREAD ENTRY] ({risk_level}) Short:{short_strike}C / Long:{long_strike}C "
        f"| Net Cost:${net_cost:.2f} | RSI:{rsi_2:.1f} | ML:{ml_prob:.0%}"
    )
    return sig
