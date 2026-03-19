"""
Stop Limit Manager
==================
Implements Law 3's trailing stop on the retained long put.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class StopLimitManager:
    """
    Manages the trailing stop limit on a position's long put once the short has been closed.
    """
    def __init__(self, config):
        self.config = config

    def calculate_stop(self, current_value: float, regime: str) -> float:
        """
        Calculates the trailing stop based on regime.
        """
        k_values = {
            'LOW_VOL': 0.40,
            'NORMAL': 0.55,
            'HIGH_VOL': 0.65,
            'CRISIS': 0.80, # or fallback
        }
        k = k_values.get(regime, 0.55)
        return current_value * (1 - k)

    def evaluate_stop(self, current_value: float, highest_value: float, trailing_stop: float, days_to_expiry: int) -> bool:
        """
        Evaluate if we should exit based on trailing stop or expiry.
        """
        if current_value <= trailing_stop:
            return True # Stop triggered
        if days_to_expiry <= getattr(self.config, 'V3_LAW1_HEDGE_REPLACE_DTE', 7):
            return True # Force close near expiry
        return False
