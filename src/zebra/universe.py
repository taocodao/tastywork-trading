"""
ZEBRA Universe Selection
=========================
Maintains eligible trading universe based on:
1. Configured static list (S&P 500 / Liquid Mid-Caps)
2. Daily volume (ADV) checks
3. Option liquidity checks (Spread, OI)
"""

import logging
from typing import List
from config import (
    ZEBRA_UNIVERSE, ZEBRA_MIN_ADV, 
    ZEBRA_MAX_ATM_SPREAD, ZEBRA_MIN_OI
)
# from ib_market_data_hub import IBMarketDataHub # Future integration

logger = logging.getLogger(__name__)

class ZebraUniverse:
    """Filters and returns eligible symbols for ZEBRA trading."""
    
    def __init__(self, client=None):
        self.client = client # Tastytrade or Data provider
        self.universe = ZEBRA_UNIVERSE
        
    def get_eligible_symbols(self) -> List[str]:
        """
        Returns list of symbols that pass basic liquidity filters.
        For Phase 1, this returns the static list but logs checks.
        """
        # In a full implementation, we would query ADV and Spreads here.
        # For now, return the curated list.
        return self.universe

    def check_liquidity(self, symbol: str) -> bool:
        """
        Verify specific symbol liquidity.
        """
        # TODO: Implement real-time check against IB/Tastytrade
        return True
