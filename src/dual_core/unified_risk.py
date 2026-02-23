"""
Dual-Core Unified Risk Manager
==============================

Enforces cross-strategy risk limits.
Ensures that the COMBINED risk of CSP and PMCC doesn't breach global limits.
"""

import logging
from typing import Dict, List, Optional

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from risk_manager import RiskCheck

logger = logging.getLogger(__name__)

class UnifiedRiskManager:
    """
    Sits above the individual CSP and PMCC Risk Managers.
    Validates portfolio-level constraints.
    """
    def __init__(self, account_size: float = 100000.0, max_symbol_concentration: float = 0.07):
        self.account_size = account_size
        self.max_symbol_concentration = max_symbol_concentration # 7% max per symbol
        
    def check_portfolio_concentration(
        self, 
        symbol: str, 
        proposed_trade_cost: float, 
        existing_csp_risk: float, 
        existing_pmcc_risk: float
    ) -> RiskCheck:
        """
        Validates that a new trade doesn't push a single symbol above the 
        concentration limit across BOTH cores combined.
        """
        current_symbol_risk = existing_csp_risk + existing_pmcc_risk
        projected_risk = current_symbol_risk + proposed_trade_cost
        
        projected_concentration = projected_risk / self.account_size
        
        if projected_concentration > self.max_symbol_concentration:
            return RiskCheck(
                passed=False, 
                reason=f"[{symbol}] Combined risk {projected_concentration*100:.1f}% exceeds max {self.max_symbol_concentration*100:.0f}%. "
                       f"(CSP: ${existing_csp_risk:.0f}, PMCC: ${existing_pmcc_risk:.0f}, Proposed: ${proposed_trade_cost:.0f})"
            )
            
        return RiskCheck(True)

    def check_total_allocation(
        self, 
        total_csp_deployed: float, 
        total_pmcc_deployed: float, 
        target_allocation: Dict[str, float]
    ) -> List[str]:
        """
        Monitors drift from the DualCoreAllocator's targets.
        Used for reporting and rebalancing.
        """
        warnings = []
        
        current_csp_pct = total_csp_deployed / self.account_size
        target_csp_pct = target_allocation.get('csp', 0.55)
        if current_csp_pct > target_csp_pct * 1.10: # 10% tolerance
             warnings.append(f"CSP Allocation ({current_csp_pct*100:.1f}%) exceeds target ({target_csp_pct*100:.1f}%)")
             
        current_pmcc_pct = total_pmcc_deployed / self.account_size
        target_pmcc_pct = target_allocation.get('pmcc', 0.20)
        if current_pmcc_pct > target_pmcc_pct * 1.10:
             warnings.append(f"PMCC Allocation ({current_pmcc_pct*100:.1f}%) exceeds target ({target_pmcc_pct*100:.1f}%)")
             
        return warnings
