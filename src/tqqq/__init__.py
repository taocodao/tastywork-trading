"""
TQQQ VIX-Adaptive Strategy
==========================
Core enums and basic configurations for the VIX-adaptive leg management strategy.
"""

from enum import Enum, auto

class TQQQStrategyState(Enum):
    """
    State machine for the TQQQ Spread strategy.

    IDLE: No position is open.
    FULL_SPREAD: The original put credit spread is fully active (short put + long put).
    LONG_PUT_ONLY: The short put was bought back (legged out); holding long put for VIX spike.
    FULL_CALL_SPREAD: A bear call credit spread is active (short call OTM + long call further OTM).
    LONG_CALL_ONLY: Short call was bought back; holding long call defensively.
    CLOSING: The position is in the process of being completely exited.
    DIAGONAL_OPEN: A put diagonal swing trade is active.
    """
    IDLE            = auto()
    FULL_SPREAD     = auto()
    LONG_PUT_ONLY   = auto()
    FULL_CALL_SPREAD = auto()   # NEW: bear call credit spread active
    LONG_CALL_ONLY  = auto()    # NEW: legged out of short call, holding long call
    CLOSING         = auto()
    DIAGONAL_OPEN   = auto()    # Put diagonal swing trade active

class MarketRegime(Enum):
    """
    VIX Regimes based on our HMM classification.
    """
    LOW_VOL = "LOW_VOL"
    NORMAL = "NORMAL"
    HIGH_VOL = "HIGH_VOL"
    CRISIS = "CRISIS"

class VIXDirection(Enum):
    """
    VIX short-term direction prediction from the Ensemble ML model.
    """
    RISING = "VIX_RISING"
    FALLING = "VIX_FALLING"
    NEUTRAL = "NEUTRAL"
