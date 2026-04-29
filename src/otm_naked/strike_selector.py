"""
OTM Naked Options — Strike Selector
======================================
Delta-based put and call strike selection using Black-Scholes.
Extends src/qqq_leaps/strike_optimizer.py with put strike support.

Usage:
    selector = OTMStrikeSelector(config)
    put_strike, put_price = selector.select_put_strike(
        S=450.0, T_years=35/365, sigma=0.25, regime="NORMAL"
    )
"""
import math
import logging
import numpy as np
from typing import Optional, Tuple
from scipy.stats import norm

from .config import OTMNakedConfig, REGIME_DELTA_MAP

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Black-Scholes primitives (standalone, no external dependency)
# ---------------------------------------------------------------------------
def _bs_d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return 0.0
    return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))


def bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes call option price."""
    if T <= 0:
        return max(S - K, 0.0)
    d1 = _bs_d1(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    return float(S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))


def bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes put option price."""
    if T <= 0:
        return max(K - S, 0.0)
    d1 = _bs_d1(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    return float(K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def bs_call_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes call delta (0 to 1)."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = _bs_d1(S, K, T, r, sigma)
    return float(norm.cdf(d1))


def bs_put_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes put delta as absolute value (0 to 1)."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S < K else 0.0
    d1 = _bs_d1(S, K, T, r, sigma)
    return float(norm.cdf(-d1))   # Put delta magnitude


def bs_all_greeks(S: float, K: float, T: float, r: float, sigma: float,
                  option_type: str = "put") -> dict:
    """Compute all Greeks for a put or call."""
    if T <= 0 or sigma <= 0:
        return {"price": 0.0, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    d1 = _bs_d1(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    phi = norm.pdf(d1)
    if option_type == "call":
        price = bs_call_price(S, K, T, r, sigma)
        delta = norm.cdf(d1)
        theta = (-(S * phi * sigma) / (2 * math.sqrt(T))
                 - r * K * math.exp(-r * T) * norm.cdf(d2)) / 365
    else:
        price = bs_put_price(S, K, T, r, sigma)
        delta = -(norm.cdf(-d1))          # Negative delta for puts
        theta = (-(S * phi * sigma) / (2 * math.sqrt(T))
                 + r * K * math.exp(-r * T) * norm.cdf(-d2)) / 365
    gamma = phi / (S * sigma * math.sqrt(T))
    vega  = S * phi * math.sqrt(T) / 100
    return {"price": price, "delta": delta, "gamma": gamma,
            "theta": theta, "vega": vega}


# ---------------------------------------------------------------------------
# Strike finder via binary search
# ---------------------------------------------------------------------------
def find_put_strike(S: float, T: float, r: float, sigma: float,
                    target_delta: float = 0.10,
                    tolerance: float = 0.005,
                    max_iter: int = 50) -> float:
    """
    Binary search for put strike with given absolute delta.

    Args:
        S:            Spot price
        T:            Time to expiry in years
        r:            Risk-free rate
        sigma:        Implied volatility (annualized)
        target_delta: Absolute delta target (e.g. 0.10 = 10-delta put)
        tolerance:    Acceptable delta error
        max_iter:     Max iterations

    Returns:
        Strike price K such that |put_delta(K)| ≈ target_delta
    """
    # Search range: 50% to 99% of spot for OTM puts
    lo, hi = S * 0.50, S * 0.99

    for _ in range(max_iter):
        K = (lo + hi) / 2
        d = bs_put_delta(S, K, T, r, sigma)
        if abs(d - target_delta) < tolerance:
            return round(K, 2)
        # Higher strike → higher put delta; lower strike → lower delta
        if d < target_delta:
            lo = K       # Need higher strike (closer to ATM)
        else:
            hi = K       # Need lower strike (farther OTM)

    return round((lo + hi) / 2, 2)


def find_call_strike(S: float, T: float, r: float, sigma: float,
                     target_delta: float = 0.10,
                     tolerance: float = 0.005,
                     max_iter: int = 50) -> float:
    """
    Binary search for call strike with given delta.

    Returns:
        Strike price K such that call_delta(K) ≈ target_delta
    """
    # Search range: 101% to 150% of spot for OTM calls
    lo, hi = S * 1.001, S * 1.50

    for _ in range(max_iter):
        K = (lo + hi) / 2
        d = bs_call_delta(S, K, T, r, sigma)
        if abs(d - target_delta) < tolerance:
            return round(K, 2)
        # Higher strike → lower call delta
        if d > target_delta:
            lo = K       # Need higher strike (farther OTM)
        else:
            hi = K       # Need lower strike (closer to ATM)

    return round((lo + hi) / 2, 2)


# ---------------------------------------------------------------------------
# OTM Strike Selector (regime-aware)
# ---------------------------------------------------------------------------
class OTMStrikeSelector:
    """
    Selects optimal put/call strikes based on:
    - VIX regime → delta target from REGIME_DELTA_MAP
    - BS binary search for precise strike
    - DTE from regime table
    """

    def __init__(self, config: Optional[OTMNakedConfig] = None):
        self.config = config or OTMNakedConfig()

    def get_regime_params(self, regime: str) -> dict:
        """Fetch delta, DTE params for the current VIX regime."""
        return REGIME_DELTA_MAP.get(regime, REGIME_DELTA_MAP["NORMAL"])

    def select_put_strike(
        self,
        S: float,
        T_years: float,
        sigma: float,
        regime: str = "NORMAL",
        rf: float = 0.045,
    ) -> Tuple[float, float, dict]:
        """
        Select optimal put strike and compute BS price + Greeks.

        Args:
            S:       Spot price
            T_years: Time to expiry in years
            sigma:   Implied vol
            regime:  VIX regime string
            rf:      Risk-free rate

        Returns:
            (strike, premium, greeks_dict)
        """
        params       = self.get_regime_params(regime)
        target_delta = params.get("put_delta", self.config.put_delta_target)

        if target_delta <= 0:
            logger.warning(f"Regime {regime} has put_delta=0; no put trade.")
            return 0.0, 0.0, {}

        strike  = find_put_strike(S, T_years, rf, sigma, target_delta,
                                  tolerance=self.config.delta_tolerance / 2)
        greeks  = bs_all_greeks(S, strike, T_years, rf, sigma, "put")
        premium = greeks["price"]

        logger.debug(f"PUT  strike={strike:.2f} delta={greeks['delta']:.3f} "
                     f"premium={premium:.3f} regime={regime}")
        return strike, premium, greeks

    def select_call_strike(
        self,
        S: float,
        T_years: float,
        sigma: float,
        regime: str = "NORMAL",
        rf: float = 0.045,
    ) -> Tuple[float, float, dict]:
        """
        Select optimal call strike and compute BS price + Greeks.
        """
        params       = self.get_regime_params(regime)
        target_delta = params.get("call_delta", self.config.call_delta_target)

        if target_delta <= 0:
            logger.warning(f"Regime {regime} has call_delta=0; no call trade.")
            return 0.0, 0.0, {}

        strike  = find_call_strike(S, T_years, rf, sigma, target_delta,
                                   tolerance=self.config.delta_tolerance / 2)
        greeks  = bs_all_greeks(S, strike, T_years, rf, sigma, "call")
        premium = greeks["price"]

        logger.debug(f"CALL strike={strike:.2f} delta={greeks['delta']:.3f} "
                     f"premium={premium:.3f} regime={regime}")
        return strike, premium, greeks

    def select_dte(self, regime: str) -> int:
        """Return target DTE from regime table."""
        params = self.get_regime_params(regime)
        dte    = params.get("dte", self.config.dte_target)
        return max(self.config.dte_min, min(dte, self.config.dte_max))

    def estimate_iv(self, hv_20: float, vix: float) -> float:
        """
        Estimate single-stock IV when live IV is unavailable.
        Uses HV20 scaled by (VIX / VIX_historical_mean).
        """
        vix_scale = vix / 18.0       # Long-term VIX mean ≈ 18
        iv_est    = hv_20 * vix_scale
        return float(np.clip(iv_est, 0.05, 2.0))   # Clamp 5%–200%
