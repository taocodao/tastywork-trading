"""
Vertical Spread Stop Manager
============================

Manages exit rules and position monitoring for vertical spreads.
Tracks profit targets, stop losses, and DTE-based exits.
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
    urgency: str  # "low", "medium", "high"
    recommended_action: str  # "hold", "monitor", "close"


@dataclass
class ExitAnalysis:
    """Complete exit analysis for a position."""
    symbol: str
    position_id: str
    should_exit: bool
    exit_reason: str
    triggered_rules: List[ExitRule]
    all_rules: List[ExitRule]
    unrealized_pnl: float
    pnl_percent: float
    days_held: int
    dte_remaining: int


class VerticalSpreadStopManager:
    """
    Manages stop losses and profit targets for vertical spreads.
    
    Exit rules:
    1. Profit target reached (default 75% of max profit)
    2. Max loss threshold hit (default 50% of max loss)
    3. DTE < threshold (default 2 days - close before expiration)
    4. Underlying moved beyond implied move (directional confirmation failed)
    """
    
    def __init__(
        self,
        profit_target_pct: float = 0.75,  # Exit at 75% of max profit
        max_loss_pct: float = 0.50,  # Exit at 50% of max loss
        min_dte: int = 2,  # Close when DTE < 2
        implied_move_multiplier: float = 1.0  # Exit if underlying moves 1x implied move against
    ):
        """
        Initialize stop manager.
        
        Args:
            profit_target_pct: Target profit as fraction of max profit
            max_loss_pct: Stop loss as fraction of max loss
            min_dte: Minimum DTE before forced close
            implied_move_multiplier: Multiplier for underlying movement stop
        """
        self.profit_target_pct = profit_target_pct
        self.max_loss_pct = max_loss_pct
        self.min_dte = min_dte
        self.implied_move_multiplier = implied_move_multiplier
    
    def check_exit_rules(
        self,
        position_data: Dict,
        market_data: Dict
    ) -> ExitAnalysis:
        """
        Check all exit rules for a position.
        
        Args:
            position_data: Dict with:
                - position_id: Unique identifier
                - symbol: Stock symbol
                - direction: "BULL" or "BEAR"
                - entry_price: Entry debit/credit per share
                - entry_date: Date position opened
                - buy_strike: Long strike
                - sell_strike: Short strike
                - expiration: Expiration date
                - max_loss_per_contract: Max loss per contract
                - max_profit_per_contract: Max profit per contract
                - contracts: Number of contracts
                - implied_move: Expected move at entry
            market_data: Dict with:
                - stock_price: Current stock price
                - spread_bid: Current spread bid
                - spread_ask: Current spread ask
                - dte: Days to expiration
        
        Returns:
            ExitAnalysis with all rule evaluations
        """
        rules = []
        
        # Calculate current P&L
        entry_price = position_data.get("entry_price", 0)
        current_spread_mid = (
            market_data.get("spread_bid", entry_price) + 
            market_data.get("spread_ask", entry_price)
        ) / 2
        
        # For debit spreads: profit = current - entry
        unrealized_pnl = (current_spread_mid - entry_price) * 100 * position_data.get("contracts", 1)
        
        max_profit = position_data.get("max_profit_per_contract", 0) * position_data.get("contracts", 1)
        max_loss = position_data.get("max_loss_per_contract", 0) * position_data.get("contracts", 1)
        
        if max_profit + max_loss > 0:
            pnl_percent = (unrealized_pnl / (max_profit + max_loss)) * 100
        else:
            pnl_percent = 0
        
        # Rule 1: Profit target
        profit_rule = self._check_profit_target(unrealized_pnl, max_profit)
        rules.append(profit_rule)
        
        # Rule 2: Stop loss
        loss_rule = self._check_stop_loss(unrealized_pnl, max_loss)
        rules.append(loss_rule)
        
        # Rule 3: DTE expiration
        dte = market_data.get("dte", 30)
        dte_rule = self._check_dte(dte)
        rules.append(dte_rule)
        
        # Rule 4: Underlying moved against position
        underlying_rule = self._check_underlying_move(
            current_price=market_data.get("stock_price", 0),
            entry_price=position_data.get("entry_stock_price", market_data.get("stock_price", 0)),
            implied_move=position_data.get("implied_move", 0),
            direction=position_data.get("direction", "BULL")
        )
        rules.append(underlying_rule)
        
        # Determine if should exit
        triggered = [r for r in rules if r.triggered]
        should_exit = len(triggered) > 0
        exit_reason = triggered[0].reason if triggered else "No exit rules triggered"
        
        # Calculate days held
        entry_date = position_data.get("entry_date")
        if isinstance(entry_date, str):
            entry_date = datetime.fromisoformat(entry_date).date()
        elif isinstance(entry_date, datetime):
            entry_date = entry_date.date()
        else:
            entry_date = date.today()
        
        days_held = (date.today() - entry_date).days
        
        return ExitAnalysis(
            symbol=position_data.get("symbol", ""),
            position_id=position_data.get("position_id", ""),
            should_exit=should_exit,
            exit_reason=exit_reason,
            triggered_rules=triggered,
            all_rules=rules,
            unrealized_pnl=round(unrealized_pnl, 2),
            pnl_percent=round(pnl_percent, 1),
            days_held=days_held,
            dte_remaining=dte
        )
    
    def _check_profit_target(
        self, 
        unrealized_pnl: float, 
        max_profit: float
    ) -> ExitRule:
        """Check if profit target is reached."""
        if max_profit <= 0:
            return ExitRule(
                name="Profit Target",
                triggered=False,
                reason="Max profit not defined",
                urgency="low",
                recommended_action="hold"
            )
        
        target = max_profit * self.profit_target_pct
        triggered = unrealized_pnl >= target
        
        return ExitRule(
            name="Profit Target",
            triggered=triggered,
            reason=f"P&L ${unrealized_pnl:.2f} {'≥' if triggered else '<'} target ${target:.2f} ({self.profit_target_pct*100:.0f}% of max)",
            urgency="high" if triggered else "low",
            recommended_action="close" if triggered else "hold"
        )
    
    def _check_stop_loss(
        self, 
        unrealized_pnl: float, 
        max_loss: float
    ) -> ExitRule:
        """Check if stop loss is hit."""
        if max_loss <= 0:
            return ExitRule(
                name="Stop Loss",
                triggered=False,
                reason="Max loss not defined",
                urgency="low",
                recommended_action="hold"
            )
        
        stop_threshold = -max_loss * self.max_loss_pct
        triggered = unrealized_pnl <= stop_threshold
        
        return ExitRule(
            name="Stop Loss",
            triggered=triggered,
            reason=f"P&L ${unrealized_pnl:.2f} {'≤' if triggered else '>'} stop ${stop_threshold:.2f} ({self.max_loss_pct*100:.0f}% of max loss)",
            urgency="high" if triggered else "low",
            recommended_action="close" if triggered else "hold"
        )
    
    def _check_dte(self, dte: int) -> ExitRule:
        """Check if approaching expiration."""
        triggered = dte < self.min_dte
        
        if triggered:
            urgency = "high"
            action = "close"
            reason = f"DTE {dte} < minimum {self.min_dte} (close before expiration)"
        elif dte <= self.min_dte + 2:
            urgency = "medium"
            action = "monitor"
            reason = f"DTE {dte} approaching minimum {self.min_dte}"
        else:
            urgency = "low"
            action = "hold"
            reason = f"DTE {dte} is safe (minimum {self.min_dte})"
        
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
        implied_move: float,
        direction: str
    ) -> ExitRule:
        """Check if underlying moved against position beyond threshold."""
        if entry_price <= 0 or implied_move <= 0:
            return ExitRule(
                name="Underlying Movement",
                triggered=False,
                reason="Entry price or implied move not available",
                urgency="low",
                recommended_action="hold"
            )
        
        price_change = current_price - entry_price
        threshold = implied_move * self.implied_move_multiplier
        
        # Bull position: concerned about downward moves
        if direction == "BULL":
            triggered = price_change < -threshold
            move_desc = f"down ${abs(price_change):.2f}"
        else:  # BEAR
            triggered = price_change > threshold
            move_desc = f"up ${price_change:.2f}"
        
        if triggered:
            return ExitRule(
                name="Underlying Movement",
                triggered=True,
                reason=f"Stock moved {move_desc}, beyond {threshold:.2f} threshold (against {direction} position)",
                urgency="high",
                recommended_action="close"
            )
        else:
            return ExitRule(
                name="Underlying Movement",
                triggered=False,
                reason=f"Stock move ${price_change:.2f} within bounds (threshold: ±${threshold:.2f})",
                urgency="low",
                recommended_action="hold"
            )
    
    def get_exit_summary(self, analysis: ExitAnalysis) -> str:
        """Generate human-readable exit summary."""
        lines = [f"Position: {analysis.symbol} ({analysis.position_id})"]
        lines.append(f"P&L: ${analysis.unrealized_pnl} ({analysis.pnl_percent}%)")
        lines.append(f"Days held: {analysis.days_held}, DTE: {analysis.dte_remaining}")
        
        if analysis.should_exit:
            lines.append(f"⚠️ EXIT RECOMMENDED: {analysis.exit_reason}")
        else:
            lines.append("✅ Position healthy - no exit rules triggered")
        
        return "\n".join(lines)
