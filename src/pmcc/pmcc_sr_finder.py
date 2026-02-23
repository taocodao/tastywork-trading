import logging
import pandas as pd
import numpy as np
from typing import List

logger = logging.getLogger(__name__)

class SupportResistanceFinder:
    """
    Finds key support and resistance levels using swing highs/lows.
    Used to optimize Short Call strike selection in the PMCC strategy,
    preventing selling calls immediately below a major breakout point.
    """
    
    def __init__(self, pivot_window: int = 3):
        """
        Args:
            pivot_window: Number of days on each side required to confirm a pivot (swing high/low).
        """
        self.pivot_window = pivot_window

    def get_resistance_levels(self, df: pd.DataFrame, current_price: float, lookback: int = 60) -> List[float]:
        """
        Finds resistance levels above the current price over the lookback period.
        
        Args:
            df: Historical daily OHLCV dataframe.
            current_price: Current stock price.
            lookback: Number of days to look back for resistance.
            
        Returns:
            List of resistance levels sorted from closest to furthest.
        """
        if df is None or len(df) < (self.pivot_window * 2 + 1):
            return []
            
        # Focus on recent history relevant for 30-45 DTE short calls
        recent_df = df.tail(lookback)
        highs = recent_df['High'].values
        
        swing_highs = []
        w = self.pivot_window
        
        # Find local peaks (swing highs)
        for i in range(w, len(highs) - w):
            is_swing = True
            for j in range(1, w + 1):
                if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                    is_swing = False
                    break
            if is_swing:
                swing_highs.append(highs[i])
                
        # Always include the absolute high of the lookback period as major resistance
        absolute_high = recent_df['High'].max()
        if absolute_high not in swing_highs:
            swing_highs.append(absolute_high)
            
        # Filter only resistances above current price
        resistances = [r for r in swing_highs if r > current_price]
        
        if not resistances:
            return []
            
        # Sort ascending
        resistances.sort()
        
        # Merge clustered resistance zones (within 1.5% of each other)
        merged_resistances = [resistances[0]]
        for r in resistances[1:]:
            if r > merged_resistances[-1] * 1.015:
                merged_resistances.append(r)
            else:
                # Merge by averaging
                merged_resistances[-1] = (merged_resistances[-1] + r) / 2.0
                
        logger.debug(f"Found {len(merged_resistances)} resistance levels above {current_price:.2f}")
        return merged_resistances

    def get_support_levels(self, df: pd.DataFrame, current_price: float, lookback: int = 60) -> List[float]:
        """
        Finds support levels below the current price over the lookback period.
        Useful for long LEAPS entry scaling.
        """
        if df is None or len(df) < (self.pivot_window * 2 + 1):
            return []
            
        recent_df = df.tail(lookback)
        lows = recent_df['Low'].values
        
        swing_lows = []
        w = self.pivot_window
        
        for i in range(w, len(lows) - w):
            is_swing = True
            for j in range(1, w + 1):
                if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                    is_swing = False
                    break
            if is_swing:
                swing_lows.append(lows[i])
                
        absolute_low = recent_df['Low'].min()
        if absolute_low not in swing_lows:
            swing_lows.append(absolute_low)
            
        supports = [s for s in swing_lows if s < current_price]
        
        if not supports:
            return []
            
        # Sort descending (closest first)
        supports.sort(reverse=True)
        
        merged_supports = [supports[0]]
        for s in supports[1:]:
            if s < merged_supports[-1] * 0.985:  # more than 1.5% away
                merged_supports.append(s)
            else:
                merged_supports[-1] = (merged_supports[-1] + s) / 2.0
                
        logger.debug(f"Found {len(merged_supports)} support levels below {current_price:.2f}")
        return merged_supports
