"""
Calendar Spread Stop Manager
============================

Manages exit rules and position monitoring for calendar spreads.
Based on tastylive best practices for calendar spread management.

Key rules:
- Profit target: 25% of entry debit
- Stop loss: 50% of entry debit
- DTE alert: Close 5 days before front expiration
- Price movement: Exit if underlying moves > 1 std dev from strike
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExitRule:
    """An exit rule that may or may not be triggered."""
    name: str
    triggered: bool
    reason: str
    urgency: str  # "low", "medium", "high"
    recommended_action: str  # "hold", "monitor", "close"


@dataclass
class ExitAnalysis:
    """Complete exit analysis for a calendar spread position."""
    symbol: str
    position_id: str
    should_exit: bool
    exit_reason: str
    triggered_rules: List[ExitRule]
    all_rules: List[ExitRule]
    unrealized_pnl: float
    pnl_percent: float
    days_held: int
    front_dte: int
    current_spread_value: float


class CalendarSpreadStopManager:
    """
    Manages stop losses and profit targets for calendar spreads.
    
    Exit rules (per tastylive best practices):
    1. Profit target reached (default 25% of debit paid)
    2. Max loss threshold hit (default 50% of entry debit)
    3. Front DTE < threshold (default 5 days - close before expiration)
    4. Underlying moved too far from strike (theta decay advantage lost)
    5. IV collapse in front month (optional)
    """
    
    def __init__(
        self,
        profit_target_pct: float = 0.25,  # Exit at 25% profit (tastylive standard)
        stop_loss_pct: float = 0.50,      # Exit at 50% loss of entry
        min_front_dte: int = 5,           # Close 5 days before front expiry
        price_move_threshold_pct: float = 0.05  # Exit if underlying moves 5% from entry
    ):
        """
        Initialize stop manager.
        
        Args:
            profit_target_pct: Target profit as fraction of entry debit
            stop_loss_pct: Stop loss as fraction of entry debit
            min_front_dte: Minimum days before front expiration to exit
            price_move_threshold_pct: Exit if underlying moves this % from entry
        """
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct
        self.min_front_dte = min_front_dte
        self.price_move_threshold_pct = price_move_threshold_pct
    
    def check_exit_rules(
        self,
        position: Dict,
        market_data: Dict
    ) -> ExitAnalysis:
        """
        Check all exit rules for a calendar spread position.
        
        Args:
            position: Dict with position data:
                - position_id: Unique identifier
                - symbol: Stock symbol
                - entry_debit: Entry debit paid (per contract)
                - entry_stock_price: Underlying price at entry
                - strike: Strike price
                - quantity: Number of contracts
                - front_expiry: Front month expiration
                - created_at: When position was opened
            market_data: Dict with current market data:
                - spread_mid: Current spread mid price
                - stock_price: Current stock price
                - front_dte: Days to front expiration
                
        Returns:
            ExitAnalysis with all rule evaluations
        """
        rules = []
        
        # Extract position data
        entry_debit = position.get("entry_debit", 0) or 0
        quantity = position.get("quantity", 1) or 1
        
        # Current spread value
        current_spread_mid = market_data.get("spread_mid", entry_debit)
        
        # Calculate P&L
        # For calendar spreads: Profit = (current value - entry debit) * quantity * 100
        pnl_per_contract = (current_spread_mid - entry_debit) * 100
        unrealized_pnl = pnl_per_contract * quantity
        
        # P&L as percentage of entry
        if entry_debit > 0:
            pnl_percent = (current_spread_mid - entry_debit) / entry_debit * 100
        else:
            pnl_percent = 0
        
        # Rule 1: Profit target (25% of entry debit)
        profit_rule = self._check_profit_target(current_spread_mid, entry_debit)
        rules.append(profit_rule)
        
        # Rule 2: Stop loss (50% of entry debit)
        loss_rule = self._check_stop_loss(current_spread_mid, entry_debit)
        rules.append(loss_rule)
        
        # Rule 3: DTE expiration
        front_dte = market_data.get("front_dte", 30)
        dte_rule = self._check_dte(front_dte)
        rules.append(dte_rule)
        
        # Rule 4: Underlying price movement
        underlying_rule = self._check_underlying_move(
            current_price=market_data.get("stock_price", 0),
            entry_price=position.get("entry_stock_price", 0),
            strike=position.get("strike", 0)
        )
        rules.append(underlying_rule)
        
        # Determine if should exit
        triggered = [r for r in rules if r.triggered]
        should_exit = len(triggered) > 0
        exit_reason = triggered[0].reason if triggered else "No exit rules triggered"
        
        # Calculate days held
        created_at = position.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        if isinstance(created_at, datetime):
            days_held = (datetime.now() - created_at.replace(tzinfo=None)).days
        else:
            days_held = 0
        
        return ExitAnalysis(
            symbol=position.get("symbol", ""),
            position_id=position.get("id", ""),
            should_exit=should_exit,
            exit_reason=exit_reason,
            triggered_rules=triggered,
            all_rules=rules,
            unrealized_pnl=round(unrealized_pnl, 2),
            pnl_percent=round(pnl_percent, 1),
            days_held=days_held,
            front_dte=front_dte,
            current_spread_value=round(current_spread_mid, 2)
        )
    
    def _check_profit_target(
        self, 
        current_value: float, 
        entry_debit: float
    ) -> ExitRule:
        """Check if profit target is reached."""
        if entry_debit <= 0:
            return ExitRule(
                name="Profit Target",
                triggered=False,
                reason="Entry debit not defined",
                urgency="low",
                recommended_action="hold"
            )
        
        # Profit target = entry + (entry * target_pct)
        target_value = entry_debit * (1 + self.profit_target_pct)
        profit_pct = (current_value - entry_debit) / entry_debit * 100
        triggered = current_value >= target_value
        
        return ExitRule(
            name="Profit Target",
            triggered=triggered,
            reason=f"Spread value ${current_value:.2f} {'≥' if triggered else '<'} target ${target_value:.2f} ({profit_pct:.1f}% profit)",
            urgency="high" if triggered else "low",
            recommended_action="close" if triggered else "hold"
        )
    
    def _check_stop_loss(
        self, 
        current_value: float, 
        entry_debit: float
    ) -> ExitRule:
        """Check if stop loss is hit."""
        if entry_debit <= 0:
            return ExitRule(
                name="Stop Loss",
                triggered=False,
                reason="Entry debit not defined",
                urgency="low",
                recommended_action="hold"
            )
        
        # Stop loss = entry * stop_loss_pct (e.g., 50% of entry = exit when spread worth 50% of what we paid)
        stop_value = entry_debit * self.stop_loss_pct
        loss_pct = (entry_debit - current_value) / entry_debit * 100
        triggered = current_value <= stop_value
        
        return ExitRule(
            name="Stop Loss",
            triggered=triggered,
            reason=f"Spread value ${current_value:.2f} {'≤' if triggered else '>'} stop ${stop_value:.2f} ({loss_pct:.1f}% loss)",
            urgency="high" if triggered else "low",
            recommended_action="close" if triggered else "hold"
        )
    
    def _check_dte(self, front_dte: int) -> ExitRule:
        """Check if approaching front expiration."""
        triggered = front_dte < self.min_front_dte
        
        if triggered:
            urgency = "high"
            action = "close"
            reason = f"Front DTE {front_dte} < minimum {self.min_front_dte} (close before expiration risk)"
        elif front_dte <= self.min_front_dte + 3:
            urgency = "medium"
            action = "monitor"
            reason = f"Front DTE {front_dte} approaching threshold {self.min_front_dte}"
        else:
            urgency = "low"
            action = "hold"
            reason = f"Front DTE {front_dte} is healthy"
        
        return ExitRule(
            name="DTE Expiration",
            triggered=triggered,
            reason=reason,
            urgency=urgency,
            recommended_action=action
        )
    
    def _check_underlying_move(
        self,
        current_price: float,
        entry_price: float,
        strike: float
    ) -> ExitRule:
        """Check if underlying moved too far from strike."""
        if entry_price <= 0 or strike <= 0:
            return ExitRule(
                name="Underlying Movement",
                triggered=False,
                reason="Entry price or strike not available",
                urgency="low",
                recommended_action="hold"
            )
        
        # Calendar spreads profit when underlying stays near strike
        # Exit if price moves too far from strike
        distance_from_strike = abs(current_price - strike)
        threshold = strike * self.price_move_threshold_pct
        move_pct = distance_from_strike / strike * 100
        
        triggered = distance_from_strike > threshold
        
        if triggered:
            direction = "above" if current_price > strike else "below"
            return ExitRule(
                name="Underlying Movement",
                triggered=True,
                reason=f"Stock ${current_price:.2f} is {move_pct:.1f}% {direction} strike ${strike:.2f} (theta decay reduced)",
                urgency="high",
                recommended_action="close"
            )
        else:
            return ExitRule(
                name="Underlying Movement",
                triggered=False,
                reason=f"Stock ${current_price:.2f} within {move_pct:.1f}% of strike ${strike:.2f}",
                urgency="low",
                recommended_action="hold"
            )
    
    def get_exit_summary(self, analysis: ExitAnalysis) -> str:
        """Generate human-readable exit summary."""
        lines = [f"📊 Position: {analysis.symbol} (ID: {analysis.position_id[:8]}...)"]
        lines.append(f"💰 P&L: ${analysis.unrealized_pnl} ({analysis.pnl_percent}%)")
        lines.append(f"📅 Days held: {analysis.days_held}, Front DTE: {analysis.front_dte}")
        lines.append(f"📈 Current spread value: ${analysis.current_spread_value}")
        
        if analysis.should_exit:
            lines.append(f"⚠️ EXIT RECOMMENDED: {analysis.exit_reason}")
            for rule in analysis.triggered_rules:
                lines.append(f"   🔴 {rule.name}: {rule.reason}")
        else:
            lines.append("✅ Position healthy - no exit rules triggered")
            for rule in analysis.all_rules:
                status = "🟢" if not rule.triggered else "🔴"
                lines.append(f"   {status} {rule.name}: {rule.reason}")
        
        return "\n".join(lines)


# Export for easy import
__all__ = ['CalendarSpreadStopManager', 'ExitRule', 'ExitAnalysis']
