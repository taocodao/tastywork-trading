"""
Diagonal Spread Stop Manager
============================

Manages exit rules and position monitoring for diagonal spreads.
Includes rolling logic for short leg management.

Key differences from vertical/calendar:
- Short leg can be rolled multiple times
- Long leg stays constant until final exit
- Need to track both legs independently
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ExitRule:
    """An exit rule that may or may not be triggered."""
    name: str
    triggered: bool
    reason: str
    urgency: str  # "low", "medium", "high", "critical"
    recommended_action: str


@dataclass
class RollOpportunity:
    """Opportunity to roll the short leg."""
    should_roll: bool
    reason: str
    suggested_new_strike: float
    suggested_new_expiration: date
    estimated_credit: float  # Credit from roll


@dataclass
class DiagonalExitAnalysis:
    """Complete exit/roll analysis for a diagonal position."""
    symbol: str
    position_id: str
    
    # Overall recommendation
    should_exit_completely: bool
    should_roll_short: bool
    exit_reason: str
    
    # Individual leg status
    long_leg_status: str  # "HEALTHY", "AT_RISK", "EXIT"
    short_leg_status: str  # "HEALTHY", "ROLL_SOON", "ROLL_NOW", "EXPIRED"
    
    # P&L
    unrealized_pnl: float
    pnl_percent: float
    
    # Timing
    days_held: int
    short_dte_remaining: int
    long_dte_remaining: int
    
    # Roll info
    roll_opportunity: Optional[RollOpportunity]
    
    # All rules checked
    triggered_rules: List[ExitRule]
    all_rules: List[ExitRule]


class DiagonalStopManager:
    """
    Manages stops and rolls for diagonal spreads.
    
    Exit rules:
    1. Profit target reached (default 50% of max profit)
    2. Max loss threshold hit (default 75% of net debit)
    3. Long leg DTE < 30 days (need to exit or roll to new diagonal)
    4. Short leg approaching expiration (roll opportunity)
    5. Stock moved significantly against position
    
    Rolling rules:
    1. Roll short leg when DTE < 5
    2. Roll if captured > 50% of short premium
    3. Roll to collect more credit
    """
    
    def __init__(
        self,
        profit_target_pct: float = 0.50,  # Exit at 50% of max profit
        max_loss_pct: float = 0.75,  # Exit at 75% loss of net debit
        min_long_dte: int = 30,  # Minimum DTE for long leg before exit
        roll_short_dte: int = 5,  # Roll short when DTE < 5
        roll_early_capture_pct: float = 0.50  # Roll if captured 50% of short premium
    ):
        """
        Initialize stop manager.
        
        Args:
            profit_target_pct: Target profit as fraction of max profit
            max_loss_pct: Stop loss as fraction of net debit
            min_long_dte: Minimum DTE for long leg before forced exit
            roll_short_dte: Days before short expiration to roll
            roll_early_capture_pct: Capture % to trigger early roll
        """
        self.profit_target_pct = profit_target_pct
        self.max_loss_pct = max_loss_pct
        self.min_long_dte = min_long_dte
        self.roll_short_dte = roll_short_dte
        self.roll_early_capture_pct = roll_early_capture_pct
    
    def check_exit_rules(
        self,
        position_data: Dict,
        market_data: Dict
    ) -> DiagonalExitAnalysis:
        """
        Check all exit and roll rules for a diagonal position.
        
        Args:
            position_data: Dict with:
                - position_id: Unique identifier
                - symbol: Stock symbol
                - direction: "BULL" or "BEAR"
                - long_strike, long_expiration, long_entry_price
                - short_strike, short_expiration, short_entry_price
                - net_debit: Original debit paid
                - max_profit: Maximum profit potential
                - entry_date: When position was opened
                - contracts: Number of contracts
                
            market_data: Dict with:
                - stock_price: Current stock price
                - long_current_price: Current long leg price
                - short_current_price: Current short leg price
                - iv: Current implied volatility
        
        Returns:
            DiagonalExitAnalysis with all rule evaluations
        """
        all_rules = []
        triggered_rules = []
        
        # Extract position data
        symbol = position_data.get("symbol", "")
        position_id = position_data.get("position_id", "")
        direction = position_data.get("direction", "BULL")
        net_debit = position_data.get("net_debit", 0)
        max_profit = position_data.get("max_profit", 0)
        contracts = position_data.get("contracts", 1)
        
        # Calculate P&L
        long_entry = position_data.get("long_entry_price", 0)
        short_entry = position_data.get("short_entry_price", 0)
        long_current = market_data.get("long_current_price", long_entry)
        short_current = market_data.get("short_current_price", short_entry)
        
        # P&L = (current value of spread) - (entry value of spread)
        current_spread_value = long_current - short_current
        unrealized_pnl = (current_spread_value - net_debit) * 100 * contracts
        pnl_percent = (unrealized_pnl / (net_debit * 100 * contracts)) * 100 if net_debit > 0 else 0
        
        # Calculate DTEs
        today = date.today()
        long_exp = position_data.get("long_expiration")
        short_exp = position_data.get("short_expiration")
        
        if isinstance(long_exp, str):
            long_exp = datetime.fromisoformat(long_exp).date()
        if isinstance(short_exp, str):
            short_exp = datetime.fromisoformat(short_exp).date()
        
        long_dte = (long_exp - today).days if long_exp else 0
        short_dte = (short_exp - today).days if short_exp else 0
        
        # Days held
        entry_date = position_data.get("entry_date")
        if isinstance(entry_date, str):
            entry_date = datetime.fromisoformat(entry_date).date()
        days_held = (today - entry_date).days if entry_date else 0
        
        # Check rules
        # 1. Profit target
        profit_rule = self._check_profit_target(unrealized_pnl, max_profit * contracts)
        all_rules.append(profit_rule)
        if profit_rule.triggered:
            triggered_rules.append(profit_rule)
        
        # 2. Stop loss
        loss_rule = self._check_stop_loss(unrealized_pnl, net_debit * 100 * contracts)
        all_rules.append(loss_rule)
        if loss_rule.triggered:
            triggered_rules.append(loss_rule)
        
        # 3. Long leg DTE
        long_dte_rule = self._check_long_dte(long_dte)
        all_rules.append(long_dte_rule)
        if long_dte_rule.triggered:
            triggered_rules.append(long_dte_rule)
        
        # 4. Short leg roll
        short_roll_rule = self._check_short_roll(short_dte)
        all_rules.append(short_roll_rule)
        if short_roll_rule.triggered:
            triggered_rules.append(short_roll_rule)
        
        # 5. Short leg early capture
        short_capture = (short_entry - short_current) / short_entry if short_entry > 0 else 0
        early_roll_rule = self._check_early_roll(short_capture)
        all_rules.append(early_roll_rule)
        if early_roll_rule.triggered:
            triggered_rules.append(early_roll_rule)
        
        # 6. Stock move check
        stock_price = market_data.get("stock_price", 0)
        entry_stock_price = position_data.get("entry_stock_price", stock_price)
        move_rule = self._check_stock_move(
            stock_price, entry_stock_price, direction
        )
        all_rules.append(move_rule)
        if move_rule.triggered:
            triggered_rules.append(move_rule)
        
        # Determine overall recommendations
        should_exit = any(r.triggered and r.urgency == "critical" for r in triggered_rules)
        should_roll = short_roll_rule.triggered or early_roll_rule.triggered
        
        # Determine leg statuses
        long_status = "HEALTHY"
        if long_dte < self.min_long_dte:
            long_status = "EXIT" if long_dte < 14 else "AT_RISK"
        
        short_status = "HEALTHY"
        if short_dte <= 0:
            short_status = "EXPIRED"
        elif short_dte <= 2:
            short_status = "ROLL_NOW"
        elif short_dte <= self.roll_short_dte:
            short_status = "ROLL_SOON"
        
        # Generate roll opportunity if applicable
        roll_opportunity = None
        if should_roll and not should_exit:
            roll_opportunity = self._generate_roll_opportunity(
                position_data, market_data, short_dte
            )
        
        # Build exit reason
        exit_reason = ""
        if triggered_rules:
            critical = [r for r in triggered_rules if r.urgency == "critical"]
            if critical:
                exit_reason = critical[0].reason
            else:
                exit_reason = triggered_rules[0].reason
        
        return DiagonalExitAnalysis(
            symbol=symbol,
            position_id=position_id,
            should_exit_completely=should_exit,
            should_roll_short=should_roll and not should_exit,
            exit_reason=exit_reason,
            long_leg_status=long_status,
            short_leg_status=short_status,
            unrealized_pnl=round(unrealized_pnl, 2),
            pnl_percent=round(pnl_percent, 1),
            days_held=days_held,
            short_dte_remaining=short_dte,
            long_dte_remaining=long_dte,
            roll_opportunity=roll_opportunity,
            triggered_rules=triggered_rules,
            all_rules=all_rules
        )
    
    def _check_profit_target(
        self,
        unrealized_pnl: float,
        max_profit: float
    ) -> ExitRule:
        """Check if profit target is reached."""
        target = max_profit * self.profit_target_pct
        triggered = unrealized_pnl >= target
        
        return ExitRule(
            name="PROFIT_TARGET",
            triggered=triggered,
            reason=f"Profit target reached: ${unrealized_pnl:.2f} ≥ ${target:.2f} (50%)",
            urgency="high" if triggered else "low",
            recommended_action="CLOSE_POSITION" if triggered else "HOLD"
        )
    
    def _check_stop_loss(
        self,
        unrealized_pnl: float,
        max_loss: float
    ) -> ExitRule:
        """Check if stop loss is hit."""
        loss_threshold = -max_loss * self.max_loss_pct
        triggered = unrealized_pnl <= loss_threshold
        
        return ExitRule(
            name="STOP_LOSS",
            triggered=triggered,
            reason=f"Stop loss hit: ${unrealized_pnl:.2f} ≤ ${loss_threshold:.2f} (75%)",
            urgency="critical" if triggered else "low",
            recommended_action="CLOSE_POSITION" if triggered else "HOLD"
        )
    
    def _check_long_dte(self, long_dte: int) -> ExitRule:
        """Check if long leg is approaching expiration."""
        triggered = long_dte < self.min_long_dte
        
        urgency = "low"
        if long_dte < 14:
            urgency = "critical"
        elif long_dte < self.min_long_dte:
            urgency = "high"
        
        return ExitRule(
            name="LONG_DTE_LOW",
            triggered=triggered,
            reason=f"Long leg DTE: {long_dte} days (min: {self.min_long_dte})",
            urgency=urgency,
            recommended_action="CLOSE_POSITION" if triggered else "HOLD"
        )
    
    def _check_short_roll(self, short_dte: int) -> ExitRule:
        """Check if short leg should be rolled."""
        triggered = short_dte <= self.roll_short_dte
        
        urgency = "low"
        if short_dte <= 0:
            urgency = "critical"
        elif short_dte <= 2:
            urgency = "high"
        elif short_dte <= self.roll_short_dte:
            urgency = "medium"
        
        return ExitRule(
            name="ROLL_SHORT",
            triggered=triggered,
            reason=f"Short leg DTE: {short_dte} days (roll at: {self.roll_short_dte})",
            urgency=urgency,
            recommended_action="ROLL_SHORT_LEG" if triggered else "HOLD"
        )
    
    def _check_early_roll(self, capture_pct: float) -> ExitRule:
        """Check if short leg has captured enough premium for early roll."""
        triggered = capture_pct >= self.roll_early_capture_pct
        
        return ExitRule(
            name="EARLY_ROLL",
            triggered=triggered,
            reason=f"Short leg captured {capture_pct*100:.0f}% of premium (target: {self.roll_early_capture_pct*100:.0f}%)",
            urgency="medium" if triggered else "low",
            recommended_action="ROLL_SHORT_LEG" if triggered else "HOLD"
        )
    
    def _check_stock_move(
        self,
        current_price: float,
        entry_price: float,
        direction: str
    ) -> ExitRule:
        """Check if stock moved significantly against position."""
        move_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Bad move for bull = stock dropped
        # Bad move for bear = stock rose
        bad_move = (direction == "BULL" and move_pct < -10) or \
                   (direction == "BEAR" and move_pct > 10)
        
        return ExitRule(
            name="ADVERSE_MOVE",
            triggered=bad_move,
            reason=f"Stock moved {move_pct:+.1f}% since entry",
            urgency="high" if bad_move else "low",
            recommended_action="CLOSE_POSITION" if bad_move else "HOLD"
        )
    
    def _generate_roll_opportunity(
        self,
        position_data: Dict,
        market_data: Dict,
        current_short_dte: int
    ) -> RollOpportunity:
        """Generate a roll opportunity for the short leg."""
        stock_price = market_data.get("stock_price", 0)
        direction = position_data.get("direction", "BULL")
        iv = market_data.get("iv", 0.25)
        
        # Suggest new strike based on current stock price + direction
        if direction == "BULL":
            # For bull diagonal, sell OTM call
            suggested_strike = round(stock_price * 1.03 / 5) * 5  # 3% OTM
        else:
            # For bear diagonal, sell OTM put
            suggested_strike = round(stock_price * 0.97 / 5) * 5  # 3% OTM
        
        # Suggest new expiration (2-3 weeks out)
        from datetime import timedelta
        suggested_exp = date.today() + timedelta(days=14)
        
        # Estimate credit (rough estimate)
        time_value = stock_price * iv * (14 / 365) ** 0.5 * 0.4
        estimated_credit = round(time_value, 2)
        
        return RollOpportunity(
            should_roll=True,
            reason=f"Short leg at {current_short_dte} DTE - roll to collect more premium",
            suggested_new_strike=suggested_strike,
            suggested_new_expiration=suggested_exp,
            estimated_credit=estimated_credit
        )
    
    def get_exit_summary(self, analysis: DiagonalExitAnalysis) -> str:
        """Generate human-readable exit summary."""
        lines = [
            f"📊 {analysis.symbol} Diagonal Analysis",
            f"P&L: ${analysis.unrealized_pnl:+.2f} ({analysis.pnl_percent:+.1f}%)",
            f"Days held: {analysis.days_held}",
            f"Long leg: {analysis.long_leg_status} ({analysis.long_dte_remaining} DTE)",
            f"Short leg: {analysis.short_leg_status} ({analysis.short_dte_remaining} DTE)",
            ""
        ]
        
        if analysis.should_exit_completely:
            lines.append(f"⚠️ EXIT RECOMMENDED: {analysis.exit_reason}")
        elif analysis.should_roll_short:
            lines.append(f"🔄 ROLL RECOMMENDED: {analysis.exit_reason}")
            if analysis.roll_opportunity:
                lines.append(
                    f"   Suggested: ${analysis.roll_opportunity.suggested_new_strike} "
                    f"@ {analysis.roll_opportunity.suggested_new_expiration} "
                    f"(~${analysis.roll_opportunity.estimated_credit:.2f} credit)"
                )
        else:
            lines.append("✅ HOLD: All checks passed")
        
        return "\n".join(lines)
