"""
Dual-Core Security Router
=========================

Routes screened symbols to the optimal strategy core.
Uses ZEBRA Security Scorer metrics (trend, IV Rank) to route capital.
"""

import logging
from typing import Dict, Any

from src.dual_core import StrategyCore

logger = logging.getLogger(__name__)

class SecurityRouter:
    """
    Decides if a given symbol should be traded via CSP, PMCC, or BOTH.
    """
    def __init__(self):
        pass
        
    def route_symbol(
        self, 
        symbol: str, 
        score_data: Dict[str, Any], 
        iv_rank: float, 
        regime: str
    ) -> str:
        """
        Determines the optimal strategy core for a given symbol context.
        """
        trend_score = score_data.get('trend_score', 0)
        fair_value_discount = score_data.get('fair_value_discount', 0.0) # < 0 means overvalued
        
        logger.debug(f"Routing {symbol}: Trend={trend_score:.1f}, IVR={iv_rank:.1f}, FV={fair_value_discount:.2f}")

        # Bearish + Low IV -> SKIP entirely (no edge anywhere)
        if trend_score < 40 and iv_rank < 30:
            return StrategyCore.SKIP

        # Strong uptrend + Low IV -> PMCC (Buy LEAPS cheap, ride trend) 
        if trend_score > 70 and iv_rank < 30:
            return StrategyCore.PMCC

        # High IV Rank -> CSP (Sell expensive premium)
        if iv_rank > 40:
            # Check valuation first for CSP bag-holding risk
            if fair_value_discount < -0.10: 
                # Stock is significantly overvalued. Do NOT sell puts on it unless PMCC is also viable
                if trend_score > 70:
                    # Very strong momentum overriding valuation concerns
                    return StrategyCore.BOTH
                return StrategyCore.SKIP
                
            # Fair or undervalued + High IV -> Sell puts
            if trend_score > 70:
                # Strong trend + High IV -> BOTH are viable
                return StrategyCore.BOTH
            else:
                return StrategyCore.CSP

        # Default fallback: Wait for better setup
        return StrategyCore.SKIP
