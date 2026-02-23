"""
Dual-Core CSP Income Strategy Package
=====================================

Standalone Options Strategy for selling cash-secured puts and put credit spreads.
Integrated with the Dual-Core Options Alpha framework.
"""

from enum import Enum

class CSPStrategyTier(Enum):
    CONSERVATIVE = "conservative"  # Focus: SPY/QQQ put credit spreads
    AGGRESSIVE = "aggressive"      # Focus: Individual high-IV stock CSPs
