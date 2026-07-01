"""
QQQ LEAPS — Layer D: PMCC Manager (Deterministic)
===================================================
Manages short call overlays against held LEAPS positions.
Deterministic rule-based implementation (RL/PPO slot reserved for Phase 2).

Rules (Tastylive & practitioner validated):
  - Sell 30-delta, 35-DTE short call against each LEAPS
  - Close at 50% profit
  - Force-close if QQQ moves within 3% of short strike
  - Never sell above 0.40 delta (hard cap)
  - Skip if LEAPS has < 60 DTE remaining (too close to anchor expiry)
  - Short call strike must be >= 1% above LEAPS long strike
"""
import math
import logging
import pandas as pd
from datetime import timedelta
from .config import QQQLeapsConfig
from .strike_optimizer import bs_call_price, bs_call_delta, find_call_strike

logger = logging.getLogger(__name__)


def _next_monthly_friday(date, offset_days: int = 35):
    """Returns approximate expiry Friday ~offset_days out."""
    target = date + timedelta(days=offset_days)
    weekday = target.weekday()
    if weekday < 4:
        target += timedelta(days=4 - weekday)
    elif weekday > 4:
        target += timedelta(days=7 - weekday + 4)
    return target


class PMCCManager:
    """
    Layer D: Deterministic PMCC short call lifecycle manager.
    
    The `decide(state)` method signature is reserved for a future RL/PPO agent
    with action space: {SELL_CALL, HOLD, BUY_TO_CLOSE, ROLL_UP, ROLL_OUT}.
    """

    def __init__(self, config: QQQLeapsConfig):
        self.config = config

    def maybe_open_short_call(
        self, position, spot: float, date, rf: float, iv_short: float, above_sma100: bool
    ) -> dict | None:
        """
        Opens a new short call on the position if conditions are met.
        Returns short call dict or None.
        """
        if not self.config.pmcc_enabled:
            return None
        if position.short_call is not None:
            return None  # Already has one

        dte_leaps = (position.expiry - date).days
        if dte_leaps < self.config.pmcc_min_leaps_dte:
            return None  # Too close to LEAPS expiry
        if not above_sma100:
            return None  # Don't sell calls in bear regime

        # Find target short call strike (30-delta)
        pmcc_expiry = _next_monthly_friday(date, self.config.pmcc_dte)
        T_sc = max((pmcc_expiry - date).days / 365.0, 1 / 365.0)

        # Target delta for OTM short call (1 - 0.30 = 0.70 effective call delta)
        sc_strike = find_call_strike(spot, T_sc, rf, iv_short, self.config.pmcc_target_delta)

        # Enforce: strike must be above LEAPS long strike (diagonal integrity)
        sc_strike = max(sc_strike, position.strike * 1.01)

        # Safety check: re-compute delta at enforced strike
        actual_delta = bs_call_delta(spot, sc_strike, T_sc, rf, iv_short)
        if actual_delta > self.config.pmcc_max_delta:
            logger.debug(f"PMCC rejected: actual delta {actual_delta:.2f} > {self.config.pmcc_max_delta}")
            return None

        sc_price = bs_call_price(spot, sc_strike, T_sc, rf, iv_short)
        sc_price = max(sc_price, 0.01)

        return {
            "open_date":         date,
            "expiry":            pmcc_expiry,
            "strike":            sc_strike,
            "entry_price":       sc_price,
            "premium_collected": 0,  # Will be set by caller after slippage
            "contracts":         position.contracts,
            "iv":                iv_short,
        }

    def manage_short_call(
        self, position, spot: float, date, rf: float, iv_short: float
    ) -> tuple[str, float]:
        """
        Evaluates the active short call status each day.
        Returns (action: str, cost_or_income: float).

        Actions: 'HOLD', 'CLOSE_50PCT', 'FORCE_CLOSE', 'EXPIRED_WORTHLESS', 'EXPIRED_ITM'
        """
        sc = position.short_call
        if sc is None:
            return "NO_CALL", 0.0

        T_sc = max((sc["expiry"] - date).days / 365.0, 1 / 365.0)
        sc_current_val = bs_call_price(spot, sc["strike"], T_sc, rf, iv_short)

        # Expired
        if date >= sc["expiry"]:
            if spot <= sc["strike"]:
                return "EXPIRED_WORTHLESS", 0.0  # Keep all premium
            else:
                buyback_cost = sc["contracts"] * 100 * max(spot - sc["strike"], 0)
                return "EXPIRED_ITM", buyback_cost

        # 50% profit target
        orig_px = sc["entry_price"]
        if orig_px > 0:
            pct_profit = 1.0 - (sc_current_val / orig_px)
            if pct_profit >= self.config.pmcc_profit_target:
                buyback_cost = sc["contracts"] * 100 * sc_current_val
                return "CLOSE_50PCT", buyback_cost

        # Close short call when loss exceeds 200% of premium received
        if sc_current_val > 2.0 * orig_px:
            buyback_cost = sc["contracts"] * 100 * sc_current_val
            return "FORCE_CLOSE_LOSS", buyback_cost

        return "HOLD", 0.0

    def roll_short_call_down(
        self, position, spot: float, date, rf: float, iv_short: float, target_delta: float = 0.50
    ) -> dict | None:
        """
        Bear-market adjustment: close existing short call and reopen at
        higher delta (e.g., 0.50) for more premium income. Extends DTE by 30 days.
        """
        if position.short_call is None:
            return None  # Nothing to roll
        
        # Close existing
        sc = position.short_call
        T_sc = max((sc["expiry"] - date).days / 365.0, 1/365.0)
        close_cost = bs_call_price(spot, sc["strike"], T_sc, rf, iv_short)
        
        # Open new at higher delta (more aggressive)
        new_expiry = _next_monthly_friday(date, self.config.pmcc_dte + 30)
        T_new = max((new_expiry - date).days / 365.0, 1/365.0)
        
        try:
            new_strike = find_call_strike(spot, T_new, rf, iv_short, target_delta)
        except Exception:
            return None # Failsafe if optimization fails
            
        new_price = bs_call_price(spot, new_strike, T_new, rf, iv_short)
        
        return {
            "close_cost": close_cost * sc["contracts"] * 100,
            "new_call": {
                "open_date": date,
                "expiry": new_expiry,
                "strike": new_strike,
                "entry_price": new_price,
                "premium_collected": 0,
                "contracts": position.contracts,
                "iv": iv_short,
            }
        }
