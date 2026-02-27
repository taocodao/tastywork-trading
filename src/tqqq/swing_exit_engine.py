"""
Swing Exit Engine
=================
5-priority cascade for diagonal positions, featuring the Theta Kicker.
"""

from enum import Enum, auto
import logging
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

class ExitDecisionType(Enum):
    HOLD = auto()
    CLOSE_ALL = auto()
    ROLL_HEDGE = auto()

@dataclass
class ExitDecision:
    decision: ExitDecisionType
    reason: str
    priority: int

class SwingExitEngine:
    """
    Evaluates exit conditions for the TQQQ Put Diagonal Swing Trade.
    """
    
    def evaluate(self, 
                 position, 
                 current_price: float, 
                 rsi_2: float, 
                 sma_5: float, 
                 regime_score: int, 
                 ml_prob: float, 
                 days_held: int,
                 ou_half_life: float = np.inf,
                 current_spread_mark: float = 0.0,
                 bp_consumed: float = 0.0,
                 bp_stop_loss_pct: float = 0.15,
                 exit_rsi: float = 65.0,
                 time_stop_days: int = 15) -> ExitDecision:

        # Extract option DTEs
        hedge_dte = getattr(position, "hedge_dte", 14) 
        anchor_dte = getattr(position, "anchor_dte", 30)

        # Priority 0: BP-Based Stop Loss (15% of BP consumed)
        entry_mark = getattr(position, "entry_mark", 0.0)
        # For credit spreads, mark increases mean loss. For backspreads, mark decreases mean loss.
        # Assuming current_spread_mark is the cost to close (positive means we pay to close).
        if bp_consumed > 0 and current_spread_mark > 0 and entry_mark != 0:
            unrealized_loss = current_spread_mark - entry_mark
            if unrealized_loss > (bp_consumed * bp_stop_loss_pct):
                return ExitDecision(ExitDecisionType.CLOSE_ALL, f"BP_STOP_LOSS: Loss ${unrealized_loss:.2f} > {bp_stop_loss_pct*100}% of BP", 0)

        # Priority 1: EMERGENCY
        entry_price = getattr(position, "entry_price", current_price)
        pct_change = (current_price - entry_price) / entry_price if entry_price > 0 else 0
        if pct_change <= -0.10:
            return ExitDecision(ExitDecisionType.CLOSE_ALL, "EMERGENCY: Underlying price drop >= 10%", 1)
            
        # Priority 2: REGIME
        if regime_score < 30:
            return ExitDecision(ExitDecisionType.CLOSE_ALL, "REGIME: Crash guard score plummeted < 30", 2)
            
        # Priority 3: PROFIT TARGET / BOUNCE
        if pct_change >= 0.05:
            return ExitDecision(ExitDecisionType.CLOSE_ALL, f"PROFIT_TARGET: +{pct_change:.1%} >= +5%", 3)
            
        if rsi_2 > exit_rsi:
            return ExitDecision(ExitDecisionType.CLOSE_ALL, f"BOUNCE: RSI-2 {rsi_2:.1f} > DE-Target {exit_rsi:.1f}", 3)
            
        # Priority 4: HEDGE ROLL (Theta Kicker)
        roll_count = getattr(position, "roll_count", 0)
        if hedge_dte <= 1:
            if regime_score >= 50 and days_held < 10 and anchor_dte > 15 and ml_prob > 0.50 and roll_count < 2:
                return ExitDecision(ExitDecisionType.ROLL_HEDGE, "THETA_KICKER: Roll expiring hedge", 4)
            else:
                return ExitDecision(ExitDecisionType.CLOSE_ALL, "HEDGE_EXPIRING: Cannot roll hedge safely", 4)
                
        # Priority 5: ADAPTIVE TIME STOP
        # Use dynamic DE parameter if passed, otherwise fallback to OU half-life bounds
        if days_held >= time_stop_days:
            return ExitDecision(ExitDecisionType.CLOSE_ALL, f"TIME_STOP: Held {days_held} days >= DE-Target {time_stop_days}", 5)
            
        time_limit = min(max(ou_half_life * 2, 3), 15)
        if days_held >= time_limit:
            return ExitDecision(ExitDecisionType.CLOSE_ALL, f"TIME_STOP_OU: Held {days_held} days >= {time_limit:.1f} (2x OU half-life)", 5)
            
        return ExitDecision(ExitDecisionType.HOLD, "HOLD", 99)
