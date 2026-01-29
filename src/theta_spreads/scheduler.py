"""
Theta Strategy Scheduler
========================

Automated scheduling for Theta strategy workflows:
- 9:45 AM: Morning analysis (symbol selection, options analysis, entry signals)
- Every 60s (9:30 AM - 4:00 PM): Position monitoring, exit signal checks
- 4:00 PM: End-of-day report generation

Uses APScheduler for reliable task scheduling.
"""

import logging
from datetime import datetime, time
from typing import Optional, Callable
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

logger = logging.getLogger(__name__)

# Market hours (Eastern Time)
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
MORNING_ANALYSIS_TIME = time(9, 45)
EOD_REPORT_TIME = time(16, 0)
TIMEZONE = pytz.timezone('US/Eastern')


class ThetaScheduler:
    """
    Manages automated execution of Theta strategy workflows.
    
    Usage:
        scheduler = ThetaScheduler()
        scheduler.start()
        
        # To stop:
        scheduler.stop()
    """
    
    def __init__(
        self,
        morning_analysis_callback: Optional[Callable] = None,
        position_monitor_callback: Optional[Callable] = None,
        eod_report_callback: Optional[Callable] = None,
        monitor_interval_seconds: int = 60
    ):
        """
        Initialize scheduler.
        
        Args:
            morning_analysis_callback: Function to run at 9:45 AM
            position_monitor_callback: Function to run every 60 seconds during market hours
            eod_report_callback: Function to run at 4:00 PM
            monitor_interval_seconds: Interval for position monitoring (default: 60s)
        """
        self.scheduler = BackgroundScheduler(timezone=TIMEZONE)
        self.morning_analysis_callback = morning_analysis_callback or self._default_morning_analysis
        self.position_monitor_callback = position_monitor_callback or self._default_position_monitor
        self.eod_report_callback = eod_report_callback or self._default_eod_report
        self.monitor_interval = monitor_interval_seconds
        self._is_running = False
    
    def start(self):
        """Start the scheduler with all configured jobs."""
        if self._is_running:
            logger.warning("Scheduler is already running")
            return
        
        # Morning Analysis - 9:45 AM Eastern, Monday-Friday
        self.scheduler.add_job(
            self._run_morning_analysis,
            CronTrigger(
                hour=9, minute=45,
                day_of_week='mon-fri',
                timezone=TIMEZONE
            ),
            id='morning_analysis',
            name='Theta Morning Analysis',
            replace_existing=True
        )
        
        # Position Monitoring - Every 60 seconds during market hours
        self.scheduler.add_job(
            self._run_position_monitor,
            IntervalTrigger(seconds=self.monitor_interval),
            id='position_monitor',
            name='Theta Position Monitor',
            replace_existing=True
        )
        
        # End of Day Report - 4:00 PM Eastern, Monday-Friday
        self.scheduler.add_job(
            self._run_eod_report,
            CronTrigger(
                hour=16, minute=0,
                day_of_week='mon-fri',
                timezone=TIMEZONE
            ),
            id='eod_report',
            name='Theta EOD Report',
            replace_existing=True
        )
        
        self.scheduler.start()
        self._is_running = True
        logger.info("Theta Scheduler started")
        self._log_next_runs()
    
    def stop(self):
        """Stop the scheduler."""
        if not self._is_running:
            logger.warning("Scheduler is not running")
            return
        
        self.scheduler.shutdown(wait=False)
        self._is_running = False
        logger.info("Theta Scheduler stopped")
    
    def run_morning_analysis_now(self):
        """Manually trigger morning analysis."""
        logger.info("Manual trigger: Morning Analysis")
        self._run_morning_analysis()
    
    def run_position_check_now(self):
        """Manually trigger position monitoring."""
        logger.info("Manual trigger: Position Monitor")
        self._run_position_monitor()
    
    def _is_market_hours(self) -> bool:
        """Check if current time is within market hours."""
        now = datetime.now(TIMEZONE)
        
        # Check if weekday (Monday = 0, Sunday = 6)
        if now.weekday() >= 5:
            return False
        
        current_time = now.time()
        return MARKET_OPEN <= current_time <= MARKET_CLOSE
    
    def _run_morning_analysis(self):
        """Execute morning analysis workflow."""
        try:
            logger.info("="*60)
            logger.info("THETA MORNING ANALYSIS - Starting")
            logger.info("="*60)
            
            self.morning_analysis_callback()
            
            logger.info("THETA MORNING ANALYSIS - Complete")
            
        except Exception as e:
            logger.error(f"Morning analysis failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _run_position_monitor(self):
        """Execute position monitoring (only during market hours)."""
        if not self._is_market_hours():
            return
        
        try:
            self.position_monitor_callback()
            
        except Exception as e:
            logger.error(f"Position monitoring failed: {e}")
    
    def _run_eod_report(self):
        """Execute end-of-day report."""
        try:
            logger.info("="*60)
            logger.info("THETA EOD REPORT - Generating")
            logger.info("="*60)
            
            self.eod_report_callback()
            
            logger.info("THETA EOD REPORT - Complete")
            
        except Exception as e:
            logger.error(f"EOD report failed: {e}")
    
    def _log_next_runs(self):
        """Log next scheduled run times."""
        jobs = self.scheduler.get_jobs()
        logger.info("\nScheduled Jobs:")
        for job in jobs:
            next_run = job.next_run_time
            if next_run:
                logger.info(f"  {job.name}: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    def _default_morning_analysis(self):
        """Default morning analysis implementation."""
        from .symbol_selector import SymbolSelector
        from .options_analyzer import OptionsAnalyzer
        from .signal_generator import ThetaSignalGenerator
        from .portfolio_manager import ThetaPortfolioManager
        
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        
        try:
            from ib_data_provider import IBDataProvider
            from signal_publisher import publish_theta_entry_signal
            import config
        except ImportError as e:
            logger.warning(f"Some imports unavailable: {e}")
            return
        
        # Initialize components
        selector = SymbolSelector(
            min_iv_percentile=config.THETA_MIN_IV_PERCENTILE,
            select_top_n=config.THETA_SELECT_TOP_N
        )
        
        analyzer = OptionsAnalyzer(
            target_delta=config.THETA_TARGET_DELTA,
            delta_tolerance=config.THETA_DELTA_TOLERANCE,
            dte_min=config.THETA_DTE_MIN,
            dte_max=config.THETA_DTE_MAX,
            min_premium=config.THETA_MIN_PREMIUM,
            min_liquidity=config.THETA_MIN_LIQUIDITY,
            confidence_threshold=config.THETA_MIN_CONFIDENCE
        )
        
        generator = ThetaSignalGenerator(
            contracts_per_trade=config.THETA_CONTRACTS_PER_TRADE,
            max_positions=config.THETA_MAX_POSITIONS,
            max_portfolio_heat=config.THETA_MAX_PORTFOLIO_HEAT,
            min_confidence=config.THETA_MIN_CONFIDENCE,
            week1_profit_pct=config.THETA_WEEK1_PROFIT_PCT,
            week2_profit_pct=config.THETA_WEEK2_PROFIT_PCT,
            week3_profit_pct=config.THETA_WEEK3_PROFIT_PCT,
            week4_profit_pct=config.THETA_WEEK4_PROFIT_PCT
        )
        
        portfolio = ThetaPortfolioManager(total_capital=config.ACCOUNT_SIZE)
        
        # Connect to IB Gateway
        ib = IBDataProvider()
        try:
            ib.connect()
            
            # Step 1: Symbol Selection
            logger.info("Step 1: Selecting watchlist...")
            current_positions = [p.symbol for p in portfolio.get_all_positions()]
            watchlist = selector.select_daily_watchlist(
                candidates=config.THETA_UNIVERSE,
                current_positions=current_positions
            )
            
            # Step 2: Options Analysis
            logger.info("Step 2: Analyzing options chains...")
            from .options_analyzer import get_available_expirations
            expirations = get_available_expirations(config.THETA_DTE_MIN, config.THETA_DTE_MAX)
            
            all_puts = []
            for symbol in watchlist:
                for exp in expirations:
                    try:
                        options = ib.get_options(symbol, exp, option_type="put")
                        scored = analyzer.analyze_symbol(symbol, 75, options)
                        all_puts.extend(scored)
                    except Exception as e:
                        logger.warning(f"Error analyzing {symbol}: {e}")
            
            all_puts.sort(key=lambda x: x.total_score, reverse=True)
            
            # Step 3: Generate Entry Signals
            logger.info("Step 3: Generating entry signals...")
            state = portfolio.get_portfolio_state()
            portfolio_dict = {
                "available_capital": state.available_capital,
                "current_heat": state.current_heat,
                "open_positions": state.open_symbols,
                "position_count": state.position_count
            }
            
            entry_signals = generator.generate_entry_signals(all_puts, portfolio_dict)
            
            # Step 4: Publish Signals
            logger.info("Step 4: Publishing entry signals...")
            for signal in entry_signals:
                publish_theta_entry_signal(signal)
            
            logger.info(f"Morning analysis complete: {len(entry_signals)} new signals")
            
        finally:
            ib.disconnect()
    
    def _default_position_monitor(self):
        """Default position monitoring implementation."""
        from .signal_generator import ThetaSignalGenerator
        from .portfolio_manager import ThetaPortfolioManager
        
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        
        try:
            from ib_data_provider import IBDataProvider
            from signal_publisher import publish_theta_exit_signal
            import config
        except ImportError as e:
            logger.warning(f"Some imports unavailable: {e}")
            return
        
        generator = ThetaSignalGenerator(
            week1_profit_pct=config.THETA_WEEK1_PROFIT_PCT,
            week2_profit_pct=config.THETA_WEEK2_PROFIT_PCT,
            week3_profit_pct=config.THETA_WEEK3_PROFIT_PCT,
            week4_profit_pct=config.THETA_WEEK4_PROFIT_PCT,
            dte_expiration_threshold=config.THETA_EXPIRATION_THRESHOLD,
            defensive_breach_pct=config.THETA_DEFENSIVE_BREACH_PCT
        )
        
        portfolio = ThetaPortfolioManager(total_capital=config.ACCOUNT_SIZE)
        
        positions = portfolio.get_all_positions()
        if not positions:
            return
        
        # Connect to IB for current prices
        ib = IBDataProvider()
        try:
            ib.connect()
            
            # Update Greeks and check for exits
            open_positions = []
            current_prices = {}
            
            for position in positions:
                try:
                    # Get current option price
                    occ_symbol = f"{position.symbol}{position.expiration.strftime('%y%m%d')}P{int(position.strike * 1000):08d}"
                    quote = ib.get_option_price_by_symbol(occ_symbol)
                    
                    if quote:
                        bid, ask, mid = quote
                        portfolio.update_position_greeks(position.position_id, {
                            "bid": bid,
                            "ask": ask
                        })
                        
                        open_positions.append({
                            "position_id": position.position_id,
                            "symbol": position.symbol,
                            "strike": position.strike,
                            "entry_price": position.entry_price,
                            "entry_date": position.entry_date,
                            "expiration": position.expiration,
                            "contracts": position.contracts,
                            "current_bid": bid,
                            "current_ask": ask
                        })
                    
                    # Get underlying price for defensive exits
                    stock_price = ib.get_price(position.symbol)
                    if stock_price:
                        current_prices[position.symbol] = stock_price
                        
                except Exception as e:
                    logger.warning(f"Error updating {position.symbol}: {e}")
            
            # Generate exit signals
            exit_signals = generator.generate_exit_signals(open_positions, current_prices)
            
            # Publish exit signals
            for signal in exit_signals:
                publish_theta_exit_signal(signal)
                logger.info(f"EXIT SIGNAL: {signal.symbol} {signal.strike}P - {signal.reason.value}")
            
        finally:
            ib.disconnect()
    
    def _default_eod_report(self):
        """Default end-of-day report implementation."""
        from .portfolio_manager import ThetaPortfolioManager
        
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        
        try:
            import config
        except ImportError:
            return
        
        portfolio = ThetaPortfolioManager(total_capital=config.ACCOUNT_SIZE)
        state = portfolio.get_portfolio_state()
        
        logger.info("\n" + "="*60)
        logger.info("THETA STRATEGY - END OF DAY REPORT")
        logger.info("="*60)
        logger.info(f"Date: {datetime.now(TIMEZONE).strftime('%Y-%m-%d')}")
        logger.info("-"*60)
        logger.info("PORTFOLIO SUMMARY")
        logger.info(f"  Total Capital: ${state.total_capital:,.0f}")
        logger.info(f"  Reserved: ${state.reserved_capital:,.0f}")
        logger.info(f"  Available: ${state.available_capital:,.0f}")
        logger.info(f"  Heat: {state.heat_pct:.1f}%")
        logger.info("-"*60)
        logger.info("POSITIONS")
        logger.info(f"  Open Positions: {state.position_count}")
        logger.info(f"  Total Premium: ${state.total_premium_received:,.0f}")
        logger.info(f"  Unrealized P&L: ${state.total_unrealized_pnl:,.0f} ({state.total_unrealized_pnl_pct:.1f}%)")
        logger.info("-"*60)
        
        for pos in state.positions:
            logger.info(f"  {pos.symbol} {pos.strike}P | Entry: ${pos.entry_price:.2f} | "
                       f"P&L: ${pos.unrealized_pnl:.0f} ({pos.unrealized_pnl_pct:.1f}%)")
        
        logger.info("="*60 + "\n")


def create_default_scheduler() -> ThetaScheduler:
    """Create scheduler with default callbacks."""
    return ThetaScheduler()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("Starting Theta Scheduler...")
    print("Press Ctrl+C to stop")
    
    scheduler = create_default_scheduler()
    scheduler.start()
    
    try:
        # Keep running
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.stop()
        print("Scheduler stopped")
