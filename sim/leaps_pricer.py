import numpy as np
from scipy.stats import norm

def get_black_scholes_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """
    Calculate the Black-Scholes price for a European Call option.
    
    :param S: Current stock price (e.g., QQQ close)
    :param K: Strike price (e.g., atm strike)
    :param T: Time to expiration in years (e.g., 365/365 = 1.0)
    :param r: Risk-free interest rate (e.g., 0.05 for 5%)
    :param sigma: Volatility of the underlying asset (e.g., VIX/100)
    :return: Call option price
    """
    if T <= 0:
        return max(0.0, S - K)
        
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    call_price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return call_price

def estimate_leaps_price(qqq_price: float, vix_price: float, dte: int = 365, is_bull_regime: bool = True) -> float:
    """
    Estimate the mid price of a roughly ATM QQQ LEAPS Call option.
    Uses VIX as a proxy for implied volatility (adjusted slightly since options are usually priced higher than spot VIX).
    """
    S = qqq_price
    K = qqq_price  # Assume we buy ATM
    T = dte / 365.25
    r = 0.045      # Assume roughly 4.5% risk-free rate in this period
    
    # VIX represents 30-day IV on S&P 500. 
    # QQQ IV is typically a bit higher than S&P IV, and 1-year IV is usually 
    # slightly higher or lower depending on term structure.
    # We add a 15% bump to VIX to approximate QQQ LEAPS IV.
    sigma = (vix_price * 1.15) / 100.0 
    
    # Floor vol at 15% to avoid weird BS pricing at extreme lows
    sigma = max(0.15, sigma)
    
    return get_black_scholes_call_price(S, K, T, r, sigma)
