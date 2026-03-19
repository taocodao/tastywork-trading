import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

class AllocationOptimizer:
    """
    Implements the Dynamic Rebalancing Core-Satellite Matrix.
    
    Inputs: 
    - Regime (BULL, SIDEWAYS, BEAR, BEAR_SMA_FORCED)
    - Signal (1 for Long, 0 for Defensive/Cash, -1 for Short)
    - ML Confidence (0.0 to 1.0)
    
    Outputs: Target percentage allocation vector across [QQQ, QLD, TQQQ, SGOV]
    """
    
    def __init__(self, params: dict = None):
        self.params = params or {}
        
        # Default Params (Used if not overridden by Optuna search)
        self.bull_high_conf_thresh = self.params.get('bull_high_conf_thresh', 0.737)
        self.bull_med_conf_thresh = self.params.get('bull_med_conf_thresh', 0.513)
        
        # Bull High Config (Aggressive)
        self.bh_qqq = self.params.get('bh_qqq', 0.17)
        self.bh_qld = self.params.get('bh_qld', 0.26)
        self.bh_tqqq = self.params.get('bh_tqqq', 0.56)
        self.bh_sgov = self.params.get('bh_sgov', 0.01)
        
        # Bull Medium Config (Moderate)
        self.bm_qqq = self.params.get('bm_qqq', 0.40)
        self.bm_qld = self.params.get('bm_qld', 0.00)
        self.bm_tqqq = self.params.get('bm_tqqq', 0.60)
        self.bm_sgov = self.params.get('bm_sgov', 0.00)
        
        # Sideways / Defensive Config (Wait/Side)
        self.def_qqq = self.params.get('def_qqq', 0.66)
        self.def_qld = self.params.get('def_qld', 0.15)
        self.def_tqqq = self.params.get('def_tqqq', 0.00)
        self.def_sgov = self.params.get('def_sgov', 0.19)
        
    def get_target_allocation(self, regime: str, signal: int, ml_confidence: float) -> Dict[str, float]:
        """
        Determines the base matrix allocation based on the regime, and scales 
        the leveraged components using fractional Kelly (approximated via confidence).
        """
        base_alloc = {"QQQ": 0.0, "QLD": 0.0, "TQQQ": 0.0, "SGOV": 1.0}
        
        # 1. HARD BEAR (SMA200 broken or HMM screams Crisis) -> Risk Off
        if regime in ["BEAR", "BEAR_SMA_FORCED"]:
            base_alloc["SGOV"] = 1.0
            logger.info("Regime is BEAR. Hard exit to 100% SGOV.")
            return base_alloc
            
        # 2. TRANSITIONAL / SIDEWAYS
        if regime == "SIDEWAYS":
            if signal == 1 and ml_confidence > self.bull_med_conf_thresh:
                base_alloc = {"QQQ": self.bm_qqq, "QLD": self.bm_qld, "TQQQ": self.bm_tqqq, "SGOV": self.bm_sgov}
            else:
                base_alloc = {"QQQ": self.def_qqq, "QLD": self.def_qld, "TQQQ": self.def_tqqq, "SGOV": self.def_sgov}
            return base_alloc
            
        # 3. BULL REGIME
        if regime == "BULL":
            if signal == 1:
                if ml_confidence > self.bull_high_conf_thresh:
                    base_alloc = {"QQQ": self.bh_qqq, "QLD": self.bh_qld, "TQQQ": self.bh_tqqq, "SGOV": self.bh_sgov}
                elif ml_confidence > self.bull_med_conf_thresh:
                    base_alloc = {"QQQ": self.bm_qqq, "QLD": self.bm_qld, "TQQQ": self.bm_tqqq, "SGOV": self.bm_sgov}
                else:
                    base_alloc = {"QQQ": self.def_qqq, "QLD": self.def_qld, "TQQQ": self.def_tqqq, "SGOV": self.def_sgov}
            else:
                base_alloc = {"QQQ": self.def_qqq, "QLD": self.def_qld, "TQQQ": self.def_tqqq, "SGOV": self.def_sgov}
                
        return base_alloc
        
if __name__ == "__main__":
    allocator = AllocationOptimizer()
    print("Test Scenario: BULL, Golden Cross, 85% Confidence")
    print(allocator.get_target_allocation("BULL", 1, 0.85))
    
    print("Test Scenario: BULL, Golden Cross, 40% Confidence")
    print(allocator.get_target_allocation("BULL", 1, 0.40))
    
    print("Test Scenario: BEAR_SMA_FORCED")
    print(allocator.get_target_allocation("BEAR_SMA_FORCED", 1, 0.99))
