"""
Position Monitor Daemon
========================
Continuously monitors open positions during market hours (9:30 AM - 4:00 PM ET).
Checks positions every 60 seconds and executes exits based on trailing stop logic.

Usage:
    nohup python3 position_monitor_daemon.py > logs/position_monitor.log 2>&1 &
"""

import time
import logging
from datetime import datetime, time as dt_time
import signal
import sys

from position_monitor import PositionMonitor
from src.theta_spreads.portfolio_manager import ThetaPortfolioManager
from ib_data_provider import IBDataProvider
from ib_order_executor import IBOrderExecutor
import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Graceful shutdown flag
shutdown_flag = False


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global shutdown_flag
    logger.info("\n🛑 Shutdown signal received. Stopping monitor...")
    shutdown_flag = True


def is_market_hours() -> bool:
    """Check if current time is during market hours (9:30 AM - 4:00 PM ET)."""
    now = datetime.now()
    current_time = now.time()
    
    market_open = dt_time(9, 30)   # 9:30 AM
    market_close = dt_time(16, 0)  # 4:00 PM
    
    # Check if weekday
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    
    return market_open <= current_time <= market_close


def run_monitor_cycle():
    """Run one monitoring cycle."""
    logger.info("\n" + "=" * 70)
    logger.info(f"🔄 MONITOR CYCLE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    ib = None
    
    try:
        # Initialize components
        ib = IBDataProvider()
        ib.connect()
        
        portfolio = ThetaPortfolioManager(total_capital=config.THETA_TOTAL_CAPITAL)
        executor = IBOrderExecutor(ib)
        monitor = PositionMonitor(ib, portfolio, executor)
        
        # Check all positions
        monitor.check_all_positions()
        
        logger.info("✅ Monitor cycle complete\n")
        
    except Exception as e:
        logger.error(f"❌ Error in monitor cycle: {e}", exc_info=True)
        
    finally:
        if ib:
            try:
                ib.disconnect()
            except:
                pass


def main():
    """Main daemon loop."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 70)
    logger.info("🚀 POSITION MONITOR DAEMON STARTING")
    logger.info("=" * 70)
    logger.info(f"Monitor frequency: Every 60 seconds")
    logger.info(f"Market hours: 9:30 AM - 4:00 PM ET (weekdays only)")
    logger.info(f"Capital: ${config.THETA_TOTAL_CAPITAL:,.0f}")
    logger.info("=" * 70 + "\n")
    
    check_interval = 60  # seconds
    
    while not shutdown_flag:
        try:
            if is_market_hours():
                run_monitor_cycle()
            else:
                current_time = datetime.now().strftime('%H:%M:%S')
                logger.info(f"⏸️  Outside market hours ({current_time}) - Sleeping...")
            
            # Sleep in small intervals to allow quick shutdown
            for _ in range(check_interval):
                if shutdown_flag:
                    break
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("\n🛑 Keyboard interrupt received")
            break
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}", exc_info=True)
            time.sleep(60)  # Wait before retrying
    
    logger.info("\n" + "=" * 70)
    logger.info("🛑 POSITION MONITOR DAEMON STOPPED")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
