"""
Unified Core Framework
======================
Runs the three officially supported TradeMind strategies:
1. Position Guardian     (Pre-market at 9:31 AM ET) — auto-close dangerous positions
2. TurboBounce           (Morning Scan at 9:30 AM ET)
3. TurboCore Pro         (End-of-Day Allocation at 3:00 PM ET)
"""

import time
import logging
import argparse
from datetime import datetime
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("UnifiedFramework")

from run_turbobounce_scheduler import TurboBounceScheduler
from run_turbocore_scheduler import TurboCoreScheduler
from position_guardian import run_sweep as guardian_sweep


def is_trading_day(dt=None) -> bool:
    """
    Returns True only if `dt` (default: today ET) is an NYSE trading day.
    Skips weekends AND all NYSE-observed holidays (Memorial Day, July 4th, etc.).
    Uses schedule() which has current holiday data.
    """
    import pandas_market_calendars as mcal
    et = pytz.timezone('US/Eastern')
    day = (dt or datetime.now(et)).date()
    nyse = mcal.get_calendar('NYSE')
    sched = nyse.schedule(start_date=str(day), end_date=str(day))
    return not sched.empty

def is_market_hours(now_et=None) -> bool:
    """True if current ET time is within NYSE trading hours on an NYSE trading day."""
    et = pytz.timezone('US/Eastern')
    now = now_et or datetime.now(et)
    if not is_trading_day(now):
        return False
    market_open  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return market_open <= now <= market_close

def run_unified_loop(force=False):
    """Main Orchestrator Loop."""
    logger.info("Starting Unified TradeMind Framework (Guardian + TurboBounce + TurboCore Pro)")
    
    et = pytz.timezone('US/Eastern')
    
    # Initialize strategy schedulers
    turbobounce_scheduler = TurboBounceScheduler(mode="MODE_A")
    turbocore_scheduler = TurboCoreScheduler()
    
    last_run_date = None
    guardian_ran_today = None   # track date guardian last fired

    while True:
        try:
            now_et = datetime.now(et)
            today_date = now_et.date()
            
            # Reset daily flags on a new day
            if last_run_date != today_date:
                turbobounce_scheduler.last_scan_date = None
                turbocore_scheduler.last_scan_date = None
                last_run_date = today_date
                logger.info(f"📅 New trading day: {today_date}")

            is_market = is_market_hours()
            
            if is_market or force:
                logger.info(f"Current Time (ET): {now_et.strftime('%I:%M:%S %p')}")

                # 0. Position Guardian @ 9:31 AM ET — close dangerous positions
                #    Fires once per NYSE trading day for every user with a linked
                #    TastyTrade account. Skips weekends AND market holidays.
                #    Must run BEFORE new entries so bad positions are cleaned first.
                guardian_trigger = (
                    force or
                    (now_et.hour == 9 and now_et.minute >= 31) or
                    now_et.hour > 9
                )
                if guardian_ran_today != today_date and guardian_trigger and is_trading_day(now_et):
                    logger.info("Running Position Guardian — scanning all linked accounts...")
                    try:
                        results = guardian_sweep(dry_run=False)
                        total_dangers = sum(r.get("dangers_found", 0) for r in results)
                        total_orders  = sum(r.get("orders_placed",  0) for r in results)
                        logger.info(
                            f"Position Guardian done: {len(results)} accounts scanned, "
                            f"{total_dangers} dangers, {total_orders} closes submitted"
                        )
                        guardian_ran_today = today_date
                    except Exception as e:
                        logger.error(f"Position Guardian failed: {e}", exc_info=True)
                        # Non-fatal — continue with rest of day

                # 1. TurboBounce Morning Scan @ 9:30 AM ET
                if turbobounce_scheduler.last_scan_date != today_date and now_et.hour >= 9:
                    # Run immediately if forced, or explicitly wait until exactly 9:30 AM ET
                    if force or (now_et.hour == 9 and now_et.minute >= 30) or now_et.hour > 9:
                        logger.info("Running TurboBounce Morning Scan...")
                        try:
                            turbobounce_scheduler.run_daily_scan()
                        except Exception as e:
                            logger.error(f"TurboBounce scan failed: {e}", exc_info=True)

                # 2. TurboCore Pro ML Allocation @ 3:00 PM ET
                if turbocore_scheduler.last_scan_date != today_date and now_et.hour >= 15:
                    logger.info("Running TurboCore Pro ML Allocation...")
                    try:
                        turbocore_scheduler.run_daily_scan()
                        turbocore_scheduler.last_scan_date = today_date
                    except Exception as e:
                        logger.error(f"TurboCore Pro scan failed: {e}", exc_info=True)
                        
            else:
                if now_et.minute % 15 == 0:
                    logger.info("Outside market hours. Sleeping...")
            
            # Sleep until next check (1 minute)
            time.sleep(60)

        except KeyboardInterrupt:
            logger.info("🛑 Framework stopped by user")
            break
        except Exception as e:
            logger.error(f"💥 Top-level orchestrator error: {e}", exc_info=True)
            time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified TradeMind Framework")
    parser.add_argument("--force", action="store_true", help="Run even outside market hours")
    args = parser.parse_args()
    
    run_unified_loop(force=args.force)
