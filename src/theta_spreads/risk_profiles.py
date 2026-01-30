"""
Risk Profiles for Theta Sprint Strategy.

Defines three risk levels with different position sizing, exit rules, and VIX thresholds.
Users select their risk tolerance: LOW (Conservative), MEDIUM (Moderate), HIGH (Aggressive).
"""

import os
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """User-selectable risk levels."""
    LOW = "low"        # Conservative - safest, lowest returns
    MEDIUM = "medium"  # Moderate - balanced risk/reward (default)
    HIGH = "high"      # Aggressive - highest returns, highest risk


@dataclass(frozen=True)
class RiskProfile:
    """
    Complete risk configuration for a trading strategy.
    
    Each profile defines position sizing, exit rules, and expected outcomes.
    """
    # Identity
    name: str
    level: RiskLevel
    description: str
    
    # Position Sizing
    max_capital_deployed_pct: float   # % of account to deploy (0.6 = 60%)
    max_positions: int                 # Maximum concurrent positions
    contracts_per_trade: int           # Base contracts per trade
    cash_reserve_pct: float            # % to keep as cash buffer
    max_portfolio_heat: float          # Maximum $ at risk
    
    # Defensive Exit Rules
    breach_threshold_pct: float        # Exit if stock < strike * (1 - this)
    breach_confirmation_days: int      # Days to confirm breach before exit
    dte_exit_threshold: int            # Exit if DTE <= this
    
    # VIX Thresholds
    vix_block_trading: float           # Don't enter new positions above this
    vix_reduce_size: float             # Reduce position size above this
    vix_close_all: float               # Emergency: close all positions above this
    vix_size_reduction: float          # Multiplier when VIX elevated (0.5 = 50%)
    
    # Time-Based Profit Exits
    week1_profit_pct: float            # Week 1 exit target
    week2_profit_pct: float            # Week 2 exit target
    week3_profit_pct: float            # Week 3 exit target
    week4_profit_pct: float            # Week 4+ exit target
    
    # Expected Outcomes (for display/reference)
    expected_max_loss_pct: float       # Max loss in black swan
    expected_annual_roi_pct: float     # Expected annual return
    recovery_time_months: str          # Estimated recovery time
    
    # Fields with default values MUST come last
    min_confidence: float = 70.0       # Minimum confidence score to generate signal
    defensive_breach_pct: float = 2.0  # % below strike to trigger defensive exit


# ============================================
# PREDEFINED RISK PROFILES
# ============================================

LOW_RISK_PROFILE = RiskProfile(
    # Identity
    name="Conservative",
    level=RiskLevel.LOW,
    description="Lowest risk, maximum protection. Best for new traders or risk-averse accounts.",
    
    # Position Sizing - Conservative
    max_capital_deployed_pct=0.60,     # Only 60% deployed
    max_positions=3,                    # Maximum 3 positions
    contracts_per_trade=5,              # Smaller positions
    cash_reserve_pct=0.40,              # 40% cash buffer
    max_portfolio_heat=30000,           # $30K max at risk
    
    # Defensive Exits - Maximum Protection
    breach_threshold_pct=0.02,          # Exit if stock < strike * 0.98
    breach_confirmation_days=3,         # Require 3-day confirmation
    dte_exit_threshold=5,               # Exit 5 days before expiry
    
    # VIX - Conservative Thresholds
    vix_block_trading=30,               # Stop trading at VIX 30
    vix_reduce_size=25,                 # Reduce size at VIX 25
    vix_close_all=40,                   # Emergency exit at VIX 40
    vix_size_reduction=0.50,            # 50% size when elevated
    
    # Time-Based Exits - Conservative Targets
    week1_profit_pct=40.0,              # Exit earlier at lower targets
    week2_profit_pct=50.0,
    week3_profit_pct=65.0,
    week4_profit_pct=80.0,
    
    # Expected Outcomes
    expected_max_loss_pct=0.20,         # -15 to -20% in black swan
    expected_annual_roi_pct=0.35,        # 35% annual return
    recovery_time_months="2-3",
)


MEDIUM_RISK_PROFILE = RiskProfile(
    # Identity
    name="Moderate",
    level=RiskLevel.MEDIUM,
    description="Balanced risk and reward. Recommended for most traders.",
    
    # Position Sizing - Moderate
    max_capital_deployed_pct=0.80,     # 80% deployed
    max_positions=5,                    # Up to 5 positions
    contracts_per_trade=8,              # Standard positions
    cash_reserve_pct=0.20,              # 20% cash buffer
    max_portfolio_heat=50000,           # $50K max at risk
    
    # Defensive Exits - Balanced
    breach_threshold_pct=0.02,          # Exit if stock < strike * 0.98
    breach_confirmation_days=3,         # Require 3-day confirmation
    dte_exit_threshold=3,               # Exit 3 days before expiry
    
    # VIX - Standard Thresholds
    vix_block_trading=35,               # Stop trading at VIX 35
    vix_reduce_size=28,                 # Reduce size at VIX 28
    vix_close_all=45,                   # Emergency exit at VIX 45
    vix_size_reduction=0.50,            # 50% size when elevated
    
    # Time-Based Exits - Standard Targets
    week1_profit_pct=50.0,
    week2_profit_pct=60.0,
    week3_profit_pct=75.0,
    week4_profit_pct=90.0,
    
    # Expected Outcomes
    expected_max_loss_pct=0.25,         # -20 to -25% in black swan
    expected_annual_roi_pct=0.47,        # 47% annual return
    recovery_time_months="3-4",
)


HIGH_RISK_PROFILE = RiskProfile(
    # Identity
    name="Aggressive",
    level=RiskLevel.HIGH,
    description="⚠️ Maximum returns, highest risk. Only for experienced traders with strong risk tolerance.",
    
    # Position Sizing - Aggressive
    max_capital_deployed_pct=1.00,     # 100% deployed
    max_positions=6,                    # Maximum 6 positions
    contracts_per_trade=10,             # Full size positions
    cash_reserve_pct=0.00,              # No cash buffer
    max_portfolio_heat=70000,           # $70K max at risk
    
    # Defensive Exits - Faster
    breach_threshold_pct=0.03,          # Exit if stock < strike * 0.97 (tighter)
    breach_confirmation_days=2,         # Only 2-day confirmation
    dte_exit_threshold=2,               # Exit 2 days before expiry
    
    # VIX - Higher Tolerance
    vix_block_trading=40,               # Stop trading at VIX 40
    vix_reduce_size=32,                 # Reduce size at VIX 32
    vix_close_all=50,                   # Emergency exit at VIX 50
    vix_size_reduction=0.75,            # Only 25% reduction when elevated
    
    # Time-Based Exits - Aggressive Targets
    week1_profit_pct=50.0,
    week2_profit_pct=60.0,
    week3_profit_pct=75.0,
    week4_profit_pct=90.0,
    
    # Expected Outcomes
    expected_max_loss_pct=0.50,         # -35 to -50% in black swan
    expected_annual_roi_pct=0.60,        # 60% annual return
    recovery_time_months="6-12",
)


# Map for easy lookup
RISK_PROFILES: Dict[RiskLevel, RiskProfile] = {
    RiskLevel.LOW: LOW_RISK_PROFILE,
    RiskLevel.MEDIUM: MEDIUM_RISK_PROFILE,
    RiskLevel.HIGH: HIGH_RISK_PROFILE,
}


def get_risk_profile(level = None) -> RiskProfile:
    """
    Get risk profile by level string, RiskLevel enum, or from environment.
    
    Args:
        level: "low", "medium", "high" (case-insensitive) OR RiskLevel enum
               If None, reads from THETA_RISK_LEVEL env var
               
    Returns:
        RiskProfile for the specified or configured level
    """
    # Handle RiskLevel enum input
    if isinstance(level, RiskLevel):
        profile = RISK_PROFILES[level]
        logger.info(f"Using {profile.name} ({profile.level.value}) risk profile")
        return profile
    
    if level is None:
        level = os.getenv("THETA_RISK_LEVEL", "medium")
    
    level = level.lower().strip()
    
    try:
        risk_level = RiskLevel(level)
        profile = RISK_PROFILES[risk_level]
        logger.info(f"Using {profile.name} ({profile.level.value}) risk profile")
        return profile
    except ValueError:
        logger.warning(f"Invalid risk level '{level}', defaulting to MEDIUM")
        return MEDIUM_RISK_PROFILE


def log_risk_profile(profile: RiskProfile) -> None:
    """Log a summary of the risk profile settings."""
    logger.info(f"""
    ┌─────────────────────────────────────────────────────┐
    │  RISK PROFILE: {profile.name.upper():^38} │
    ├─────────────────────────────────────────────────────┤
    │  Level: {profile.level.value.upper():<44} │
    │  Capital Deployed: {profile.max_capital_deployed_pct*100:.0f}%{' ':<35} │
    │  Max Positions: {profile.max_positions:<37} │
    │  Contracts/Trade: {profile.contracts_per_trade:<35} │
    │  Cash Reserve: {profile.cash_reserve_pct*100:.0f}%{' ':<36} │
    ├─────────────────────────────────────────────────────┤
    │  Breach Threshold: {profile.breach_threshold_pct*100:.0f}% below strike{' ':<21} │
    │  Confirmation Days: {profile.breach_confirmation_days:<33} │
    │  VIX Block: >{profile.vix_block_trading:.0f}{' ':<38} │
    │  VIX Close All: >{profile.vix_close_all:.0f}{' ':<34} │
    ├─────────────────────────────────────────────────────┤
    │  Expected Max Loss: -{profile.expected_max_loss_pct*100:.0f}%{' ':<30} │
    │  Expected Annual ROI: {profile.expected_annual_roi_pct*100:.0f}%{' ':<30} │
    │  Recovery Time: {profile.recovery_time_months} months{' ':<29} │
    └─────────────────────────────────────────────────────┘
    """)
