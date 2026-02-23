"""
Tail Hedge Manager
==================

Optimization 5 from Strategy Report:
Allocates 1-2% of annual premium income to purchase 20-25% OTM SPY puts 
expiring in ~90 days, providing a dedicated crash hedge.
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.theta_spreads.options_analyzer import OptionsAnalyzer

logger = logging.getLogger(__name__)

@dataclass
class TailHedgeCandidate:
    symbol: str
    strike: float
    expiration: date
    dte: int
    premium: float
    capital_cost: float
    pct_otm: float
    rationale: str

class TailHedgeManager:
    """
    Manages the quarterly "insurance policy" for the Dual-Core portfolio.
    """
    def __init__(self, target_symbol: str = "SPY"):
        self.target_symbol = target_symbol
        
    def calculate_hedge_budget(self, portfolio_size: float, annual_return_target_pct: float = 0.15) -> float:
        """
        Calculates the quarterly budget available for hedges.
        1-2% of ANNUAL premium income.
        """
        expected_annual_income = portfolio_size * annual_return_target_pct
        annual_hedge_budget = expected_annual_income * 0.015 # 1.5% average
        return annual_hedge_budget / 4.0 # Quarterly budget
        
    def scan_hedge_candidates(
        self, 
        current_price: float, 
        vix_level: float, 
        chain_data: List[Dict],
        quarterly_budget: float
    ) -> List[TailHedgeCandidate]:
        """
        Scans for 90-day, 20-25% OTM SPY puts.
        """
        logger.info(f"Scanning Tail Hedges for {self.target_symbol} (VIX: {vix_level:.1f})")
        
        candidates = []
        target_strike_max = current_price * 0.80 # 20% OTM
        target_strike_min = current_price * 0.75 # 25% OTM
        
        for opt in chain_data:
            if opt.get('type') != 'P':
                continue
                
            strike = opt.get('strike', 0)
            if strike > target_strike_max or strike < target_strike_min:
                continue
                
            expiration_str = opt.get('expiration')
            try:
                exp_date = datetime.strptime(expiration_str, '%Y-%m-%d').date()
            except:
                continue
                
            dte = (exp_date - datetime.now().date()).days
            if dte < 75 or dte > 105: # ~ 90 days
                continue
                
            mid_price = (opt.get('bid', 0) + opt.get('ask', 0)) / 2
            if mid_price <= 0.0:
                continue
                
            capital_cost = mid_price * 100
            
            # VIX dependent sizing logic (Optimization 5)
            # If VIX is very low, buy more protection (puts are cheap).
            # If VIX > 30, protection is expensive, reduce purchase.
            budget_multiplier = 1.0
            if vix_level < 15.0:
                budget_multiplier = 1.5
            elif vix_level > 30.0:
                budget_multiplier = 0.5
                
            adjusted_budget = quarterly_budget * budget_multiplier
            
            # How many contracts can we buy?
            contracts_affordable = int(adjusted_budget // capital_cost)
            if contracts_affordable == 0:
                # Need at least 1, maybe budget is too small
                if capital_cost < adjusted_budget * 1.5: 
                    contracts_affordable = 1
                else:
                    continue
                    
            pct_otm = (current_price - strike) / current_price
            
            candidates.append(TailHedgeCandidate(
                symbol=self.target_symbol,
                strike=strike,
                expiration=exp_date,
                dte=dte,
                premium=mid_price,
                capital_cost=capital_cost * contracts_affordable,
                pct_otm=pct_otm,
                rationale=f"VIX: {vix_level:.1f} | {pct_otm*100:.1f}% OTM | Buys {contracts_affordable} contracts"
            ))
            
        # Sort by closest to 20% OTM
        candidates.sort(key=lambda x: abs(x.pct_otm - 0.20))
        return candidates
