"""
TurboBounce Options: Daily Scanner
==================================

Pulls data for the universe, applies filters (Oversold/Overbought/Liquidity),
scores them, and returns the top ranked candidates for strategy selection.
"""

import logging
from typing import Dict, List, Any
from .universe import get_turbobounce_symbols, get_category_for_symbol
from .data_provider import MultiTickerDataProvider
from .scoring import TurboBounceScorer, SymbolScore

logger = logging.getLogger(__name__)

class TurboBounceScanner:
    def __init__(self, data_provider: MultiTickerDataProvider):
        self.data_provider = data_provider
        self.scorer = TurboBounceScorer()
        
    def run_daily_scan(self) -> Dict[str, List[SymbolScore]]:
        """
        Executes the daily morning scan (08:00 ET).
        1. Fetches universe data
        2. Applies Filter 1 (Oversold/Overbought) & Filter 2 (Liquidity) & Filter 3 (Regime)
        3. Scores & Ranks candidates
        4. Returns top 3 of each direction
        """
        symbols = get_turbobounce_symbols()
        logger.info(f"Running TurboBounce Daily Scan on {len(symbols)} symbols...")
        
        batch_metrics = self.data_provider.fetch_batch_data(symbols)
        valid_candidates = []
        
        for sym, metrics in batch_metrics.items():
            category = get_category_for_symbol(sym)
            
            # --- Hard Filter 1: Liquidity ---
            # Using 2M as minimum volume (adjusted from 5M so more tech names pass)
            if metrics.get('avg_volume', 0) < 2000000:
                logger.debug(f"{sym} rejected: low volume ({metrics.get('avg_volume', 0)})")
                continue
                
            # --- Hard Filter 2: Regime (200 SMA) ---
            # To catch true bounces, we prefer stocks above their 200 SMA
            # But we allow deep capitulation crashes if they are extreme (e.g. VIX logic)
            dist_sma = metrics.get('dist_sma_200', 0)
            if dist_sma < -0.25:
                logger.debug(f"{sym} rejected: >25% below 200 SMA (falling knife)")
                continue

            # --- Signal Filter: Oversold vs Overbought ---
            rsi_2 = metrics.get('rsi_2', 50)
            pct_b = metrics.get('pct_b', 0.5)
            ret_3d = metrics.get('ret_3d', 0.0)
            
            is_oversold = (rsi_2 < 10) or (pct_b < 0) or (ret_3d < -0.08)
            is_overbought = (rsi_2 > 90) or (pct_b > 1.0) or (ret_3d > 0.10)
            
            if not (is_oversold or is_overbought):
                continue
                
            # --- Score and Keep ---
            score_obj = self.scorer.score_candidate(sym, category, metrics)
            valid_candidates.append(score_obj)
            logger.info(f"Candidate {sym}: {score_obj.direction} (Score: {score_obj.total_score:.1f}, RSI: {rsi_2:.1f})")

        # Rank and return top 3 of each
        ranked = self.scorer.rank_candidates(valid_candidates, top_n=3)
        
        logger.info(f"Scan complete. Found {len(ranked['top_oversold'])} oversold, {len(ranked['top_overbought'])} overbought.")
        return ranked
