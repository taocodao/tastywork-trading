"""
QQQ LEAPS — Layer E: Drawdown Guard
=====================================
Monitors live P&L per position and triggers protective overlays.
Three-tier response matching the risk mitigation plan.
"""
import logging
from dataclasses import dataclass
from enum import Enum
from .config import QQQLeapsConfig

logger = logging.getLogger(__name__)


class DrawdownAction(Enum):
    HOLD                 = "HOLD"
    ROLL_SHORT_CALL_DOWN = "ROLL_SHORT_CALL_DOWN"  # Roll from target delta -> 0.50 delta
    EXIT_POSITION        = "EXIT_POSITION"         # Structural impairment (DTE + delta)
    CLOSE_52W_LOW        = "CLOSE_52W_LOW"         # Regime change emergency exit


class DrawdownGuard:
    """
    Layer E: Protective overlay trigger logic based on structural impairment.
    AQR research validates delta degradation over simple P&L-based protective puts.
    """

    def __init__(self, config: QQQLeapsConfig):
        self.config = config

    def evaluate(
        self,
        leaps_delta: float,
        leaps_dte: int,
        spot: float,
        spot_52w_low: float,
        regime: str,
        has_active_short_call: bool,
    ) -> DrawdownAction:
        """
        Returns the appropriate structural protective action for a position.
        """
        # Tier 3: Emergency regime change (52-week low)
        if spot_52w_low > 0 and spot <= spot_52w_low * 1.001:
            logger.info(f"DrawdownGuard: Spot {spot:.2f} near 52W Low {spot_52w_low:.2f} -> CLOSE_52W_LOW")
            return DrawdownAction.CLOSE_52W_LOW

        # Tier 2: Structural impairment (Time running out + deep out of money)
        if leaps_dte < self.config.dd_dte_exit_trigger and leaps_delta < self.config.dd_delta_exit_trigger:
            logger.info(f"DrawdownGuard: delta={leaps_delta:.2f}, dte={leaps_dte} -> EXIT_POSITION")
            return DrawdownAction.EXIT_POSITION

        # Tier 1: Delta degradation -> Roll short call down for more income
        if leaps_delta < self.config.dd_delta_rolldown_trigger:
            if has_active_short_call:
                logger.info(f"DrawdownGuard: delta={leaps_delta:.2f} < {self.config.dd_delta_rolldown_trigger} -> ROLL_SHORT_CALL_DOWN")
                return DrawdownAction.ROLL_SHORT_CALL_DOWN

        return DrawdownAction.HOLD
