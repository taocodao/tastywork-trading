"""
Calendar Spreads Bot - Greeks Calculator
=========================================

Black-Scholes option pricing and Greeks calculation.
Used for spread valuation and position monitoring.
"""

import math
from dataclasses import dataclass
from typing import Tuple
from scipy.stats import norm
import numpy as np


@dataclass
class OptionGreeks:
    """Option Greeks for a single option."""
    price: float
    delta: float
    gamma: float
    theta: float  # Daily theta (negative for long options)
    vega: float
    rho: float


@dataclass
class SpreadGreeks:
    """Combined Greeks for a calendar spread."""
    spread_value: float
    net_delta: float
    net_gamma: float
    net_theta: float  # Should be positive (benefiting from time decay)
    net_vega: float
    
    @property
    def theta_advantage(self) -> float:
        """Daily $ advantage from theta decay."""
        return abs(self.net_theta) * 100  # Per contract


class BlackScholesCalculator:
    """
    Black-Scholes option pricing model.
    
    Used for calculating theoretical option prices and Greeks.
    """
    
    def __init__(self, risk_free_rate: float = 0.05):
        """
        Initialize calculator.
        
        Args:
            risk_free_rate: Annualized risk-free rate (default 5%)
        """
        self.r = risk_free_rate
    
    def _d1(self, S: float, K: float, T: float, sigma: float) -> float:
        """Calculate d1 parameter."""
        if T <= 0 or sigma <= 0:
            return 0.0
        return (math.log(S / K) + (self.r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    
    def _d2(self, S: float, K: float, T: float, sigma: float) -> float:
        """Calculate d2 parameter."""
        if T <= 0 or sigma <= 0:
            return 0.0
        return self._d1(S, K, T, sigma) - sigma * math.sqrt(T)
    
    def call_price(self, S: float, K: float, T: float, sigma: float) -> float:
        """
        Calculate call option price.
        
        Args:
            S: Current stock price
            K: Strike price
            T: Time to expiration (in years)
            sigma: Implied volatility (annualized)
        
        Returns:
            Theoretical call price
        """
        if T <= 0:
            return max(0, S - K)
        
        d1 = self._d1(S, K, T, sigma)
        d2 = self._d2(S, K, T, sigma)
        
        price = S * norm.cdf(d1) - K * math.exp(-self.r * T) * norm.cdf(d2)
        return max(0, price)
    
    def put_price(self, S: float, K: float, T: float, sigma: float) -> float:
        """Calculate put option price."""
        if T <= 0:
            return max(0, K - S)
        
        d1 = self._d1(S, K, T, sigma)
        d2 = self._d2(S, K, T, sigma)
        
        price = K * math.exp(-self.r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        return max(0, price)
    
    def delta(self, S: float, K: float, T: float, sigma: float, option_type: str = "call") -> float:
        """Calculate option delta."""
        if T <= 0:
            if option_type == "call":
                return 1.0 if S > K else 0.0
            else:
                return -1.0 if S < K else 0.0
        
        d1 = self._d1(S, K, T, sigma)
        
        if option_type == "call":
            return norm.cdf(d1)
        else:
            return norm.cdf(d1) - 1
    
    def gamma(self, S: float, K: float, T: float, sigma: float) -> float:
        """Calculate option gamma (same for calls and puts)."""
        if T <= 0 or sigma <= 0:
            return 0.0
        
        d1 = self._d1(S, K, T, sigma)
        return norm.pdf(d1) / (S * sigma * math.sqrt(T))
    
    def theta(self, S: float, K: float, T: float, sigma: float, option_type: str = "call") -> float:
        """
        Calculate option theta (daily).
        
        Returns negative value for long options (losing value over time).
        """
        if T <= 0 or sigma <= 0:
            return 0.0
        
        d1 = self._d1(S, K, T, sigma)
        d2 = self._d2(S, K, T, sigma)
        
        # First term (same for calls and puts)
        first_term = -(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
        
        if option_type == "call":
            second_term = -self.r * K * math.exp(-self.r * T) * norm.cdf(d2)
        else:
            second_term = self.r * K * math.exp(-self.r * T) * norm.cdf(-d2)
        
        # Annualized theta, convert to daily by dividing by 365
        annual_theta = first_term + second_term
        return annual_theta / 365
    
    def vega(self, S: float, K: float, T: float, sigma: float) -> float:
        """Calculate option vega (same for calls and puts)."""
        if T <= 0:
            return 0.0
        
        d1 = self._d1(S, K, T, sigma)
        # Return vega per 1% change in volatility
        return S * norm.pdf(d1) * math.sqrt(T) / 100
    
    def rho(self, S: float, K: float, T: float, sigma: float, option_type: str = "call") -> float:
        """Calculate option rho."""
        if T <= 0:
            return 0.0
        
        d2 = self._d2(S, K, T, sigma)
        
        if option_type == "call":
            return K * T * math.exp(-self.r * T) * norm.cdf(d2) / 100
        else:
            return -K * T * math.exp(-self.r * T) * norm.cdf(-d2) / 100
    
    def get_all_greeks(
        self, 
        S: float, 
        K: float, 
        T: float, 
        sigma: float, 
        option_type: str = "call"
    ) -> OptionGreeks:
        """Calculate all Greeks for an option."""
        if option_type == "call":
            price = self.call_price(S, K, T, sigma)
        else:
            price = self.put_price(S, K, T, sigma)
        
        return OptionGreeks(
            price=price,
            delta=self.delta(S, K, T, sigma, option_type),
            gamma=self.gamma(S, K, T, sigma),
            theta=self.theta(S, K, T, sigma, option_type),
            vega=self.vega(S, K, T, sigma),
            rho=self.rho(S, K, T, sigma, option_type)
        )
    
    def implied_volatility(
        self,
        option_price: float,
        S: float,
        K: float,
        T: float,
        option_type: str = "call",
        max_iterations: int = 100,
        tolerance: float = 1e-6
    ) -> float:
        """
        Calculate implied volatility using Newton-Raphson method.
        
        Args:
            option_price: Market price of the option
            S, K, T: Stock price, Strike, Time to expiry
            option_type: "call" or "put"
        
        Returns:
            Implied volatility (annualized)
        """
        if T <= 0:
            return 0.0
        
        # Initial guess
        sigma = 0.2
        
        for _ in range(max_iterations):
            if option_type == "call":
                price = self.call_price(S, K, T, sigma)
            else:
                price = self.put_price(S, K, T, sigma)
            
            vega = self.vega(S, K, T, sigma) * 100  # Convert back from per 1%
            
            if vega < tolerance:
                break
            
            diff = price - option_price
            sigma = sigma - diff / vega
            
            # Constrain sigma to reasonable range
            sigma = max(0.01, min(sigma, 5.0))
            
            if abs(diff) < tolerance:
                break
        
        return sigma


class SpreadCalculator:
    """
    Calculator for calendar spread values and Greeks.
    """
    
    def __init__(self):
        self.bs = BlackScholesCalculator()
    
    def calculate_spread(
        self,
        stock_price: float,
        strike: float,
        short_dte: int,
        long_dte: int,
        iv: float
    ) -> SpreadGreeks:
        """
        Calculate calendar spread theoretical value and Greeks.
        
        Args:
            stock_price: Current stock price
            strike: Strike price (same for both legs)
            short_dte: Days to expiry for short leg
            long_dte: Days to expiry for long leg
            iv: Implied volatility (annualized)
        
        Returns:
            SpreadGreeks with net values
        """
        # Convert DTE to years
        T_short = short_dte / 365
        T_long = long_dte / 365
        
        # Get Greeks for both legs
        short_greeks = self.bs.get_all_greeks(stock_price, strike, T_short, iv, "call")
        long_greeks = self.bs.get_all_greeks(stock_price, strike, T_long, iv, "call")
        
        # Calendar spread: LONG long-dated, SHORT short-dated
        # Net position = Long - Short
        return SpreadGreeks(
            spread_value=long_greeks.price - short_greeks.price,
            net_delta=long_greeks.delta - short_greeks.delta,
            net_gamma=long_greeks.gamma - short_greeks.gamma,
            net_theta=short_greeks.theta - long_greeks.theta,  # Positive = good
            net_vega=long_greeks.vega - short_greeks.vega
        )
    
    def calculate_profit_target(
        self,
        entry_debit: float,
        target_pct: float = 5.0
    ) -> float:
        """Calculate spread value at profit target."""
        return entry_debit * (1 + target_pct / 100)
    
    def calculate_stop_loss(
        self,
        entry_debit: float,
        stop_pct: float = -10.0
    ) -> float:
        """Calculate spread value at stop loss."""
        return entry_debit * (1 + stop_pct / 100)


if __name__ == "__main__":
    # Example: IWM calendar spread
    calc = SpreadCalculator()
    
    stock_price = 241.68
    strike = 242
    short_dte = 1  # Tomorrow
    long_dte = 7   # Next week
    iv = 0.20      # 20% implied volatility
    
    spread = calc.calculate_spread(stock_price, strike, short_dte, long_dte, iv)
    
    print("Calendar Spread Analysis")
    print("=" * 50)
    print(f"Stock: ${stock_price:.2f}, Strike: ${strike}")
    print(f"Short Leg: {short_dte} DTE, Long Leg: {long_dte} DTE")
    print(f"IV: {iv:.0%}")
    print()
    print(f"Spread Value (Net Debit): ${spread.spread_value * 100:.2f}")
    print(f"Net Delta: {spread.net_delta:.4f}")
    print(f"Net Theta: ${spread.net_theta * 100:.2f}/day (advantage)")
    print(f"Net Vega: ${spread.net_vega * 100:.2f}")
