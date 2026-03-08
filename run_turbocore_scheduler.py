#!/usr/bin/env python3
"""
TurboCore ML Scheduler
==================================================
Runs the daily data fetch, ML Regime detection, XGBoost scoring, 
and Kelly-sized allocation for the 530+SMA200 strategy.
Emits the final allocation vector to the signal_publisher to be picked up
by auto_approve.py.
"""

import os
import time
import logging
from datetime import datetime, date, timedelta
import pytz
from dotenv import load_dotenv

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

# Load environment variables
load_dotenv()

from src.tqqq_turbocore.data_pipeline import TurboCoreDataPipeline
from src.tqqq_turbocore.base_strategy import BaseStrategy
from src.tqqq_turbocore.ml.regime_detector import TurboCoreRegimeDetector
from src.tqqq_turbocore.ml.signal_scorer import TurboCoreSignalScorer
from src.tqqq_turbocore.allocation_optimizer import AllocationOptimizer
from signal_publisher.turbocore import publish_turbocore_rebalance_signal

# Configure logging
home_dir = os.path.expanduser("~")
log_dir = os.path.join(home_dir, "tastywork-trading", "logs")
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'run_turbocore_scheduler.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("TurboCoreScheduler")

class TurboCoreScheduler:
    def __init__(self):
        self.data_pipe = TurboCoreDataPipeline()
        self.regime_detector = TurboCoreRegimeDetector()
        self.scorer = TurboCoreSignalScorer()
        self.allocator = AllocationOptimizer()
        self.tz = pytz.timezone('US/Eastern')
        self.last_scan_date = None
        
    def run_daily_scan(self):
        logger.info("--- Starting TurboCore ML Daily Scan ---")
        
        # 1. Fetch & Prepare Data
        self.data_pipe.fetch_data("2y")
        master_df = self.data_pipe.prepare_core_features()
        
        if master_df.empty:
            logger.error("Data pipeline returned empty dataframe. Aborting.")
            return
            
        # 2. Base Rules + HMM + XGBoost Layers
        base = BaseStrategy(master_df)
        df = base.evaluate()
        
        df = self.regime_detector.predict_regimes(df)
        df = self.scorer.predict_confidence(df)
        
        # 3. Assess Today's Actionable Output
        today_row = df.iloc[-1]
        
        regime = str(today_row['final_regime'])
        base_signal = int(today_row.get('base_signal', 0))
        confidence = float(today_row.get('ml_confidence', 0.5))
        is_sma_forced = bool(today_row.get('qqq_below_sma200_sell', False))
        
        # 4. Determine Dynamic Allocation Matrix
        target_allocation = self.allocator.get_target_allocation(
            regime=regime,
            signal=base_signal,
            ml_confidence=confidence
        )
        
        logger.info(f"Generated Allocation: {target_allocation}")
        
        rationale = f"Regime: {regime} | Conf: {confidence:.0%} | SMA Drop: {is_sma_forced}"
        
        # 5. Publish
        publish_turbocore_rebalance_signal(
            regime=regime,
            confidence=confidence,
            alloc_dict=target_allocation,
            rationale=rationale,
            ema_signal=base_signal,
            sma200_gate=not is_sma_forced
        )
        
        logger.info("--- TurboCore Scan Complete ---")

    def run_loop(self):
        """Main execution loop for continuous running."""
        logger.info("Starting TurboCore Background Daemon loop...")
        
        while True:
            try:
                now = datetime.now(self.tz)
                is_open = is_market_open()
                
                time_to_scan = False
                if now.hour >= 8 and now.hour < 16 and now.weekday() < 5:
                    if self.last_scan_date != now.date():
                        time_to_scan = True
                
                if time_to_scan:
                    self.run_daily_scan()
                    self.last_scan_date = now.date()
                    
                if is_open:
                    # Check periodically just in case (e.g. 10m)
                    time.sleep(600)
                else:
                    sleep_time = time_until_market_open()
                    logger.info(f"Market closed. Sleeping for {sleep_time/3600:.1f} hours.")
                    for _ in range(int(sleep_time / 300)):
                        time.sleep(300)
            except Exception as e:
                logger.error(f"Fatal error in scheduler loop: {e}", exc_info=True)
                time.sleep(60)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TurboCore ML Scheduler")
    parser.add_argument("--once", action="store_true", help="Run a single scan and exit")
    args = parser.parse_args()
    
    scheduler = TurboCoreScheduler()
    if args.once:
        scheduler.run_daily_scan()
    else:
        scheduler.run_loop()
