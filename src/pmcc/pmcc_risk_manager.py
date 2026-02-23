import logging
from dataclasses import dataclass
from typing import Optional, List, Dict

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from risk_manager import RiskManager, RiskCheck

logger = logging.getLogger(__name__)

class PMCCRiskManager(RiskManager):
    """
    Risk manager specifically tailored for PMCC strategy.
    
    PMCC requires more capital per trade than vertical spreads because of the LEAPS leg.
    Rules:
    - Max risk per trade: 5% of account (LEAPS are capital intensive)
    - Max concurrent PMCC positions: 8
    - Emergency circuit breakers for extreme market conditions
    """
    def __init__(
        self,
        account_size: float = 100000.0,
        max_risk_pct: float = 0.05, 
        max_positions: int = 8,
        max_daily_loss_pct: float = 0.03
    ):
        super().__init__(
            account_size=account_size,
            max_risk_pct=max_risk_pct,
            max_positions=max_positions,
            max_daily_loss_pct=max_daily_loss_pct
        )
        
    def check_pmcc_can_trade(
        self,
        trade_cost: float,
        current_positions: int,
        vix: Optional[float] = None,
        correlation_score: Optional[float] = None
    ) -> RiskCheck:
        """
        Extends the base risk checks with PMCC specific constraints.
        """
        # 1. Check base limits (Account size, max positions, daily loss, VIX)
        base_check = self.check_can_trade(trade_cost, current_positions, vix)
        if not base_check.passed:
            return base_check
            
        # 2. PMCC VIX constraint (Halt selling new short calls / new PMCCs in extreme VIX)
        if vix and vix > 35:
            return RiskCheck(False, f"VIX too high for PMCC at {vix:.1f} (max 35)")
            
        # 3. Correlation guardrail (Avoid over-concentration in same sector)
        if correlation_score and correlation_score > 0.70:
            return RiskCheck(False, f"Portfolio correlation too high: {correlation_score:.2f} > 0.70")
            
        return RiskCheck(True)
        
    def check_emergency_conditions(self, market_data: Dict) -> List[str]:
        """
        Circuit breakers evaluated during position monitoring.
        Returns a list of triggered panic rules that might require manual intervention 
        or immediate mass closures.
        """
        panics = []
        
        # 1. Flash crash detection
        stock_drop_pct = market_data.get("daily_drop_pct", 0.0)
        if stock_drop_pct < -0.15:
            panics.append(f"FLASH CRASH: Stock dropped {stock_drop_pct*100:.1f}%. Evaluate LEAPS support.")
            
        # 2. Market-wide panic
        vix = market_data.get("vix", 20.0)
        if vix > 45:
            panics.append(f"MARKET PANIC: VIX at {vix:.1f}. Volatility expansion hurts LEAPS if delta collapses.")
            
        # 3. Short assignment risk (circuit breaker level)
        short_assigned = market_data.get("short_assigned_flag", False)
        if short_assigned:
            panics.append("ASSIGNMENT: Short call assigned. Must exercise LEAPS or cover shares immediately.")
            
        return panics
