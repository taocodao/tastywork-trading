#!/usr/bin/env python3
"""
TurboBounce Options: Multi-Ticker Scheduler Daemon
==================================================
Runs the daily scanning, strategy routing, and signal publishing
for the 47-ticker universe. 
"""

import os
import time
import logging
from datetime import datetime, date, timedelta
import pytz
import yfinance as yf

from src.turbobounce.data_provider import MultiTickerDataProvider
from src.turbobounce.scanner import TurboBounceScanner
from src.turbobounce.strategy_router import StrategyRouter
from signal_publisher.turbobounce import publish_turbobounce_entry_signal
from src.turbobounce.risk_manager import TurboBounceRiskManager
def is_market_open() -> bool:
    tz = pytz.timezone('US/Eastern')
    now = datetime.now(tz)
    if now.weekday() >= 5: return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close

def time_until_market_open() -> float:
    tz = pytz.timezone('US/Eastern')
    now = datetime.now(tz)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now > market_open:
        market_open += timedelta(days=1)
    while market_open.weekday() >= 5:
        market_open += timedelta(days=1)
    return (market_open - now).total_seconds()

# Ensure necessary directories exist
home_dir = os.path.expanduser("~")
log_dir = os.path.join(home_dir, "tastywork-trading", "logs")
os.makedirs(log_dir, exist_ok=True)

# Configure rotating logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'run_turbobounce_scheduler.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TurboBounceScheduler")

class TurboBounceScheduler:
    def __init__(self, mode="MODE_A"):
        self.data_provider = MultiTickerDataProvider()
        self.scanner = TurboBounceScanner(self.data_provider)
        self.router = StrategyRouter()
        self.risk_manager = TurboBounceRiskManager(mode=mode)
        
        self.last_scan_date = None
        self.tz = pytz.timezone('US/Eastern')
        logger.info(f"TurboBounce Scheduler initialized in {mode}")

    def run_daily_scan(self):
        """Runs the morning scan and publishes signals."""
        now = datetime.now(self.tz)
        today = now.date()
        
        if self.last_scan_date == today:
            logger.info("Daily scan already performed today. Skipping.")
            return
            
        logger.info(f"--- Starting TurboBounce Daily Scan for {today} ---")
        
        # 1. Run the Multi-Ticker Scanner
        ranked_picks = self.scanner.run_daily_scan()
        
        # Fetch live VIX for the StrategyRouter (crucial for option structure selection)
        try:
            vix_df = yf.download("^VIX", period="200d", auto_adjust=True, progress=False)
            if not vix_df.empty and len(vix_df) >= 50:
                # Handle potential MultiIndex format from yfinance
                close_col = vix_df['Close']
                if hasattr(close_col, "iloc"):
                    live_vix = float(close_col.iloc[-1].item() if hasattr(close_col.iloc[-1], 'item') else close_col.iloc[-1])
                    vix_sma_50 = float(close_col.rolling(window=50).mean().iloc[-1].item() if hasattr(close_col.rolling(window=50).mean().iloc[-1], 'item') else close_col.rolling(window=50).mean().iloc[-1])
                else:
                    live_vix, vix_sma_50 = 22.0, 18.0
            else:
                live_vix, vix_sma_50 = 22.0, 18.0
                logger.warning("VIX data missing/insufficient, using default mock values.")
        except Exception as e:
            logger.error(f"Failed to fetch live VIX: {e}")
            live_vix, vix_sma_50 = 22.0, 18.0
        
        all_picks = ranked_picks['top_oversold'] + ranked_picks['top_overbought']
        if not all_picks:
            logger.info("No actionable candidates found today.")
            self.last_scan_date = today
            return
            
        # 2. Route each pick through the Strategy Matrix
        routed_strategies = {}
        for pick in all_picks:
            route = self.router.route_candidate(pick, live_vix, vix_sma_50)
            if route:
                routed_strategies[pick.symbol] = route

        # 3. Publish to unified framework
        if routed_strategies:
            publish_count = 0
            for rank, pick in enumerate(all_picks):
                sym = pick.symbol
                route = routed_strategies.get(sym)
                if not route:
                    continue
                    
                display_rank = rank + 1 if rank < 3 else (rank - 3) + 1
                
                publish_turbobounce_entry_signal(
                    symbol=sym,
                    action_type=route.strategy_type,
                    direction=route.direction,
                    scanner_rank=display_rank,
                    total_score=round(pick.total_score, 1),
                    rsi_2=round(pick.rsi_2, 1),
                    iv_rank=round(pick.iv_rank, 1),
                    category=pick.category,
                    rationale=route.rationale,
                    target_anchor_dte=route.target_anchor_dte,
                    target_hedge_dte=route.target_hedge_dte,
                    target_delta=route.target_delta
                )
                publish_count += 1
            logger.info(f"Published {publish_count} unified TurboBounce Multi-Ticker signals.")
        else:
            logger.info("No candidates passed routing.")
            
        self.last_scan_date = today
        logger.info(f"--- Daily Scan Complete ({len(routed_strategies)} signals published) ---")

    def run_loop(self):
        """Main execution loop."""
        logger.info("Starting TurboBounce Background Daemon loop...")
        
        while True:
            try:
                now = datetime.now(self.tz)
                
                # We want to run the scan in the morning, around 08:00 - 09:30 ET
                # or anytime if the market is currently open and we haven't scanned yet
                is_open = is_market_open()
                
                # Determine if it's time to scan
                time_to_scan = False
                if now.hour >= 8 and now.hour < 16 and now.weekday() < 5:
                    if self.last_scan_date != now.date():
                        time_to_scan = True
                
                if time_to_scan:
                    self.run_daily_scan()
                    
                # Sleep interval
                if is_open:
                    # Check every 10 minutes during market hours
                    time.sleep(600)
                else:
                    sleep_time = time_until_market_open()
                    logger.info(f"Market closed. Sleeping for {sleep_time/3600:.1f} hours.")
                    # Sleep in chunks to allow interruption
                    for _ in range(int(sleep_time / 300)):
                        time.sleep(300)
                        
            except Exception as e:
                logger.error(f"Fatal error in scheduler loop: {e}", exc_info=True)
                time.sleep(60) # Wait a minute before retrying

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TurboBounce Scheduler")
    parser.add_argument("--once", action="store_true", help="Run a single scan and exit")
    parser.add_argument("--mode", type=str, default="MODE_A", help="Allocation mode (MODE_A or MODE_B)")
    args = parser.parse_args()
    
    scheduler = TurboBounceScheduler(mode=args.mode)
    if args.once:
        scheduler.run_daily_scan()
    else:
        scheduler.run_loop()
