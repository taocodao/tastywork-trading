
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ZebraPositionSizer:
    """Calculate position size based on user's risk profile."""
    
    RISK_PROFILES = {
        "LOW":    {"max_pct": 0.05, "max_contracts": 1, "ml_min": 0.70},
        "MEDIUM": {"max_pct": 0.10, "max_contracts": 3, "ml_min": 0.60},
        "HIGH":   {"max_pct": 0.15, "max_contracts": 5, "ml_min": 0.55},
    }
    
    def calculate(
        self, 
        user_capital: float, 
        risk_level: str, 
        signal_cost: float, 
        ml_confidence: float
    ) -> Dict[str, Any]:
        """
        Calculate suggested position size.
        
        Returns: 
            Dict containing:
            - contracts: int
            - capital_required: float
            - should_trade: bool
            - reason: str (if should_trade is False)
        """
        profile = self.RISK_PROFILES.get(risk_level, self.RISK_PROFILES["MEDIUM"])
        
        # 1. Check ML Confidence
        if ml_confidence < profile["ml_min"]:
            return {
                "contracts": 0,
                "should_trade": False,
                "reason": f"ML Confidence {ml_confidence:.2f} < Min {profile['ml_min']}"
            }
            
        # 2. Capital Allocation
        max_capital = user_capital * profile["max_pct"]
        
        # 3. Contract Sizing (Floor division)
        # Prevent division by zero if signal cost is missing or zero
        if signal_cost <= 0:
             return {
                "contracts": 0,
                "should_trade": False,
                "reason": "Signal cost zero or invalid"
            }
            
        contracts_by_capital = int(max_capital // (signal_cost * 100))
        
        # 4. Cap by Risk Profile
        contracts = min(contracts_by_capital, profile["max_contracts"])
        
        # 5. Min contract check
        if contracts < 1:
             return {
                "contracts": 0,
                "should_trade": False,
                "reason": f"Insufficient capital/allocation. Max alloc: ${max_capital:.2f}, Cost: ${signal_cost*100:.2f}"
            }
            
        return {
            "contracts": contracts,
            "capital_required": contracts * signal_cost * 100,
            "should_trade": True,
            "reason": "Criteria met"
        }
