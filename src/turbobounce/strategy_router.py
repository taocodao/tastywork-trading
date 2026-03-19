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
        # Thresholds from V5 Architecture
        self.iv_high_thresh = 30.0   # High IV -> Credit Spreads
        self.iv_low_thresh = 30.0    # Low IV -> Deep ITM LEAPS

    def route_candidate(self, score_obj, vix_level: float, vix_50d_sma: float) -> RoutedStrategy:
        """
        Implements the Strategy Selection Matrix from the Plan.
        """
        sym = score_obj.symbol
        iv_rank = score_obj.iv_rank
        direction = "BULLISH" if score_obj.direction == "OVERSOLD" else "BEARISH"
        
        # OVERSOLD (Bullish Play)
        if direction == "BULLISH":
            # Leveraged ETFs (TQQQ, LABU etc.) have distorted IV — force CREDIT_SPREAD
            LEVERAGED_ETFS = {'TQQQ', 'LABU', 'NUGT', 'SQQQ', 'UVXY'}
            if sym in LEVERAGED_ETFS:
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="CREDIT_SPREAD",
                    rationale=f"Leveraged ETF ({sym}) — forced CREDIT_SPREAD",
                    target_anchor_dte=30,
                    target_delta=0.20
                )
            if iv_rank >= 70 and vix_level > vix_50d_sma:
                # Extreme IV only — BWB is complex, use sparingly
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="PUT_BWB",
                    rationale=f"Extreme IV ({iv_rank:.1f}) + elevated VIX —> Put BWB Credit",
                    target_anchor_dte=30,
                    target_hedge_dte=None
                )
            elif vix_level > 30.0:
                # V5 CrashGuard: VIX > 30 (Crisis Regime), forbid LEAPS, force Credit Spreads
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="CREDIT_SPREAD",
                    rationale=f"VIX > 30 ({vix_level:.1f}) -> Forced Credit Spread (Crash Guard)",
                    target_anchor_dte=30,
                    target_delta=0.20
                )
            elif iv_rank >= self.iv_high_thresh:
                # High IV -> Bull Put Credit Spread (sell premium)
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="CREDIT_SPREAD",
                    rationale=f"High IV ({iv_rank:.1f}) -> Bull Put Credit Spread",
                    target_anchor_dte=30,
                    target_delta=0.20
                )
            else:
                # Low IV (<30) -> Premium is cheap, buy directional Deep ITM LEAPS (V5 Edge)
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="NAKED_LONG",
                    rationale=f"Low IV Rank ({iv_rank:.1f}) -> Deep ITM LEAPS (180 DTE)",
                    target_anchor_dte=180,
                    target_delta=0.80
                )
                
        # OVERBOUGHT (Bearish Play) - Retaining for completeness, although scanner will filter
        else:
            if vix_level > 30.0:
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="CREDIT_SPREAD",
                    rationale=f"VIX > 30 -> Bear Call Credit Spread (Crash Guard)",
                    target_anchor_dte=30,
                    target_delta=0.20
                )
            elif iv_rank >= self.iv_high_thresh:
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="CREDIT_SPREAD",
                    rationale=f"High IV Rank ({iv_rank:.1f}) -> Bear Call Credit Spread",
                    target_anchor_dte=30,
                    target_delta=0.20
                )
            else:
                return RoutedStrategy(
                    symbol=sym,
                    direction=direction,
                    strategy_type="NAKED_LONG",
                    rationale=f"Low IV Rank ({iv_rank:.1f}) -> Deep ITM Put LEAPS (180 DTE)",
                    target_anchor_dte=180,
                    target_delta=0.80
                )
