"""
Dual-Core Signal Publisher
==========================

Publishes actionable trading signals from the CSP Engine and 
meta-signals from the Dual-Core Allocator.
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from signal_publisher.base import BaseSignal, SignalRouter

logger = logging.getLogger(__name__)

# --- CSP Signals ---

@dataclass
class CSPEntrySignal(BaseSignal):
    symbol: str
    tier: str
    sell_strike: float
    expiration: str
    premium_credit: float
    capital_required: float
    is_spread: bool
    buy_strike: Optional[float] = None
    
    @property
    def strategy(self) -> str:
        return "CSP_SPREAD" if self.is_spread else "CSP_NAKED"
        
    def to_dict(self) -> Dict:
        d = super().to_dict()
        d.update({
            "tier": self.tier,
            "sell_strike": self.sell_strike,
            "expiration": self.expiration,
            "premium_credit": self.premium_credit,
            "capital_required": self.capital_required,
            "is_spread": self.is_spread,
            "buy_strike": self.buy_strike
        })
        return d
        
@dataclass
class CSPExitSignal(BaseSignal):
    symbol: str
    position_id: str
    action_type: str # CLOSE, ROLL_TIME, ROLL_DOWN, EXPIRE, ASSIGNED
    current_pnl: float
    
    @property
    def strategy(self) -> str:
        return "CSP_MANAGEMENT"

# --- Orchestrator Signals ---

@dataclass
class AllocationChangeSignal(BaseSignal):
    old_csp_pct: float
    new_csp_pct: float
    old_pmcc_pct: float
    new_pmcc_pct: float
    vix_level: float
    trigger_reason: str # "VIX_SPIKE", "ML_OPTIMIZER", "REGIME_CHANGE"

    @property
    def strategy(self) -> str:
        return "DUAL_CORE_ALLOCATOR"
        
class DualCoreSignalPublisher:
    """Publishes CSP and Dual-Core events"""
    def __init__(self, router: SignalRouter):
        self.router = router
        
    def publish_csp_entries(self, candidates: List[Any]):
        """Publishes a batch of CSP entry candidates."""
        for c in candidates:
            sig = CSPEntrySignal(
                symbol=c.symbol,
                confidence=c.score,
                reasoning=c.rationale,
                tier=c.tier,
                sell_strike=c.sell_strike,
                expiration=c.expiration.strftime('%Y-%m-%d'),
                premium_credit=c.premium_credit,
                capital_required=c.capital_required,
                is_spread=c.is_spread,
                buy_strike=c.buy_strike
            )
            self.router.route(sig)
            logger.info(f"Published CSP Entry Signal for {c.symbol}")

    def publish_allocation_change(self, old_alloc: Dict, new_alloc: Dict, vix: float, reason: str):
        sig = AllocationChangeSignal(
            symbol="PORTFOLIO",
            confidence=100.0,
            reasoning=reason,
            old_csp_pct=old_alloc.get("csp", 0),
            new_csp_pct=new_alloc.get("csp_conservative_pct", 0) + new_alloc.get("csp_aggressive_pct", 0),
            old_pmcc_pct=old_alloc.get("pmcc", 0),
            new_pmcc_pct=new_alloc.get("pmcc_moderate_pct", 0),
            vix_level=vix,
            trigger_reason=reason
        )
        self.router.route(sig)
