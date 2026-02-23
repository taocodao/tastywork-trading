"""
LSTM IV Switch Router
=====================

Extends the LSTM IV Forecaster to output a strategy routing signal.
Biases the Dual-Core allocator toward the core that benefits from the predicted IV direction.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# Assumes existence from PMCC ML Phase
from src.pmcc.ml.iv_forecaster import LSTMIVForecaster

logger = logging.getLogger(__name__)

@dataclass
class RoutingSignal:
    bias: str # "CSP" | "PMCC" | "NEUTRAL"
    csp_weight_boost: float
    pmcc_weight_boost: float
    reason: str
    confidence: float

class IVSwitchRouter:
    """
    Translates IV predictions into Capital Allocation Biases.
    """
    def __init__(self, forecaster: LSTMIVForecaster, confidence_threshold: float = 0.70):
        self.forecaster = forecaster
        self.confidence_threshold = confidence_threshold
        
    def get_routing_signal(self, market_data: Dict[str, Any]) -> RoutingSignal:
        """
        Polls the LSTM for an IV forecast and maps it to a strategy bias.
        """
        if not self.forecaster:
            return self._neutral("No LSTM Forecaster initialized.")
            
        try:
            # Expected return mapping: {"direction": "UP"|"DOWN"|"FLAT", "confidence": float}
            prediction = self.forecaster.predict(market_data) 
            
            direction = prediction.get("direction", "FLAT")
            confidence = prediction.get("confidence", 0.0)
            
            # Require high confidence to modify macro allocation
            if confidence < self.confidence_threshold:
                return self._neutral(f"LSTM confidence {confidence:.2f} < {self.confidence_threshold}")
                
            if direction == "UP":
                return RoutingSignal(
                    bias="CSP",
                    csp_weight_boost=0.10,   # Boost CSP by 10%
                    pmcc_weight_boost=-0.05, # Reduce LEAPS (expensive)
                    reason=f"LSTM predicts IV EXPANSION (Conf: {confidence:.2f}) -> CSP premium opportunity",
                    confidence=confidence
                )
            elif direction == "DOWN":
                return RoutingSignal(
                    bias="PMCC",
                    csp_weight_boost=-0.05,  # Reduce CSP (thin premiums)
                    pmcc_weight_boost=0.10,  # Boost LEAPS (cheap entries)
                    reason=f"LSTM predicts IV CONTRACTION (Conf: {confidence:.2f}) -> LEAPS entry opportunity",
                    confidence=confidence
                )
            else:
                return self._neutral("LSTM predicts FLAT IV Environment.")
                
        except Exception as e:
            logger.error(f"Error executing IV Switch Router: {e}")
            return self._neutral(f"Error querying LSTM: {str(e)}")
            
    def _neutral(self, reason: str) -> RoutingSignal:
        return RoutingSignal(
            bias="NEUTRAL",
            csp_weight_boost=0.0,
            pmcc_weight_boost=0.0,
            reason=reason,
            confidence=0.0
        )
