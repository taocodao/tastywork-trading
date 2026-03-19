import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

class AllocationOptimizer:
        """
        Implements the Dynamic Rebalancing Core-Satellite Matrix for TurboCore v2.0 LEAPS-Enhanced.
        
        Inputs: 
        - Regime (BULL, SIDEWAYS, BEAR, BEAR_SMA_FORCED)
        - Signal (1 for Long, 0 for Defensive/Cash, -1 for Short)
        - ML Confidence (0.0 to 1.0)
        - QQQ Drawdown from ATH (-0.0 to -1.0)
        
        Outputs: Target percentage allocation vector across [QQQ, QLD, QQQ_LEAPS, SGOV]
        """
        
        def __init__(self, params: dict = None):
            self.params = params or {}
            
            # Confidence Thresholds
            self.bull_high_conf_thresh = self.params.get('bull_high_conf_thresh', 0.60)
            self.bull_med_conf_thresh = self.params.get('bull_med_conf_thresh', 0.50)
            self.deep_crash_thresh = self.params.get('deep_crash_thresh', -0.30)
            
        def get_target_allocation(self, regime: str, signal: int, ml_confidence: float, qqq_drawdown: float = 0.0) -> Dict[str, float]:
            """
            Determines the base matrix allocation based on the regime, signal, and ML confidence.
            Also accounts for Deep Crash scenarios based on drawdown from ATH.
            """
            # 1. DEEP CRASH RECOVERY RULE (Overrides normal bear rules if we are recovering)
            if qqq_drawdown <= self.deep_crash_thresh and regime != "BEAR":
                base_alloc = {"QQQ": 0.10, "QLD": 0.10, "QQQ_LEAPS": 0.70, "SGOV": 0.10}
                logger.debug(f"Deep Crash Recovery Mode Active. Drawdown: {qqq_drawdown:.2%}")
                return base_alloc
                
            # 2. HARD BEAR (Risk-Off)
            if regime in ["BEAR", "BEAR_SMA_FORCED"]:
                base_alloc = {"QQQ": 0.0, "QLD": 0.0, "QQQ_LEAPS": 0.0, "SGOV": 1.0}
                logger.debug("Regime is BEAR. Hard exit to 100% SGOV.")
                return base_alloc
                
            # 3. TRANSITIONAL / SIDEWAYS
            if regime == "SIDEWAYS":
                base_alloc = {"QQQ": 0.50, "QLD": 0.20, "QQQ_LEAPS": 0.25, "SGOV": 0.05}
                return base_alloc
                
            # 4. BULL REGIME
            if regime == "BULL":
                # Continuous Kelly-based sizing (Fix for Masked Signal Problem)
                p = ml_confidence
                b = 2.0  # Assumed win/loss ratio for LEAPS trend following
                kelly_full = (p * b - (1.0 - p)) / b
                
                # Quarter-Kelly safety margin, with multiplier to hit 70% max allocation
                kelly_quarter = kelly_full * 0.25
                regime_leverage_cap = 4.0
                
                if kelly_quarter <= 0:
                    leaps_weight = 0.10
                else:
                    leaps_weight = min(0.70, kelly_quarter * regime_leverage_cap)
                    
                leaps_weight = round(max(0.10, leaps_weight), 3)
                
                qld_weight = 0.20
                remaining = 1.0 - leaps_weight - qld_weight
                
                sgov_weight = 0.05 if leaps_weight <= 0.15 else 0.0
                qqq_weight = round(remaining - sgov_weight, 3)
                
                base_alloc = {
                    "QQQ": float(qqq_weight),
                    "QLD": float(qld_weight),
                    "QQQ_LEAPS": float(leaps_weight),
                    "SGOV": float(sgov_weight)
                }
                    
            return base_alloc
        
if __name__ == "__main__":
    allocator = AllocationOptimizer()
    print("Test Scenario: BULL, Golden Cross, 85% Confidence")
    print(allocator.get_target_allocation("BULL", 1, 0.85, 0.0))
    
    print("Test Scenario: BULL, Golden Cross, 40% Confidence")
    print(allocator.get_target_allocation("BULL", 1, 0.40, 0.0))
    
    print("Test Scenario: BEAR_SMA_FORCED")
    print(allocator.get_target_allocation("BEAR_SMA_FORCED", 1, 0.99, -0.40))
    
    print("Test Scenario: TRANSITIONAL Deep Crash Recovery")
    print(allocator.get_target_allocation("SIDEWAYS", 1, 0.8, -0.35))
