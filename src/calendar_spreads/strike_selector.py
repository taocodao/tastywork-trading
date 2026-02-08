"""
Strike Selection for Calendar Spreads
======================================
Delta-based strike selection for optimal theta capture

Research basis:
- Neutral bias: 0.45-0.55 delta (ATM)
- Bullish bias: 0.55-0.65 delta (slightly ITM calls)
- Bearish bias: -0.45 to -0.55 delta (slightly ITM puts)

Key principle: Maximum time value at ATM = maximum theta
"""

from dataclasses import dataclass
from typing import Optional, Literal
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


@dataclass
class StrikeConfig:
    """
    Strike selection configuration
    
    Delta targets for different strategy biases:
    - Neutral: ATM for maximum theta
    - Bullish: Slightly ITM calls for positive delta
    - Bearish: Slightly ITM puts for negative delta
    """
    # Neutral (ATM) targets
    neutral_delta_min: float = 0.45
    neutral_delta_max: float = 0.55
    
    # Bullish (slightly ITM calls)
    bullish_delta_min: float = 0.55
    bullish_delta_max: float = 0.65
    
    # Bearish (slightly ITM puts)
    bearish_delta_min: float = -0.55
    bearish_delta_max: float = -0.45
    
    # Fallback: how close to ATM is acceptable
    atm_tolerance_pct: float = 0.02  # 2% of stock price


StrategyBias = Literal['neutral', 'bullish', 'bearish']


class CalendarStrikeSelector:
    """
    Select optimal strike for calendar spreads based on delta
    
    Usage:
        selector = CalendarStrikeSelector()
        
        # Select best strike from filtered chain
        strike = selector.select_strike(
            chain=filtered_options,
            current_price=450.0,
            strategy_bias='neutral'
        )
        
        # Or find specific strike with theta optimization
        strike = selector.select_theta_optimal_strike(
            short_chain=short_exp_options,
            long_chain=long_exp_options,
            current_price=450.0
        )
    """
    
    def __init__(self, config: Optional[StrikeConfig] = None):
        self.config = config or StrikeConfig()
    
    def select_strike(self,
                     chain: pd.DataFrame,
                     current_price: float,
                     strategy_bias: StrategyBias = 'neutral') -> Optional[float]:
        """
        Select optimal strike for calendar spread
        
        Args:
            chain: Options chain with 'delta', 'strike', and optionally 'liquidity_score'
            current_price: Current stock price
            strategy_bias: 'neutral', 'bullish', or 'bearish'
        
        Returns:
            Optimal strike price or None if no suitable options
        """
        if chain.empty:
            logger.warning("Empty chain provided to strike selector")
            return None
        
        # Get delta range based on bias
        delta_range = self._get_delta_range(strategy_bias)
        
        # Filter to target delta range
        if 'delta' in chain.columns:
            candidates = chain[
                (chain['delta'].abs() >= abs(delta_range[0])) &
                (chain['delta'].abs() <= abs(delta_range[1]))
            ].copy()
        else:
            # No delta available, use ATM fallback
            logger.warning("No delta column in chain, using ATM fallback")
            return self._find_atm_strike(chain, current_price)
        
        if candidates.empty:
            logger.info(
                f"No options in delta range [{delta_range[0]:.2f}, {delta_range[1]:.2f}], "
                f"using ATM fallback"
            )
            return self._find_atm_strike(chain, current_price)
        
        # Select strike with highest liquidity score in range
        if 'liquidity_score' in candidates.columns:
            best = candidates.nlargest(1, 'liquidity_score')
        else:
            # Fall back to closest to target delta
            target_delta = (delta_range[0] + delta_range[1]) / 2
            candidates['delta_diff'] = (candidates['delta'].abs() - abs(target_delta)).abs()
            best = candidates.nsmallest(1, 'delta_diff')
        
        strike = float(best.iloc[0]['strike'])
        delta = best.iloc[0]['delta']
        
        logger.info(
            f"Strike selection ({strategy_bias}): ${strike} "
            f"(delta: {delta:.2f}, target: {delta_range[0]:.2f}-{delta_range[1]:.2f})"
        )
        
        return strike
    
    def select_theta_optimal_strike(self,
                                   short_chain: pd.DataFrame,
                                   long_chain: pd.DataFrame,
                                   current_price: float,
                                   min_theta_differential: float = 0.01) -> Optional[float]:
        """
        Select strike that maximizes theta differential between expirations
        
        For calendar spreads, we want:
        - Short leg theta to decay faster than long leg
        - Both legs to have similar deltas (neutral spread)
        
        Args:
            short_chain: Near-term expiration options
            long_chain: Far-term expiration options
            current_price: Current stock price
            min_theta_differential: Minimum theta per day difference
        
        Returns:
            Optimal strike or None
        """
        if short_chain.empty or long_chain.empty:
            logger.warning("Missing chain data for theta optimization")
            return None
        
        # Find common strikes
        short_strikes = set(short_chain['strike'].unique())
        long_strikes = set(long_chain['strike'].unique())
        common_strikes = short_strikes & long_strikes
        
        if not common_strikes:
            logger.warning("No common strikes between expirations")
            return self._find_atm_strike(short_chain, current_price)
        
        # Calculate theta differential for each strike
        results = []
        for strike in common_strikes:
            short_opt = short_chain[short_chain['strike'] == strike]
            long_opt = long_chain[long_chain['strike'] == strike]
            
            if short_opt.empty or long_opt.empty:
                continue
            
            short_theta = short_opt.iloc[0].get('theta', 0)
            long_theta = long_opt.iloc[0].get('theta', 0)
            
            # Theta is negative, so short expiry has MORE negative theta
            # Calendar profit = |short_theta| - |long_theta| 
            theta_diff = abs(short_theta) - abs(long_theta)
            
            # Get delta for neutrality check
            short_delta = short_opt.iloc[0].get('delta', 0)
            long_delta = long_opt.iloc[0].get('delta', 0)
            
            # Prefer strikes close to ATM (high delta ~0.50)
            delta_score = 1 - abs(abs(short_delta) - 0.50)
            
            # Liquidity score if available
            liquidity = short_opt.iloc[0].get('liquidity_score', 0.5)
            
            # Combined score
            combined_score = theta_diff * 0.5 + delta_score * 0.3 + liquidity * 0.2
            
            results.append({
                'strike': strike,
                'theta_diff': theta_diff,
                'short_theta': short_theta,
                'long_theta': long_theta,
                'short_delta': short_delta,
                'long_delta': long_delta,
                'delta_score': delta_score,
                'liquidity': liquidity,
                'combined_score': combined_score
            })
        
        if not results:
            logger.warning("Could not calculate theta for any strikes")
            return self._find_atm_strike(short_chain, current_price)
        
        # Find best by combined score
        results_df = pd.DataFrame(results)
        
        # Filter by minimum theta differential
        valid = results_df[results_df['theta_diff'] >= min_theta_differential]
        
        if valid.empty:
            logger.info(
                f"No strikes with theta diff >= ${min_theta_differential:.3f}, "
                f"using best available"
            )
            valid = results_df
        
        best = valid.nlargest(1, 'combined_score').iloc[0]
        strike = float(best['strike'])
        
        logger.info(
            f"Theta-optimal strike: ${strike} | "
            f"Theta diff: ${best['theta_diff']:.3f}/day | "
            f"Delta: {best['short_delta']:.2f}/{best['long_delta']:.2f}"
        )
        
        return strike
    
    def _get_delta_range(self, bias: StrategyBias) -> tuple:
        """Get min/max delta for given strategy bias"""
        if bias == 'neutral':
            return (self.config.neutral_delta_min, self.config.neutral_delta_max)
        elif bias == 'bullish':
            return (self.config.bullish_delta_min, self.config.bullish_delta_max)
        else:  # bearish
            return (self.config.bearish_delta_min, self.config.bearish_delta_max)
    
    def _find_atm_strike(self, chain: pd.DataFrame, price: float) -> float:
        """Find strike closest to current price (ATM)"""
        if chain.empty:
            return price
        
        chain = chain.copy()
        chain['distance'] = abs(chain['strike'] - price)
        atm_strike = chain.nsmallest(1, 'distance').iloc[0]['strike']
        
        logger.info(f"ATM fallback: ${atm_strike} (price: ${price})")
        
        return float(atm_strike)
    
    def get_strike_range(self,
                        current_price: float,
                        width_pct: float = 0.10) -> tuple:
        """
        Get acceptable strike range around current price
        
        Args:
            current_price: Current stock price
            width_pct: Percentage range (e.g., 0.10 = ±10%)
        
        Returns:
            (min_strike, max_strike)
        """
        min_strike = current_price * (1 - width_pct)
        max_strike = current_price * (1 + width_pct)
        
        return min_strike, max_strike
    
    def validate_strike(self,
                       strike: float,
                       current_price: float,
                       short_delta: float,
                       long_delta: float) -> tuple[bool, str]:
        """
        Validate a strike choice for calendar spread
        
        Returns:
            (is_valid, reason)
        """
        # Check strike is reasonably close to price
        distance_pct = abs(strike - current_price) / current_price
        if distance_pct > 0.15:  # More than 15% away
            return False, f"Strike ${strike} is {distance_pct:.0%} away from price ${current_price}"
        
        # Check delta is reasonable for calendar
        if abs(short_delta) < 0.20 or abs(short_delta) > 0.80:
            return False, f"Short delta {short_delta:.2f} is too extreme for calendar"
        
        # Deltas should be similar (both ITM or both OTM)
        delta_diff = abs(abs(short_delta) - abs(long_delta))
        if delta_diff > 0.15:
            return True, f"Warning: Large delta difference ({delta_diff:.2f}) between legs"
        
        return True, "Valid strike for calendar spread"


# Convenience function
def find_atm_strike(strikes: list, current_price: float) -> float:
    """
    Find the at-the-money strike from a list
    
    Args:
        strikes: List of available strikes
        current_price: Current stock price
    
    Returns:
        Strike closest to current price
    """
    if not strikes:
        return current_price
    
    return min(strikes, key=lambda x: abs(x - current_price))


def get_strike_ladder(current_price: float,
                     interval: float = 5.0,
                     count: int = 5) -> list:
    """
    Generate a strike ladder around current price
    
    Args:
        current_price: Current stock price
        interval: Strike interval (e.g., $5)
        count: Number of strikes above and below ATM
    
    Returns:
        List of strikes centered around ATM
    """
    # Round to nearest interval
    atm = round(current_price / interval) * interval
    
    strikes = []
    for i in range(-count, count + 1):
        strikes.append(atm + (i * interval))
    
    return strikes
