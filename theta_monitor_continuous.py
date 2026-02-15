#!/usr/bin/env python3
"""
Theta Sprint - Continuous Monitoring Service
==============================================

Runs 24/7 as a systemd service on EC2. During market hours:
- Every 5 minutes: Scan for NEW entry opportunities (signal generation)
- Every 5 minutes: Monitor existing positions for exits
- Both happen on every cycle during market hours

Key design:
- Uses ET timezone for market hours (9:30 AM - 4:00 PM ET)
- Entry signals generated CONTINUOUSLY throughout market hours
- Position exits checked on same schedule
- Proper separation between entry generation (--once) and exit checks (--check)
"""

import subprocess
import time
import logging
from datetime import datetime
import pytz
import signal as sig
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('theta_monitor.log'),
        logging.StreamHandler()
    ])

logger = logging.getLogger(__name__)

# Constants
TIMEZONE = pytz.timezone('America/New_York')
SCAN_INTERVAL = 300  # 5 minutes between full scans
WORKING_DIR = os.path.dirname(os.path.abspath(__file__))

# Market hours (Eastern Time)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_requested = True


def is_market_hours(now: datetime) -> bool:
    """Check if market is currently open (9:30 AM - 4:00 PM ET, weekdays only)."""
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    market_open = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
    market_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0, microsecond=0)
    return market_open <= now <= market_close


def run_entry_scan() -> bool:
    """
    Run entry signal generation scan.
    Scans the market for new theta spread opportunities and publishes signals.
    """
    try:
        logger.info("📡 Running ENTRY scan (looking for new opportunities)...")
        result = subprocess.run(
            ['python3', 'run_theta_scheduler.py', '--once'],
            cwd=WORKING_DIR,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            logger.info("✅ Entry scan completed successfully")
            if result.stdout:
                # Show last few lines of output
                for line in result.stdout.strip().split('\n')[-5:]:
                    logger.info(f"   {line}")
            return True
        else:
            logger.error(f"❌ Entry scan failed with code {result.returncode}")
            if result.stderr:
                logger.error(f"   Error: {result.stderr[-300:]}")
            return False
        
    except subprocess.TimeoutExpired:
        logger.error("❌ Entry scan timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"❌ Error running entry scan: {e}")
        return False


def run_position_check() -> bool:
    """
    Run position monitoring check.
    Checks existing positions for exit conditions (profit targets, stop losses).
    """
    try:
        logger.info("🔍 Running POSITION CHECK (monitoring exits)...")
        result = subprocess.run(
            ['python3', 'run_theta_scheduler.py', '--check'],
            cwd=WORKING_DIR,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            logger.info("✅ Position check completed successfully")
            if result.stdout:
                for line in result.stdout.strip().split('\n')[-5:]:
                    logger.info(f"   {line}")
            return True
        else:
            logger.error(f"❌ Position check failed with code {result.returncode}")
            if result.stderr:
                logger.error(f"   Error: {result.stderr[-300:]}")
            return False
        
    except subprocess.TimeoutExpired:
        logger.error("❌ Position check timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"❌ Error running position check: {e}")
        return False


def run_continuous_monitor():
    """Main continuous monitoring loop."""
    
    logger.info("=" * 70)
    logger.info("🚀 THETA SPRINT - CONTINUOUS MONITORING SERVICE")
    logger.info("=" * 70)
    logger.info(f"Started at: {datetime.now(TIMEZONE)}")
    logger.info(f"Working directory: {WORKING_DIR}")
    logger.info("-" * 70)
    logger.info(f"Market hours: {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} - {MARKET_CLOSE_HOUR}:{MARKET_CLOSE_MINUTE:02d} ET")
    logger.info(f"Scan interval: {SCAN_INTERVAL}s ({SCAN_INTERVAL // 60} min)")
    logger.info(f"Mode: CONTINUOUS entry + exit scanning during market hours")
    logger.info("=" * 70)
    
    last_scan_time = None
    iteration = 0
    consecutive_errors = 0
    
    while not shutdown_requested:
        try:
            iteration += 1
            now = datetime.now(TIMEZONE)
            
            logger.info(f"\n[Iteration {iteration}] {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            is_weekday = now.weekday() < 5
            in_market = is_market_hours(now)
            
            logger.info(f"   Weekday: {is_weekday} | Market open: {in_market}")
            
            # Skip weekends
            if not is_weekday:
                logger.info("   📅 Weekend - sleeping 1 hour")
                time.sleep(3600)
                continue
            
            # During market hours: run entry scans AND position checks
            if in_market:
                time_since_last_scan = (
                    (now - last_scan_time).total_seconds()
                    if last_scan_time else 999999
                )
                
                if time_since_last_scan >= SCAN_INTERVAL:
                    logger.info("")
                    logger.info("=" * 70)
                    logger.info(f"🔄 MARKET SCAN CYCLE @ {now.strftime('%H:%M:%S %Z')}")
                    logger.info("=" * 70)
                    
                    # 1. Scan for new entry opportunities
                    entry_success = run_entry_scan()
                    
                    # 2. Check existing positions for exits
                    position_success = run_position_check()
                    
                    if entry_success or position_success:
                        last_scan_time = now
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                    
                    logger.info("-" * 70)
                    logger.info(f"   Entry scan: {'✅' if entry_success else '❌'}")
                    logger.info(f"   Position check: {'✅' if position_success else '❌'}")
                    logger.info("=" * 70)
                else:
                    remaining = int(SCAN_INTERVAL - time_since_last_scan)
                    logger.info(f"   Next scan in {remaining}s")
            else:
                logger.info("   📴 Outside market hours - scanning paused")
            
            # Sleep until next check
            logger.info(f"   ⏸  Sleeping 60s until next check...")
            time.sleep(60)
            
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"❌ Unexpected error in main loop: {e}")
            import traceback
            traceback.print_exc()
            
            sleep_time = min(60 * consecutive_errors, 600)
            logger.info(f"   Waiting {sleep_time}s before retry (error count: {consecutive_errors})")
            time.sleep(sleep_time)
            
            if consecutive_errors >= 10:
                logger.error("Too many consecutive errors, exiting for restart")
                sys.exit(1)
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("🛑 CONTINUOUS MONITORING SERVICE STOPPED")
    logger.info(f"Stopped at: {datetime.now(TIMEZONE)}")
    logger.info(f"Total iterations: {iteration}")
    logger.info("=" * 70)


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    sig.signal(sig.SIGTERM, signal_handler)
    sig.signal(sig.SIGINT, signal_handler)
    
    try:
        os.chdir(WORKING_DIR)
        run_continuous_monitor()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
