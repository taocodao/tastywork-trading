"""
Calendar Spreads Bot - Risk Manager
====================================

Enforces risk limits and position sizing rules.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from config import (
    ACCOUNT_SIZE, RISK_PER_TRADE_PCT, MAX_CONCURRENT_POSITIONS,
    MAX_DAILY_LOSS_PCT, MIN_TRADE_COST, MAX_TRADE_COST,
    MIN_VIX, MAX_VIX
)

logger = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    """Result of a risk check."""
    passed: bool
    reason: str = ""
    
    def __bool__(self) -> bool:
        return self.passed


class RiskManager:
    """
    Enforces risk management rules for calendar spreads.
    
    Rules:
    - Max risk per trade: 2% of account
    - Max concurrent positions: 3
    - Max daily loss: 3% of account
    - Trade within VIX range
    - Stop after consecutive losses
    """
    
    def __init__(
        self,
        account_size: float = ACCOUNT_SIZE,
        max_risk_pct: float = RISK_PER_TRADE_PCT,
        max_positions: int = MAX_CONCURRENT_POSITIONS,
        max_daily_loss_pct: float = MAX_DAILY_LOSS_PCT
    ):
        self.account_size = account_size
        self.max_risk_pct = max_risk_pct
        self.max_positions = max_positions
        self.max_daily_loss_pct = max_daily_loss_pct
        
        # State
        self.today_pnl = 0.0
        self.consecutive_losses = 0
        self.current_positions = 0
        self.today_date = date.today()
    
    @property
    def max_risk_per_trade(self) -> float:
        """Maximum dollar risk per trade."""
        return self.account_size * (self.max_risk_pct / 100)
    
    @property
    def max_daily_loss(self) -> float:
        """Maximum daily loss in dollars."""
        return self.account_size * (self.max_daily_loss_pct / 100)
    
    def reset_daily(self):
        """Reset daily counters (call at start of each day)."""
        if date.today() != self.today_date:
            self.today_pnl = 0.0
            self.today_date = date.today()
            logger.info("Daily risk counters reset")
    
    def update_pnl(self, pnl: float):
        """Update daily P&L."""
        self.reset_daily()
        self.today_pnl += pnl
        
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
    
    def check_can_trade(
        self,
        trade_cost: float,
        current_positions: int,
        vix: Optional[float] = None
    ) -> RiskCheck:
        """
        Check if we can open a new trade.
        
        Args:
            trade_cost: Cost of the proposed trade
            current_positions: Number of currently open positions
            vix: Current VIX level (optional)
        
        Returns:
            RiskCheck with pass/fail and reason
        """
        self.reset_daily()
        
        # Check daily loss limit
        if self.today_pnl <= -self.max_daily_loss:
            return RiskCheck(
                False,
                f"Daily loss limit reached: ${self.today_pnl:.2f}"
            )
        
        # Check max positions
        if current_positions >= self.max_positions:
            return RiskCheck(
                False,
                f"Max positions reached: {current_positions}/{self.max_positions}"
            )
        
        # Check trade cost is within acceptable range
        if trade_cost < MIN_TRADE_COST:
            return RiskCheck(
                False,
                f"Trade cost ${trade_cost:.2f} below minimum ${MIN_TRADE_COST}"
            )
        
        if trade_cost > MAX_TRADE_COST:
            return RiskCheck(
                False,
                f"Trade cost ${trade_cost:.2f} above maximum ${MAX_TRADE_COST}"
            )
        
        # Check trade cost doesn't exceed max risk
        if trade_cost > self.max_risk_per_trade:
            return RiskCheck(
                False,
                f"Trade cost ${trade_cost:.2f} exceeds max risk ${self.max_risk_per_trade:.2f}"
            )
        
        # Check VIX filter
        if vix is not None:
            if vix < MIN_VIX:
                return RiskCheck(False, f"VIX {vix:.1f} too low (min {MIN_VIX})")
            if vix > MAX_VIX:
                return RiskCheck(False, f"VIX {vix:.1f} too high (max {MAX_VIX})")
        
        # Check consecutive losses
        if self.consecutive_losses >= 3:
            return RiskCheck(
                False,
                f"Consecutive losses: {self.consecutive_losses}. Take a break."
            )
        
        return RiskCheck(True, "All risk checks passed")
    
    def calculate_position_size(
        self,
        trade_cost_per_contract: float
    ) -> int:
        """
        Calculate optimal number of contracts.
        
        Args:
            trade_cost_per_contract: Cost of one calendar spread
        
        Returns:
            Number of contracts to trade
        """
        # Never risk more than max_risk_per_trade
        max_contracts = int(self.max_risk_per_trade / trade_cost_per_contract)
        
        # Start conservative with 1 contract
        # Scale up as account grows and strategy proves profitable
        return max(1, min(max_contracts, 1))
    
    def get_available_capital(self) -> float:
        """Get capital available for new trades."""
        # Account for open positions
        used = self.current_positions * MAX_TRADE_COST
        available = self.account_size - used
        
        # Subtract today's losses
        if self.today_pnl < 0:
            available += self.today_pnl
        
        return max(0, available)
    
    def get_status(self) -> dict:
        """Get current risk status."""
        return {
            "account_size": self.account_size,
            "available_capital": self.get_available_capital(),
            "max_risk_per_trade": self.max_risk_per_trade,
            "max_daily_loss": self.max_daily_loss,
            "today_pnl": self.today_pnl,
            "consecutive_losses": self.consecutive_losses,
            "current_positions": self.current_positions,
            "can_trade": self.consecutive_losses < 3 and self.today_pnl > -self.max_daily_loss
        }


class VolatilityFilter:
    """
    Filter trades based on market volatility.
    """
    
    def __init__(self, min_vix: float = MIN_VIX, max_vix: float = MAX_VIX):
        self.min_vix = min_vix
        self.max_vix = max_vix
    
    def check(self, vix: float) -> RiskCheck:
        """Check if VIX is in acceptable range."""
        if vix < self.min_vix:
            return RiskCheck(
                False,
                f"VIX {vix:.1f} too low. Not enough premium to capture."
            )
        
        if vix > self.max_vix:
            return RiskCheck(
                False,
                f"VIX {vix:.1f} too high. Market too volatile."
            )
        
        return RiskCheck(True, f"VIX {vix:.1f} in range [{self.min_vix}, {self.max_vix}]")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Risk Manager Demo")
    print("=" * 60)
    
    rm = RiskManager()
    
    print(f"Account Size: ${rm.account_size:,.0f}")
    print(f"Max Risk/Trade: ${rm.max_risk_per_trade:,.0f}")
    print(f"Max Daily Loss: ${rm.max_daily_loss:,.0f}")
    print()
    
    # Test trade checks
    test_cases = [
        (200, 0, 18),   # Normal trade
        (500, 0, 18),   # Too expensive
        (200, 3, 18),   # Max positions reached
        (200, 0, 10),   # VIX too low
        (200, 0, 30),   # VIX too high
    ]
    
    for cost, positions, vix in test_cases:
        result = rm.check_can_trade(cost, positions, vix)
        status = "✅" if result.passed else "❌"
        print(f"{status} Cost=${cost}, Pos={positions}, VIX={vix}: {result.reason}")
    
    print()
    
    # Simulate losses
    print("Simulating losses:")
    for i in range(4):
        rm.update_pnl(-50)
        result = rm.check_can_trade(200, 0, 18)
        print(f"  Loss #{i+1}: consec={rm.consecutive_losses}, can_trade={result.passed}")
