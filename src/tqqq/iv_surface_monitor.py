"""
IV Surface Monitor
==================
Analyzes the live TQQQ Implied Volatility (IV) surface (term structure & skew)
to dynamically adjust DTE and Delta targets in SpreadBuilder.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class IVSurfaceMonitor:
    """
    Calculates term structure slope and skew steepness from live option chains.
    Feeds adjustments back to SpreadBuilder.
    """
    
    def __init__(self):
        pass
        
    def analyze_surface(self, chain_data: List[Dict[str, Any]], current_price: float) -> Dict[str, Any]:
        """
        Extracts key structural components from the raw options chain.
        """
        if not chain_data:
            return {}
            
        slope = self._get_term_structure_slope(chain_data)
        skew = self._get_skew_steepness(chain_data, current_price)
        
        return {
            "term_slope": slope,
            "skew_steepness": skew
        }
        
    def recommend_adjustments(self, surface_metrics: Dict[str, Any], base_dte: int, base_delta: float) -> Tuple[int, float]:
        """
        Recommends shifts to DTE and Delta based on surface metrics.
        """
        adj_dte = base_dte
        adj_delta = base_delta
        
        slope = surface_metrics.get("term_slope", 0.0)
        skew = surface_metrics.get("skew_steepness", 0.0)
        
        # --- DTE Adjustment (Term Structure) ---
        # If term structure is steeply in contango (slope > 0.02), shorter DTEs are relatively rich.
        if slope > 0.02:
            adj_dte = max(14, base_dte - 7)
            logger.info(f"IV Term Structure steep positive. Adjusting DTE {base_dte} -> {adj_dte}.")
        # If backwardation (crises usually), stretch DTE
        elif slope < -0.01:
            adj_dte = min(45, base_dte + 7)
            logger.info(f"IV Term Structure backwardation. Adjusting DTE {base_dte} -> {adj_dte}.")
            
        # --- Strike Adjustment (Skew) ---
        # If put skew is unusually steep, our short OTM puts are rich. Shift closer to ATM lightly to capture it.
        if skew > 0.10:
            adj_delta = max(-0.35, base_delta - 0.05)
            logger.info(f"Put skew is very steep. Adjusting Target Delta {base_delta} -> {adj_delta}")
        elif skew < 0.02:
            adj_delta = min(-0.15, base_delta + 0.05)
            
        return adj_dte, adj_delta

    def _get_term_structure_slope(self, chain_data: List[Dict[str, Any]]) -> float:
        """
        Approximate slope of ATM IV across the expiries.
        Returns difference between 45 DTE ATM IV and 21 DTE ATM IV.
        """
        # (Simplified logic - in a live system we interpolate true constant maturity)
        dtes = [c.get('dte') for c in chain_data if c.get('dte')]
        if not dtes: return 0.0
        
        # Not enough spread to calculate slope
        if max(dtes) - min(dtes) < 10:
            return 0.0
            
        # Placeholder: returning a flat slope for now
        return 0.0
        
    def _get_skew_steepness(self, chain_data: List[Dict[str, Any]], current_price: float) -> float:
        """
        OTM Put IV minus ATM Put IV for the ~30 day expiry.
        """
        # Placeholder: returning average steepness
        return 0.05
