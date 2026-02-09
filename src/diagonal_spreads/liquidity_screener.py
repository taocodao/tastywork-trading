"""
Liquidity Screener: Multi-stage filter for diagonal spread eligibility

Based on SUPPLEMENT doc design:
- Stage 1: Basic market filters (market cap, volume)
- Stage 2: Options-specific filters (bid-ask, open interest)
- Stage 3: IV activity filters (minimum IV, volume)

Output: 25-30 approved securities sorted by liquidity score
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


@dataclass
class LiquidityResult:
    """Result of liquidity screening for a security"""
    symbol: str
    passed: bool
    liquidity_score: float  # 0-100
    stage_passed: int  # 0-3 (0 = failed stage 1)
    failure_reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class LiquidityScreener:
    """
    Screens securities for diagonal spread trading eligibility.
    
    Input: Market data for securities
    Output: 25-30 approved underlyings sorted by liquidity score
    """
    
    # Asset-class-specific IV floors (prevents excluding TLT/GLD during calm periods)
    DEFAULT_IV_FLOORS = {
        "equity": 0.15,     # SPY, QQQ, sector ETFs
        "bond": 0.08,       # TLT, HYG
        "commodity": 0.10,  # GLD, SLV, GDX
        "default": 0.15     # Fallback
    }
    
    # Symbol to asset class mapping
    ASSET_CLASS_MAP = {
        "SPY": "equity", "QQQ": "equity", "IWM": "equity",
        "XLK": "equity", "XLF": "equity", "XLV": "equity",
        "XLE": "equity", "XLY": "equity", "XLI": "equity",
        "SMH": "equity", "XBI": "equity", "XOP": "equity", "XLU": "equity",
        "EEM": "equity", "EWZ": "equity", "FXI": "equity",
        "TLT": "bond", "HYG": "bond", "LQD": "bond",
        "GLD": "commodity", "SLV": "commodity", "GDX": "commodity",
    }
    
    def __init__(
        self,
        # Stage 1: Basic market filters
        min_market_cap: float = 1_000_000_000,  # $1B minimum
        min_daily_volume: int = 500_000,  # 500K shares
        
        # Stage 2: Options-specific filters
        min_open_interest: int = 500,  # per strike
        min_options_volume: int = 1_000,  # daily
        max_bid_ask_spread_dollars: float = 0.10,
        max_bid_ask_spread_percent: float = 0.05,  # 5%
        min_bid_ask_size: int = 10,  # lots
        
        # Stage 3: IV activity filters (can be overridden per asset class)
        min_implied_volatility: float = 0.15,  # Default 15% minimum IV
        asset_class_iv_floors: Optional[Dict[str, float]] = None,
        
        # Output limit
        max_output_count: int = 30
    ):
        # Stage 1 parameters
        self.min_market_cap = min_market_cap
        self.min_daily_volume = min_daily_volume
        
        # Stage 2 parameters
        self.min_open_interest = min_open_interest
        self.min_options_volume = min_options_volume
        self.max_bid_ask_spread_dollars = max_bid_ask_spread_dollars
        self.max_bid_ask_spread_percent = max_bid_ask_spread_percent
        self.min_bid_ask_size = min_bid_ask_size
        
        # Stage 3 parameters
        self.min_implied_volatility = min_implied_volatility
        self.asset_class_iv_floors = asset_class_iv_floors or self.DEFAULT_IV_FLOORS.copy()
        
        # Output limit
        self.max_output_count = max_output_count
    
    def screen_single(self, security_data: Dict[str, Any]) -> LiquidityResult:
        """
        Screen a single security through all stages.
        
        Args:
            security_data: Dictionary containing:
                - symbol: str
                - market_cap: float
                - daily_volume: int
                - price: float
                - options: Dict with:
                    - open_interest: int
                    - volume: int
                    - bid_ask_spread: float
                    - bid_ask_size: int
                    - iv: float
        
        Returns:
            LiquidityResult with pass/fail and score
        """
        symbol = security_data.get("symbol", "UNKNOWN")
        details = {}
        
        # Stage 1: Basic market filters
        stage1_result = self._pass_stage1(security_data)
        details["stage1"] = stage1_result
        if not stage1_result["passed"]:
            return LiquidityResult(
                symbol=symbol,
                passed=False,
                liquidity_score=0.0,
                stage_passed=0,
                failure_reason=f"Stage 1 failed: {stage1_result['failures']}",
                details=details
            )
        
        # Stage 2: Options-specific filters
        stage2_result = self._pass_stage2(security_data)
        details["stage2"] = stage2_result
        if not stage2_result["passed"]:
            return LiquidityResult(
                symbol=symbol,
                passed=False,
                liquidity_score=0.0,
                stage_passed=1,
                failure_reason=f"Stage 2 failed: {stage2_result['failures']}",
                details=details
            )
        
        # Stage 3: IV activity filters
        stage3_result = self._pass_stage3(security_data)
        details["stage3"] = stage3_result
        if not stage3_result["passed"]:
            return LiquidityResult(
                symbol=symbol,
                passed=False,
                liquidity_score=0.0,
                stage_passed=2,
                failure_reason=f"Stage 3 failed: {stage3_result['failures']}",
                details=details
            )
        
        # Calculate liquidity score
        score = self._calculate_liquidity_score(security_data)
        
        return LiquidityResult(
            symbol=symbol,
            passed=True,
            liquidity_score=score,
            stage_passed=3,
            failure_reason=None,
            details=details
        )
    
    def screen_universe(self, securities_data: List[Dict[str, Any]]) -> List[LiquidityResult]:
        """
        Screen all securities and return approved list.
        
        Input: 5,000+ securities from market data
        Output: Up to max_output_count approved underlyings
        
        Args:
            securities_data: List of security data dictionaries
            
        Returns:
            List of LiquidityResult for passed securities, sorted by score
        """
        passed_results = []
        
        for security in securities_data:
            result = self.screen_single(security)
            if result.passed:
                passed_results.append(result)
        
        # Sort by liquidity score descending
        passed_results.sort(key=lambda x: x.liquidity_score, reverse=True)
        
        # Return top N most liquid
        return passed_results[:self.max_output_count]
    
    def _pass_stage1(self, security: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 1: Basic market filters"""
        checks = {
            "market_cap": security.get("market_cap", 0) >= self.min_market_cap,
            "daily_volume": security.get("daily_volume", 0) >= self.min_daily_volume,
        }
        
        failures = [k for k, v in checks.items() if not v]
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "failures": failures
        }
    
    def _pass_stage2(self, security: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 2: Options-specific filters"""
        options_data = security.get("options", {})
        price = security.get("price", 1)
        bid_ask_spread = options_data.get("bid_ask_spread", float('inf'))
        
        # Calculate spread as percentage of underlying price
        spread_pct = bid_ask_spread / price if price > 0 else float('inf')
        
        checks = {
            "open_interest": options_data.get("open_interest", 0) >= self.min_open_interest,
            "options_volume": options_data.get("volume", 0) >= self.min_options_volume,
            "bid_ask_spread_dollars": bid_ask_spread <= self.max_bid_ask_spread_dollars,
            "bid_ask_spread_percent": spread_pct <= self.max_bid_ask_spread_percent,
            "bid_ask_size": options_data.get("bid_ask_size", 0) >= self.min_bid_ask_size,
        }
        
        failures = [k for k, v in checks.items() if not v]
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "failures": failures
        }
    
    def _pass_stage3(self, security: Dict[str, Any]) -> Dict[str, Any]:
        """Stage 3: IV activity filters with asset-class-specific floors"""
        options_data = security.get("options", {})
        symbol = security.get("symbol", "").upper()
        
        # Get asset-class-specific IV floor
        asset_class = self.ASSET_CLASS_MAP.get(symbol, "default")
        iv_floor = self.asset_class_iv_floors.get(asset_class, self.min_implied_volatility)
        
        current_iv = options_data.get("iv", 0)
        
        checks = {
            "implied_volatility": current_iv >= iv_floor,
        }
        
        failures = [k for k, v in checks.items() if not v]
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "failures": failures,
            "asset_class": asset_class,
            "iv_floor_used": iv_floor,
            "current_iv": current_iv
        }
    
    def _calculate_liquidity_score(self, security: Dict[str, Any]) -> float:
        """
        Calculate a 0-100 liquidity score based on multiple factors.
        
        Factors weighted:
        - Daily volume: 30%
        - Options volume: 25%
        - Open interest: 20%
        - Bid-ask spread (inverse): 15%
        - Market cap: 10%
        """
        options_data = security.get("options", {})
        
        # Normalize factors to 0-1 scale with reasonable caps
        volume_score = min(security.get("daily_volume", 0) / 50_000_000, 1.0)  # Cap at 50M
        options_vol_score = min(options_data.get("volume", 0) / 500_000, 1.0)  # Cap at 500K
        oi_score = min(options_data.get("open_interest", 0) / 50_000, 1.0)  # Cap at 50K
        
        # Bid-ask: lower is better, invert the score
        bid_ask = options_data.get("bid_ask_spread", 0.10)
        bid_ask_score = max(0, 1 - (bid_ask / 0.10))  # 0 at $0.10+, 1 at $0
        
        market_cap_score = min(security.get("market_cap", 0) / 1_000_000_000_000, 1.0)  # Cap at $1T
        
        # Weighted average
        score = (
            volume_score * 0.30 +
            options_vol_score * 0.25 +
            oi_score * 0.20 +
            bid_ask_score * 0.15 +
            market_cap_score * 0.10
        ) * 100
        
        return round(score, 2)


class UniverseScanner:
    """
    Scans the ETF universe and filters by liquidity.
    
    Integrates ETFUniverse with LiquidityScreener for real-time scanning.
    """
    
    def __init__(self, data_provider=None, screener: Optional[LiquidityScreener] = None):
        """
        Args:
            data_provider: Data provider (IB, etc.) for market data
            screener: Optional custom LiquidityScreener instance
        """
        self.data_provider = data_provider
        self.screener = screener or LiquidityScreener()
        
        # Import here to avoid circular imports
        from .etf_universe import get_etf_universe
        self.universe = get_etf_universe()
    
    def fetch_security_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch market data for a symbol.
        
        Returns None if data unavailable.
        """
        if self.data_provider is None:
            logger.warning(f"No data provider available for {symbol}")
            return None
        
        try:
            # Get underlying data
            market_data = self.data_provider.get_market_data(symbol)
            if not market_data:
                return None
            
            # Get options data (ATM strike)
            options_data = self.data_provider.get_options_data(symbol)
            
            return {
                "symbol": symbol,
                "market_cap": market_data.get("market_cap", 0),
                "daily_volume": market_data.get("volume", 0),
                "price": market_data.get("last", 0),
                "options": {
                    "open_interest": options_data.get("open_interest", 0),
                    "volume": options_data.get("volume", 0),
                    "bid_ask_spread": options_data.get("bid_ask_spread", 0.10),
                    "bid_ask_size": options_data.get("bid_ask_size", 0),
                    "iv": options_data.get("iv", 0),
                }
            }
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None
    
    def scan_universe(
        self,
        include_tier2: bool = True,
        include_tier3: bool = False
    ) -> List[LiquidityResult]:
        """
        Scan the ETF universe and return filtered results.
        
        Args:
            include_tier2: Include Tier 2 securities
            include_tier3: Include Tier 3 securities
            
        Returns:
            List of LiquidityResult for passed securities
        """
        symbols = self.universe.get_prioritized_scan_list(
            include_tier2=include_tier2,
            include_tier3=include_tier3
        )
        
        securities_data = []
        for symbol in symbols:
            data = self.fetch_security_data(symbol)
            if data:
                securities_data.append(data)
        
        return self.screener.screen_universe(securities_data)
    
    def get_tradeable_symbols(
        self,
        include_tier2: bool = True,
        include_tier3: bool = False,
        min_liquidity_score: float = 50.0
    ) -> List[str]:
        """
        Get list of tradeable symbols meeting liquidity requirements.
        
        Args:
            include_tier2: Include Tier 2 securities
            include_tier3: Include Tier 3 securities
            min_liquidity_score: Minimum score to include
            
        Returns:
            List of symbol strings
        """
        results = self.scan_universe(
            include_tier2=include_tier2,
            include_tier3=include_tier3
        )
        
        return [
            r.symbol for r in results
            if r.liquidity_score >= min_liquidity_score
        ]
