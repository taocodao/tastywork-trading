"""
Symbol Selector for Theta Strategy
====================================

Implements the 5-factor symbol selection system:
1. IV Percentile (30 pts) - High IV = better premiums
2. Liquidity (25 pts) - Volume + tight spreads
3. Premium Availability (20 pts) - 30-delta puts available
4. Technical Trend (15 pts) - Uptrends preferred
5. Sector Diversification (10 pts) - Avoid concentration

Selects top 12 symbols daily from 50+ liquid candidates.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class SymbolScore:
    """Symbol scoring result."""
    symbol: str
    total_score: int
    iv_score: int
    liquidity_score: int
    premium_score: int
    trend_score: int
    sector_score: int
    iv_percentile: float
    volume: int
    price: float
    sector: str


class SymbolSelector:
    """
    Daily symbol selection using intelligent multi-factor scoring.
    
    Usage:
        selector = SymbolSelector()
        watchlist = selector.select_daily_watchlist()
        # Returns: ["QQQ", "SPY", "IWM", "TLT", ...]
    """
    
    # Universe of 50+ liquid symbols
    UNIVERSE = [
        # Large Cap ETFs
        "SPY", "QQQ", "IWM", "DIA",
        # Bond/Fixed Income
        "TLT", "IEF", "LQD", "HYG", "SHY", "AGG",
        # Commodities
        "GLD", "SLV", "USO", "UNG", "DBC", "PDBC",
        # Sector ETFs
        "XLV", "XLK", "XLF", "XLI", "XLY", "XLE", "XLRE", "XLU", "XLP", "XLB",
        # Volatility
        "VXX", "UVXY",
        # International
        "EEM", "FXI", "EWJ", "EWG", "EWZ", "EWU",
        # Growth
        "ARKK", "QQQM", "VUG", "IWF",
        # Value/Dividend
        "VTV", "VYM", "SCHV", "DVY",
        # Small/Mid Cap
        "MDY", "IJR", "VB",
        # Real Estate
        "VNQ", "IYR",
        # Additional Liquid ETFs
        "RSP", "EFA", "VEA", "VWO", "BND",
    ]
    
    # Sector mapping
    SECTORS = {
        "SPY": "BROAD", "QQQ": "TECH", "IWM": "SMALL_CAP", "DIA": "BROAD",
        "TLT": "BONDS", "IEF": "BONDS", "LQD": "BONDS", "HYG": "BONDS",
        "SHY": "BONDS", "AGG": "BONDS", "BND": "BONDS",
        "GLD": "COMMODITIES", "SLV": "COMMODITIES", "USO": "COMMODITIES",
        "UNG": "COMMODITIES", "DBC": "COMMODITIES", "PDBC": "COMMODITIES",
        "XLV": "HEALTHCARE", "XLK": "TECH", "XLF": "FINANCE", "XLI": "INDUSTRIAL",
        "XLY": "CONSUMER", "XLE": "ENERGY", "XLRE": "REAL_ESTATE", "XLU": "UTILITIES",
        "XLP": "CONSUMER", "XLB": "MATERIALS",
        "VXX": "VOLATILITY", "UVXY": "VOLATILITY",
        "EEM": "INTERNATIONAL", "FXI": "INTERNATIONAL", "EWJ": "INTERNATIONAL",
        "EWG": "INTERNATIONAL", "EWZ": "INTERNATIONAL", "EWU": "INTERNATIONAL",
        "ARKK": "GROWTH", "QQQM": "TECH", "VUG": "GROWTH", "IWF": "GROWTH",
        "VTV": "VALUE", "VYM": "VALUE", "SCHV": "VALUE", "DVY": "VALUE",
        "MDY": "MID_CAP", "IJR": "SMALL_CAP", "VB": "SMALL_CAP",
        "VNQ": "REAL_ESTATE", "IYR": "REAL_ESTATE",
        "RSP": "BROAD", "EFA": "INTERNATIONAL", "VEA": "INTERNATIONAL", "VWO": "INTERNATIONAL",
    }
    
    def __init__(
        self,
        min_iv_percentile: int = 20,
        min_volume: int = 100_000,
        max_bid_ask_spread_pct: float = 0.10,
        exclude_pre_earnings_days: int = 21,
        max_sector_pct: float = 25.0,
        select_top_n: int = 12
    ):
        """
        Initialize symbol selector.
        
        Args:
            min_iv_percentile: Minimum IV percentile to consider (default: 20)
            min_volume: Minimum daily volume (default: 100K)
            max_bid_ask_spread_pct: Maximum bid-ask spread % (default: 10%)
            exclude_pre_earnings_days: Skip if earnings within N days (default: 21)
            max_sector_pct: Maximum % per sector (default: 25%)
            select_top_n: Number of symbols to select (default: 12)
        """
        self.min_iv_percentile = min_iv_percentile
        self.min_volume = min_volume
        self.max_bid_ask_spread_pct = max_bid_ask_spread_pct
        self.exclude_pre_earnings_days = exclude_pre_earnings_days
        self.max_sector_pct = max_sector_pct
        self.select_top_n = select_top_n
        
        # Cache for current portfolio sector exposure
        self._current_sector_exposure: Dict[str, int] = {}
    
    def select_daily_watchlist(
        self,
        candidates: Optional[List[str]] = None,
        current_positions: Optional[List[str]] = None
    ) -> List[str]:
        """
        Select top N symbols for today's trading.
        
        Args:
            candidates: List of symbols to score (default: UNIVERSE)
            current_positions: Currently held symbols for sector calculation
            
        Returns:
            List of top N symbols, sorted by score (highest first)
        """
        if candidates is None:
            candidates = self.UNIVERSE
        
        # Calculate sector exposure from current positions
        if current_positions:
            self._calculate_sector_exposure(current_positions)
        
        logger.info(f"Scoring {len(candidates)} candidate symbols...")
        
        scores: List[SymbolScore] = []
        
        for symbol in candidates:
            try:
                # Apply pre-filters
                if not self._apply_filters(symbol):
                    continue
                
                # Get market data
                market_data = self._get_market_data(symbol)
                if not market_data:
                    continue
                
                # Score the symbol
                score = self.score_symbol(symbol, market_data)
                if score:
                    scores.append(score)
                    
            except Exception as e:
                logger.warning(f"Error scoring {symbol}: {e}")
                continue
        
        # Sort by total score (highest first)
        scores.sort(key=lambda x: x.total_score, reverse=True)
        
        # Apply sector balance filter
        balanced_scores = self._apply_sector_balance(scores)
        
        # Select top N
        selected = balanced_scores[:self.select_top_n]
        watchlist = [s.symbol for s in selected]
        
        logger.info(f"Selected {len(watchlist)} symbols from {len(scores)} qualified")
        self._log_selection(selected)
        
        return watchlist
    
    def score_symbol(self, symbol: str, market_data: Dict) -> Optional[SymbolScore]:
        """
        Score a symbol across 5 factors (0-100 scale).
        
        Args:
            symbol: Stock symbol
            market_data: Dict with price, volume, iv_percentile, etc.
            
        Returns:
            SymbolScore object or None if invalid
        """
        score = 0
        
        # Factor 1: IV Percentile (30 points max)
        iv_pct = market_data.get("iv_percentile", 0)
        if iv_pct >= 70:
            iv_score = 30
        elif iv_pct >= 50:
            iv_score = 25
        elif iv_pct >= 30:
            iv_score = 20
        elif iv_pct >= 20:
            iv_score = 10
        else:
            return None  # Skip low IV
        
        # Factor 2: Liquidity (25 points max)
        volume = market_data.get("volume", 0)
        spread_pct = market_data.get("bid_ask_spread_pct", 100)
        
        if volume >= 5_000_000 and spread_pct < 0.05:
            liquidity_score = 25
        elif volume >= 2_000_000 and spread_pct < 0.08:
            liquidity_score = 20
        elif volume >= 1_000_000 and spread_pct < 0.10:
            liquidity_score = 15
        elif volume >= 500_000 and spread_pct < 0.15:
            liquidity_score = 10
        else:
            liquidity_score = 5
        
        # Factor 3: Premium Availability (20 points max)
        # Count of 30-delta puts available (simulated for now)
        puts_available = market_data.get("puts_30delta_count", 1)
        if puts_available >= 3:
            premium_score = 20
        elif puts_available == 2:
            premium_score = 15
        elif puts_available == 1:
            premium_score = 10
        else:
            premium_score = 0
        
        # Factor 4: Technical Trend (15 points max)
        trend = market_data.get("trend", "SIDEWAYS")
        price_vs_sma = market_data.get("price_vs_sma200", 1.0)
        rsi = market_data.get("rsi", 50)
        
        if trend == "UPTREND" and price_vs_sma > 1.0 and rsi < 70:
            trend_score = 15
        elif trend == "UPTREND" and price_vs_sma > 1.0:
            trend_score = 12
        elif trend == "SIDEWAYS" and price_vs_sma > 0.95:
            trend_score = 8
        else:
            trend_score = 0
        
        # Factor 5: Sector Diversification (10 points max)
        sector = self.SECTORS.get(symbol, "OTHER")
        current_exposure = self._current_sector_exposure.get(sector, 0)
        
        if current_exposure < 15:
            sector_score = 10
        elif current_exposure < 20:
            sector_score = 5
        elif current_exposure < 25:
            sector_score = 2
        else:
            sector_score = 0
        
        total_score = iv_score + liquidity_score + premium_score + trend_score + sector_score
        
        return SymbolScore(
            symbol=symbol,
            total_score=total_score,
            iv_score=iv_score,
            liquidity_score=liquidity_score,
            premium_score=premium_score,
            trend_score=trend_score,
            sector_score=sector_score,
            iv_percentile=iv_pct,
            volume=volume,
            price=market_data.get("price", 0),
            sector=sector
        )
    
    def _apply_filters(self, symbol: str) -> bool:
        """Apply pre-filters before scoring."""
        # Check earnings proximity (placeholder - would use real earnings API)
        if self._is_pre_earnings(symbol):
            logger.debug(f"{symbol}: Skipped - earnings within {self.exclude_pre_earnings_days} days")
            return False
        
        return True
    
    def _is_pre_earnings(self, symbol: str) -> bool:
        """Check if symbol has earnings within exclusion window."""
        # Placeholder - in production, use Perplexity API or yfinance
        # For now, assume no earnings conflict
        return False
    
    def _get_market_data(self, symbol: str) -> Optional[Dict]:
        """
        Fetch market data for symbol.
        
        Returns dict with:
        - price, volume, iv_percentile
        - bid_ask_spread_pct
        - trend, price_vs_sma200, rsi
        - puts_30delta_count
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            hist = ticker.history(period="1mo")
            
            if hist.empty:
                return None
            
            current_price = hist['Close'].iloc[-1]
            volume = int(hist['Volume'].iloc[-1])
            
            # Estimate IV percentile (placeholder - would use real IV data)
            iv_percentile = 30.0  # Default moderate IV
            
            # Calculate spread (using yfinance bid/ask if available)
            bid = info.get('bid', current_price * 0.995)
            ask = info.get('ask', current_price * 1.005)
            spread_pct = (ask - bid) / current_price if current_price > 0 else 1.0
            
            # Calculate SMA200
            if len(hist) >= 200:
                sma200 = hist['Close'].rolling(200).mean().iloc[-1]
                price_vs_sma = current_price / sma200 if sma200 > 0 else 1.0
            else:
                price_vs_sma = 1.0
            
            # Determine trend (simple: price vs SMA)
            if price_vs_sma > 1.05:
                trend = "UPTREND"
            elif price_vs_sma < 0.95:
                trend = "DOWNTREND"
            else:
                trend = "SIDEWAYS"
            
            # Calculate RSI (simplified)
            delta = hist['Close'].diff()
            gains = delta.where(delta > 0, 0).rolling(14).mean()
            losses = -delta.where(delta < 0, 0).rolling(14).mean()
            rs = gains / losses if losses.iloc[-1] > 0 else 100
            rsi = 100 - (100 / (1 + rs.iloc[-1])) if not rs.isna().iloc[-1] else 50
            
            return {
                "price": current_price,
                "volume": volume,
                "iv_percentile": iv_percentile,
                "bid_ask_spread_pct": spread_pct,
                "trend": trend,
                "price_vs_sma200": price_vs_sma,
                "rsi": rsi,
                "puts_30delta_count": 2,  # Placeholder - would query options chain
            }
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None
    
    def _calculate_sector_exposure(self, current_positions: List[str]):
        """Calculate current sector exposure from open positions."""
        self._current_sector_exposure = {}
        total = len(current_positions)
        
        if total == 0:
            return
        
        for symbol in current_positions:
            sector = self.SECTORS.get(symbol, "OTHER")
            self._current_sector_exposure[sector] = self._current_sector_exposure.get(sector, 0) + 1
        
        # Convert to percentages
        for sector in self._current_sector_exposure:
            self._current_sector_exposure[sector] = (self._current_sector_exposure[sector] / total) * 100
    
    def _apply_sector_balance(self, scores: List[SymbolScore]) -> List[SymbolScore]:
        """
        Filter scores to maintain sector balance.
        Ensures no sector exceeds max_sector_pct of watchlist.
        """
        balanced = []
        sector_counts: Dict[str, int] = {}
        
        for score in scores:
            sector = score.sector
            current_count = sector_counts.get(sector, 0)
            sector_pct = (current_count / self.select_top_n) * 100
            
            if sector_pct < self.max_sector_pct:
                balanced.append(score)
                sector_counts[sector] = current_count + 1
            else:
                logger.debug(f"{score.symbol}: Skipped - sector {sector} at {sector_pct:.1f}% (max {self.max_sector_pct}%)")
        
        return balanced
    
    def _log_selection(self, selected: List[SymbolScore]):
        """Log selected watchlist with scores."""
        logger.info("\n" + "="*80)
        logger.info(f"DAILY WATCHLIST - {datetime.now().strftime('%Y-%m-%d')}")
        logger.info("="*80)
        logger.info(f"{'Rank':<5} {'Symbol':<8} {'Score':<6} {'IV%':<6} {'Volume':<12} {'Sector':<15}")
        logger.info("-"*80)
        
        for rank, score in enumerate(selected, 1):
            logger.info(
                f"{rank:<5} {score.symbol:<8} {score.total_score:<6} "
                f"{score.iv_percentile:<6.1f} {score.volume:<12,} {score.sector:<15}"
            )
        
        logger.info("="*80 + "\n")
