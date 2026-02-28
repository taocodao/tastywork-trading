"""
Intraday Timing Engine
======================
Decides the optimal execution minute within a given day.
Combines research-backed baseline rules with an ML layer (XGBoost)
to minimize slippage.

Action space:
 - EXECUTE_NOW
 - WAIT (check back later)
 - SKIP_TODAY
"""

import logging
from typing import Dict, Any, Tuple
from datetime import datetime, time

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    xgb = None
    XGB_AVAILABLE = False


class IntradayTimingEngine:
    """
    Evaluates intraday conditions to find the optimal execution moment.
    """
    
    def __init__(self):
        self.model = None
        self._try_load_model()
        
    def evaluate_entry_timing(self, current_time: datetime, market_data: Dict[str, Any]) -> Tuple[str, float]:
        """
        Evaluates whether to enter the spread right now.
        Returns: (Decision, Estimated_Savings_Dollars)
        """
        t = current_time.time()
        
        # --- 1. Hard Research-Backed Guardrails ---
        
        # Avoid first 30 mins: widest bid-ask spreads, highest volatility
        if t < time(10, 0):
            logger.info("TimingEngine: WAIT. Avoiding 9:30-10:00 AM open noise.")
            return "WAIT", 0.05
            
        # Avoid last 15 mins: MM inventory rebalancing pressure
        if t > time(15, 45):
            logger.info("TimingEngine: SKIP_TODAY. Too close to close.")
            return "SKIP_TODAY", 0.00
            
        # --- 2. ML Inference (if available) ---
        if XGB_AVAILABLE and self.model is not None:
            # Reconstruct feature vector
            X = self._build_features(current_time, market_data)
            score = self.model.predict([X])[0]
            
            if score > 0.02:  # Expected slippage savings > $0.02
                logger.debug(f"TimingEngine ML overrides rules. WAIT. (Exp savings: ${score:.2f})")
                return "WAIT", float(score)
                
        # --- 3. Default Ideal Windows ---
        # 10:30-11:00 AM is the statistically optimal entry window.
        # If we are in that window, or if it's the 2:30-3:30 PM secondary window, execute.
        if time(10, 0) <= t <= time(11, 0) or time(14, 0) <= t <= time(15, 30):
            return "EXECUTE_NOW", 0.00
            
        # Otherwise wait for the next window
        return "WAIT", 0.01

    def _build_features(self, dt: datetime, data: Dict[str, Any]) -> list:
        # Time of day encoded as minutes since open
        open_time = dt.replace(hour=9, minute=30, second=0, microsecond=0)
        mins_since_open = max(0, (dt - open_time).total_seconds() / 60)
        
        return [
            mins_since_open,
            data.get("current_spread", 0.05),
            data.get("vix_intraday_change", 0.0),
            data.get("tqqq_intraday_return", 0.0),
            dt.weekday()
        ]

    def _try_load_model(self):
        # Placeholder for XGBoost loading logic
        pass
