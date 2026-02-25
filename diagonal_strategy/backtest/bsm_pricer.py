"""
BSM Pricer
==========
Black-Scholes option pricing functions for generating synthetic options
in the backtest runner.
"""

import math
from scipy.stats import norm

def bs_put(S: float, K: float, T: float, v: float, r: float = 0.05) -> float:
    """Black-Scholes put price with basic volatility skew applied."""
    if T <= 0.0001 or v <= 0.0001:
        return max(0.0, K - S)
        
    # Apply synthetic volatility skew: OTM puts get higher IV
    # Base v is ATM volatility. Skew adds ~1 volatility point per 1% OTM.
    moneyness = K / S
    if moneyness < 1.0:
        skew_adj = 1.0 + ((1.0 - moneyness) * 0.5) # e.g. 20% OTM -> 1.1x IV multiplier
        v = v * skew_adj
        
    try:
        d1 = (math.log(S / K) + (r + 0.5 * v**2) * T) / (v * math.sqrt(T))
        d2 = d1 - v * math.sqrt(T)
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    except:
        return max(0.0, K - S)

def put_delta(S: float, K: float, T: float, v: float, r: float = 0.05) -> float:
    """Black-Scholes put delta."""
    if T <= 0.0001 or v <= 0.0001:
        return -1.0 if S < K else 0.0
    try:
        d1 = (math.log(S / K) + (r + 0.5 * v**2) * T) / (v * math.sqrt(T))
        return norm.cdf(d1) - 1.0
    except:
        return -1.0 if S < K else 0.0

def put_strike(S: float, delta_target: float, iv: float, dte: int, r: float = 0.05) -> float:
    """Find strike for a target put delta."""
    T = dte / 365.0
    if T <= 0: return S
    
    # Delta of a put is approximately N(d1) - 1
    # So N(d1) = delta_target + 1
    nd1 = delta_target + 1.0
    
    if nd1 <= 0.0001: nd1 = 0.0001
    if nd1 >= 0.9999: nd1 = 0.9999
    
    d1 = norm.ppf(nd1)
    ln_s_k = d1 * iv * math.sqrt(T) - (r + 0.5 * iv**2) * T
    K = S / math.exp(ln_s_k)
    return round(K * 2) / 2 # Round to nearest 0.5 strike
