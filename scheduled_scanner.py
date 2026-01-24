"""
Scheduled Scanner
==================
Runs the calendar spread scanner on a schedule and publishes
real signals from IB Gateway to the WebSocket server.

Usage:
    python scheduled_scanner.py             # Run once
    python scheduled_scanner.py --loop      # Run continuously
    python scheduled_scanner.py --interval 300  # Every 5 min
"""

import argparse
import logging
import time
import os
from datetime import datetime
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Earnings Intelligence Imports
try:
    from src.earnings_intelligence import PerplexityClient, EarningsStrategyRouter, IVCrushPredictor
    EARNINGS_AVAILABLE = True
except ImportError:
    logger.warning("Earnings Intelligence modules not found. Earnings scan disabled.")
    EARNINGS_AVAILABLE = False

from dataclasses import dataclass
from typing import Optional

@dataclass
class EarningsOpportunity:
    symbol: str
    earnings_date: str
    days_to_earnings: int
    current_iv: float
    iv_percentile: float
    predicted_class: str
    confidence: float
    predicted_crush_pct: float
    decision: str
    score: float
    reason: str
    current_price: float = 0.0
    strategy: str = "Calendar Spread"
    analyst_consensus: str = ""
    analyst_price_target: float = 0.0
    recent_analyst_changes: str = ""
    significant_news: str = ""
    news_sentiment: str = "neutral"


def is_market_hours() -> bool:
    """Check if we're in market hours (9:30 AM - 4:00 PM ET, weekdays)."""
    now = datetime.now()
    
    # Skip weekends
    if now.weekday() >= 5:
        return False
    
    # Market hours (simplified - doesn't account for holidays)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= now <= market_close


def run_scanner(use_mock: bool = False) -> int:
    """
    Run the scanner and publish signals.
    
    Args:
        use_mock: If True, force usage of mock data
        
    Returns:
        Number of signals published
    """
    from scanner import CalendarSpreadScanner
    from signal_publisher import publish_signals
    
    data_provider = None
    
    if not use_mock:
        # 1. Try IB Gateway FIRST for Market Data (Option Chains)
        # Tastytrade SDK has issues with empty option chain responses
        # IB Gateway is already running at 34.235.119.67:4004
        logger.info("🔍 Connecting to Data Provider...")
        
        ib_host = os.getenv('IB_HOST', 'localhost')  # On EC2, set to localhost since IB Gateway runs locally
        ib_port = int(os.getenv('IB_PORT', '4004'))
        try:
            from ib_data_provider import IBDataProvider
            provider = IBDataProvider(host=ib_host, port=ib_port)
            if provider.connect():
                data_provider = provider
                logger.info("✅ Connected to IB Gateway for Market Data (Option Chains)")
        except Exception as e:
            logger.warning(f"IB Gateway connection failed: {e}")

        # 2. Fallback to Tastytrade API (if IB unavailable)
        if not data_provider:
            try:
                from tasty_data_provider import TastytradeDataProvider
                provider = TastytradeDataProvider()
                if provider.connect():
                    data_provider = provider
                    logger.info("✅ Connected to Tastytrade API for Market Data (Fallback)")
                else:
                    logger.warning("❌ Failed to connect to Tastytrade API")
            except Exception as e:
                logger.error(f"Tastytrade provider error: {e}")
        
        # 3. Fallback to Mock
        if not data_provider:
            logger.warning("⚠️ No data provider available, using MOCK data")
    else:
        logger.info("⚠️ Forced mock mode")
    
    # Create scanner
    scanner = CalendarSpreadScanner(
        underlyings=['SPY', 'QQQ', 'IWM', 'AAPL', 'MSFT'],
        data_provider=data_provider
    )
    
    # Scan for setups
    logger.info("📊 Scanning for calendar spread opportunities...")
    setups = scanner.scan_all()
    
    logger.info(f"Found {len(setups)} potential setups")
    
    if not setups:
        logger.info("No setups found")
        return 0
    
    # Log top setups
    for i, setup in enumerate(setups[:5]):
        logger.info(f"  #{i+1}: {setup}")
    
    # Publish top 5 signals
    published = publish_signals(setups, max_signals=5)
    
    logger.info(f"✅ Published {published} signals to WebSocket")
    
    return published


def run_earnings_scanner(symbols: list = None) -> int:
    """Run the earnings intelligence scanner."""
    if not EARNINGS_AVAILABLE:
        return 0
        
    logger.info("🧠 Running Earnings Intelligence Scan...")
    
    symbols = symbols or ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'AMD', 'NFLX', 'SPY', 'QQQ', 'IWM']
    
    try:
        client = PerplexityClient()
        router = EarningsStrategyRouter()
        # Predictor is loaded by router lazily
        
        from signal_publisher import publish_earnings_signals
        
        opportunities = []
        
        for symbol in symbols:
            logger.info(f"  Analysing {symbol} earnings...")
            try:
                # 1. Get Context
                context = client.get_earnings_context(symbol)
                
                # 2. Get Decision (uses ML internally)
                decision = router.decide(symbol, context)
                
                # 3. Create Opportunity Object
                if decision.action in ["APPROVE", "REDUCE_SIZE"]:
                    opp = EarningsOpportunity(
                        symbol=symbol,
                        earnings_date=context.get('announcement_date', 'Unknown'),
                        days_to_earnings=context.get('days_to_earnings', 0),
                        current_iv=context.get('iv_rank', 0) / 100.0,
                        iv_percentile=float(context.get('iv_rank', 0)),
                        predicted_class=decision.predicted_class or "UNKNOWN",
                        confidence=decision.confidence or 0.0,
                        predicted_crush_pct=decision.predicted_crush_pct or 0.0,
                        decision=decision.action,
                        score=decision.confidence or 50.0,
                        reason=decision.reason
                    )
                    opportunities.append(opp)
                    logger.info(f"    -> Opportunity found: {decision.action}")
            except Exception as e:
                logger.error(f"    Error analysing {symbol}: {e}")
        
        # Publish
        if opportunities:
            published = publish_earnings_signals(opportunities)
            logger.info(f"✅ Published {published} earnings signals")
            return published
            
    except Exception as e:
        logger.error(f"Earnings scan failed: {e}")
        
    return 0


def run_loop(interval_seconds: int = 300, use_mock: bool = False, force: bool = False):
    """
    Run scanner in a loop.
    
    Args:
        interval_seconds: Seconds between scans (default: 5 min)
        use_mock: If True, use mock data
        force: If True, run even outside market hours
    """
    logger.info(f"🔄 Starting scanner loop (interval: {interval_seconds}s)")
    
    while True:
        try:
            if is_market_hours() or use_mock or force:
                logger.info("--- Starting Calendar Scan ---")
                run_scanner(use_mock=use_mock)
                
                logger.info("--- Starting Earnings Scan ---")
                run_earnings_scanner() # Always run earnings check in loop
            else:
                logger.info("⏸️ Outside market hours, skipping scan")
            
            # Wait for next scan
            logger.info(f"💤 Sleeping for {interval_seconds}s...")
            time.sleep(interval_seconds)
            
        except KeyboardInterrupt:
            logger.info("🛑 Scanner stopped by user")
            break
        except Exception as e:
            logger.error(f"Scanner error: {e}")
            time.sleep(60)  # Wait 1 min on error


def main():
    parser = argparse.ArgumentParser(description='Calendar Spread Scanner')
    parser.add_argument('--loop', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=300, 
                       help='Scan interval in seconds (default: 300)')
    parser.add_argument('--force', action='store_true',
                       help='Run even outside market hours')
    parser.add_argument('--mock', action='store_true',
                       help='Force use of mock data (testing)')
    
    args = parser.parse_args()
    
    if args.loop:
        run_loop(args.interval, use_mock=args.mock, force=args.force)
    else:
        if not is_market_hours() and not args.force and not args.mock:
            logger.info("⏸️ Outside market hours. Use --force to run anyway.")
            return
        run_scanner(use_mock=args.mock)
        run_earnings_scanner()


if __name__ == '__main__':
    main()
