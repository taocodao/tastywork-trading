#!/usr/bin/env python3
"""
Theta Sprint - Continuous Monitoring Service

Simple wrapper that runs the existing run_theta_scheduler.py on schedule:
- Morning analysis at 9:35 AM ET (new entries)
- Position monitoring every 5 minutes (exits)
- Runs 24/7
"""

import subprocess
import time
import logging
from datetime import datetime
import pytz
import signal as sig

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
MORNING_ANALYSIS_HOUR = 9
MORNING_ANALYSIS_MINUTE = 35
POSITION_CHECK_INTERVAL = 300  # 5 minutes
TIMEZONE = pytz.timezone('America/New_York')

# Global flag for graceful shutdown
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_requested = True

def run_scheduler():
    """Run the theta scheduler once."""
    import os
    try:
        logger.info("Running theta scheduler...")
        # Use current script's directory as CWD
        cwd = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run(
            ['python3', 'run_theta_scheduler.py', '--once'],  # Must use 'python3' on Ubuntu EC2
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            logger.info("✅ Scheduler completed successfully")
            if result.stdout:
                logger.info(f"Output: {result.stdout[-500:]}")  # Last 500 chars
        else:
            logger.error(f"❌ Scheduler failed with code {result.returncode}")
            if result.stderr:
                logger.error(f"Error: {result.stderr[-500:]}")
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        logger.error("❌ Scheduler timed out after 5 minutes")
        return False
    except Exception as e:
        logger.error(f"❌ Error running scheduler: {e}")
        return False

def run_continuous_monitor():
    """Main continuous monitoring loop."""
    
    logger.info("="*70)
    logger.info("🚀 THETA SPRINT - CONTINUOUS MONITORING SERVICE")
    logger.info("="*70)
    logger.info(f"Started at: {datetime.now(TIMEZONE)}")
    logger.info(f"Morning analysis: {MORNING_ANALYSIS_HOUR}:{MORNING_ANALYSIS_MINUTE:02d} ET")
    logger.info(f"Position check interval: {POSITION_CHECK_INTERVAL}s (5 min)")
    logger.info("="*70)
    
    last_morning_analysis = None
    last_position_check = None
    iteration = 0
    
    while not shutdown_requested:
        try:
            iteration += 1
            now = datetime.now(TIMEZONE)
            current_date = now.date()
            current_hour = now.hour
            current_minute = now.minute
            
            logger.info(f"\n[Iteration {iteration}] {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            # 1. Check if it's time for morning analysis
            is_morning_time = (current_hour == MORNING_ANALYSIS_HOUR and 
                             current_minute == MORNING_ANALYSIS_MINUTE)
            
            if is_morning_time and last_morning_analysis != current_date:
                logger.info("⏰ TIME FOR MORNING ANALYSIS")
                logger.info("="*70)
                
                success = run_scheduler()
                if success:
                    last_morning_analysis = current_date
                    logger.info("✅ Morning analysis complete")
                else:
                    logger.error("❌ Morning analysis failed - will retry tomorrow")
            
            # 2. Monitor existing positions (every 5 minutes)
            time_since_last_check = (
                (now - last_position_check).total_seconds() 
                if last_position_check else 999999
            )
            
            if time_since_last_check >= POSITION_CHECK_INTERVAL:
                logger.info("🔍 MONITORING POSITIONS (running scheduler)")
                logger.info("-"*70)
                
                success = run_scheduler()
                if success:
                    last_position_check = now
                    logger.info("✅ Position check complete")
                else:
                    logger.error("❌ Position check failed")
            
            # 3. Sleep until next check
            # Check every minute to catch morning analysis time
            sleep_seconds = 60
            logger.info(f"⏸  Sleeping {sleep_seconds}s until next check...")
            time.sleep(sleep_seconds)
            
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except Exception as e:
            logger.error(f"❌ Unexpected error in main loop: {e}")
            import traceback
            traceback.print_exc()
            logger.info("Waiting 60s before retry...")
            time.sleep(60)
    
    logger.info("="*70)
    logger.info("🛑 CONTINUOUS MONITORING SERVICE STOPPED")
    logger.info(f"Stopped at: {datetime.now(TIMEZONE)}")
    logger.info("="*70)


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    sig.signal(sig.SIGTERM, signal_handler)
    sig.signal(sig.SIGINT, signal_handler)
    
    try:
        run_continuous_monitor()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        import sys
        sys.exit(1)
