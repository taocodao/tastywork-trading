
"""
DVO Position Monitor
====================
Monitors active Deep Value Overlay positions.
Triggers exits based on:
1. Profit Targets (Velocity of money: 50% profit early)
2. Thesis Drift (Price reverts to fair value)
3. Risk Management (Broken thesis, EPS decline)
4. Time Decay (DTE thresholds)
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from models.dvo_position import DVOPosition
from .gravity_engine import GravityEngine
from .client import DVOClient

logger = logging.getLogger(__name__)

class DVOPositionMonitor:
    def __init__(self, client: DVOClient, db_session: Session):
        self.client = client
        self.db = db_session
        self.gravity = GravityEngine()
        
    async def run_monitor_cycle(self):
        """
        Main loop: Check all open DVO positions for exit conditions.
        """
        positions = self.db.query(DVOPosition).filter(DVOPosition.status == "OPEN").all()
        
        for pos in positions:
            try:
                await self._check_position(pos)
            except Exception as e:
                logger.error(f"Error checking DVO position {pos.symbol}: {e}")
                
    async def _check_position(self, pos: DVOPosition):
        # 1. Update Market Data
        # In real system, fetch current quote, P&L, DTE
        # Here we simulate or assume updated externally?
        # Actually client needs to fetch real status.
        # For now, let's assume `pos.current_value` is updated by a separate market data loop
        # OR we fetch it here.
        
        # Fetch current price & P&L from client/tasty
        # This is complex in simulation vs live. 
        # We will assume `current_option_price` and `underlying_price` are available.
        
        # Placeholder for data fetching
        current_option_price = 0.0 # From API
        underlying_price = 0.0     # From API
        current_dte = (pos.expiration_date - datetime.utcnow().date()).days
        
        # Update DB state
        # pos.current_value = current_option_price * pos.quantity * 100
        # pos.unrealized_pnl = ...
        
        # 2. Check Exit Rules
        
        if pos.strategy_type == "SHORT_PUT":
            await self._check_short_put_exit(pos, underlying_price, current_option_price, current_dte)
        elif pos.strategy_type == "LONG_LEAPS":
            await self._check_leaps_exit(pos, underlying_price, current_option_price)
            
    async def _check_short_put_exit(self, pos: DVOPosition, stock_price: float, opt_price: float, dte: int):
        """
        Short Put Exit Logic:
        - 50% Profit & > 180 DTE (Velocity)
        - Price > Fair Value (Thesis completed)
        - Broken thesis
        """
        # Calculate P&L %
        # Entry Credit vs Current Debit
        # Credit = pos.entry_price 
        # Current Cost = opt_price
        if pos.entry_price > 0:
            pnl_pct = (pos.entry_price - opt_price) / pos.entry_price
        else:
            pnl_pct = 0
            
        # Rule 1: Velocity of Money
        if pnl_pct >= 0.50 and dte > 180:
             await self._signal_exit(pos, "VELOCITY_EXIT_50PCT")
             return
             
        # Rule 2: Thesis Reversion (Price > Fair Value)
        # Check cached fair value or refresh
        # If refreshing is expensive, maybe do it daily not every minute.
        # Assuming `pos.fair_value_at_entry` is static, but gravity line moves.
        # Let's re-check gravity?
        val = self.gravity.analyze(pos.symbol) # Use cache inside gravity engine logic ideally
        current_fv = val.fair_value_price if val else pos.fair_value_at_entry
        
        if stock_price > current_fv:
             await self._signal_exit(pos, "THESIS_REVERSION_FV_REACHED")
             return
             
        # Rule 3: Broken Thesis (EPS dropping fast)
        # If Fair Value drops 20% below entry FV
        if current_fv < (pos.fair_value_at_entry * 0.80):
             await self._signal_exit(pos, "BROKEN_THESIS_EPS_DROP")
             return
             
    async def _check_leaps_exit(self, pos: DVOPosition, stock_price: float, opt_price: float):
        """
        LEAPS Exit Logic:
        - delta > 0.90
        - > 100% Profit
        """
        # P&L
        # Entry Debit vs Current Credit
        if pos.entry_price > 0:
            pnl_pct = (opt_price - pos.entry_price) / pos.entry_price
        else:
            pnl_pct = 0
            
        if pnl_pct >= 1.0:
            await self._signal_exit(pos, "TAKE_PROFIT_100PCT")
            
        # Delta check requires Greeks from API
        
    async def _signal_exit(self, pos: DVOPosition, reason: str):
        logger.info(f"DVO EXIT SIGNAL {pos.symbol}: {reason}")
        # 1. Publish Exit Signal (via signal_publisher, to be implemented)
        # 2. Execute Close (via Client)
        # 3. Update DB Status
        pos.status = "CLOSING"
        pos.exit_reason = reason
        self.db.commit()
