"""
ETF Universe: 3-Tier Security Universe for Diagonal Spreads

Based on SUPPLEMENT doc design:
- Tier 1: Core Holdings (60-70% allocation) - SPY, QQQ, IWM, TLT, GLD, SLV
- Tier 2: Sector/International ETFs (20-25%) - XLF, XLE, EEM, etc.
- Tier 3: Opportunistic (5-15%) - XBI, SMH, XLU, XOP, etc.

Key principles:
1. ETFs only in Tier 1 (no earnings risk)
2. Quarterly updates from market data
3. Correlation filter to prevent duplicates
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class UniverseTier(Enum):
    """Security tier classification"""
    TIER_1_CORE = 1      # Always include, highest liquidity
    TIER_2_ROTATION = 2  # Rotate based on conditions
    TIER_3_OPPORTUNISTIC = 3  # Only when IV conditions exceptional
    TIER_4_EQUITIES = 4  # Individual mega-cap equities for PMCC


@dataclass
class SecurityConfig:
    """Configuration for a single security in the universe"""
    symbol: str
    name: str
    tier: UniverseTier
    liquidity_score: int  # 0-100
    weight: float  # Target weight in portfolio
    description: str = ""
    sector: str = ""
    correlation_group: str = ""  # Securities in same group are correlated
    has_earnings_risk: bool = False
    min_options_volume: int = 1000
    max_bid_ask_spread_pct: float = 0.05
    
    def __hash__(self):
        return hash(self.symbol)


# ============================================================================
# TIER 1: CORE ETFs - Always include, no earnings risk
# ============================================================================
TIER_1_CORE_ETFS: Dict[str, SecurityConfig] = {
    "SPY": SecurityConfig(
        symbol="SPY",
        name="S&P 500 ETF",
        tier=UniverseTier.TIER_1_CORE,
        liquidity_score=100,
        weight=0.20,
        description="S&P 500 tracking, best liquidity",
        sector="Broad Market",
        correlation_group="SP500",
        has_earnings_risk=False,
        min_options_volume=500000,
        max_bid_ask_spread_pct=0.01
    ),
    "QQQ": SecurityConfig(
        symbol="QQQ",
        name="Nasdaq 100 ETF",
        tier=UniverseTier.TIER_1_CORE,
        liquidity_score=99,
        weight=0.15,
        description="Tech-heavy Nasdaq tracking",
        sector="Technology",
        correlation_group="NASDAQ",
        has_earnings_risk=False,
        min_options_volume=400000,
        max_bid_ask_spread_pct=0.01
    ),
    "IWM": SecurityConfig(
        symbol="IWM",
        name="Russell 2000 ETF",
        tier=UniverseTier.TIER_1_CORE,
        liquidity_score=95,
        weight=0.10,
        description="Small-cap exposure",
        sector="Small Cap",
        correlation_group="Russell",
        has_earnings_risk=False,
        min_options_volume=200000,
        max_bid_ask_spread_pct=0.02
    ),
    "TLT": SecurityConfig(
        symbol="TLT",
        name="20+ Year Treasury ETF",
        tier=UniverseTier.TIER_1_CORE,
        liquidity_score=92,
        weight=0.08,
        description="Long-term bonds, negative equity correlation",
        sector="Bonds",
        correlation_group="Bonds",
        has_earnings_risk=False,
        min_options_volume=100000,
        max_bid_ask_spread_pct=0.02
    ),
    "GLD": SecurityConfig(
        symbol="GLD",
        name="Gold ETF",
        tier=UniverseTier.TIER_1_CORE,
        liquidity_score=90,
        weight=0.05,
        description="Gold exposure, safe haven",
        sector="Commodities",
        correlation_group="PreciousMetals",
        has_earnings_risk=False,
        min_options_volume=50000,
        max_bid_ask_spread_pct=0.02
    ),
    "SLV": SecurityConfig(
        symbol="SLV",
        name="Silver ETF",
        tier=UniverseTier.TIER_1_CORE,
        liquidity_score=85,
        weight=0.02,
        description="Silver exposure",
        sector="Commodities",
        correlation_group="PreciousMetals",
        has_earnings_risk=False,
        min_options_volume=30000,
        max_bid_ask_spread_pct=0.03
    ),
}


# ============================================================================
# TIER 2: SECTOR ETFs - Rotation based on market conditions
# ============================================================================
TIER_2_SECTOR_ETFS: Dict[str, SecurityConfig] = {
    "XLK": SecurityConfig(
        symbol="XLK",
        name="Technology Select Sector",
        tier=UniverseTier.TIER_2_ROTATION,
        liquidity_score=94,
        weight=0.05,
        sector="Technology",
        correlation_group="Tech",
    ),
    "XLF": SecurityConfig(
        symbol="XLF",
        name="Financials Select Sector",
        tier=UniverseTier.TIER_2_ROTATION,
        liquidity_score=93,
        weight=0.05,
        sector="Financials",
        correlation_group="Financials",
    ),
    "XLV": SecurityConfig(
        symbol="XLV",
        name="Healthcare Select Sector",
        tier=UniverseTier.TIER_2_ROTATION,
        liquidity_score=91,
        weight=0.05,
        sector="Healthcare",
        correlation_group="Healthcare",
    ),
    "XLE": SecurityConfig(
        symbol="XLE",
        name="Energy Select Sector",
        tier=UniverseTier.TIER_2_ROTATION,
        liquidity_score=90,
        weight=0.04,
        sector="Energy",
        correlation_group="Energy",
    ),
    "XLY": SecurityConfig(
        symbol="XLY",
        name="Consumer Discretionary",
        tier=UniverseTier.TIER_2_ROTATION,
        liquidity_score=89,
        weight=0.03,
        sector="Consumer",
        correlation_group="Consumer",
    ),
    "XLI": SecurityConfig(
        symbol="XLI",
        name="Industrials Select Sector",
        tier=UniverseTier.TIER_2_ROTATION,
        liquidity_score=88,
        weight=0.03,
        sector="Industrials",
        correlation_group="Industrials",
    ),
    "EEM": SecurityConfig(
        symbol="EEM",
        name="Emerging Markets ETF",
        tier=UniverseTier.TIER_2_ROTATION,
        liquidity_score=88,
        weight=0.03,
        sector="International",
        correlation_group="EM",
    ),
    "EWZ": SecurityConfig(
        symbol="EWZ",
        name="Brazil ETF",
        tier=UniverseTier.TIER_2_ROTATION,
        liquidity_score=85,
        weight=0.02,
        sector="International",
        correlation_group="EM",
    ),
}


# ============================================================================
# TIER 3: OPPORTUNISTIC - Only when IV conditions exceptional
# ============================================================================
TIER_3_OPPORTUNISTIC: Dict[str, SecurityConfig] = {
    "SMH": SecurityConfig(
        symbol="SMH",
        name="Semiconductor ETF",
        tier=UniverseTier.TIER_3_OPPORTUNISTIC,
        liquidity_score=88,
        weight=0.03,
        sector="Technology",
        correlation_group="Semis",
    ),
    "XBI": SecurityConfig(
        symbol="XBI",
        name="Biotech ETF",
        tier=UniverseTier.TIER_3_OPPORTUNISTIC,
        liquidity_score=86,
        weight=0.02,
        sector="Healthcare",
        correlation_group="Biotech",
    ),
    "GDX": SecurityConfig(
        symbol="GDX",
        name="Gold Miners ETF",
        tier=UniverseTier.TIER_3_OPPORTUNISTIC,
        liquidity_score=85,
        weight=0.02,
        sector="Materials",
        correlation_group="GoldMiners",
    ),
    "XOP": SecurityConfig(
        symbol="XOP",
        name="Oil & Gas Exploration ETF",
        tier=UniverseTier.TIER_3_OPPORTUNISTIC,
        liquidity_score=84,
        weight=0.02,
        sector="Energy",
        correlation_group="OilGas",
    ),
    "XLU": SecurityConfig(
        symbol="XLU",
        name="Utilities Select Sector",
        tier=UniverseTier.TIER_3_OPPORTUNISTIC,
        liquidity_score=87,
        weight=0.02,
        sector="Utilities",
        correlation_group="Utilities",
    ),
    "FXI": SecurityConfig(
        symbol="FXI",
        name="China Large Cap ETF",
        tier=UniverseTier.TIER_3_OPPORTUNISTIC,
        liquidity_score=84,
        weight=0.02,
        sector="International",
        correlation_group="China",
    ),
}


# ============================================================================
# TIER 4: MEGA CAL EQUITIES - Primarily for PMCC Strategy
# ============================================================================
TIER_4_MEGA_CAP_EQUITIES: Dict[str, SecurityConfig] = {
    "AAPL": SecurityConfig(
        symbol="AAPL",
        name="Apple Inc.",
        tier=UniverseTier.TIER_4_EQUITIES,
        liquidity_score=99,
        weight=0.05,
        sector="Technology",
        correlation_group="MegaCapTech",
        has_earnings_risk=True,
    ),
    "MSFT": SecurityConfig(
        symbol="MSFT",
        name="Microsoft Corporation",
        tier=UniverseTier.TIER_4_EQUITIES,
        liquidity_score=99,
        weight=0.05,
        sector="Technology",
        correlation_group="MegaCapTech",
        has_earnings_risk=True,
    ),
    "NVDA": SecurityConfig(
        symbol="NVDA",
        name="NVIDIA Corporation",
        tier=UniverseTier.TIER_4_EQUITIES,
        liquidity_score=98,
        weight=0.04,
        sector="Technology",
        correlation_group="Semis",
        has_earnings_risk=True,
    ),
    "AMZN": SecurityConfig(
        symbol="AMZN",
        name="Amazon.com Inc.",
        tier=UniverseTier.TIER_4_EQUITIES,
        liquidity_score=98,
        weight=0.04,
        sector="Consumer Discretionary",
        correlation_group="eCommerce",
        has_earnings_risk=True,
    ),
    "META": SecurityConfig(
        symbol="META",
        name="Meta Platforms Inc.",
        tier=UniverseTier.TIER_4_EQUITIES,
        liquidity_score=95,
        weight=0.03,
        sector="Communication Services",
        correlation_group="SocialMedia",
        has_earnings_risk=True,
    ),
    "GOOGL": SecurityConfig(
        symbol="GOOGL",
        name="Alphabet Inc.",
        tier=UniverseTier.TIER_4_EQUITIES,
        liquidity_score=95,
        weight=0.03,
        sector="Communication Services",
        correlation_group="Search",
        has_earnings_risk=True,
    ),
}


class ETFUniverse:
    """
    Manages the 3-tier ETF universe for diagonal spread trading.
    
    Allocation Guidelines:
    - Tier 1: 60-70% of capital
    - Tier 2: 20-25% of capital
    - Tier 3: 5-15% of capital (only when conditions favorable)
    """
    
    # Maximum correlation allowed between positions
    MAX_CORRELATION = 0.70
    
    def __init__(self):
        self.tier1 = TIER_1_CORE_ETFS.copy()
        self.tier2 = TIER_2_SECTOR_ETFS.copy()
        self.tier3 = TIER_3_OPPORTUNISTIC.copy()
        self.tier4 = TIER_4_MEGA_CAP_EQUITIES.copy()
        self._active_correlation_groups: Set[str] = set()
    
    def get_all_securities(self) -> Dict[str, SecurityConfig]:
        """Get complete universe of securities."""
        combined = {}
        combined.update(self.tier1)
        combined.update(self.tier2)
        combined.update(self.tier3)
        combined.update(self.tier4)
        return combined
    
    def get_tier_securities(self, tier: UniverseTier) -> Dict[str, SecurityConfig]:
        """Get securities for a specific tier."""
        if tier == UniverseTier.TIER_1_CORE:
            return self.tier1
        elif tier == UniverseTier.TIER_2_ROTATION:
            return self.tier2
        elif tier == UniverseTier.TIER_3_OPPORTUNISTIC:
            return self.tier3
        else:
            return self.tier4
    
    def get_symbols_by_tier(self, tier: UniverseTier) -> List[str]:
        """Get list of symbols for a tier."""
        return list(self.get_tier_securities(tier).keys())
    
    def get_all_symbols(self) -> List[str]:
        """Get all symbols in universe."""
        return list(self.get_all_securities().keys())
    
    def get_security_config(self, symbol: str) -> Optional[SecurityConfig]:
        """Get configuration for a single security."""
        all_securities = self.get_all_securities()
        return all_securities.get(symbol.upper())
    
    def check_correlation_conflict(self, symbol: str) -> bool:
        """
        Check if adding a symbol would create correlation conflict.
        
        Args:
            symbol: Symbol to check
            
        Returns:
            True if there's a conflict (shouldn't add), False if OK to add
        """
        config = self.get_security_config(symbol)
        if not config or not config.correlation_group:
            return False
        return config.correlation_group in self._active_correlation_groups
    
    def add_to_active_positions(self, symbol: str) -> None:
        """Mark a symbol's correlation group as active."""
        config = self.get_security_config(symbol)
        if config and config.correlation_group:
            self._active_correlation_groups.add(config.correlation_group)
    
    def remove_from_active_positions(self, symbol: str) -> None:
        """Remove a symbol's correlation group from active set."""
        config = self.get_security_config(symbol)
        if config and config.correlation_group:
            self._active_correlation_groups.discard(config.correlation_group)
    
    def reset_active_positions(self) -> None:
        """Clear all active correlation groups."""
        self._active_correlation_groups.clear()
    
    def get_prioritized_scan_list(
        self,
        include_tier2: bool = True,
        include_tier3: bool = False,
        include_tier4: bool = False
    ) -> List[str]:
        """
        Get prioritized list of symbols to scan, ordered by liquidity score.
        
        Args:
            include_tier2: Include Tier 2 securities
            include_tier3: Include Tier 3 securities (only for exceptional IV)
            include_tier4: Include Tier 4 equities (e.g. for PMCC)
            
        Returns:
            List of symbols sorted by priority (liquidity score)
        """
        securities = []
        securities.extend(self.tier1.values())
        
        if include_tier2:
            securities.extend(self.tier2.values())
        
        if include_tier3:
            securities.extend(self.tier3.values())
            
        if include_tier4:
            securities.extend(self.tier4.values())
        
        # Sort by liquidity score (highest first)
        securities.sort(key=lambda x: x.liquidity_score, reverse=True)
        
        return [s.symbol for s in securities]
    
    def get_target_allocation(self) -> Dict[str, float]:
        """Get target allocation weights for all securities."""
        return {s.symbol: s.weight for s in self.get_all_securities().values()}
    
    def get_tier_allocation_range(self, tier: UniverseTier) -> tuple:
        """Get min/max allocation range for a tier."""
        if tier == UniverseTier.TIER_1_CORE:
            return (0.60, 0.70)
        elif tier == UniverseTier.TIER_2_ROTATION:
            return (0.20, 0.25)
        elif tier == UniverseTier.TIER_3_OPPORTUNISTIC:
            return (0.05, 0.15)
        else:
            return (0.00, 0.20)  # PMCC Equities have higher risk / custom allocation


# Singleton instance
_universe_instance: Optional[ETFUniverse] = None


def get_etf_universe() -> ETFUniverse:
    """Get the singleton ETF universe instance."""
    global _universe_instance
    if _universe_instance is None:
        _universe_instance = ETFUniverse()
    return _universe_instance
