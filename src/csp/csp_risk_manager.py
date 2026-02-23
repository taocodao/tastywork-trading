"""
CSP Risk Manager
================

Risk manager specifically tailored for the CSP strategy.
Extends base RiskManager with tier-specific IV Rank and fair-value checks.
"""

import logging
from typing import Optional, List, Dict

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from risk_manager import RiskManager, RiskCheck

logger = logging.getLogger(__name__)

class CSPRiskManager(RiskManager):
    """
    Risk manager specifically tailored for CSPs and Put Credit Spreads.
    """
    def __init__(
        self,
        account_size: float = 100000.0,
        max_risk_pct: float = 0.05, 
        max_positions: int = 15,  # Higher than PMCC because spreads use less capital
        max_daily_loss_pct: float = 0.03
    ):
        super().__init__(
            account_size=account_size,
            max_risk_pct=max_risk_pct,
            max_positions=max_positions,
            max_daily_loss_pct=max_daily_loss_pct
        )
        
    def check_csp_can_trade(
        self,
        symbol: str,
        tier: str,
        trade_cost: float,
        current_positions: int,
        vix: Optional[float] = None,
        iv_rank: Optional[float] = None,
        fair_value_discount: Optional[float] = None
    ) -> RiskCheck:
        """
        Extends the base risk checks with CSP specific constraints.
        """
        # 1. Base limits (Account size, max positions, daily loss)
        base_check = self.check_can_trade(trade_cost, current_positions, vix)
        if not base_check.passed:
            return base_check
            
        # 2. VIX gating (too low = no premium, too high = panic)
        if vix is not None:
            if vix < 15.0 and tier == "conservative":
                return RiskCheck(False, f"VIX {vix:.1f} < 15. Premium too thin for Conservative CSP.")
            if vix > 45.0:
                return RiskCheck(False, f"VIX {vix:.1f} > 45. Extreme panic. Halting all new CSPs.")
                
        # 3. IV Rank enforcement
        if iv_rank is not None:
            if tier == "aggressive" and iv_rank < 40:
                return RiskCheck(False, f"IV Rank {iv_rank:.1f} < 40 for Aggressive tier. Not enough edge.")
            if tier == "conservative" and iv_rank < 30:
                return RiskCheck(False, f"IV Rank {iv_rank:.1f} < 30 for Conservative tier.")
                
        # 4. Fair value check (Aggressive tier only)
        if tier == "aggressive" and fair_value_discount is not None:
             if fair_value_discount < -0.10: # Overvalued by more than 10%
                 return RiskCheck(False, f"{symbol} is >10% overvalued. Bag-holding risk too high.")
                 
        return RiskCheck(True)
