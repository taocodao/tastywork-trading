import math
from scipy.stats import norm

def bs_call_price(S, K, T, r, sigma):
    """European call via Black-Scholes."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)

def bs_put_price(S, K, T, r, sigma):
    """European put via Black-Scholes."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def bs_call_delta(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1)

def bs_put_delta(S, K, T, r, sigma):
    return bs_call_delta(S, K, T, r, sigma) - 1.0

def find_strike_for_delta(S, T, r, sigma, target_delta, option_type='call'):
    """Binary search for strike at target delta."""
    lo, hi = S * 0.30, S * 1.40
    for _ in range(80):
        mid = (lo + hi) / 2
        if option_type == 'call':
            d = bs_call_delta(S, mid, T, r, sigma)
            if abs(d - target_delta) < 1e-4:
                return mid
            lo, hi = (mid, hi) if d > target_delta else (lo, mid)
        else:
            d = abs(bs_put_delta(S, mid, T, r, sigma))
            if abs(d - target_delta) < 1e-4:
                return mid
            lo, hi = (lo, mid) if d > target_delta else (mid, hi)
    return mid

# IV calibration constants (Perplexity-validated 2026-03-22)
TQQQ_ATM_HV_MULT    = 1.20    # ATM IV = max(HV20 * 1.2, VIX * 3)
TQQQ_LEVERAGE_FLOOR = 3.00    # TQQQ: leverage factor on VIX
TQQQ_OTM_SKEW       = 1.30    # 10-delta OTM put skew premium
QQQ_LEAPS_IV_SCALE  = 1.10    # 1y QQQ IV = VIX * 1.10 (term premium; no ITM discount)
QQQ_PMCC_IV_SCALE   = 1.08    # OTM short call: VIX * 1.08

def tqqq_put_iv(hv20, vix):
    atm  = max(hv20 * TQQQ_ATM_HV_MULT, vix / 100 * TQQQ_LEVERAGE_FLOOR)
    return min(atm * TQQQ_OTM_SKEW, 3.0)

def qqq_leaps_call_iv(vix):
    return vix / 100 * QQQ_LEAPS_IV_SCALE

def qqq_short_call_iv(vix):
    return vix / 100 * QQQ_PMCC_IV_SCALE

# Slippage
SLIPPAGE_PER_SIDE = 1.50   # $/contract per leg
COMMISSION        = 1.00   # $/contract
