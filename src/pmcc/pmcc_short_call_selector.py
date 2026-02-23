import logging
from typing import Dict, List, Optional
import pandas as pd
from datetime import date

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.pmcc.pmcc_sr_finder import SupportResistanceFinder
from ib_data_provider import IBDataProvider

logger = logging.getLogger(__name__)

class PMCCShortCallSelector:
    """
    Selects the optimal short call for a PMCC position (both entry and rolling).
    Incorporates resistance levels to avoid capping upside prematurely, while
    targeting a specific delta (e.g. 0.20-0.30) to generate income.
    """
    
    def __init__(self, data_provider: Optional[IBDataProvider] = None, bandit=None):
        self.ib = data_provider or IBDataProvider()
        self.sr_finder = SupportResistanceFinder()
        self.bandit = bandit
        
    def select_short_call(
        self,
        symbol: str,
        stock_price: float,
        hist_df: pd.DataFrame,
        target_delta: float = 0.25,
        min_delta: float = 0.15,
        max_delta: float = 0.35,
        min_dte: int = 7,
        max_dte: int = 45,
        leaps_break_even: Optional[float] = None,
        pmcc_features: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Select the best short call strike considering delta target and resistance.
        
        Args:
            symbol: Stock symbol
            stock_price: Current stock price
            hist_df: Historical dataframe for S/R calculation
            target_delta: Ideal delta for the short call
            min_delta, max_delta: Acceptable delta range
            min_dte, max_dte: Acceptable DTE range
            leaps_break_even: If provided, ensures short strike is above this for BCI rule
            
        Returns:
            Dictionary of the selected option from the chain, or None
        """
        # 0. Evaluate Contextual Bandit for Delta Override
        if self.bandit and pmcc_features is not None:
            bandit_pred = self.bandit.predict(pmcc_features)
            arm = bandit_pred.get('selected_arm', 1)
            
            if arm == 5: # Skip cycle arm
                logger.info(f"{symbol}: LinUCB Bandit elected to SKIP cycle (Arm 5). No short call selected.")
                return None
                
            bandit_delta = self.bandit.map_arm_to_delta(arm)
            if bandit_delta is not None:
                logger.info(f"{symbol}: LinUCB Bandit overridden target delta from {target_delta} to {bandit_delta} (Arm {arm}, Conf: {bandit_pred.get('confidence', 0):.2f})")
                target_delta = bandit_delta
                
        # 1. Find Resistance Levels
        resistances = self.sr_finder.get_resistance_levels(hist_df, stock_price)
        
        # 2. Get next expiration
        # Try to find something roughly 30 days out
        short_exp = self.ib.get_next_expiry(symbol, 30)
        if not short_exp:
            logger.warning(f"{symbol}: No expiration found around 30 days")
            return None
            
        short_dte = (short_exp - date.today()).days
        if not (min_dte <= short_dte <= max_dte):
            logger.warning(f"{symbol}: Expiration {short_exp} ({short_dte} DTE) outside bounds")
            return None
            
        # 3. Fetch Chain
        chain = self.ib.get_call_chain_for_pmcc(
            symbol=symbol,
            expiry=short_exp,
            delta_min=min_delta,
            delta_max=max_delta,
            is_leaps=False
        )
        
        if not chain:
            logger.warning(f"{symbol}: No valid short calls found in target delta range")
            return None
            
        # 4. Filter and Score Candidates
        # We want to pick a strike that is:
        # a) Close to target delta
        # b) Ideally exactly AT or SLIGHTLY ABOVE a major resistance level
        # c) Above leaps_break_even (BCI rule)
        
        scored_candidates = []
        
        for option in chain:
            strike = option['strike']
            delta_diff = abs(option['delta'] - target_delta)
            
            # Base score penalizes deviation from target delta
            score = 100 - (delta_diff * 100)
            
            # Penalize if below BCI breakeven
            if leaps_break_even and strike <= leaps_break_even:
                score -= 50  # Heavy penalty for violating BCI guaranteed no-loss
                
            # Resistance checks
            near_resistance = False
            for r in resistances:
                dist_pct = (strike - r) / r
                # If strike is 0-2% ABOVE resistance, it's a great spot (it acts as a ceiling)
                if 0 <= dist_pct <= 0.02:
                    score += 20
                    near_resistance = True
                # If strike is 0-2% BELOW resistance, it's a bad spot (we cap before breakout)
                elif -0.02 <= dist_pct < 0:
                    score -= 30
                    near_resistance = True
            
            # If no resistance nearby, neutral effect.
            
            scored_candidates.append({
                'option': option,
                'score': score,
                'near_resistance': near_resistance
            })
            
        if not scored_candidates:
            return None
            
        # 5. Sort by score descending and return the best
        scored_candidates.sort(key=lambda x: x['score'], reverse=True)
        best_candidate = scored_candidates[0]['option']
        best_score = scored_candidates[0]['score']
        
        logger.info(f"{symbol} Best Short Call: Strike {best_candidate['strike']} (Delta {best_candidate['delta']:.2f}) - Score: {best_score:.1f}")
        return best_candidate
