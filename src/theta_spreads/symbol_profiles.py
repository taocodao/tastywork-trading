"""
Symbol-specific configuration profiles for Theta Sprint strategy.

Research-validated baseline approach following academic best practices:
- GMO (2018): Cross-asset volatility premia  
- Eurex (2025): Bond ETF option strategies
- Bailey & López de Prado (2013): Avoiding overfitting
- First Sentier (2022): Commodity spike risk

Theory-driven parameters, not data-fitted.
"""

from dataclasses import dataclass, replace
from typing import Dict, Optional
from .risk_profiles import RiskLevel


@dataclass(frozen=True)
class SymbolProfile:
    """
    Symbol-specific parameters for theta decay strategy.
    
    Research-validated baselines by asset class:
    - EQUITY_BASELINE: 50/60/75/90% targets, 2% breach
    - BOND_BASELINE: 50/60/75/90% targets, 2% breach  
    - COMMODITY_BASELINE: 50/60/75/90% targets, 4% breach (wider for spikes)
    """
    symbol: str
    base_risk_level: RiskLevel = RiskLevel.MEDIUM
    
    # Time-based profit targets (% of max profit)
    week1_profit_pct: float = 50.0
    week2_profit_pct: float = 60.0
    week3_profit_pct: float = 75.0
    week4_profit_pct: float = 90.0
    
    # Defensive exit parameters
    breach_threshold_pct: float = 0.02  # % below strike
    confirmation_days: int = 3          # Multi-day confirmation
    dte_exit_threshold: int = 3         # Exit when DTE <= threshold
    
    # Symbol characteristics (informational)
    avg_iv: float = 0.18
    price_volatility: str = "medium"
    mean_reversion_strength: str = "medium"
    
    def _replace(self, **kwargs):
        """Helper to replace fields."""
        return replace(self, **kwargs)


# =============================================================================
# RESEARCH-VALIDATED BASELINE PROFILES
# Based on academic research: GMO (2018), Eurex (2025), Bailey & López de Prado
# Using theory-driven parameters, not data-fitted
# =============================================================================

# Standard Industry Baseline - All Equity ETFs
# Source: CBOE PUT index methodology, Option pricing literature
EQUITY_BASELINE = SymbolProfile(
    symbol="EQUITY_BASELINE",
    base_risk_level=RiskLevel.MEDIUM,
    
    # Industry-standard profit targets (NOT optimized to 2024 data)
    week1_profit_pct=50.0,  # 50% of max profit in week 1
    week2_profit_pct=60.0,  # 60% in week 2
    week3_profit_pct=75.0,  # 75% in week 3
    week4_profit_pct=90.0,  # 90% in week 4
    
    # Moderate breach threshold for liquid equity markets
    breach_threshold_pct=0.02,  # 2% below strike
    confirmation_days=3,         # Multi-day confirmation prevents whipsaw
    dte_exit_threshold=3,        # Exit close to expiration
    
    avg_iv=0.18,  # Typical equity IV
    price_volatility="medium",
    mean_reversion_strength="strong"
)

# Bond ETF Baseline - Lower volatility, similar theta structure
# Source: Eurex (2025) IDTL study shows bonds follow similar patterns
BOND_BASELINE = SymbolProfile(
    symbol="BOND_BASELINE",
    base_risk_level=RiskLevel.LOW,
    
    # SAME targets as equity (Eurex research shows similar structure)
    week1_profit_pct=50.0,
    week2_profit_pct=60.0,
    week3_profit_pct=75.0,
    week4_profit_pct=90.0,
    
    # 2% breach (duration jumps similar to equity gaps)
    breach_threshold_pct=0.02,
    confirmation_days=3,
    dte_exit_threshold=5,  # Hold longer due to lower premiums
    
    avg_iv=0.10,
    price_volatility="low",
    mean_reversion_strength="medium"
)

# Commodity/Energy Baseline - Higher jump risk requires wider stops
# Source: First Sentier (2022), BIS commodity volatility research
COMMODITY_BASELINE = SymbolProfile(
    symbol="COMMODITY_BASELINE",
    base_risk_level=RiskLevel.MEDIUM,
    
    # Standard targets (theta decay is universal)
    week1_profit_pct=50.0,
    week2_profit_pct=60.0,
    week3_profit_pct=75.0,
    week4_profit_pct=90.0,
    
    # WIDER breach for spike/jump risk (research-validated)
    breach_threshold_pct=0.04,  # 4% below strike (vs 2% for equity)
    confirmation_days=3,
    dte_exit_threshold=5,
    
    avg_iv=0.25,
    price_volatility="high",
    mean_reversion_strength="medium"
)


# =============================================================================
# APPLY BASELINES TO ALL SYMBOLS
# Theory-driven approach: same parameters within asset class
# =============================================================================

# Core Equity ETFs - Use standard baseline
SPY_PROFILE = EQUITY_BASELINE._replace(symbol="SPY", avg_iv=0.15)
QQQ_PROFILE = EQUITY_BASELINE._replace(symbol="QQQ", avg_iv=0.22)
IWM_PROFILE = EQUITY_BASELINE._replace(symbol="IWM", avg_iv=0.25)
DIA_PROFILE = EQUITY_BASELINE._replace(symbol="DIA", avg_iv=0.14)

# Bond ETFs - Use bond baseline
TLT_PROFILE = BOND_BASELINE._replace(symbol="TLT", avg_iv=0.12)
IEF_PROFILE = BOND_BASELINE._replace(symbol="IEF", avg_iv=0.08)
LQD_PROFILE = BOND_BASELINE._replace(symbol="LQD", avg_iv=0.10)
AGG_PROFILE = BOND_BASELINE._replace(symbol="AGG", avg_iv=0.06)
HYG_PROFILE = BOND_BASELINE._replace(symbol="HYG", avg_iv=0.12)

# Commodities - Use commodity baseline (wider breach)
GLD_PROFILE = COMMODITY_BASELINE._replace(symbol="GLD", avg_iv=0.18)
SLV_PROFILE = COMMODITY_BASELINE._replace(symbol="SLV", avg_iv=0.25)
USO_PROFILE = COMMODITY_BASELINE._replace(symbol="USO", avg_iv=0.35)

# Sector ETFs - Grouped by asset class characteristics
# Tech sectors: Use equity baseline (liquid, moderate vol)
XLK_PROFILE = EQUITY_BASELINE._replace(symbol="XLK", avg_iv=0.20)
ARKK_PROFILE = EQUITY_BASELINE._replace(symbol="ARKK", avg_iv=0.40)

# Defensive sectors: Use equity baseline
XLV_PROFILE = EQUITY_BASELINE._replace(symbol="XLV", avg_iv=0.15)
XLP_PROFILE = EQUITY_BASELINE._replace(symbol="XLP", avg_iv=0.12)
XLU_PROFILE = EQUITY_BASELINE._replace(symbol="XLU", avg_iv=0.14)

# Cyclical sectors: Use equity baseline 
XLF_PROFILE = EQUITY_BASELINE._replace(symbol="XLF", avg_iv=0.22)
XLI_PROFILE = EQUITY_BASELINE._replace(symbol="XLI", avg_iv=0.18)
XLY_PROFILE = EQUITY_BASELINE._replace(symbol="XLY", avg_iv=0.19)
XLB_PROFILE = EQUITY_BASELINE._replace(symbol="XLB", avg_iv=0.20)
XLRE_PROFILE = EQUITY_BASELINE._replace(symbol="XLRE", avg_iv=0.20)

# Energy: Use commodity baseline (spike risk like oil/gas)
XLE_PROFILE = COMMODITY_BASELINE._replace(symbol="XLE", avg_iv=0.30)

# International: Use equity baseline
EEM_PROFILE = EQUITY_BASELINE._replace(symbol="EEM", avg_iv=0.24)
EWZ_PROFILE = EQUITY_BASELINE._replace(symbol="EWZ", avg_iv=0.35)
FXI_PROFILE = EQUITY_BASELINE._replace(symbol="FXI", avg_iv=0.26)


# =============================================================================
# EXCLUDE LIST - Never trade these (volatility decay products)
# =============================================================================

THETA_EXCLUDE_SYMBOLS = ["VXX", "UVXY", "SVXY", "UNG"]


# =============================================================================
# SYMBOL PROFILE REGISTRY
# =============================================================================

SYMBOL_PROFILES: Dict[str, SymbolProfile] = {
    # Core Equity Index
    "SPY": SPY_PROFILE,
    "QQQ": QQQ_PROFILE,
    "IWM": IWM_PROFILE,
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


def get_symbol_profile(symbol: str, default_risk_level: RiskLevel = RiskLevel.MEDIUM) -> SymbolProfile:
    """
    Get symbol-specific profile or fall back to baseline.
    
    Research-validated approach:
    - Returns pre-configured profile if exists
    - Falls back to EQUITY_BASELINE for unknown symbols
    - All profiles use theory-driven parameters, not data-fitted
    """
    if symbol in SYMBOL_PROFILES:
        return SYMBOL_PROFILES[symbol]
    
    # Fallback to equity baseline for unknown symbols
    return EQUITY_BASELINE._replace(symbol=symbol, base_risk_level=default_risk_level)


def list_all_profiles() -> Dict[str, SymbolProfile]:
    """Return all configured symbol profiles."""
    return SYMBOL_PROFILES.copy()


def get_excluded_symbols() -> list:
    """Return list of excluded symbols (never trade)."""
    return THETA_EXCLUDE_SYMBOLS.copy()
