"""
Dual-Core Capital Allocator
===========================

Dynamically shifts capital between the CSP Engine and PMCC Engine
based on Market Regime and VIX.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))


from src.dual_core.config import StrategyConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)

@dataclass
class AllocationPlan:
    csp_conservative_pct: float
    csp_aggressive_pct: float
    pmcc_moderate_pct: float
    cash_reserve_pct: float
    tail_hedge_pct: float
    money_market_pct: float
    
    # ML extensions
    is_ml_driven: bool = False
    confidence: float = 0.0

class DualCoreAllocator:
    """
    Computes the optimal capital allocation.
    Uses rule-based logic (VIX thresholds) by default, with an optional
    ML Agent override for the final Phase 4 integration.
    """
    def __init__(self, rl_agent=None, iv_router=None):
        self.rl_agent = rl_agent
        self.iv_router = iv_router
        self.base_config = DEFAULT_CONFIG
        
    def compute_allocation(
        self, 
        regime: str, 
        vix: float, 
        portfolio_state: Dict
    ) -> AllocationPlan:
        """
        Calculates current capital distribution targets.
        """
        logger.info(f"Computing allocation for Regime: {regime}, VIX: {vix:.1f}")
        
        # 1. Check ML Agent (Phase 4 Hook)
        if self.rl_agent and self.iv_router:
            try:
                # Get predictive bias
                routing_signal = self.iv_router.get_routing_signal(portfolio_state) # Mock access
                
                # Fetch ML Allocation
                ml_alloc, conf = self.rl_agent.predict_allocation(vix, regime, portfolio_state, routing_signal)
                
                if conf >= 0.65:
                    logger.info(f"Using ML-Driven Allocation (Conf: {conf:.2f})")
                    return ml_alloc
                else:
                    logger.info(f"ML Confidence too low ({conf:.2f} < 0.65). Falling back to rules.")
            except Exception as e:
                logger.error(f"Error querying ML Allocator: {e}. Falling back to rules.")
                
        # 2. Rule-Based Fallback
        return self._compute_rule_based_allocation(regime, vix)
        
    def _compute_rule_based_allocation(self, regime: str, vix: float) -> AllocationPlan:
        """
        Static rule-based logic from the strategy report.
        """
        # Start from base
        plan = AllocationPlan(
            csp_conservative_pct=self.base_config.csp_conservative_pct,
            csp_aggressive_pct=self.base_config.csp_aggressive_pct,
            pmcc_moderate_pct=self.base_config.pmcc_moderate_pct,
            cash_reserve_pct=self.base_config.cash_reserve_pct,
            tail_hedge_pct=self.base_config.tail_hedge_pct,
            money_market_pct=self.base_config.money_market_pct
        )
        
        # Logic 1: High Volatility (VIX > 25)
        # Shift capital toward CSP (rich premiums), decrease PMCC (LEAPS expensive)
        if vix > 25.0:
            logger.info("High Volatility detected. Shifting to CSP Heavy.")
            plan.csp_conservative_pct = 0.45
            plan.csp_aggressive_pct = 0.20
            plan.pmcc_moderate_pct = 0.10
            plan.cash_reserve_pct = 0.20
            
        # Logic 2: Low Volatility (VIX < 15)
        # Shift capital to PMCC (cheap LEAPS), decrease CSP (thin premiums)
        elif vix < 15.0:
            logger.info("Low Volatility detected. Shifting to PMCC Heavy.")
            plan.csp_conservative_pct = 0.30
            plan.csp_aggressive_pct = 0.05
            plan.pmcc_moderate_pct = 0.35
            plan.cash_reserve_pct = 0.25
            
        # Logic 3: Bear Market Regime / Crisis
        # Drastically increase cash, reduce all exposure
        if regime in ['BEAR', 'CRISIS']:
            logger.info("Bear/Crisis Regime detected. Shifting to Defensive.")
            plan.cash_reserve_pct = 0.40
            plan.csp_conservative_pct = 0.30
            plan.pmcc_moderate_pct = 0.10
            plan.csp_aggressive_pct = 0.0
            plan.money_market_pct = 0.18 # Park remainder securely
            
        return plan
