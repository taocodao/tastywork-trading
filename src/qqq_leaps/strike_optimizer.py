"""
QQQ LEAPS — Layer C: Strike & Roll Optimizer
=============================================
Selects the optimal LEAPS delta/DTE combination given current regime.
Evaluates three event-driven roll triggers (replacing calendar-based annual rolls).
"""
import math
import logging
import pandas as pd
import numpy as np
from scipy.stats import norm
from .config import QQQLeapsConfig

logger = logging.getLogger(__name__)


def bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes European call price."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def bs_call_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes call delta."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1)


def find_call_strike(
    S: float, T: float, r: float, sigma: float, target_delta: float = 0.80
) -> float:
    """Binary search for call strike with a given target delta."""
    lo, hi = S * 0.30, S * 1.40
    for _ in range(80):
        mid  = (lo + hi) / 2
        d    = bs_call_delta(S, mid, T, r, sigma)
        if abs(d - target_delta) < 1e-5:
            return mid
        if d > target_delta:
            lo = mid
        else:
            hi = mid
    return S   # ATM fallback


class StrikeOptimizer:
    """
    Layer C: Selects strike/DTE for a new LEAPS and evaluates roll triggers.
    """

    def __init__(self, config: QQQLeapsConfig):
        self.config = config

    def select_entry_parameters(
        self,
        spot: float,
        rf: float,
        iv: float,
        regime: str,
        leaps_params,    # LeapsParams from regime_classifier
    ) -> dict:
        """
        Returns the best entry contract parameters for a new LEAPS position.
        Phase 1: rule-based by regime. Phase 2: GBR model.
        """
        delta  = leaps_params.delta
        dte    = leaps_params.dte
        T      = dte / 365.0
        strike = find_call_strike(spot, T, rf, iv, delta)
        price  = bs_call_price(spot, strike, T, rf, iv)

        return {
            "delta":   round(delta, 3),
            "dte":     dte,
            "T":       T,
            "strike":  round(strike, 2),
            "price":   round(max(price, 0.01), 2),
        }

    def evaluate_roll_triggers(
        self,
        position,         # LeapsPosition object
        spot: float,
        current_date,
        rf: float,
        iv: float,
    ) -> tuple:
        """
        Evaluates the three event-driven roll triggers.
        Returns (should_roll: bool, reason: str).
        """
        dte_today = (position.expiry - current_date).days
        T_current = max(dte_today / 365.0, 1 / 365.0)

        # Current delta
        current_delta = bs_call_delta(spot, position.strike, T_current, rf, iv)

        # Signal A: Delta drift too high (LEAPS lost elasticity)
        if current_delta > self.config.roll_trigger_delta_high:
            return True, f"DELTA_DRIFT({current_delta:.2f})"

        # Signal B: DTE below threshold with deep ITM status
        if dte_today < self.config.roll_trigger_dte_min and current_delta > 0.75:
            return True, f"DTE_DECAY({dte_today}d)"

        # Signal C: Underlying up 20%+ since entry
        if position.entry_spot > 0:
            gain_since_entry = (spot - position.entry_spot) / position.entry_spot
            if gain_since_entry >= self.config.roll_trigger_price_up:
                return True, f"PRICE_UP({gain_since_entry*100:.0f}%)"

        return False, ""
