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


# =============================================================================
# BOND ETF PROFILES - Lower volatility, trending behavior
# =============================================================================

TLT_PROFILE = SymbolProfile(
    symbol="TLT",
    base_risk_level=RiskLevel.LOW,
    
    # Bonds trend more than mean-revert, take profits quickly
    week1_profit_pct=35.0,
    week2_profit_pct=45.0,
    week3_profit_pct=60.0,
    week4_profit_pct=75.0,
    
    # Tighter breach for lower volatility asset
    breach_threshold_pct=0.015,  # 1.5%
    confirmation_days=2,
    dte_exit_threshold=5,
    
    avg_iv=0.12,
    price_volatility="low",
    mean_reversion_strength="weak"
)

# Apply same profile to other bond ETFs
IEF_PROFILE = SymbolProfile(symbol="IEF", base_risk_level=RiskLevel.LOW,
    week1_profit_pct=35.0, week2_profit_pct=45.0,
    breach_threshold_pct=0.015, confirmation_days=2, dte_exit_threshold=5,
    avg_iv=0.08, price_volatility="low", mean_reversion_strength="weak")

LQD_PROFILE = SymbolProfile(symbol="LQD", base_risk_level=RiskLevel.LOW,
    week1_profit_pct=35.0, week2_profit_pct=45.0,
    breach_threshold_pct=0.015, confirmation_days=2, dte_exit_threshold=5,
    avg_iv=0.10, price_volatility="low", mean_reversion_strength="weak")

AGG_PROFILE = SymbolProfile(symbol="AGG", base_risk_level=RiskLevel.LOW,
    week1_profit_pct=35.0, week2_profit_pct=45.0,
    breach_threshold_pct=0.015, confirmation_days=2, dte_exit_threshold=5,
    avg_iv=0.06, price_volatility="low", mean_reversion_strength="weak")

HYG_PROFILE = SymbolProfile(symbol="HYG", base_risk_level=RiskLevel.LOW,
    week1_profit_pct=40.0, week2_profit_pct=50.0,
    breach_threshold_pct=0.02, confirmation_days=2, dte_exit_threshold=5,
    avg_iv=0.12, price_volatility="medium", mean_reversion_strength="medium")


# =============================================================================
# COMMODITY ETF PROFILES - Regime-dependent, can spike
# =============================================================================

GLD_PROFILE = SymbolProfile(
    symbol="GLD",
    base_risk_level=RiskLevel.MEDIUM,
    
    # Gold can spike during crises, give more room
    week1_profit_pct=45.0,
    week2_profit_pct=55.0,
    week3_profit_pct=70.0,
    week4_profit_pct=85.0,
    
    # Wider breach for commodity volatility
    breach_threshold_pct=0.035,  # 3.5%
    confirmation_days=3,
    dte_exit_threshold=5,
    
    avg_iv=0.14,
    price_volatility="medium",
    mean_reversion_strength="medium"
)

SLV_PROFILE = SymbolProfile(symbol="SLV", base_risk_level=RiskLevel.MEDIUM,
    week1_profit_pct=40.0, week2_profit_pct=50.0,
    breach_threshold_pct=0.04, confirmation_days=3, dte_exit_threshold=5,
    avg_iv=0.22, price_volatility="high", mean_reversion_strength="medium")

USO_PROFILE = SymbolProfile(symbol="USO", base_risk_level=RiskLevel.MEDIUM,
    week1_profit_pct=40.0, week2_profit_pct=50.0,
    breach_threshold_pct=0.05, confirmation_days=3, dte_exit_threshold=7,
    avg_iv=0.30, price_volatility="high", mean_reversion_strength="weak")


# =============================================================================
# TECH SECTOR PROFILES - High beta, similar to QQQ
# =============================================================================

XLK_PROFILE = SymbolProfile(
    symbol="XLK",
    base_risk_level=RiskLevel.MEDIUM,
    
    # Tech sector: exit faster like QQQ
    week1_profit_pct=30.0,
    week2_profit_pct=40.0,
    week3_profit_pct=55.0,
    week4_profit_pct=70.0,
    
    breach_threshold_pct=0.03,
    confirmation_days=2,
    dte_exit_threshold=7,
    
    avg_iv=0.22,
    price_volatility="high",
    mean_reversion_strength="medium"
)

ARKK_PROFILE = SymbolProfile(symbol="ARKK", base_risk_level=RiskLevel.HIGH,
    week1_profit_pct=25.0, week2_profit_pct=35.0, week3_profit_pct=50.0, week4_profit_pct=65.0,
    breach_threshold_pct=0.04, confirmation_days=2, dte_exit_threshold=7,
    avg_iv=0.40, price_volatility="high", mean_reversion_strength="weak")


# =============================================================================
# DEFENSIVE SECTOR PROFILES - Lower volatility, stable
# =============================================================================

XLV_PROFILE = SymbolProfile(symbol="XLV", base_risk_level=RiskLevel.LOW,
    week1_profit_pct=40.0, week2_profit_pct=50.0,
    breach_threshold_pct=0.02, confirmation_days=3, dte_exit_threshold=3,
    avg_iv=0.14, price_volatility="low", mean_reversion_strength="strong")

XLP_PROFILE = SymbolProfile(symbol="XLP", base_risk_level=RiskLevel.LOW,
    week1_profit_pct=40.0, week2_profit_pct=50.0,
    breach_threshold_pct=0.02, confirmation_days=3, dte_exit_threshold=3,
    avg_iv=0.12, price_volatility="low", mean_reversion_strength="strong")

XLU_PROFILE = SymbolProfile(symbol="XLU", base_risk_level=RiskLevel.LOW,
    week1_profit_pct=40.0, week2_profit_pct=50.0,
    breach_threshold_pct=0.02, confirmation_days=3, dte_exit_threshold=3,
    avg_iv=0.15, price_volatility="low", mean_reversion_strength="strong")


# =============================================================================
# CYCLICAL SECTOR PROFILES - Economic sensitive
# =============================================================================

XLF_PROFILE = SymbolProfile(symbol="XLF", base_risk_level=RiskLevel.MEDIUM,
    week1_profit_pct=45.0, week2_profit_pct=55.0,
    breach_threshold_pct=0.025, confirmation_days=3, dte_exit_threshold=3,
    avg_iv=0.18, price_volatility="medium", mean_reversion_strength="medium")

XLE_PROFILE = SymbolProfile(symbol="XLE", base_risk_level=RiskLevel.MEDIUM,
    week1_profit_pct=40.0, week2_profit_pct=50.0,
    breach_threshold_pct=0.04, confirmation_days=3, dte_exit_threshold=5,
    avg_iv=0.25, price_volatility="high", mean_reversion_strength="medium")

XLI_PROFILE = SymbolProfile(symbol="XLI", base_risk_level=RiskLevel.MEDIUM,
    week1_profit_pct=45.0, week2_profit_pct=55.0,
    breach_threshold_pct=0.025, confirmation_days=3, dte_exit_threshold=3,
    avg_iv=0.16, price_volatility="medium", mean_reversion_strength="medium")

XLY_PROFILE = SymbolProfile(symbol="XLY", base_risk_level=RiskLevel.MEDIUM,
    week1_profit_pct=45.0, week2_profit_pct=55.0,
    breach_threshold_pct=0.025, confirmation_days=3, dte_exit_threshold=3,
    avg_iv=0.18, price_volatility="medium", mean_reversion_strength="medium")

XLRE_PROFILE = SymbolProfile(symbol="XLRE", base_risk_level=RiskLevel.LOW,
    week1_profit_pct=40.0, week2_profit_pct=50.0,
    breach_threshold_pct=0.03, confirmation_days=3, dte_exit_threshold=5,
    avg_iv=0.18, price_volatility="medium", mean_reversion_strength="medium")

XLB_PROFILE = SymbolProfile(symbol="XLB", base_risk_level=RiskLevel.MEDIUM,
    week1_profit_pct=45.0, week2_profit_pct=55.0,
    breach_threshold_pct=0.025, confirmation_days=3, dte_exit_threshold=3,
    avg_iv=0.18, price_volatility="medium", mean_reversion_strength="medium")


# =============================================================================
# INTERNATIONAL ETF PROFILES - Higher risk, currency effects
# =============================================================================

EEM_PROFILE = SymbolProfile(symbol="EEM", base_risk_level=RiskLevel.MEDIUM,
    week1_profit_pct=40.0, week2_profit_pct=50.0,
    breach_threshold_pct=0.035, confirmation_days=3, dte_exit_threshold=5,
    avg_iv=0.20, price_volatility="high", mean_reversion_strength="medium")

EWZ_PROFILE = SymbolProfile(symbol="EWZ", base_risk_level=RiskLevel.HIGH,
    week1_profit_pct=35.0, week2_profit_pct=45.0,
    breach_threshold_pct=0.04, confirmation_days=2, dte_exit_threshold=7,
    avg_iv=0.30, price_volatility="high", mean_reversion_strength="weak")

FXI_PROFILE = SymbolProfile(symbol="FXI", base_risk_level=RiskLevel.MEDIUM,
    week1_profit_pct=40.0, week2_profit_pct=50.0,
    breach_threshold_pct=0.035, confirmation_days=3, dte_exit_threshold=5,
    avg_iv=0.25, price_volatility="high", mean_reversion_strength="medium")


# =============================================================================
# EQUITY INDEX (Default MEDIUM behavior)
# =============================================================================

DIA_PROFILE = SymbolProfile(symbol="DIA", base_risk_level=RiskLevel.MEDIUM,
    week1_profit_pct=45.0, week2_profit_pct=55.0,
    breach_threshold_pct=0.02, confirmation_days=3, dte_exit_threshold=3,
    avg_iv=0.14, price_volatility="medium", mean_reversion_strength="strong")


# =============================================================================
# EXCLUDE LIST - Never trade these (volatility decay products)
# =============================================================================

THETA_EXCLUDE_SYMBOLS = ["VXX", "UVXY", "SVXY", "UNG"]


# Symbol profile registry
SYMBOL_PROFILES: Dict[str, SymbolProfile] = {
    # Core Equity Index
    "QQQ": QQQ_PROFILE,
    "IWM": IWM_PROFILE,
    "SPY": SPY_PROFILE,
    "DIA": DIA_PROFILE,
    
    # Bonds
    "TLT": TLT_PROFILE,
    "IEF": IEF_PROFILE,
    "LQD": LQD_PROFILE,
    "AGG": AGG_PROFILE,
    "HYG": HYG_PROFILE,
    
    # Commodities
    "GLD": GLD_PROFILE,
    "SLV": SLV_PROFILE,
    "USO": USO_PROFILE,
    
    # Tech Sector
    "XLK": XLK_PROFILE,
    "ARKK": ARKK_PROFILE,
    
    # Defensive Sectors
    "XLV": XLV_PROFILE,
    "XLP": XLP_PROFILE,
    "XLU": XLU_PROFILE,
    
    # Cyclical Sectors
    "XLF": XLF_PROFILE,
    "XLE": XLE_PROFILE,
    "XLI": XLI_PROFILE,
    "XLY": XLY_PROFILE,
    "XLRE": XLRE_PROFILE,
    "XLB": XLB_PROFILE,
    
    # International
    "EEM": EEM_PROFILE,
    "EWZ": EWZ_PROFILE,
    "FXI": FXI_PROFILE,
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
