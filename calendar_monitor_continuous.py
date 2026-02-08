#!/usr/bin/env python3
"""
Calendar Spread - Continuous Monitoring Service
=================================================

24/7 monitoring service for calendar spread trading, following the
successful Theta Sprint pattern but optimized for calendar spreads.

Schedule:
- 3:50 PM ET: Entry scan (end-of-day IV typically elevated)
- 9:35 AM ET: Morning exit/adjustment scan
- Every 5 minutes: Position monitoring for profit targets/stops

Key differences from Theta Sprint:
- Target 35% profit (vs 50% for theta)
- Longer hold periods (7-14 days typical)
- Focus on IV differential decay

Deployment:
```bash
# Copy to EC2
scp calendar_monitor_continuous.py ubuntu@ec2:~/tastywork-trading/

# Install as systemd service
sudo cp calendar-monitor.service /etc/systemd/system/
sudo systemctl enable calendar-monitor
sudo systemctl start calendar-monitor
```
"""

import subprocess
import time
import logging
from datetime import datetime
from typing import Optional
import pytz
import signal as sig
import os
import sys

# Configure logging
LOG_FILE = 'calendar_monitor.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Timezone
TIMEZONE = pytz.timezone('America/New_York')

# Entry scan: 3:50 PM ET (capture end-of-day IV)
ENTRY_HOUR = 15
ENTRY_MINUTE = 50

# Exit scan: 9:35 AM ET (morning check)
EXIT_HOUR = 9
EXIT_MINUTE = 35

# Position monitoring interval
POSITION_CHECK_INTERVAL = 300  # 5 minutes

# Market hours
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# Working directory
WORKING_DIR = os.path.dirname(os.path.abspath(__file__))
if not WORKING_DIR:
    WORKING_DIR = '/home/ubuntu/tastywork-trading'

# ============================================================================
# GLOBAL STATE
# ============================================================================

shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_requested = True


def is_market_hours(now: datetime) -> bool:
    """Check if market is currently open."""
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    market_open = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0)
    market_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0)
    
    return market_open <= now <= market_close


def run_scheduler(mode: str = '--once') -> bool:
    """
    Run the calendar scheduler with specified mode.
    
    Modes:
        --once: Run full cycle (entry + monitor)
        --entry: Entry scan only
        --exit: Exit scan only
        --monitor: Position monitoring only
    """
    try:
        logger.info(f"Running calendar scheduler with mode: {mode}")
        
        result = subprocess.run(
            ['python3', 'run_calendar_scheduler.py', mode],
            cwd=WORKING_DIR,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            logger.info("✅ Scheduler completed successfully")
            # Log last 500 chars of output
            if result.stdout:
                output_preview = result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
                for line in output_preview.strip().split('\n')[-5:]:
                    logger.info(f"   {line}")
            return True
        else:
            logger.error(f"❌ Scheduler failed with code {result.returncode}")
            if result.stderr:
                logger.error(f"   Error: {result.stderr[-300:]}")
            return False
        
    except subprocess.TimeoutExpired:
        logger.error("❌ Scheduler timed out after 5 minutes")
        return False
    except FileNotFoundError:
        logger.error(f"❌ run_calendar_scheduler.py not found in {WORKING_DIR}")
        return False
    except Exception as e:
        logger.error(f"❌ Error running scheduler: {e}")
        return False


def check_time_match(now: datetime, hour: int, minute: int) -> bool:
    """Check if current time matches specified hour:minute."""
    return now.hour == hour and now.minute == minute


def run_continuous_monitor():
    """
    Main continuous monitoring loop.
    
    Runs indefinitely until shutdown signal received.
    """
    logger.info("=" * 70)
    logger.info("🚀 CALENDAR SPREAD - CONTINUOUS MONITORING SERVICE")
    logger.info("=" * 70)
    logger.info(f"Started at: {datetime.now(TIMEZONE)}")
    logger.info(f"Working directory: {WORKING_DIR}")
    logger.info("-" * 70)
    logger.info(f"Entry scan: {ENTRY_HOUR}:{ENTRY_MINUTE:02d} ET")
    logger.info(f"Exit scan: {EXIT_HOUR}:{EXIT_MINUTE:02d} ET")
    logger.info(f"Position check interval: {POSITION_CHECK_INTERVAL}s ({POSITION_CHECK_INTERVAL // 60} min)")
    logger.info("=" * 70)
    
    # Track last actions to avoid duplicates
    last_entry_scan_date: Optional[datetime.date] = None
    last_exit_scan_date: Optional[datetime.date] = None
    last_position_check: Optional[datetime] = None
    
    iteration = 0
    consecutive_errors = 0
    
    while not shutdown_requested:
        try:
            iteration += 1
            now = datetime.now(TIMEZONE)
            today = now.date()
            
            # Heartbeat log every minute
            logger.info(f"\n[Iteration {iteration}] {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            is_weekday = now.weekday() < 5
            in_market = is_market_hours(now)
            
            logger.info(f"   Weekday: {is_weekday} | Market open: {in_market}")
            
            # Skip weekends
            if not is_weekday:
                logger.info("   📅 Weekend - sleeping 1 hour")
                time.sleep(3600)
                continue
            
            # ================================================================
            # 1. Entry Scan at 3:50 PM ET
            # ================================================================
            if check_time_match(now, ENTRY_HOUR, ENTRY_MINUTE):
                if last_entry_scan_date != today:
                    logger.info("")
                    logger.info("=" * 70)
                    logger.info("⏰ ENTRY SCAN TIME (3:50 PM)")
                    logger.info("=" * 70)
                    
                    if run_scheduler('--entry'):
                        last_entry_scan_date = today
                        logger.info("✅ Entry scan completed")
                    else:
                        logger.error("❌ Entry scan failed - will retry tomorrow")
                else:
                    logger.info("   Entry scan already completed today")
            
            # ================================================================
            # 2. Exit Scan at 9:35 AM ET
            # ================================================================
            if check_time_match(now, EXIT_HOUR, EXIT_MINUTE):
                if last_exit_scan_date != today:
                    logger.info("")
                    logger.info("=" * 70)
                    logger.info("⏰ EXIT SCAN TIME (9:35 AM)")
                    logger.info("=" * 70)
                    
                    if run_scheduler('--exit'):
                        last_exit_scan_date = today
                        logger.info("✅ Exit scan completed")
                    else:
                        logger.error("❌ Exit scan failed")
                else:
                    logger.info("   Exit scan already completed today")
            
            # ================================================================
            # 3. Position Monitoring (every 5 minutes during market hours)
            # ================================================================
            if in_market:
                time_since_last_check = (
                    (now - last_position_check).total_seconds()
                    if last_position_check else 999999
                )
                
                if time_since_last_check >= POSITION_CHECK_INTERVAL:
                    logger.info("")
                    logger.info("-" * 70)
                    logger.info("🔍 POSITION MONITORING")
                    logger.info("-" * 70)
                    
                    if run_scheduler('--monitor'):
                        last_position_check = now
                        logger.info("✅ Position check completed")
                    else:
                        logger.error("❌ Position check failed")
                else:
                    remaining = int(POSITION_CHECK_INTERVAL - time_since_last_check)
                    logger.info(f"   Next position check in {remaining}s")
            else:
                logger.info("   Outside market hours - position monitoring paused")
            
            # Reset error counter on successful iteration
            consecutive_errors = 0
            
            # Sleep until next check (1 minute interval for time precision)
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
            
            # Exponential backoff on repeated errors
            sleep_time = min(60 * consecutive_errors, 600)  # Max 10 min
            logger.info(f"   Waiting {sleep_time}s before retry (error count: {consecutive_errors})")
            time.sleep(sleep_time)
            
            # If too many consecutive errors, exit for systemd to restart
            if consecutive_errors >= 10:
                logger.error("Too many consecutive errors, exiting for restart")
                sys.exit(1)
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("🛑 CONTINUOUS MONITORING SERVICE STOPPED")
    logger.info(f"Stopped at: {datetime.now(TIMEZONE)}")
    logger.info(f"Total iterations: {iteration}")
    logger.info("=" * 70)


def main():
    """Entry point."""
    # Register signal handlers for graceful shutdown
    sig.signal(sig.SIGTERM, signal_handler)
    sig.signal(sig.SIGINT, signal_handler)
    
    try:
        # Verify working directory
        if not os.path.exists(WORKING_DIR):
            logger.error(f"Working directory not found: {WORKING_DIR}")
            sys.exit(1)
        
        os.chdir(WORKING_DIR)
        logger.info(f"Working directory set to: {WORKING_DIR}")
        
        # Check for required files
        scheduler_path = os.path.join(WORKING_DIR, 'run_calendar_scheduler.py')
        if not os.path.exists(scheduler_path):
            logger.warning(f"Scheduler not found at: {scheduler_path}")
        
        # Start monitoring
        run_continuous_monitor()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
