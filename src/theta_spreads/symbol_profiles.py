"""
Symbol-Specific Risk Profiles
==============================
Allows different risk parameters per symbol to optimize performance.

QQQ needs tighter profit targets and earlier exits due to tech volatility.
IWM performs well with aggressive parameters.
SPY is balanced with standard settings.
"""

from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum

from .risk_profiles import RiskLevel, RiskProfile, RISK_PROFILES


@dataclass
class SymbolProfile:
    """
    Symbol-specific parameter overrides for Theta strategy.
    
    Allows customization of exit rules per symbol while maintaining
    base risk profile structure.
    """
    symbol: str
    base_risk_level: RiskLevel
    
    # Optional overrides (None = use base profile defaults)
    breach_threshold_pct: Optional[float] = None
    confirmation_days: Optional[int] = None
    dte_exit_threshold: Optional[int] = None
    week1_profit_pct: Optional[float] = None
    week2_profit_pct: Optional[float] = None
    week3_profit_pct: Optional[float] = None
    week4_profit_pct: Optional[float] = None
    
    # Symbol characteristics (for reference/analysis)
    avg_iv: float = 0.20
    price_volatility: str = "medium"  # low, medium, high
    mean_reversion_strength: str = "medium"  # how well it recovers from dips
    
    def get_effective_profile(self) -> RiskProfile:
        """
        Return effective risk profile with symbol-specific overrides applied.
        
        Returns:
            RiskProfile with symbol customizations
        """
        base = RISK_PROFILES[self.base_risk_level]
        
        # Apply overrides
        return RiskProfile(
            name=f"{base.name} ({self.symbol})",
            level=base.level,
            description=f"Symbol-optimized {base.description}",
            
            # Position sizing (use base)
            max_capital_deployed_pct=base.max_capital_deployed_pct,
            max_positions=base.max_positions,
            contracts_per_trade=base.contracts_per_trade,
            cash_reserve_pct=base.cash_reserve_pct,
            max_portfolio_heat=base.max_portfolio_heat,
            
            # Defensive exits (allow overrides)
            breach_threshold_pct=self.breach_threshold_pct or base.breach_threshold_pct,
            breach_confirmation_days=self.confirmation_days or base.breach_confirmation_days,
            dte_exit_threshold=self.dte_exit_threshold or base.dte_exit_threshold,
            
            # VIX thresholds (use base)
            vix_block_trading=base.vix_block_trading,
            vix_reduce_size=base.vix_reduce_size,
            vix_close_all=base.vix_close_all,
            vix_size_reduction=base.vix_size_reduction,
            
            # Time-based exits (allow overrides)
            week1_profit_pct=self.week1_profit_pct or base.week1_profit_pct,
            week2_profit_pct=self.week2_profit_pct or base.week2_profit_pct,
            week3_profit_pct=self.week3_profit_pct or base.week3_profit_pct,
            week4_profit_pct=self.week4_profit_pct or base.week4_profit_pct,
            
            # Expected outcomes (use base)
            expected_max_loss_pct=base.expected_max_loss_pct,
            expected_annual_roi_pct=base.expected_annual_roi_pct,
            recovery_time_months=base.recovery_time_months,
            
            # Defaults
            min_confidence=base.min_confidence,
            defensive_breach_pct=base.defensive_breach_pct
        )


# =============================================================================
# SYMBOL-SPECIFIC CONFIGURATIONS
# =============================================================================

QQQ_PROFILE = SymbolProfile(
    symbol="QQQ",
    base_risk_level=RiskLevel.MEDIUM,
    
    # QQQ-specific tuning based on backtest analysis
    # Problem: QQQ had negative P&L with standard settings
    # Solution: Tighter profit targets, earlier exits, more room for volatility
    
    week1_profit_pct=30.0,  # 30% vs 50% - exit faster
    week2_profit_pct=40.0,  # 40% vs 60% - lock in gains
    week3_profit_pct=55.0,  # 55% vs 75%
    week4_profit_pct=70.0,  # 70% vs 90%
    
    dte_exit_threshold=7,    # Exit 7 days before expiry (vs 3)
    breach_threshold_pct=0.03,  # 3% breach tolerance (vs 2%)
    confirmation_days=2,     # 2 days confirmation (vs 3) - react faster
    
    # Characteristics
    avg_iv=0.25,  # Higher than SPY
    price_volatility="high",  # Tech volatility
    mean_reversion_strength="medium"  # Recovers but volatile
)

IWM_PROFILE = SymbolProfile(
    symbol="IWM",
    base_risk_level=RiskLevel.HIGH,  # IWM performed best with aggressive
    
    # IWM crushed it with HIGH settings - keep those
    # No overrides needed, just use HIGH profile defaults
    
    avg_iv=0.22,
    price_volatility="high",
    mean_reversion_strength="strong"  # Small caps bounce well
)

SPY_PROFILE = SymbolProfile(
    symbol="SPY",
    base_risk_level=RiskLevel.MEDIUM,
    
    # SPY is balanced - slight tweaks for optimization
    week1_profit_pct=45.0,  # Slightly tighter than 50%
    week2_profit_pct=55.0,  # Slightly tighter than 60%
    
    avg_iv=0.15,  # Lower than QQQ/IWM
    price_volatility="medium",
    mean_reversion_strength="strong"  # Blue chips recover well
)


# Symbol profile registry
SYMBOL_PROFILES: Dict[str, SymbolProfile] = {
    "QQQ": QQQ_PROFILE,
    "IWM": IWM_PROFILE,
    "SPY": SPY_PROFILE,
}


def get_symbol_profile(symbol: str, default_risk_level: RiskLevel = RiskLevel.MEDIUM) -> RiskProfile:
    """
    Get symbol-specific risk profile with optimizations.
    
    Args:
        symbol: Ticker symbol (SPY, QQQ, IWM, etc.)
        default_risk_level: Fallback if symbol not configured
        
    Returns:
        RiskProfile with symbol-specific optimizations
    """
    if symbol in SYMBOL_PROFILES:
        return SYMBOL_PROFILES[symbol].get_effective_profile()
    else:
        # Unknown symbol - use default risk level
        return RISK_PROFILES[default_risk_level]


def get_symbol_characteristics(symbol: str) -> Dict[str, str]:
    """
    Get symbol market characteristics for analysis.
    
    Returns:
        Dict with avg_iv, volatility, mean_reversion
    """
    if symbol in SYMBOL_PROFILES:
        profile = SYMBOL_PROFILES[symbol]
        return {
            "avg_iv": profile.avg_iv,
            "price_volatility": profile.price_volatility,
            "mean_reversion": profile.mean_reversion_strength
        }
    else:
        return {
            "avg_iv": 0.20,
            "price_volatility": "medium",
            "mean_reversion": "medium"
        }
