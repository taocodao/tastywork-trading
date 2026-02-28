"""
TurboBounce Options: Strategy Router
====================================

Takes the top scanner candidates and selects the optimal options structure
(Diagonal, Vertical, or Naked) based on IV Rank and VIX regime.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class RoutedStrategy:
    symbol: str
    direction: str       # 'BULLISH' (for oversold) or 'BEARISH' (for overbought)
    strategy_type: str   # 'DIAGONAL', 'CREDIT_SPREAD', 'NAKED_LONG'
    rationale: str
    target_anchor_dte: Optional[int] = None
    target_hedge_dte: Optional[int] = None
    target_delta: Optional[float] = None

class StrategyRouter:
    """Selects structure per ticker dynamically based on IV environment."""
    
    def __init__(self):
        # Thresholds
        self.iv_high_thresh = 50.0
        self.iv_low_thresh = 30.0

    def route_candidate(self, score_obj, vix_level: float, vix_50d_sma: float) -> RoutedStrategy:
        """
        Implements the Strategy Selection Matrix from the Plan.
        """
        sym = score_obj.symbol
        iv_rank = score_obj.iv_rank
        direction = "BULLISH" if score_obj.direction == "OVERSOLD" else "BEARISH"
        
        # OVERSOLD (Bullish Play)
        if direction == "BULLISH":
            if iv_rank > self.iv_high_thresh and vix_level > vix_50d_sma:
                # High IV + High VIX -> Sell rich premium, buy cheap short-term hedge
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="DIAGONAL",
                    rationale=f"High IV Rank ({iv_rank:.1f}) + VIX above SMA -> Put Diagonal Spread",
                    target_anchor_dte=45,
                    target_hedge_dte=10
                )
            elif iv_rank > self.iv_high_thresh:
                # High IV but VIX not expanding -> Vertical spread to avoid term structure risk
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="CREDIT_SPREAD",
                    rationale=f"High IV Rank ({iv_rank:.1f}) -> Bull Put Credit Spread",
                    target_anchor_dte=30,
                    target_delta=0.20
                )
            elif iv_rank < self.iv_low_thresh and vix_level < vix_50d_sma:
                # Low IV -> Premium is cheap, buy naked leverage
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="NAKED_LONG",
                    rationale=f"Low IV Rank ({iv_rank:.1f}) + Low VIX -> Naked Long Call",
                    target_anchor_dte=14,
                    target_delta=0.30
                )
            else:
                # Default middle ground
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="DIAGONAL",
                    rationale=f"Mid-range IV ({iv_rank:.1f}) -> Standard Put Diagonal",
                    target_anchor_dte=30,
                    target_hedge_dte=10
                )
                
        # OVERBOUGHT (Bearish Play)
        else:
            if iv_rank > self.iv_high_thresh:
                # High IV -> Fade the spike by selling premium
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="DIAGONAL",
                    rationale=f"High IV Rank ({iv_rank:.1f}) -> Call Diagonal (Bearish)",
                    target_anchor_dte=45,
                    target_hedge_dte=10
                )
            else:
                # Low IV -> Fade with cheap long premium
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="NAKED_LONG",
                    rationale=f"Low IV Rank ({iv_rank:.1f}) -> Naked Long Put",
                    target_anchor_dte=14,
                    target_delta=0.30
                )
