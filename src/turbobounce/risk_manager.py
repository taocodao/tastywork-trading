"""
TurboBounce Options: Risk & Allocation Manager
==============================================
Manages capital allocation across the two user-defined modes:
- Mode A (Dedicated): 50% TQQQ Swing pool + 50% Multi-Ticker pool
- Mode B (Unified): 100% Multi-Ticker pool (TQQQ competes with all other tickers)
"""

import logging
from dataclasses import dataclass
from typing import List, Dict

logger = logging.getLogger(__name__)

@dataclass
class AllocationLimits:
    max_total_positions: int = 6
    max_tqqq_positions: int = 3
    max_multiticker_positions: int = 3
    max_correlated_positions: int = 2 # Max positions in same category (e.g. Semi)

class TurboBounceRiskManager:
    def __init__(self, mode: str = "MODE_B"):
        # "MODE_A" (Dedicated 50/50) or "MODE_B" (Unified 100%)
        self.mode = mode.upper()
        
        self.limits = AllocationLimits()
        if self.mode == "MODE_B":
            # Unified mode: all 6 positions can theoretically be multi-ticker.
            # TQQQ just competes for these slots.
            self.limits.max_multiticker_positions = 6
            self.limits.max_tqqq_positions = 6  
            
    def get_available_slots(self, open_positions: List[Dict], target_pool: str = "MULTI_TICKER") -> int:
        """
        Determines how many new entries can be opened in the target pool.
        open_positions: list of dicts with keys 'symbol' and 'pool'
        """
        total_open = len(open_positions)
        if total_open >= self.limits.max_total_positions:
            logger.info("RiskManager: Maximum total positions (6) reached.")
            return 0
            
        tqqq_open = sum(1 for p in open_positions if p.get('symbol') == 'TQQQ')
        multi_open = sum(1 for p in open_positions if p.get('pool') == 'MULTI_TICKER')
        
        if self.mode == "MODE_A":
            if target_pool == "TQQQ":
                return max(0, self.limits.max_tqqq_positions - tqqq_open)
            else:
                return max(0, self.limits.max_multiticker_positions - multi_open)
                
        elif self.mode == "MODE_B":
            # In Unified Mode, everything effectively pulls from the same 6-slot limit.
            return max(0, self.limits.max_total_positions - total_open)
            
        return 0

    def check_correlation_guard(self, target_category: str, open_positions: List[Dict]) -> bool:
        """
        Prevents too much concentration in a single sector.
        Returns False if adding a position to this category would exceed limits.
        """
        # Exclude Core ETFs and 3x Leveraged from strict sector correlation limits,
        # they represent broad market beta anyway.
        if "Core ETF" in target_category or "3x Leveraged" in target_category:
            return True
            
        count_in_category = sum(1 for p in open_positions if p.get('category') == target_category)
        
        if count_in_category >= self.limits.max_correlated_positions:
            logger.warning(f"RiskManager: Correlation guard triggered. Already have {count_in_category} in {target_category}.")
            return False
            
        return True
