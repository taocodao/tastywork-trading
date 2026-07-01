import logging
from typing import List
from src.otm_naked.sndk.live.state_manager import LivePosition

logger = logging.getLogger(__name__)

class LiveRiskManager:
    """Kill switches and portfolio safety limits."""
    
    def __init__(self, config):
        self.config = config
        self.daily_realized_pnl = 0.0
        self.peak_nav = 0.0
        
    def reset_daily_stats(self):
        """Called at market open to reset daily PnL trackers."""
        self.daily_realized_pnl = 0.0
        
    def record_pnl(self, realized_pnl: float):
        self.daily_realized_pnl += realized_pnl
        
    def update_peak_nav(self, nav: float):
        if nav > self.peak_nav:
            self.peak_nav = nav
            
    def is_safe_to_enter(self, nav: float, positions: List[LivePosition], target_direction: str, earnings_days_away: int) -> bool:
        """Returns True if all risk checks pass."""
        # Update peak NAV tracker
        self.update_peak_nav(nav)
        
        # 1. Daily Loss Limit (2% of NAV)
        daily_loss_limit = -0.02 * nav
        if self.daily_realized_pnl <= daily_loss_limit:
            logger.warning(f"KILL SWITCH: Daily loss limit exceeded ({self.daily_realized_pnl:.2f} <= {daily_loss_limit:.2f})")
            return False
            
        # 2. Max Drawdown Limit (15% from peak)
        if self.peak_nav > 0:
            drawdown = (self.peak_nav - nav) / self.peak_nav
            if drawdown > 0.15:
                logger.warning(f"KILL SWITCH: Max drawdown exceeded ({drawdown*100:.1f}%)")
                return False
                
        # 3. Earnings Blackout
        if earnings_days_away <= 14:
            logger.warning(f"RISK LIMIT: Earnings within 14 days ({earnings_days_away} days away)")
            return False
            
        # 4. Position Count Limits
        calls = [p for p in positions if p.opt_type == "call"]
        puts = [p for p in positions if p.opt_type == "put"]
        
        if target_direction == "call" and len(calls) >= self.config.max_rungs_per_side:
            logger.warning(f"RISK LIMIT: Max call rungs reached ({len(calls)})")
            return False
            
        if target_direction == "put" and len(puts) >= self.config.max_rungs_per_side:
            logger.warning(f"RISK LIMIT: Max put rungs reached ({len(puts)})")
            return False
            
        return True
