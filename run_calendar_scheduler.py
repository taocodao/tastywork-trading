"""
Calendar Spread Strategy Scheduler
===================================
Continuous scheduler for calendar spread trading using IB Gateway paper trading.

Similar to Theta scheduler but for calendar spreads:
- Entry: 3:50 PM daily (scan for best setups)
- Exit: 9:35 AM daily (check positions)
- Runs continuously during market hours
"""

import logging
import time
from datetime import datetime, time as dt_time
from typing import Optional
import sys

# Add src to path
sys.path.insert(0, '.')

from scanner import CalendarSpreadScanner, check_vix_filter, SpreadSetup
from position_manager import PositionManager, ExitReason
from risk_manager import RiskManager
from greeks_calculator import SpreadCalculator
from ib_data_provider import IBDataProvider
from config import ACCOUNT_SIZE, UNDERLYINGS

# Setup logging (no emojis for Windows)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CalendarSpreadScheduler:
    """
    Automated scheduler for calendar spread trading.
    
    Schedule:
    - 3:50 PM: Scan for entry opportunities
    - 9:35 AM: Monitor and exit positions
    - Every 60 seconds: Update position values
    """
    
    def __init__(self, host: str = "34.235.119.67", port: int = 4004):
        """Initialize scheduler with EC2 IB Gateway connection."""
        self.host = host
        self.port = port
        
        # Initialize components
        self.ib_provider = IBDataProvider(host=host, port=port, client_id=6000)
        self.scanner = CalendarSpreadScanner(data_provider=self.ib_provider)
        self.position_manager = PositionManager()
        self.risk_manager = RiskManager(account_size=ACCOUNT_SIZE)
        self.calculator = SpreadCalculator()
        
        self.running = False
        
    def is_market_hours(self) -> bool:
        """Check if market is open (9:30 AM - 4:00 PM ET)."""
        now = datetime.now()
        current_time = now.time()
        
        # Market hours: 9:30 AM - 4:00 PM ET
        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)
        
        # Check if weekday
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
            
        return market_open <= current_time <= market_close
    
    def is_entry_window(self) -> bool:
        """Check if in entry window (3:50 PM - 3:59 PM)."""
        current_time = datetime.now().time()
        return dt_time(15, 50) <= current_time <= dt_time(15, 59)
    
    def is_exit_window(self) -> bool:
        """Check if in exit window (9:30 AM - 10:00 AM)."""
        current_time = datetime.now().time()
        return dt_time(9, 30) <= current_time <= dt_time(10, 0)
    
    def scan_and_enter(self) -> None:
        """Scan for opportunities and enter best setup."""
        logger.info("=" * 70)
        logger.info("ENTRY WINDOW: Scanning for calendar spread opportunities")
        logger.info("=" * 70)
        
        # Check VIX filter
        vix_ok, vix = check_vix_filter()
        logger.info(f"VIX: {vix:.1f} - {'OK' if vix_ok else 'SKIP (too high)'}")
        
        if not vix_ok:
            logger.info("Market conditions not suitable for calendar spreads")
            return
        
        # Check position limit
        open_positions = len(self.position_manager.get_open_positions())
        if open_positions >= 3:
            logger.info(f"Max positions reached ({open_positions}/3), skipping entry")
            return
        
        # Scan for setups
        try:
            setups = self.scanner.scan_all()
            
            if not setups:
                logger.info("No suitable opportunities found")
                return
            
            # Get best setup
            best_setup = setups[0]  # Already sorted by score
            
            logger.info(f"Found {len(setups)} opportunities, best: {best_setup.symbol}")
            logger.info(f"  Strike: ${best_setup.strike}")
            logger.info(f"  Net Debit: ${best_setup.net_debit:.2f}")
            logger.info(f"  Theta Edge: ${best_setup.theta_edge:.2f}/day")
            logger.info(f"  Score: {best_setup.score:.1f}")
            
            # Risk check
            risk_check = self.risk_manager.check_can_trade(
                trade_cost=best_setup.net_debit,
                current_positions=open_positions,
                vix=vix if vix_ok else None
            )
            
            if not risk_check.passed:
                logger.warning(f"Risk check failed: {risk_check.reason}")
                return
            
            # Calculate position size
            contracts = self.risk_manager.calculate_position_size(best_setup.net_debit)
            
            # Open position (paper trading - logged only)
            position = self.position_manager.open_position(best_setup, contracts)
            
            logger.info("=" * 70)
            logger.info(f"POSITION OPENED (PAPER): {best_setup.symbol} ${best_setup.strike} x{contracts}")
            logger.info(f"  Entry Debit: ${best_setup.net_debit:.2f}")
            logger.info(f"  Profit Target: ${position.profit_target:.2f}")
            logger.info(f"  Stop Loss: ${position.stop_loss:.2f}")
            logger.info("=" * 70)
            
        except Exception as e:
            logger.error(f"Error during scan/entry: {e}", exc_info=True)
    
    def monitor_and_exit(self) -> None:
        """Monitor positions and exit if targets hit."""
        logger.info("=" * 70)
        logger.info("EXIT WINDOW: Monitoring positions")
        logger.info("=" * 70)
        
        positions = self.position_manager.get_open_positions()
        
        if not positions:
            logger.info("No open positions to monitor")
            return
        
        logger.info(f"Monitoring {len(positions)} position(s)")
        
        for pos in positions:
            # Simulate position value update (in production, fetch from IB)
            hours_held = (datetime.now() - datetime.fromisoformat(pos.entry_time)).total_seconds() / 3600
            
            # Simulate theta decay (calendar spreads gain ~5-8% from theta in 1-3 days)
            simulated_gain_pct = min(8, hours_held * 0.3)  # ~0.3%/hour
            new_value = pos.entry_debit * (1 + simulated_gain_pct / 100)
            
            self.position_manager.update_position(pos.id, new_value)
            
            logger.info(f"Position {pos.id}: {pos.symbol} ${pos.strike}")
            logger.info(f"  Entry: ${pos.entry_debit:.2f} ({hours_held:.1f}h ago)")
            logger.info(f"  Current: ${new_value:.2f} ({pos.pnl_pct:+.1f}%)")
            logger.info(f"  Target: ${pos.profit_target:.2f} | Stop: ${pos.stop_loss:.2f}")
            
            # Check exit conditions
            exit_signal = self.position_manager.check_exit_conditions(pos)
            
            if exit_signal.should_exit:
                logger.info(f"  EXIT SIGNAL: {exit_signal.message}")
                
                # Close position
                self.position_manager.close_position(
                    pos.id,
                    new_value,
                    exit_signal.reason
                )
                
                self.risk_manager.update_pnl(pos.realized_pnl or 0)
                
                logger.info("=" * 70)
                logger.info(f"POSITION CLOSED: {pos.symbol} ${pos.strike}")
                logger.info(f"  Realized P&L: ${pos.realized_pnl:.2f} ({pos.pnl_pct:+.1f}%)")
                logger.info(f"  Exit Reason: {exit_signal.reason}")
                logger.info("=" * 70)
            else:
                logger.info(f"  Status: HOLD")
    
    def update_positions(self) -> None:
        """Update position values every 60 seconds during market hours."""
        positions = self.position_manager.get_open_positions()
        
        if not positions:
            return
        
        for pos in positions:
            # Simulate value update
            hours_held = (datetime.now() - datetime.fromisoformat(pos.entry_time)).total_seconds() / 3600
            simulated_gain_pct = min(8, hours_held * 0.3)
            new_value = pos.entry_debit * (1 + simulated_gain_pct / 100)
            
            self.position_manager.update_position(pos.id, new_value)
    
    def run(self) -> None:
        """
        Main scheduler loop.
        Runs continuously, scanning and monitoring during market hours.
        """
        self.running = True
        
        logger.info("=" * 70)
        logger.info("CALENDAR SPREAD SCHEDULER STARTED")
        logger.info("=" * 70)
        logger.info("")
        logger.info("Configuration:")
        logger.info(f"  IB Gateway: {self.host}:{self.port}")
        logger.info(f"  Account Size: ${ACCOUNT_SIZE:,.0f}")
        logger.info(f"  Underlyings: {', '.join(UNDERLYINGS)}")
        logger.info(f"  Max Positions: 3")
        logger.info("")
        logger.info("Schedule:")
        logger.info("  Entry Window: 3:50 PM - 3:59 PM ET")
        logger.info("  Exit Window: 9:30 AM - 10:00 AM ET")
        logger.info("  Position Updates: Every 60 seconds (market hours)")
        logger.info("")
        logger.info("Press Ctrl+C to stop.")
        logger.info("")
        
        entry_executed = False
        exit_executed = False
        
        while self.running:
            try:
                current_time = datetime.now().time()
                
                # Reset daily flags at midnight
                if current_time.hour == 0 and current_time.minute == 0:
                    entry_executed = False
                    exit_executed = False
                
                # Check if market is open
                if not self.is_market_hours():
                    if current_time.hour == 22 and current_time.minute == 0:
                        logger.info("Market closed for the day. Scheduler idle until 9:30 AM ET.")
                    time.sleep(300)  # Check every 5 minutes when market closed
                    continue
                
                # Entry window (3:50 PM - 3:59 PM)
                if self.is_entry_window() and not entry_executed:
                    self.scan_and_enter()
                    entry_executed = True
                
                # Exit window (9:30 AM - 10:00 AM)
                elif self.is_exit_window() and not exit_executed:
                    self.monitor_and_exit()
                    exit_executed = True
                
                # Update positions every 60 seconds during market hours
                else:
                    self.update_positions()
                
                # Sleep for 60 seconds
                time.sleep(60)
                
            except KeyboardInterrupt:
                logger.info("\nShutting down scheduler...")
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                time.sleep(60)
        
        self.running = False
        logger.info("Scheduler stopped.")


def run_scheduler():
    """Main entry point."""
    scheduler = CalendarSpreadScheduler(
        host="34.235.119.67",  # EC2 IB Gateway
        port=4004              # Paper trading port
    )
    
    scheduler.run()


if __name__ == "__main__":
    run_scheduler()
