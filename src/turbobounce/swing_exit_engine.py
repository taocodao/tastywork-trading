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
    
    def _get_val(self, obj, key, default):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

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
                 bp_stop_loss_pct: float = 0.50,
                 exit_rsi: float = 65.0,
                 time_stop_days: int = 15,
                 pnl_pct: float = None) -> ExitDecision:

        # Extract position metadata
        hedge_dte = self._get_val(position, "hedge_dte", 14) 
        anchor_dte = self._get_val(position, "anchor_dte", 30)
        direction = self._get_val(position, "direction", "BULLISH").upper()
        strategy = self._get_val(position, "strategy_type", "DIAGONAL").upper()

        # Priority 0 / 3: Options PnL (Stop Loss & Profit Target)
        if pnl_pct is None:
            # Calculate live PnL dynamically if not passed from backtester
            entry_mark = self._get_val(position, "entry_mark", 0.0)
            if entry_mark > 0 and current_spread_mark > 0:
                if strategy == "CREDIT_SPREAD":
                    unrealized_pnl = entry_mark - current_spread_mark 
                else:
                    unrealized_pnl = current_spread_mark - entry_mark
                
                # bp_consumed acts as the denominator. If 0, fallback to entry_mark
                denominator = bp_consumed if bp_consumed > 0 else entry_mark
                pnl_pct = unrealized_pnl / denominator
            else:
                pnl_pct = 0.0

        if pnl_pct <= -bp_stop_loss_pct:
            return ExitDecision(ExitDecisionType.CLOSE_ALL, f"BP_STOP_LOSS: PnL {pnl_pct*100:.1f}% <= -{bp_stop_loss_pct*100}%", 0)

        # Aligning with historical Option PnL targets (+40% Longs, +60% Credit Spreads)
        if strategy == "CREDIT_SPREAD":
            profit_target = 0.60
            time_limit = 15
        elif strategy == "NAKED_LONG":
            profit_target = 0.40
            time_limit = 5
        else: # DIAGONAL
            profit_target = 0.40
            time_limit = 15

        if pnl_pct >= profit_target:
            return ExitDecision(ExitDecisionType.CLOSE_ALL, f"PROFIT_TARGET: Option PnL +{pnl_pct*100:.1f}% >= +{profit_target*100}%", 3)
            
        # Priority 4: HEDGE ROLL (Theta Kicker - optional safety for diagonals)
        roll_count = self._get_val(position, "roll_count", 0)
        if hedge_dte <= 1 and strategy == "DIAGONAL":
            if regime_score >= 50 and days_held < 10 and anchor_dte > 15 and ml_prob > 0.50 and roll_count < 2:
                return ExitDecision(ExitDecisionType.ROLL_HEDGE, "THETA_KICKER: Roll expiring hedge", 4)
            else:
                return ExitDecision(ExitDecisionType.CLOSE_ALL, "HEDGE_EXPIRING: Cannot roll hedge safely", 4)
                
        # Priority 5: TIME STOP (Aligning to backtest standard duration)
        if days_held >= time_limit:
            return ExitDecision(ExitDecisionType.CLOSE_ALL, f"TIME_STOP_STRATEGY: Held {days_held} days >= {time_limit}", 5)
            
        return ExitDecision(ExitDecisionType.HOLD, "HOLD", 99)
