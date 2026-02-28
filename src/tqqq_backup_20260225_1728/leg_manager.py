"""
TQQQ Leg Manager
================
Quantitative logic to evaluate when to leg out of a vertical spread,
when to sell the retained long put, and when to abandon the position.
"""

import logging

logger = logging.getLogger(__name__)

class TQQQLegManager:
    """
    Evaluates specific leg management conditions based on current option values,
    time to expiration, and ML-driven regime signals.
    """
    
    def evaluate_leg_out(
        self,
        short_put_value: float,
        original_credit: float,
        dte: int,
        regime: str,
        vix_direction: str,
        confidence: float,
        legout_threshold: float,
        min_dte: int,
        min_confidence: float
    ) -> bool:
        """
        Should we leg out of the vertical spread by buying back the short put?
        
        Leg-out requires:
        1. Short put must be cheap (e.g., <= 15% of original credit).
        2. Plenty of time left on the clock (e.g., >= 14 days).
        3. Calm market regime with VIX not predicting a sudden spike (e.g., LOW_VOL + NEUTRAL).
        4. High AI confidence.
        """
        is_cheap = short_put_value <= (original_credit * legout_threshold)
        has_time = dte >= min_dte
        is_calm_regime = regime == "LOW_VOL" and vix_direction == "NEUTRAL"
        is_confident = confidence >= min_confidence
        
        if is_cheap and has_time and is_calm_regime and is_confident:
            logger.info(f"Leg-Out Triggered: Short put value ${short_put_value:.2f} <= Threshold "
                        f"(${original_credit * legout_threshold:.2f}). DTE: {dte}. Regime: {regime}.")
            return True
            
        return False
        
    def evaluate_long_put_sell(
        self,
        long_put_current_value: float,
        long_put_legout_value: float,
        profit_target_mult: float,
        regime: str,
        vix_direction: str
    ) -> bool:
        """
        Should we take profit on the retained long put?
        
        Take profit requires:
        1. VIX is actively spiking (HIGH_VOL or CRISIS) + RISING direction.
        2. The long put has multiplied in value since the leg-out (e.g., >= 2.0x).
        """
        is_spiking = regime in ["HIGH_VOL", "CRISIS"] and vix_direction == "VIX_RISING"
        target_value = long_put_legout_value * profit_target_mult
        is_profitable = long_put_current_value >= target_value
        
        if is_spiking and is_profitable:
            logger.info(f"VIX Spike Triggered Profit Take: Long put value ${long_put_current_value:.2f} >= "
                        f"Target (${target_value:.2f}). Regime: {regime}.")
            return True
            
        return False
        
    def evaluate_abandon(
        self, 
        long_put_current_value: float, 
        min_value: float, 
        dte: int
    ) -> bool:
        """
        Should we give up on the retained long put and close the trade?
        
        Abandon if:
        1. Theta decay has eroded the value too much (e.g., <= $0.10).
        2. We are too close to expiration (e.g., <= 5 days).
        """
        if long_put_current_value <= min_value:
            logger.info(f"Abandoning long put: Value ${long_put_current_value:.2f} <= Min (${min_value:.2f}).")
            return True
            
        if dte <= 5:
            logger.info(f"Abandoning long put: DTE ({dte}) <= 5.")
            return True
            
        return False
