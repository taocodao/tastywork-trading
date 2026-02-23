"""
CSP Position Manager
====================

Manages open CSP and Put Credit Spread positions.
Extends ThetaPortfolioManager with specific exit/roll logic.

Rules:
1. ≥ 50% max profit -> Close
2. DTE <= 7, profit < 50% -> Roll to next monthly
3. Underlying down > 10%, DTE > 14 -> Roll down for credit
4. DTE <= 3, Delta < 0.05 -> Let expire
5. ITM at DTE <= 1 -> Assignment alert
"""

import logging
from typing import List, Dict, Tuple
from datetime import datetime, date, timedelta

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.theta_spreads.portfolio_manager import ThetaPortfolioManager, ThetaPosition

logger = logging.getLogger(__name__)

class CSPPositionManager(ThetaPortfolioManager):
    """
    Manages CSPs and Put Credit Spreads, enforcing Dual-Core exit rules.
    """
    def __init__(self, total_capital: float = 100000.0, positions_file: str = "csp_positions.json"):
        super().__init__(total_capital=total_capital, positions_file=positions_file)
        
    def check_exit_rules(self, position_id: str, market_data: Dict) -> Dict:
        """
        Evaluate a position against the 5 CSP management rules.
        """
        pos = self.get_position(position_id)
        if not pos or pos.status != "OPEN":
            return {"action": "NONE", "reason": "Position not open or not found"}
            
        # Update Greeks and P&L
        current_price = market_data.get('current_price', 0)
        if current_price > 0:
            self.update_position_state(position_id, current_price)
            
        underlying_price = market_data.get('underlying_price', 0)
        
        # Rule 1: Close at 50% max profit
        if pos.unrealized_pnl_pct >= 0.50:
            return {
                "action": "CLOSE",
                "reason": f"Reached 50% max profit target ({pos.unrealized_pnl_pct*100:.1f}%)"
            }
            
        # Rule 5: Assignment Alert (ITM at DTE <= 1)
        if pos.days_to_expiration <= 1 and underlying_price > 0 and underlying_price < pos.strike:
            return {
                "action": "ASSIGNMENT_ALERT",
                "reason": f"DTE {pos.days_to_expiration} and ITM (Price: {underlying_price} < Strike: {pos.strike})"
            }
            
        # Rule 4: Let Expire (DTE <= 3, Delta < 0.05)
        # Assuming we track delta in market_data
        delta = abs(market_data.get('delta', pos.delta))
        if pos.days_to_expiration <= 3 and delta < 0.05:
            return {
                "action": "LET_EXPIRE",
                "reason": f"DTE {pos.days_to_expiration} and Delta {delta:.3f} < 0.05. Let expire worthless."
            }
            
        # Rule 2: Roll at DTE <= 7 if profit < 50%
        if pos.days_to_expiration <= 7:
            return {
                "action": "ROLL",
                "roll_type": "TIME",
                "reason": f"DTE {pos.days_to_expiration} (<= 7) and profit target not reached."
            }
            
        # Rule 3: Roll Down (Defensive) completely decoupled from DTE <= 7
        # Require underlying price history from market_data
        entry_underlying_price = market_data.get('entry_underlying_price')
        if entry_underlying_price and underlying_price > 0 and pos.days_to_expiration > 14:
            drop_pct = (entry_underlying_price - underlying_price) / entry_underlying_price
            if drop_pct > 0.10:
                return {
                    "action": "ROLL",
                    "roll_type": "DEFENSIVE_DOWN",
                    "reason": f"Underlying dropped {drop_pct*100:.1f}% (> 10%). Roll down for credit."
                }
                
        return {"action": "HOLD", "reason": "No exit rules triggered"}
