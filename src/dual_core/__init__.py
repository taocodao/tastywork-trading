"""
Dual-Core Options Alpha Orchestrator
====================================

The intelligent coordination layer that sits above the CSP and PMCC engines.
"""

from typing import Dict, Any

class StrategyCore:
    CSP = "CSP"
    PMCC = "PMCC"
    BOTH = "BOTH"
    SKIP = "SKIP"
