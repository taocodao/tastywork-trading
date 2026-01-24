"""
AI-Powered Earnings Scanner.
Uses Perplexity to discover upcoming earnings, IB Gateway for market data,
and ML model to generate ranked trade signals.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class EarningsOpportunity:
    """A stock with upcoming earnings that passed screening."""
    symbol: str
    company_name: str
    earnings_date: str
    days_to_earnings: int
    
    # Market data (from IB)
    current_price: float = 0.0
    current_iv: float = 0.0
    iv_percentile: float = 0.0
    avg_volume: float = 0.0
    
    # Earnings context (from Perplexity)
    expected_move_pct: float = 0.0
    historical_move_pct: float = 0.0
    crush_probability: float = 0.0
    
    # Analyst ratings (from Perplexity)
    analyst_consensus: str = ""  # BUY, HOLD, SELL, STRONG_BUY
    analyst_price_target: float = 0.0
    recent_analyst_changes: str = ""  # Summary of recent upgrades/downgrades
    
    # Significant news (from Perplexity)
    significant_news: str = ""  # Summary of price-moving news
    news_sentiment: str = ""  # bullish, bearish, neutral
    
    # ML prediction
    predicted_class: str = ""  # SEVERE, NORMAL, NO_CRUSH, EXPANSION
    confidence: float = 0.0
    predicted_crush_pct: float = 0.0
    
    # Trading recommendation
    decision: str = ""  # APPROVE, REJECT, REDUCE_SIZE, ALTERNATIVE
    strategy: str = ""  # "Calendar Spread", "Reverse Calendar", "Skip"
    position_multiplier: float = 1.0
    risk_factor: float = 1.0
    reason: str = ""
    
    # Composite score for ranking (higher = better opportunity)
    score: float = 0.0
    
    def calculate_score(self):
        """Calculate composite score for ranking opportunities."""
        score = 0.0
        
        # Days to earnings (sweet spot: 3-7 days)
        if 3 <= self.days_to_earnings <= 7:
            score += 30
        elif 1 <= self.days_to_earnings <= 2:
            score += 15  # Risky but high potential
        elif 8 <= self.days_to_earnings <= 14:
            score += 20
        
        # IV percentile (higher = more premium to capture)
        if self.iv_percentile >= 70:
            score += 25
        elif self.iv_percentile >= 50:
            score += 15
        
        # Crush probability (higher = better for calendars)
        score += self.crush_probability * 20
        
        # ML confidence
        score += self.confidence * 0.15
        
        # Decision bonus
        if self.decision == "APPROVE":
            score += 10
        elif self.decision == "REDUCE_SIZE":
            score += 5
        
        self.score = round(score, 1)
        return self.score


class EarningsScanner:
    """
    Scans for earnings opportunities using:
    1. Perplexity AI to discover stocks with upcoming earnings
    2. IB Gateway for real-time IV and liquidity data
    3. ML model for IV crush predictions
    4. Strategy router for trade recommendations
    """
    
    # Liquidity requirements (from Options-Selection-Best-Practices.md)
    MIN_VOLUME = 2_000_000  # 2M daily volume
    MIN_MARKET_CAP = 5_000_000_000  # $5B
    MIN_OPTIONS_VOLUME = 500  # Contracts per day
    MIN_OPEN_INTEREST = 1000  # Contracts
    MAX_BID_ASK_SPREAD_PCT = 10  # 10% max spread
    
    def __init__(self, use_ib: bool = True, use_cache: bool = True):
        """
        Initialize scanner.
        
        Args:
            use_ib: Use IB Gateway for market data (else fallback)
            use_cache: Cache Perplexity responses
        """
        self.use_ib = use_ib
        self.use_cache = use_cache
        
        # Lazy load components
        self._perplexity = None
        self._ib_provider = None
        self._predictor = None
        self._router = None
    
    @property
    def perplexity(self):
        """Lazy load Perplexity client."""
        if self._perplexity is None:
            from src.earnings_intelligence.client import PerplexityClient
            self._perplexity = PerplexityClient()
        return self._perplexity
    
    @property
    def ib_provider(self):
        """Lazy load IB data provider."""
        if self._ib_provider is None and self.use_ib:
            try:
                from ib_data_provider import IBDataProvider
                self._ib_provider = IBDataProvider()
                self._ib_provider.connect()
            except Exception as e:
                logger.warning(f"IB Gateway not available: {e}")
                self._ib_provider = None
        return self._ib_provider
    
    @property
    def predictor(self):
        """Lazy load ML predictor."""
        if self._predictor is None:
            from src.earnings_intelligence.iv_crush_model import IVCrushPredictor
            self._predictor = IVCrushPredictor()
        return self._predictor
    
    @property
    def router(self):
        """Lazy load strategy router."""
        if self._router is None:
            from src.earnings_intelligence.router import EarningsStrategyRouter
            self._router = EarningsStrategyRouter()
        return self._router
    
    def discover_earnings(self, days_ahead: int = 14) -> List[Dict[str, Any]]:
        """
        Ask Perplexity to find stocks with upcoming earnings.
        
        Args:
            days_ahead: Look for earnings in next N days
            
        Returns:
            List of discovered stocks with earnings data
        """
        query = f"""
        List US stocks with earnings announcements in the next {days_ahead} days that have:
        1. Average daily trading volume > 2 million shares
        2. Market cap > $5 billion
        3. Liquid options market
        4. Are NOT penny stocks
        
        For each stock, provide:
        - Symbol
        - Company name
        - Earnings date (exact date)
        - Expected move % (options implied)
        - Historical average move % after earnings
        - Whether pre-market or after-hours
        
        Focus on stocks that are popular for options trading.
        Return as a structured list.
        """
        
        logger.info(f"Discovering stocks with earnings in next {days_ahead} days...")
        
        try:
            response = self.perplexity.query(query)
            stocks = self._parse_discovery_response(response)
            logger.info(f"Discovered {len(stocks)} stocks with upcoming earnings")
            return stocks
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            return []
    
    def _parse_discovery_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse Perplexity response into structured data."""
        stocks = []
        
        # Words to exclude (not stock symbols)
        exclude_words = {
            "AI", "US", "USD", "AM", "PM", "ETF", "IPO", "CEO", "CFO", "COO",
            "SEC", "NYSE", "NASDAQ", "USA", "UK", "EU", "Q1", "Q2", "Q3", "Q4",
            "THE", "FOR", "AND", "NOT", "BUT", "WITH", "FROM", "HAVE", "ARE",
            "THIS", "THAT", "YOUR", "OR", "AN", "AS", "AT", "BE", "BY", "HAS",
            "IT", "OF", "ON", "TO", "WAS", "IF", "IN", "IS", "NO", "SO", "UP",
            "EPS", "PE", "IV", "ATM", "OTM", "ITM", "DTE", "ROI", "YTD", "MTD"
        }
        
        # Known high-liquid stocks that often have earnings (80+ symbols)
        known_symbols = {
            # Tech Giants
            "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA", "AMD", "INTC", "AVGO", "QCOM", "MU", "AMAT", "LRCX",
            # Financials
            "JPM", "BAC", "GS", "WFC", "V", "MA", "AXP", "C", "MS", "BLK", "SCHW", "USB", "PNC", "TFC",
            # Healthcare
            "UNH", "JNJ", "PFE", "ABBV", "LLY", "MRK", "BMY", "AMGN", "GILD", "VRTX", "REGN", "ISRG", "MDT",
            # Consumer
            "WMT", "COST", "HD", "TGT", "LOW", "MCD", "SBUX", "NKE", "KO", "PEP", "PG", "CL", "EL",
            # Enterprise Software
            "CRM", "ADBE", "ORCL", "NOW", "SNOW", "PLTR", "PANW", "NET", "DDOG", "ZS", "CRWD", "OKTA", "WDAY",
            # Media & Entertainment
            "NFLX", "DIS", "ROKU", "PARA", "WBD", "CMCSA", "CHTR", "T", "VZ", "TMUS",
            # Industrials
            "CAT", "DE", "BA", "HON", "RTX", "LMT", "GE", "MMM", "UPS", "FDX", "UNP", "CSX",
            # Energy
            "XOM", "CVX", "COP", "SLB", "HAL", "EOG", "PXD", "OXY",
            # ETFs (high liquidity)
            "SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK"
        }
        
        # Try to parse structured response
        import re
        lines = response.split('\n')
        for line in lines:
            # Look for stock symbols (uppercase, 2-5 chars, not common words)
            symbols = re.findall(r'\b([A-Z]{2,5})\b', line)
            for sym in symbols:
                if sym in exclude_words:
                    continue
                if sym in known_symbols:
                    if sym not in [s.get('symbol') for s in stocks]:
                        stocks.append({
                            'symbol': sym,
                            'raw_text': line
                        })
        
        # If no results, return known symbols as fallback (expanded list)
        if not stocks:
            logger.info("Using fallback earnings stocks list (30 stocks)...")
            # Popular earnings stocks across sectors
            fallback = [
                "AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN", "TSLA", "AMD",
                "JPM", "V", "MA", "GS", "BAC",
                "UNH", "JNJ", "LLY", "PFE", "ABBV",
                "WMT", "COST", "HD", "MCD", "NKE",
                "NFLX", "DIS", "CRM", "ADBE", "ORCL",
                "XOM", "CVX"
            ]
            stocks = [{'symbol': s} for s in fallback]
        
        return stocks[:20]  # Limit to 20 stocks
    
    def scan(self, days_ahead: int = 14, min_score: float = 30) -> List[EarningsOpportunity]:
        """
        Full scan: discover earnings, validate, predict, rank.
        
        Args:
            days_ahead: Look for earnings in next N days
            min_score: Minimum score to include in results
            
        Returns:
            List of EarningsOpportunity sorted by score
        """
        logger.info("=" * 60)
        logger.info("EARNINGS SCANNER - Starting Full Scan")
        logger.info("=" * 60)
        
        # Step 1: Discover stocks with upcoming earnings
        discovered = self.discover_earnings(days_ahead)
        
        if not discovered:
            logger.warning("No stocks discovered. Using fallback list.")
            discovered = [{'symbol': s} for s in ['AAPL', 'MSFT', 'NVDA', 'META', 'GOOGL']]
        
        opportunities = []
        
        for stock in discovered:
            symbol = stock.get('symbol')
            logger.info(f"\n[{symbol}] Analyzing...")
            
            try:
                # Step 2: Get detailed earnings context
                earnings_ctx = self.perplexity.get_earnings_context(symbol, use_cache=self.use_cache)
                
                if not earnings_ctx:
                    logger.info(f"  -> Skipped (no earnings data)")
                    continue
                
                days = earnings_ctx.get('days_to_earnings', 999)
                if days > days_ahead:
                    logger.info(f"  -> Skipped (earnings too far: {days} days)")
                    continue
                
                # Step 3: Create opportunity object with earnings + analyst + news data
                # Extract analyst data
                analyst_data = earnings_ctx.get('analyst_rating', {}) or {}
                analyst_consensus = analyst_data.get('consensus', '') if isinstance(analyst_data, dict) else ''
                analyst_price_target = analyst_data.get('price_target', 0) if isinstance(analyst_data, dict) else 0
                
                # Format recent analyst changes
                recent_changes = analyst_data.get('recent_changes', []) if isinstance(analyst_data, dict) else []
                changes_summary = ""
                if recent_changes and isinstance(recent_changes, list):
                    changes_list = []
                    for change in recent_changes[:3]:  # Limit to 3
                        if isinstance(change, dict):
                            action = change.get('action', '')
                            analyst = change.get('analyst', '')
                            to_rating = change.get('to_rating', '')
                            if action and analyst:
                                changes_list.append(f"{analyst}: {action} to {to_rating}")
                    changes_summary = "; ".join(changes_list)
                
                # Format significant news
                news_items = earnings_ctx.get('significant_news', []) or []
                news_summary = ""
                news_sentiment = "neutral"
                if news_items and isinstance(news_items, list):
                    news_list = []
                    sentiments = []
                    for item in news_items[:3]:
                        if isinstance(item, dict):
                            headline = item.get('headline', '')
                            impact = item.get('impact', 'neutral')
                            if headline:
                                news_list.append(headline)
                                sentiments.append(impact)
                    news_summary = " | ".join(news_list)
                    # Determine overall sentiment
                    if sentiments:
                        bullish = sentiments.count('bullish')
                        bearish = sentiments.count('bearish')
                        if bullish > bearish:
                            news_sentiment = "bullish"
                        elif bearish > bullish:
                            news_sentiment = "bearish"
                
                opp = EarningsOpportunity(
                    symbol=symbol,
                    company_name=earnings_ctx.get('company_name', symbol),
                    earnings_date=str(earnings_ctx.get('announcement_date', '')),
                    days_to_earnings=days,
                    expected_move_pct=earnings_ctx.get('expected_move_pct', 0) or 0,
                    historical_move_pct=earnings_ctx.get('historical_move_avg_pct', 0) or 0,
                    crush_probability=earnings_ctx.get('crush_probability', 0.5) or 0.5,
                    # Analyst data
                    analyst_consensus=analyst_consensus,
                    analyst_price_target=float(analyst_price_target) if analyst_price_target else 0.0,
                    recent_analyst_changes=changes_summary,
                    # News data
                    significant_news=news_summary,
                    news_sentiment=news_sentiment
                )
                
                # Step 4: Get IB market data (if available)
                if self.ib_provider:
                    try:
                        # Get stock price
                        price = self.ib_provider.get_price(symbol)
                        opp.current_price = price
                        
                        # Get real ATM IV from options chain
                        atm_iv = self.ib_provider.get_atm_iv(symbol, days_out=30)
                        if atm_iv > 0:
                            opp.current_iv = atm_iv * 100  # Convert to percentage
                            opp.iv_percentile = self.ib_provider.get_iv_percentile(atm_iv, symbol)
                            logger.info(f"  IV: {opp.current_iv:.1f}% (Percentile: {opp.iv_percentile})")
                        else:
                            opp.current_iv = 30.0  # Fallback
                            opp.iv_percentile = 50
                    except Exception as e:
                        logger.debug(f"  IB data error: {e}")
                        opp.current_iv = 30.0
                        opp.iv_percentile = 50
                
                # Step 5: ML prediction
                prediction = self.predictor.predict(earnings_ctx)
                opp.predicted_class = prediction.get('predicted_class', 'UNKNOWN')
                opp.confidence = prediction.get('confidence', 0)
                opp.predicted_crush_pct = prediction.get('predicted_crush_pct', 0)
                
                # Step 6: Strategy routing
                decision = self.router.decide(symbol, earnings_ctx)
                opp.decision = decision.action
                opp.position_multiplier = decision.multiplier
                opp.risk_factor = decision.risk_factor
                opp.reason = decision.reason
                
                # Determine strategy recommendation
                if decision.action == "APPROVE":
                    opp.strategy = "Calendar Spread (Standard)"
                elif decision.action == "REDUCE_SIZE":
                    opp.strategy = "Calendar Spread (Reduced Size)"
                elif decision.action == "REJECT":
                    if opp.predicted_class == "SEVERE":
                        opp.strategy = "Reverse Calendar / Skip"
                    else:
                        opp.strategy = "Skip Trade"
                
                # Step 7: Calculate score
                opp.calculate_score()
                
                if opp.score >= min_score:
                    opportunities.append(opp)
                    logger.info(f"  ✓ Score: {opp.score} | {opp.decision} | {opp.predicted_class}")
                else:
                    logger.info(f"  ✗ Score too low: {opp.score}")
                    
            except Exception as e:
                logger.warning(f"  Error analyzing {symbol}: {e}")
                continue
        
        # Sort by score (highest first)
        opportunities.sort(key=lambda x: x.score, reverse=True)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"SCAN COMPLETE: {len(opportunities)} opportunities found")
        logger.info(f"{'='*60}")
        
        return opportunities
    
    def get_top_opportunities(self, limit: int = 5, days_ahead: int = 14) -> List[EarningsOpportunity]:
        """Get top N trading opportunities."""
        all_opps = self.scan(days_ahead=days_ahead)
        return all_opps[:limit]
    
    def print_opportunities(self, opportunities: List[EarningsOpportunity]):
        """Pretty print opportunities table with analyst and news data."""
        if not opportunities:
            print("\nNo opportunities found.")
            return
        
        print("\n" + "=" * 100)
        print("EARNINGS OPPORTUNITIES - Ranked by Score")
        print("=" * 100)
        print(f"{'#':<3} {'Symbol':<6} {'Days':<5} {'Score':<6} {'Class':<8} {'Conf':<6} {'Analyst':<10} {'Decision':<12} {'Strategy'}")
        print("-" * 100)
        
        for i, opp in enumerate(opportunities, 1):
            status = "✓" if opp.decision == "APPROVE" else "⚠" if opp.decision == "REDUCE_SIZE" else "✗"
            consensus = opp.analyst_consensus[:8] if opp.analyst_consensus else "N/A"
            print(f"{i:<3} {opp.symbol:<6} {opp.days_to_earnings:<5} {opp.score:<6.1f} "
                  f"{opp.predicted_class:<8} {opp.confidence:<5.0f}% {consensus:<10} {status} {opp.decision:<10} {opp.strategy}")
            
            # Show analyst changes if any
            if opp.recent_analyst_changes:
                print(f"    📊 Analyst Changes: {opp.recent_analyst_changes[:70]}...")
            
            # Show news if any
            if opp.significant_news:
                sentiment_icon = "📈" if opp.news_sentiment == "bullish" else "📉" if opp.news_sentiment == "bearish" else "📰"
                print(f"    {sentiment_icon} News ({opp.news_sentiment}): {opp.significant_news[:70]}...")
            
            # Show price target if available
            if opp.analyst_price_target > 0 and opp.current_price > 0:
                upside = ((opp.analyst_price_target / opp.current_price) - 1) * 100
                print(f"    🎯 Price Target: ${opp.analyst_price_target:.0f} ({upside:+.1f}% vs ${opp.current_price:.2f})")
        
        print("=" * 100)


def main():
    """Run the scanner from command line."""
    import argparse
    
    parser = argparse.ArgumentParser(description="AI-Powered Earnings Scanner")
    parser.add_argument("--days", type=int, default=14, help="Days ahead to scan")
    parser.add_argument("--top", type=int, default=10, help="Show top N opportunities")
    parser.add_argument("--no-ib", action="store_true", help="Disable IB Gateway")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    
    args = parser.parse_args()
    
    scanner = EarningsScanner(
        use_ib=not args.no_ib,
        use_cache=not args.no_cache
    )
    
    opportunities = scanner.get_top_opportunities(limit=args.top, days_ahead=args.days)
    scanner.print_opportunities(opportunities)


if __name__ == "__main__":
    main()
