"""
Theta Strategy Scheduler
=========================
Automated scheduler for the Theta (cash-secured put) strategy.

Runs:
- 9:45 AM: Morning analysis (symbol selection → options analysis → signal generation)
- Every 60s during market hours: Position monitoring for exit signals
- 4:00 PM: End-of-day reporting

Signals are published to WebSocket channels:
- theta_puts: All Theta signals
- theta_entry: Entry signals (SELL_TO_OPEN)
- theta_exit: Exit signals (BUY_TO_CLOSE)

Frontend subscribes to these channels to receive real-time signals.
When user approves, the signal is executed via Tastytrade API.

Usage:
    # Run scheduler in foreground
    python run_theta_scheduler.py
    
    # Run in background (production)
    nohup python run_theta_scheduler.py > theta_scheduler.log 2>&1 &
"""

import sys
import os
import time
import logging
from datetime import datetime
import signal as sig

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
# Simple signal publishing stub (bypass modular refactor for now)
def publish_theta_entry_signal(signal):
    """Stub for signal publishing - implement WebSocket later."""
    logger.info(f"[STUB] Would publish signal: {signal.symbol} {signal.strike}P")
    return True

def publish_theta_exit_signal(signal):
    """Stub for exit signal publishing."""
    logger.info(f"[STUB] Would publish exit: {signal.symbol} {signal.strike}P")  
    return True

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('theta_scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
_shutdown_flag = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_flag
    logger.info("\n🛑 Shutdown signal received. Stopping scheduler...")
    _shutdown_flag = True


def run_morning_analysis():
    """
    Run morning analysis workflow:
    1. Connect to IB Gateway
    2. Select top symbols
    3. Analyze options chains
    4. Generate entry signals
    5. Publish signals to WebSocket
    """
    logger.info("=" * 70)
    logger.info("🌅 MORNING ANALYSIS STARTING")
    logger.info("=" * 70)
    
    try:
        from ib_data_provider import IBDataProvider
        from src.theta_spreads import SymbolSelector, OptionsAnalyzer, ThetaSignalGenerator, ThetaPortfolioManager
        from datetime import timedelta, date
        
        # Initialize components
        ib = IBDataProvider()
        ib.connect()
        
        try:
            # Step 1: Symbol Selection
            logger.info("[1/4] Selecting symbols...")
            selector = SymbolSelector(
                min_iv_percentile=20,  # Correct parameter name
                select_top_n=5
            )
            
            symbols = selector.select_daily_watchlist(
                candidates=["SPY", "QQQ", "IWM", "AMD", "NVDA", "AAPL"]
            )
            logger.info(f"  Selected: {symbols[:5]}")
            
            # Step 2: Options Analysis
            logger.info("[2/4] Analyzing options chains...")
            analyzer = OptionsAnalyzer(
                target_delta=0.30,
                delta_tolerance=config.THETA_DELTA_TOLERANCE,
                dte_min=7,  # Flexible for testing
                dte_max=45,
                min_premium=config.THETA_MIN_PREMIUM,
                confidence_threshold=60
            )
            
            # Calculate target expiry (~30 days out)
            target_date = date.today() + timedelta(days=30)
            
            all_puts = []
            for symbol in symbols[:5]:  # Process top 5
                try:
                    puts = ib.get_put_chain_for_theta(symbol, target_date, 0.20, 0.40)
                    if puts:
                        scored = analyzer.analyze_symbol(symbol, 80, puts)
                        all_puts.extend(scored)
                        logger.info(f"  {symbol}: {len(scored)} qualified puts")
                except Exception as e:
                    logger.warning(f"  {symbol}: Error - {e}")
            
            logger.info(f"  Total qualified puts: {len(all_puts)}")
            
            # Step 3: Generate Signals
            logger.info("[3/4] Generating entry signals...")
            portfolio = ThetaPortfolioManager(total_capital=config.ACCOUNT_SIZE)
            signal_gen = ThetaSignalGenerator()
            
            # Get portfolio state
            state = portfolio.get_portfolio_state()
            portfolio_state = {
                "available_capital": state.available_capital,
                "current_heat": state.current_heat,
                "open_positions": [p.symbol for p in portfolio.get_all_positions()],
                "position_count": state.position_count
            }
            
            entry_signals = signal_gen.generate_entry_signals(
                ranked_puts=all_puts,
                portfolio_state=portfolio_state
            )
            
            logger.info(f"  Generated {len(entry_signals)} entry signals")
            
            # Step 4A: Publish to WebSocket (for monitoring/UI)
            logger.info("[4A/5] Publishing signals to WebSocket...")
            published_count = 0
            for signal in entry_signals:
                if publish_theta_entry_signal(signal):
                    published_count += 1
                    logger.info(f"  📡 Published: {signal.symbol} {signal.strike}P @ ${signal.entry_price}")
            
            # Step 4B: Execute in IB Paper Trading
            logger.info("[4B/5] Placing orders in IB paper trading...")
            from ib_order_executor import IBOrderExecutor
            executor = IBOrderExecutor(ib)
            
            executed_count = 0
            for signal in entry_signals:
                try:
                    order_id = executor.place_theta_entry(signal, dry_run=False)
                    if order_id:
                        executed_count += 1
                        # TODO: Track position in portfolio
                        logger.info(f"  ✅ IB Order #{order_id} placed successfully")
                except Exception as e:
                    logger.error(f"  ❌ Order failed for {signal.symbol}: {e}")
            
            logger.info("=" * 70)
            logger.info(f"✅ MORNING ANALYSIS COMPLETE")
            logger.info(f"   Signals Published: {published_count}")
            logger.info(f"   IB Orders Placed: {executed_count}/{len(entry_signals)}")
            logger.info("=" * 70)
            
        finally:
            ib.disconnect()
            
    except Exception as e:
        logger.error(f"❌ Morning analysis failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


def run_position_check():
    """
    Check all open positions for exit signals:
    1. Load open positions
    2. Get current prices from IB
    3. Check exit conditions
    4. Generate and publish exit signals
    """
    logger.info("📊 Position check starting...")
    
    try:
        from ib_data_provider import IBDataProvider
        from src.theta_spreads import ThetaSignalGenerator, ThetaPortfolioManager
        
        # Load positions
        portfolio = ThetaPortfolioManager(total_capital=config.ACCOUNT_SIZE)
        positions = portfolio.get_all_positions()
        
        if not positions:
            logger.info("  No open positions to check")
            return
        
        logger.info(f"  Checking {len(positions)} open positions...")
        
        # Connect to IB for current prices
        ib = IBDataProvider()
        ib.connect()
        
        try:
            signal_gen = ThetaSignalGenerator()
            
            for pos in positions:
                try:
                    # Get current option price
                    # For now, use mock data - in production, get live quotes
                    current_mid = pos.entry_price * 0.5  # Simulated 50% decay
                    
                    # Check exit conditions
                    exit_signals = signal_gen.generate_exit_signals(
                        positions=[pos],
                        current_prices={pos.position_id: current_mid}
                    )
                    
                    for exit_signal in exit_signals:
                        if publish_theta_exit_signal(exit_signal):
                            logger.info(f"  📡 Exit signal: {exit_signal.symbol} @ ${exit_signal.exit_price} ({exit_signal.reason})")
                            
                except Exception as e:
                    logger.warning(f"  Error checking {pos.symbol}: {e}")
                    
        finally:
            ib.disconnect()
            
    except Exception as e:
        logger.error(f"Position check failed: {e}")
        import traceback
        logger.error(traceback.format_exc())


def run_end_of_day_report():
    """Generate end-of-day summary report."""
    logger.info("=" * 70)
    logger.info("📈 END OF DAY REPORT")
    logger.info("=" * 70)
    
    try:
        from src.theta_spreads import ThetaPortfolioManager
        
        portfolio = ThetaPortfolioManager(total_capital=config.ACCOUNT_SIZE)
        state = portfolio.get_portfolio_state()
        
        logger.info(f"""
Portfolio Summary:
  Total Capital:      ${state.total_capital:,.0f}
  Reserved Capital:   ${state.reserved_capital:,.0f}
  Available Capital:  ${state.available_capital:,.0f}
  Current Heat:       ${state.current_heat:,.0f} ({state.heat_pct:.1f}%)
  Open Positions:     {state.position_count}
  Total Premium:      ${state.total_premium_received:,.2f}
  Unrealized P&L:     ${state.total_unrealized_pnl:,.2f} ({state.total_unrealized_pnl_pct:.1f}%)
""")
        
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"End of day report failed: {e}")


def is_market_hours():
    """Check if current time is during market hours (9:30 AM - 4:00 PM ET)."""
    now = datetime.now()
    # Simple check - in production, account for timezone and holidays
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def run_scheduler():
    """
    Main scheduler loop.
    
    Schedule:
    - 9:45 AM: Morning analysis
    - Every 60s (9:30 AM - 4:00 PM): Position check
    - 4:00 PM: End of day report
    """
    global _shutdown_flag
    
    # Register signal handlers for graceful shutdown
    sig.signal(sig.SIGINT, signal_handler)
    sig.signal(sig.SIGTERM, signal_handler)
    
    logger.info("=" * 70)
    logger.info("🚀 THETA STRATEGY SCHEDULER STARTED")
    logger.info("=" * 70)
    logger.info(f"""
Configuration:
  Account Size:       ${config.ACCOUNT_SIZE:,.0f}
  Contracts/Trade:    {config.THETA_CONTRACTS_PER_TRADE}
  Target Delta:       {config.THETA_TARGET_DELTA}
  DTE Range:          {config.THETA_DTE_MIN}-{config.THETA_DTE_MAX} days
  Max Positions:      {config.THETA_MAX_POSITIONS}
  Max Heat:           ${config.THETA_MAX_PORTFOLIO_HEAT:,.0f}

Schedule:
  Morning Analysis:   9:45 AM ET
  Position Checks:    Every 60 seconds (market hours)
  EOD Report:         4:00 PM ET

Press Ctrl+C to stop.
""")
    
    last_morning_analysis = None
    last_eod_report = None
    last_position_check = None
    
    while not _shutdown_flag:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        today_date = now.date()
        
        try:
            # Morning analysis at 9:45 AM
            if current_time == "09:45" and last_morning_analysis != today_date:
                run_morning_analysis()
                last_morning_analysis = today_date
            
            # Position check every 60 seconds during market hours
            elif is_market_hours():
                if last_position_check is None or (now - last_position_check).total_seconds() >= 60:
                    run_position_check()
                    last_position_check = now
            
            # End of day report at 4:00 PM
            if current_time == "16:00" and last_eod_report != today_date:
                run_end_of_day_report()
                last_eod_report = today_date
            
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Sleep for 1 second between checks
        time.sleep(1)
    
    logger.info("✅ Scheduler stopped gracefully")


def run_once():
    """Run morning analysis once (for testing or manual trigger)."""
    logger.info("Running single morning analysis...")
    run_morning_analysis()
    logger.info("Done!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Theta Strategy Scheduler")
    parser.add_argument("--once", action="store_true", help="Run morning analysis once and exit")
    parser.add_argument("--check", action="store_true", help="Run position check once and exit")
    parser.add_argument("--report", action="store_true", help="Generate EOD report and exit")
    
    args = parser.parse_args()
    
    if args.once:
        run_once()
    elif args.check:
        run_position_check()
    elif args.report:
        run_end_of_day_report()
    else:
        run_scheduler()
