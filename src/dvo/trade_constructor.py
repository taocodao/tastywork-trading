
"""
DVO Trade Constructor
=====================
Converts DVOSignals into concrete Option Trade Structures.
Handles:
1. Finding Expirations (365-730 DTE for Puts, 500+ DTE for LEAPS)
2. Selecting Strikes (Margin of Safety based)
3. Sizing (Qty based on RiskGuardian limits)
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from .risk_guardian import RiskGuardian

logger = logging.getLogger(__name__)

@dataclass
class DVOTradeStruct:
    symbol: str
    structure_type: str # 'SHORT_PUT' or 'LEAPS_CALL'
    
    # Legs
    expiration: str
    strike: float
    option_type: str # 'P' or 'C'
    action: str # 'SELL_TO_OPEN' or 'BUY_TO_OPEN'
    quantity: int
    
    # Metadata
    dte: int
    delta: float
    estimated_price: float
    limit_price: float
    
    # Linked
    recycling_source_id: Optional[str] = None # If this is a LEAPS funded by a Put

class TradeConstructor:
    def __init__(self, risk_level="MEDIUM"):
        self.risk = RiskGuardian(risk_level)
        
    def find_short_put_candidate(self, 
                                 chain: Dict, 
                                 fair_value: float, 
                                 current_price: float,
                                 min_dte: int = 365,
                                 max_dte: int = 730) -> Optional[DVOTradeStruct]:
        """
        Scan option chain for a suitable short put.
        """
        # 1. Filter Expirations
        target_expirations = []
        for exp_date_str in chain.keys():
            exp_date = datetime.strptime(exp_date_str, '%Y-%m-%d')
            dte = (exp_date - datetime.now()).days
            if min_dte <= dte <= max_dte:
                target_expirations.append((exp_date_str, dte))
        
        if not target_expirations:
            logger.warning("No suitable expirations found for DVO Put.")
            return None
            
        # Sort by DTE (prefer longer duration for tax/stability?)
        # Or prefer shortest valid to decay faster?
        # Strategy doc says "time = gravity", prefer longer.
        target_expirations.sort(key=lambda x: x[1], reverse=True)
        
        chosen_exp, chosen_dte = target_expirations[0]
        strikes = chain[chosen_exp]['strikes']
        
        # 2. Select Strike
        # Strike should be <= fair_value * (1 - desired_margin_of_safety)
        # OR just <= current_price * 0.80 (20% OTM)
        # Doc says: Strike set so MoS >= 20%
        
        # Calculate max strike price allowed
        desired_entry_mos = self.risk.profile.min_margin_of_safety # e.g. 0.20
        max_strike = fair_value * (1.0 - desired_entry_mos)
        
        # Also cap at ITM? usually OTM.
        if max_strike > current_price:
            max_strike = current_price * 0.95 # Force at least 5% OTM if Fair Value is way high
            
        # Find closest strike <= max_strike
        candidate_strike = None
        best_delta = -999
        
        # Assuming strikes dict has 'puts': {strike: {delta, bid, ask}}
        # We need to adapt to actual chain structure passed in. 
        # Assuming standard dict structure from Tasty helper
        
        # Simplification: iterate strikes
        valid_strikes = [s for s in strikes if s <= max_strike]
        if not valid_strikes:
             logger.warning(f"No strikes found below {max_strike}")
             return None
             
        candidate_strike = max(valid_strikes) # Highest strike that is still safe
        
        # Get Quote
        quote = strikes[candidate_strike]['put']
        
        return DVOTradeStruct(
            symbol="UNKNOWN", # Caller fills in
            structure_type="SHORT_PUT",
            expiration=chosen_exp,
            strike=candidate_strike,
            option_type="P",
            action="SELL_TO_OPEN",
            quantity=1, # Sizer will adjust
            dte=chosen_dte,
            delta=quote.get('delta', 0),
            estimated_price=quote.get('mid', 0),
            limit_price=quote.get('mid', 0) # Placeholder
        )

    def find_leaps_call_candidate(self,
                                  chain: Dict,
                                  budget: float,
                                  min_dte: int = 500) -> Optional[DVOTradeStruct]:
        """
        Find a LEAPS call to buy with the premium budget.
        Target delta 0.70-0.80.
        """
        # 1. Filter Expirations
        target_expirations = []
        for exp_date_str in chain.keys():
            exp_date = datetime.strptime(exp_date_str, '%Y-%m-%d')
            dte = (exp_date - datetime.now()).days
            if dte >= min_dte:
                target_expirations.append((exp_date_str, dte))
                
        if not target_expirations:
             return None
             
        # Sort desc DTE
        target_expirations.sort(key=lambda x: x[1], reverse=True)
        chosen_exp, chosen_dte = target_expirations[0]
        strikes = chain[chosen_exp]['strikes']
        
        # 2. Find Delta 0.75
        best_strike = None
        min_diff = 999
        
        for k, v in strikes.items():
            call = v.get('call')
            if not call: continue
            
            # Cost check
            if call['ask'] * 100 > budget:
                continue
                
            delta = call.get('delta', 0)
            diff = abs(delta - 0.75)
            if diff < min_diff:
                min_diff = diff
                best_strike = k
                
        if not best_strike:
            return None
            
        quote = strikes[best_strike]['call']
        
        return DVOTradeStruct(
            symbol="UNKNOWN",
            structure_type="LEAPS_CALL",
            expiration=chosen_exp,
            strike=best_strike,
            option_type="C",
            action="BUY_TO_OPEN",
            quantity=1, 
            dte=chosen_dte,
            delta=quote.get('delta', 0),
            estimated_price=quote.get('ask', 0),
            limit_price=quote.get('ask', 0)
        )
