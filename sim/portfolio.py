import math
from typing import Dict, List

class SimPortfolio:
    """
    Virtual portfolio ledger for TurboCore Pro backtesting.
    Tracks cash balance, integer share positions, and LEAPS options.
    """
    
    def __init__(self, initial_capital: float = 25000.0):
        self.cash: float = initial_capital
        # Dict[symbol, int shares]
        self.positions: Dict[str, int] = {}
        # Dict[underlying_symbol, {"qty": int, "strike": float, "dte": int, "entry_price": float}]
        self.options: Dict[str, Dict] = {}
        
    def apply_order(self, action: str, symbol: str, quantity: int, fill_price: float, date_str: str):
        """Execute a stock order and update cash and positions."""
        cost = quantity * fill_price
        
        if action == "BUY":
            # You can theoretically have momentary negative cash if margin is used,
            # but integer rounding in execute_orders prevents margin calls typically.
            self.cash -= cost
            self.positions[symbol] = self.positions.get(symbol, 0) + quantity
        elif action == "SELL":
            self.cash += cost
            current_qty = self.positions.get(symbol, 0)
            if quantity > current_qty:
                raise ValueError(f"[{date_str}] Attempting to sell {quantity} {symbol} but only hold {current_qty}")
            
            self.positions[symbol] -= quantity
            if self.positions[symbol] == 0:
                del self.positions[symbol]
                
    def apply_leaps_order(self, action: str, underlying: str, contracts: int, fill_price: float, strike: float, dte: int, date_str: str):
        """Execute a LEAPS option order (multiplier 100)."""
        cost = contracts * 100 * fill_price
        
        if action == "BUY_TO_OPEN":
            self.cash -= cost
            # For simplicity, track one LEAPS contract at a time per underlying
            self.options[underlying] = {
                "qty": contracts,
                "strike": strike,
                "dte": dte,
                "entry_price": fill_price
            }
        elif action == "SELL_TO_CLOSE":
            # Add transaction cost: $1.00 per contract to close
            self.cash += (cost - (contracts * 1.00))
            if underlying in self.options:
                del self.options[underlying]

    def total_value(self, current_prices: Dict[str, float], leaps_bs_price: float = 0.0) -> float:
        """
        Calculate Net Liquidating Value (Cash + Equity + Options).
        prices: current market prices for equities
        leaps_bs_price: current Black-Scholes mid price for the held LEAPS
        """
        equity_val = 0.0
        for sym, qty in self.positions.items():
            if sym in current_prices:
                equity_val += qty * current_prices[sym]
                
        options_val = 0.0
        for underlying, opt in self.options.items():
            options_val += opt["qty"] * 100 * leaps_bs_price
            
        return self.cash + equity_val + options_val
