"""
TurboBounce Options: Scoring & Ranking Engine
===========================================

Ranks the universe of candidates using the 4-factor scoring formula:
Score = 0.35 * RSI_Extremity + 0.25 * IV_Rank + 0.20 * Options_Liquidity + 0.20 * Mean_Reversion_History
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

@dataclass
class SymbolScore:
    symbol: str
    total_score: float
    rsi_2: float
    iv_rank: float
    liquidity_score: float
    mean_reversion_history: float
    direction: str  # 'OVERSOLD' or 'OVERBOUGHT'
    category: str
    metrics: Dict[str, Any]

class TurboBounceScorer:
    """Evaluates and ranks candidates from the daily scan."""
    
    def __init__(self):
        # Weights defined in the implementation plan
        self.w_rsi = 0.35
        self.w_iv = 0.25
        self.w_liq = 0.20
        self.w_mrv = 0.20
        
    def score_candidate(self, symbol: str, category: str, metrics: Dict[str, Any]) -> SymbolScore:
        """
        Calculate the 0-100 score for a candidate.
        Expects metrics to contain: rsi_2, iv_rank, bid_ask_spread, volume
        """
        rsi_2 = metrics.get('rsi_2', 50.0)
        iv_rank = metrics.get('iv_rank', 0.0)
        
        # 1. RSI Extremity (0-100)
        # If deeply oversold (RSI < 10), extremity is high. 
        # If deeply overbought (RSI > 90), extremity is high.
        direction = "OVERSOLD" if rsi_2 < 50 else "OVERBOUGHT"
        
        if direction == "OVERSOLD":
            # Map RSI 10 -> 0 score, RSI 0 -> 100 score
            rsi_score = max(0, min(100, (15 - rsi_2) * 6.66)) 
        else:
            # Map RSI 85 -> 0 score, RSI 100 -> 100 score
            rsi_score = max(0, min(100, (rsi_2 - 85) * 6.66))
            
        # 2. IV Rank Score (0-100)
        # Higher is better for IV rank as we want rich premiums
        iv_score = max(0, min(100, iv_rank))
        
        # 3. Liquidity Score (0-100)
        # Tighter bid-ask spread = better execution
        spread = metrics.get('bid_ask_spread', 0.20)
        # Map $0.15 spread -> 0 score, $0.01 spread -> 100 score
        liq_score = max(0, min(100, (0.15 - spread) * 714))
        
        # 4. Mean Reversion History (0-100)
        # Placeholder for historical 5-day bounce rate. Default to 50 if unknown.
        # For leveraged ETFs, hardcode a higher expected mean reversion.
        mrv_score = metrics.get('mean_reversion_history', 50.0)
        if category == "3x Leveraged":
            mrv_score = 85.0
            
        # Calculate final weighted score
        total_score = (
            (self.w_rsi * rsi_score) +
            (self.w_iv * iv_score) +
            (self.w_liq * liq_score) +
            (self.w_mrv * mrv_score)
        )
        
        return SymbolScore(
            symbol=symbol,
            total_score=total_score,
            rsi_2=rsi_2,
            iv_rank=iv_rank,
            liquidity_score=liq_score,
            mean_reversion_history=mrv_score,
            direction=direction,
            category=category,
            metrics=metrics
        )
        
    def rank_candidates(self, scored_symbols: List[SymbolScore], top_n: int = 3) -> Dict[str, List[SymbolScore]]:
        """Separates and ranks the top oversold and overbought candidates."""
        oversold = [s for s in scored_symbols if s.direction == "OVERSOLD" and s.total_score > 40]
        overbought = [s for s in scored_symbols if s.direction == "OVERBOUGHT" and s.total_score > 40]
        
        # Sort descending by total score
        oversold.sort(key=lambda x: x.total_score, reverse=True)
        overbought.sort(key=lambda x: x.total_score, reverse=True)
        
        return {
            "top_oversold": oversold[:top_n],
            "top_overbought": overbought[:top_n]
        }
