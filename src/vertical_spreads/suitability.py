"""
Vertical Spread Suitability Validator
=====================================

Pre-trade validation to ensure customer account is suitable for vertical spreads.
Checks account size, options approval level, and position risk limits.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SuitabilityCheck:
    """Result of a single suitability check."""
    name: str
    passed: bool
    reason: str
    customer_value: Optional[str] = None
    required_value: Optional[str] = None


@dataclass
class SuitabilityResult:
    """Complete suitability validation result."""
    suitable: bool
    checks: List[SuitabilityCheck]
    blocking_issues: List[str]
    warnings: List[str]
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "suitable": self.suitable,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "reason": c.reason,
                    "customerValue": c.customer_value,
                    "requiredValue": c.required_value
                }
                for c in self.checks
            ],
            "blockingIssues": self.blocking_issues,
            "warnings": self.warnings
        }


class VerticalSpreadSuitabilityValidator:
    """
    Validates customer suitability for vertical spread trading.
    
    Checks:
    1. Account balance >= minimum (default $2,000)
    2. Options approval level >= required (default Level 2)
    3. Trade size <= maximum risk per trade (default 2% of account)
    4. Account age and experience (optional)
    """
    
    def __init__(
        self,
        min_account_balance: float = 2000,
        min_options_level: int = 2,
        max_risk_per_trade_pct: float = 0.02,
        min_account_age_days: int = 0,  # 0 = no requirement
        min_prior_trades: int = 0  # 0 = no requirement
    ):
        """
        Initialize validator.
        
        Args:
            min_account_balance: Minimum account balance required
            min_options_level: Minimum options approval level (1-4)
            max_risk_per_trade_pct: Maximum risk as fraction of account
            min_account_age_days: Minimum account age in days
            min_prior_trades: Minimum number of prior option trades
        """
        self.min_account_balance = min_account_balance
        self.min_options_level = min_options_level
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.min_account_age_days = min_account_age_days
        self.min_prior_trades = min_prior_trades
    
    def validate(
        self,
        customer_profile: Dict,
        proposed_trade: Optional[Dict] = None
    ) -> SuitabilityResult:
        """
        Validate customer suitability for vertical spreads.
        
        Args:
            customer_profile: Dict with:
                - account_balance: Current account balance
                - options_level: Options approval level (1-4)
                - account_open_date: Date account was opened (optional)
                - options_trades_count: Number of prior option trades (optional)
                - risk_tolerance: "conservative", "medium", or "aggressive"
            proposed_trade: Optional dict with:
                - max_loss_per_contract: Max loss per contract
                - contracts: Number of contracts
        
        Returns:
            SuitabilityResult with all checks and overall suitability
        """
        checks = []
        blocking_issues = []
        warnings = []
        
        # Check 1: Account balance
        balance_check = self._validate_account_balance(customer_profile)
        checks.append(balance_check)
        if not balance_check.passed:
            blocking_issues.append(balance_check.reason)
        
        # Check 2: Options level
        level_check = self._validate_options_level(customer_profile)
        checks.append(level_check)
        if not level_check.passed:
            blocking_issues.append(level_check.reason)
        
        # Check 3: Account age (if configured)
        if self.min_account_age_days > 0:
            age_check = self._validate_account_age(customer_profile)
            checks.append(age_check)
            if not age_check.passed:
                blocking_issues.append(age_check.reason)
        
        # Check 4: Prior trades (if configured)
        if self.min_prior_trades > 0:
            trades_check = self._validate_prior_trades(customer_profile)
            checks.append(trades_check)
            if not trades_check.passed:
                warnings.append(trades_check.reason)  # Warning, not blocking
        
        # Check 5: Trade size (if trade provided)
        if proposed_trade:
            size_check = self._validate_trade_size(customer_profile, proposed_trade)
            checks.append(size_check)
            if not size_check.passed:
                blocking_issues.append(size_check.reason)
        
        # Determine overall suitability
        suitable = len(blocking_issues) == 0
        
        return SuitabilityResult(
            suitable=suitable,
            checks=checks,
            blocking_issues=blocking_issues,
            warnings=warnings
        )
    
    def _validate_account_balance(self, profile: Dict) -> SuitabilityCheck:
        """Check minimum account balance."""
        balance = profile.get("account_balance", 0)
        passed = balance >= self.min_account_balance
        
        return SuitabilityCheck(
            name="Account Balance",
            passed=passed,
            reason=f"Minimum ${self.min_account_balance:,.0f} required" if not passed else "Account balance adequate",
            customer_value=f"${balance:,.2f}",
            required_value=f"${self.min_account_balance:,.0f}"
        )
    
    def _validate_options_level(self, profile: Dict) -> SuitabilityCheck:
        """Check options approval level."""
        level = profile.get("options_level", 0)
        passed = level >= self.min_options_level
        
        level_descriptions = {
            0: "No options",
            1: "Covered calls/cash-secured puts",
            2: "Spreads (required for verticals)",
            3: "Advanced spreads",
            4: "Naked options"
        }
        
        customer_desc = level_descriptions.get(level, f"Level {level}")
        required_desc = level_descriptions.get(self.min_options_level, f"Level {self.min_options_level}")
        
        return SuitabilityCheck(
            name="Options Approval Level",
            passed=passed,
            reason=f"Level {self.min_options_level}+ required for spreads" if not passed else "Options level approved",
            customer_value=f"Level {level} ({customer_desc})",
            required_value=f"Level {self.min_options_level} ({required_desc})"
        )
    
    def _validate_account_age(self, profile: Dict) -> SuitabilityCheck:
        """Check account age."""
        open_date = profile.get("account_open_date")
        
        if not open_date:
            return SuitabilityCheck(
                name="Account Age",
                passed=True,  # Skip if no data
                reason="Account age unknown",
                customer_value="Unknown",
                required_value=f"{self.min_account_age_days} days"
            )
        
        if isinstance(open_date, str):
            open_date = datetime.fromisoformat(open_date).date()
        elif isinstance(open_date, datetime):
            open_date = open_date.date()
        
        from datetime import date
        age_days = (date.today() - open_date).days
        passed = age_days >= self.min_account_age_days
        
        return SuitabilityCheck(
            name="Account Age",
            passed=passed,
            reason=f"Account must be at least {self.min_account_age_days} days old" if not passed else "Account age adequate",
            customer_value=f"{age_days} days",
            required_value=f"{self.min_account_age_days} days"
        )
    
    def _validate_prior_trades(self, profile: Dict) -> SuitabilityCheck:
        """Check prior trading experience."""
        trades = profile.get("options_trades_count", 0)
        passed = trades >= self.min_prior_trades
        
        return SuitabilityCheck(
            name="Trading Experience",
            passed=passed,
            reason=f"Recommend {self.min_prior_trades}+ prior trades" if not passed else "Adequate trading experience",
            customer_value=f"{trades} trades",
            required_value=f"{self.min_prior_trades} trades"
        )
    
    def _validate_trade_size(
        self, 
        profile: Dict, 
        trade: Dict
    ) -> SuitabilityCheck:
        """Check if proposed trade size is appropriate."""
        account_balance = profile.get("account_balance", 0)
        max_loss = trade.get("max_loss_per_contract", 0)
        contracts = trade.get("contracts", 1)
        total_risk = max_loss * contracts
        
        max_allowed = account_balance * self.max_risk_per_trade_pct
        passed = total_risk <= max_allowed
        
        return SuitabilityCheck(
            name="Trade Size",
            passed=passed,
            reason=f"Risk ${total_risk:,.0f} exceeds {self.max_risk_per_trade_pct*100:.0f}% limit (${max_allowed:,.0f})" if not passed else "Trade size within limits",
            customer_value=f"${total_risk:,.0f} risk",
            required_value=f"≤ ${max_allowed:,.0f} ({self.max_risk_per_trade_pct*100:.0f}% of account)"
        )
    
    def is_pattern_day_trader(self, profile: Dict) -> bool:
        """
        Check if account is subject to PDT rules.
        
        PDT rule: If account < $25K and made 4+ day trades in 5 business days.
        """
        balance = profile.get("account_balance", 0)
        day_trades_last_5_days = profile.get("day_trades_last_5_days", 0)
        
        if balance >= 25000:
            return False  # Not subject to PDT
        
        return day_trades_last_5_days >= 4
    
    def get_suitability_summary(self, result: SuitabilityResult) -> str:
        """Generate human-readable suitability summary."""
        lines = []
        
        if result.suitable:
            lines.append("✅ Account approved for vertical spread trading")
        else:
            lines.append("❌ Account NOT approved for vertical spread trading")
            lines.append("")
            lines.append("Blocking issues:")
            for issue in result.blocking_issues:
                lines.append(f"  • {issue}")
        
        if result.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in result.warnings:
                lines.append(f"  ⚠️ {warning}")
        
        lines.append("")
        lines.append("Checks performed:")
        for check in result.checks:
            status = "✓" if check.passed else "✗"
            lines.append(f"  {status} {check.name}: {check.customer_value}")
        
        return "\n".join(lines)
