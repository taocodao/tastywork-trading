"""
VOSS Liquidity Filter for Calendar Spreads
==========================================
Volume + Open Interest + Spread + Strike filtering

Based on research: Options-Selection-Best-Practices-Deep-Research.md
Priority: Liquidity FIRST, then expiration, then strike
"""

from dataclasses import dataclass
from typing import Tuple, Optional
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class VOSSCriteria:
    """
    VOSS filtering thresholds
    
    Based on research for optimal options selection:
    - Open Interest: Minimum 1,000 contracts (prefer 5,000+)
    - Volume: Minimum 500 daily (prefer 2,000+)
    - Bid-Ask Spread: Maximum 10% (prefer 5%)
    - Bid-Ask Size: Minimum 10 contracts at bid/ask
    """
    # Minimum thresholds (must pass)
    min_open_interest: int = 1000
    min_volume: int = 500
    max_bid_ask_pct: float = 0.10
    min_bid_ask_size: int = 10
    
    # Preferred thresholds (for scoring)
    preferred_open_interest: int = 5000
    preferred_volume: int = 2000
    preferred_bid_ask_pct: float = 0.05
    preferred_bid_ask_size: int = 50


class VOSSLiquidityFilter:
    """
    Filter options chains for liquidity using VOSS framework
    
    VOSS = Volume + Open Interest + Spread + Strike
    
    Usage:
        filter = VOSSLiquidityFilter()
        filtered_chain = filter.filter_options_chain(raw_chain)
        
        # Or check single option:
        passes, score = filter.check_single_option(
            open_interest=2500,
            volume=1000,
            bid=1.50,
            ask=1.65
        )
    """
    
    def __init__(self, criteria: Optional[VOSSCriteria] = None):
        self.criteria = criteria or VOSSCriteria()
    
    def filter_options_chain(self, chain: pd.DataFrame) -> pd.DataFrame:
        """
        Apply VOSS filtering to options chain
        
        Args:
            chain: DataFrame with columns:
                - strike (float)
                - bid (float)
                - ask (float)
                - volume (int)
                - openInterest (int)
                - Optional: bidSize, askSize
        
        Returns:
            Filtered DataFrame sorted by liquidity_score (descending)
            Empty DataFrame if no options pass filters
        """
        if chain.empty:
            logger.warning("Empty chain provided to VOSS filter")
            return chain
        
        initial_count = len(chain)
        
        # Step 1: CRITICAL liquidity filters (must pass all)
        filtered = chain.copy()
        
        # Filter by open interest
        if 'openInterest' in filtered.columns:
            filtered = filtered[filtered['openInterest'] >= self.criteria.min_open_interest]
            if filtered.empty:
                logger.info(f"VOSS: All options filtered by open interest < {self.criteria.min_open_interest}")
                return filtered
        
        # Filter by volume
        if 'volume' in filtered.columns:
            filtered = filtered[filtered['volume'] >= self.criteria.min_volume]
            if filtered.empty:
                logger.info(f"VOSS: All options filtered by volume < {self.criteria.min_volume}")
                return filtered
        
        # Calculate and filter by bid-ask spread percentage
        if 'bid' in filtered.columns and 'ask' in filtered.columns:
            # Avoid division by zero
            valid_ask = filtered['ask'] > 0
            filtered = filtered[valid_ask].copy()
            
            if not filtered.empty:
                filtered['spread_pct'] = (filtered['ask'] - filtered['bid']) / filtered['ask']
                filtered = filtered[filtered['spread_pct'] <= self.criteria.max_bid_ask_pct]
                
                if filtered.empty:
                    logger.info(f"VOSS: All options filtered by spread > {self.criteria.max_bid_ask_pct:.0%}")
                    return filtered
        
        # Step 2: Calculate quality/liquidity score
        filtered = self._calculate_liquidity_scores(filtered)
        
        # Sort by liquidity score (best first)
        filtered = filtered.sort_values('liquidity_score', ascending=False)
        
        final_count = len(filtered)
        logger.info(f"VOSS filter: {final_count}/{initial_count} options passed ({final_count/initial_count:.0%})")
        
        return filtered
    
    def _calculate_liquidity_scores(self, chain: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate liquidity scores for filtered options
        
        Score components (weighted):
        - Open interest contribution: 40%
        - Volume contribution: 30%
        - Spread tightness contribution: 30%
        """
        chain = chain.copy()
        
        # Open interest score (0-1, capped at preferred level)
        if 'openInterest' in chain.columns:
            oi_score = (chain['openInterest'] / self.criteria.preferred_open_interest).clip(upper=1.0)
        else:
            oi_score = 0.5
        
        # Volume score (0-1, capped at preferred level)  
        if 'volume' in chain.columns:
            vol_score = (chain['volume'] / self.criteria.preferred_volume).clip(upper=1.0)
        else:
            vol_score = 0.5
        
        # Spread score (0-1, tighter is better)
        if 'spread_pct' in chain.columns:
            # Normalize: 0% spread = 1.0, max_spread = 0
            spread_score = 1 - (chain['spread_pct'] / self.criteria.max_bid_ask_pct)
            spread_score = spread_score.clip(lower=0.0, upper=1.0)
        else:
            spread_score = 0.5
        
        # Weighted total score
        chain['liquidity_score'] = (
            oi_score * 0.40 +
            vol_score * 0.30 +
            spread_score * 0.30
        )
        
        # Also store component scores for debugging
        chain['oi_score'] = oi_score
        chain['volume_score'] = vol_score
        chain['spread_score'] = spread_score
        
        return chain
    
    def check_single_option(self,
                           open_interest: int,
                           volume: int,
                           bid: float,
                           ask: float,
                           bid_size: int = 50,
                           ask_size: int = 50) -> Tuple[bool, float]:
        """
        Check if a single option passes VOSS criteria
        
        Args:
            open_interest: Open interest count
            volume: Daily volume
            bid: Bid price
            ask: Ask price
            bid_size: Contracts available at bid
            ask_size: Contracts available at ask
        
        Returns:
            (passes: bool, liquidity_score: float 0-1)
        """
        # Check minimum thresholds
        if open_interest < self.criteria.min_open_interest:
            return False, 0.0
        
        if volume < self.criteria.min_volume:
            return False, 0.0
        
        # Calculate spread percentage
        if ask <= 0:
            return False, 0.0
        
        spread_pct = (ask - bid) / ask
        if spread_pct > self.criteria.max_bid_ask_pct:
            return False, 0.0
        
        # Check bid/ask size if we have thresholds
        if bid_size < self.criteria.min_bid_ask_size or ask_size < self.criteria.min_bid_ask_size:
            return False, 0.0
        
        # Calculate liquidity score
        oi_score = min(open_interest / self.criteria.preferred_open_interest, 1.0)
        vol_score = min(volume / self.criteria.preferred_volume, 1.0)
        spread_score = 1 - (spread_pct / self.criteria.max_bid_ask_pct)
        
        score = (oi_score * 0.40 + vol_score * 0.30 + spread_score * 0.30)
        
        return True, score
    
    def get_summary_stats(self, chain: pd.DataFrame) -> dict:
        """
        Get summary statistics for an options chain
        
        Returns:
            Dictionary with min/max/avg for key liquidity metrics
        """
        if chain.empty:
            return {'status': 'empty'}
        
        stats = {
            'count': len(chain),
            'avg_liquidity_score': chain['liquidity_score'].mean() if 'liquidity_score' in chain.columns else 0,
            'avg_open_interest': chain['openInterest'].mean() if 'openInterest' in chain.columns else 0,
            'avg_volume': chain['volume'].mean() if 'volume' in chain.columns else 0,
            'avg_spread_pct': chain['spread_pct'].mean() if 'spread_pct' in chain.columns else 0,
            'best_strike': chain.iloc[0]['strike'] if 'strike' in chain.columns and 'liquidity_score' in chain.columns else None
        }
        
        return stats


# Convenience function for quick filtering
def filter_liquid_options(chain: pd.DataFrame,
                         min_oi: int = 1000,
                         min_volume: int = 500,
                         max_spread_pct: float = 0.10) -> pd.DataFrame:
    """
    Quick filtering of options chain
    
    Args:
        chain: Raw options chain DataFrame
        min_oi: Minimum open interest
        min_volume: Minimum daily volume
        max_spread_pct: Maximum bid-ask spread as percentage
    
    Returns:
        Filtered DataFrame
    """
    criteria = VOSSCriteria(
        min_open_interest=min_oi,
        min_volume=min_volume,
        max_bid_ask_pct=max_spread_pct
    )
    
    filter = VOSSLiquidityFilter(criteria)
    return filter.filter_options_chain(chain)
