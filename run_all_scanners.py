"""
Unified Scanner Service
========================
Runs ALL TradeMind trading strategies during market hours
from a single orchestrated process.

Schedules:
- 9:45 AM ET: Theta morning analysis (once per day)
- Every 5 min: Calendar spread scan
- Every 30 min: ZEBRA scan
- Every 60 min: DVO scan
- Every 60 sec: Theta position exit checks
- 4:00 PM ET: End of day report
"""

import time
import logging
import argparse
from datetime import datetime, timedelta
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Import strategy runners
from run_theta_scheduler import run_morning_analysis, run_position_check, run_end_of_day_report
from scheduled_scanner import run_scanner as run_calendar_scanner, run_zebra_scanner
from run_dvo_scheduler import run_dvo_scan

def is_market_hours() -> bool:
    """Check if we're in market hours (9:30 AM - 4:00 PM ET, weekdays)."""
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    
    # Skip weekends
    if now.weekday() >= 5:
        return False
    
    # Market hours in ET
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= now <= market_close

def run_unified_loop(use_mock=False, force=False):
    """Main Orchestrator Loop."""
    logger.info("🚀 Starting Unified Scanner Orchestrator")
    
    et = pytz.timezone('US/Eastern')
    
    # Track when tasks last ran
    last_calendar = datetime.min
    last_zebra = datetime.min
    last_dvo = datetime.min
    last_theta_check = datetime.min
    
    # Flags for daily once-off tasks
    morning_analysis_done = False
    eod_report_done = False
    last_run_date = None

    while True:
        try:
            now_et = datetime.now(et)
            now_utc = datetime.utcnow()
            today_date = now_et.date()
            
            # Reset daily flags on a new day
            if last_run_date != today_date:
                morning_analysis_done = False
                eod_report_done = False
                last_run_date = today_date
                logger.info(f"📅 New trading day: {today_date}")

            is_market = is_market_hours()
            
            if is_market or force:
                logger.info(f"⏰ Current Time (ET): {now_et.strftime('%I:%M:%S %p')}")

                # 1. Theta Morning Analysis @ 9:45 AM ET (Run once daily)
                if not morning_analysis_done and now_et.hour == 9 and now_et.minute >= 45:
                    logger.info("🌅 Running Theta Morning Analysis...")
                    try:
                        run_morning_analysis()
                    except Exception as e:
                        logger.error(f"Theta morning analysis failed: {e}")
                    morning_analysis_done = True

                # 2. End of Day Report @ 4:00 PM ET (Run once daily)
                if not eod_report_done and now_et.hour == 16 and now_et.minute >= 0:
                    logger.info("🌇 Running End of Day Report...")
                    try:
                        run_end_of_day_report()
                    except Exception as e:
                        logger.error(f"EOD report failed: {e}")
                    eod_report_done = True
                
                # 3. Position Checks (Every 60 seconds)
                if (now_utc - last_theta_check).total_seconds() >= 60:
                    logger.info("🔍 Running Theta Position Checks...")
                    try:
                        run_position_check()
                    except Exception as e:
                        logger.error(f"Position check failed: {e}")
                    last_theta_check = now_utc

                # 4. Calendar Spreads (Every 5 minutes)
                if (now_utc - last_calendar).total_seconds() >= 300:
                    logger.info("📅 Running Calendar Spread Scanner...")
                    try:
                        run_calendar_scanner(use_mock=use_mock)
                    except Exception as e:
                        logger.error(f"Calendar scanner failed: {e}")
                    last_calendar = now_utc

                # 5. ZEBRA Scan (Every 30 minutes)
                if (now_utc - last_zebra).total_seconds() >= 1800:
                    logger.info("🦓 Running ZEBRA Strategy Scan...")
                    try:
                        run_zebra_scanner()
                    except Exception as e:
                        logger.error(f"ZEBRA scanner failed: {e}")
                    last_zebra = now_utc

                # 6. DVO Scan (Every 60 minutes)
                if (now_utc - last_dvo).total_seconds() >= 3600:
                    logger.info("💎 Running DVO Value Scan...")
                    try:
                        run_dvo_scan()
                    except Exception as e:
                        logger.error(f"DVO scanner failed: {e}")
                    last_dvo = now_utc

            else:
                if now_utc.minute % 15 == 0:  # Log occasionally outside market hours
                    logger.info("⏸️ Outside market hours. Sleeping...")
            
            # Loop sleeps 60s
            time.sleep(60)

        except KeyboardInterrupt:
            logger.info("🛑 Scanner stopped by user")
            break
        except Exception as e:
            logger.error(f"💥 Top-level orchestrator error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified TradeMind Scanner")
    parser.add_argument("--force", action="store_true", help="Run even outside market hours")
    parser.add_argument("--mock", action="store_true", help="Use mock data (testing)")
    args = parser.parse_args()
    
    run_unified_loop(use_mock=args.mock, force=args.force)
