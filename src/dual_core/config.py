"""
Dual-Core Configuration
=======================

Strategy-level configuration and default capital allocation weights.
"""

from dataclasses import dataclass
from typing import Dict

@dataclass
class StrategyConfig:
    csp_conservative_pct: float = 0.40
    csp_aggressive_pct: float = 0.15
    pmcc_moderate_pct: float = 0.20
    cash_reserve_pct: float = 0.20
    tail_hedge_pct: float = 0.02
    money_market_pct: float = 0.03
    
    @property
    def total_csp_pct(self) -> float:
        return self.csp_conservative_pct + self.csp_aggressive_pct

    def validate(self):
        total = (self.csp_conservative_pct + self.csp_aggressive_pct + 
                 self.pmcc_moderate_pct + self.cash_reserve_pct + 
                 self.tail_hedge_pct + self.money_market_pct)
        assert abs(total - 1.0) < 0.001, f"Total allocation must equal 100%. Got {total*100}%"

DEFAULT_CONFIG = StrategyConfig()
