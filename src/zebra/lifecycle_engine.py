"""
ZEBRA Lifecycle Engine
=======================
Evaluates open positions and determines management actions.
"""

import logging
from enum import Enum
from typing import Tuple, Optional
from datetime import datetime
from dataclasses import dataclass

from config import (
    ZEBRA_PROFIT_TARGET_PCT, ZEBRA_TIME_EXIT_PCT,
    ZEBRA_STOP_LOSS_PCT, ZEBRA_RECENTER_DOWN_PCT,
    ZEBRA_RECENTER_UP_PCT, ZEBRA_ASSIGNMENT_DTE,
    ZEBRA_DIVIDEND_DAYS, ZEBRA_MAX_RECENTERS
)

logger = logging.getLogger(__name__)

class ZebraAction(Enum):
    HOLD = "HOLD"
    TAKE_PROFIT = "TAKE_PROFIT"
    TIME_EXIT = "TIME_EXIT"
    STOP_LOSS = "STOP_LOSS"
    RECENTER_LOSS = "RECENTER_LOSS"   # Move strikes to follow adverse move
    RECENTER_PROFIT = "RECENTER_PROFIT" # Move/Roll to lock gains/reset delta
    ASSIGNMENT_EXIT = "ASSIGNMENT_EXIT"
    DIVIDEND_EXIT = "DIVIDEND_EXIT"
    MAX_LOSS_EXIT = "MAX_LOSS_EXIT"   # Safety valve

@dataclass
class ZebraPositionState:
    """Snapshot of current position state for evaluation."""
    symbol: str
    direction: str # LONG/SHORT
    entry_price: float
    current_stock_price: float
    
    # Contract details
    long_strike: float
    short_strike: float
    contracts: int
    expiry: datetime
    
    # Financials
    entry_debit: float
    current_value: float # Mark-to-market total value
    
    # Time
    entry_date: datetime
    current_date: datetime
    
    # Metadata
    recenters_count: int = 0
    short_leg_delta: float = 0.50 # Current delta of short leg


class ZebraLifecycleEngine:
    """
    Evaluates ZEBRA positions against the decision tree.
    """
    
    def evaluate(self, state: ZebraPositionState) -> Tuple[ZebraAction, str]:
        """
        Evaluate position state and return recommended action.
        
        Returns:
            Tuple(Action, Reason string)
        """
        # 1. Calculate Core Metrics
        pnl = state.current_value - state.entry_debit
        pnl_pct = (pnl / state.entry_debit) * 100 if state.entry_debit != 0 else 0
        
        days_held = (state.current_date - state.entry_date).days
        total_duration = (state.expiry - state.entry_date).days
        time_used_pct = (days_held / total_duration * 100) if total_duration > 0 else 100
        days_to_expiry = (state.expiry - state.current_date).days
        
        stock_move_pct = ((state.current_stock_price - state.entry_price) / state.entry_price) * 100
        
        # 2. Safety Checks (Assignment/Dividend)
        # Short leg ITM check
        short_itm = False
        if state.direction == "LONG":
            if state.current_stock_price > state.short_strike: short_itm = True
        else: # SHORT
            if state.current_stock_price < state.short_strike: short_itm = True
            
        if short_itm and days_to_expiry <= ZEBRA_ASSIGNMENT_DTE:
            return ZebraAction.ASSIGNMENT_EXIT, f"Short leg ITM with {days_to_expiry} DTE"
            
        # Dividend check would go here (requires ex-div date data)
        # if short_itm and days_to_ex_div <= ZEBRA_DIVIDEND_DAYS:
        #    return ZebraAction.DIVIDEND_EXIT, "Dividend risk on ITM short leg"

        # 3. Stop Loss
        if pnl_pct <= ZEBRA_STOP_LOSS_PCT:
            return ZebraAction.STOP_LOSS, f"P&L {pnl_pct:.1f}% hit stop ({ZEBRA_STOP_LOSS_PCT}%)"
            
        # 4. Profit Target
        # "50% of max theoretical profit" is tricky for synthetic stock.
        # Approx: If stock moves 2x debit, we doubled our money?
        # Standard ZEBRA rule: Take profit at 25-50% return on debit for management
        if pnl_pct >= ZEBRA_PROFIT_TARGET_PCT:
            return ZebraAction.TAKE_PROFIT, f"P&L {pnl_pct:.1f}% hit target ({ZEBRA_PROFIT_TARGET_PCT}%)"

        # 5. Time Exit
        if time_used_pct >= ZEBRA_TIME_EXIT_PCT:
            return ZebraAction.TIME_EXIT, f"Time used {time_used_pct:.1f}% >= {ZEBRA_TIME_EXIT_PCT}%"

        # 6. Re-center Logic (Adverse Move)
        # Only if we haven't exceeded max re-centers
        if state.recenters_count < ZEBRA_MAX_RECENTERS:
            if state.direction == "LONG":
                # Bullish: Stock drops -> Re-center DOWN
                if stock_move_pct <= ZEBRA_RECENTER_DOWN_PCT:
                     # Check if we still have conviction (DC score check happens in monitor)
                     return ZebraAction.RECENTER_LOSS, f"Stock dropped {stock_move_pct:.1f}%"
            else:
                # Bearish: Stock rallies -> Re-center UP (loss management)
                if stock_move_pct >= abs(ZEBRA_RECENTER_DOWN_PCT): # e.g. +8%
                    return ZebraAction.RECENTER_LOSS, f"Stock rallied {stock_move_pct:.1f}%"

        # 7. Re-center Logic (Favorable Move / Delta Compression)
        # If delta of short leg gets too high (deep ITM), we lose the "zero extrinsic" benefit/gamma
        # or if we just want to lock in gains and roll up
        # Typically handled by Profit Target, but specific "Roll Up" logic exists
        # Not implementing complex roll-up logic in Phase 1 simple path. 
        # Rely on Take Profit -> New Entry

        return ZebraAction.HOLD, f"P&L: {pnl_pct:.1f}%, DTE: {days_to_expiry}"
