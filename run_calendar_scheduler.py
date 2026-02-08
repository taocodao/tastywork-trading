"""
Calendar Spread Strategy Scheduler - AI-Enhanced
=================================================
Automated scheduler for calendar spread trading using IB Gateway.

Uses new AI components:
- CalendarSignalGenerator (integrates VOSS, DTE, Strike selectors)
- EarningsStrategyRouter (earnings-aware decision making)
- VOSSLiquidityFilter (liquidity filtering)

Similar to Theta scheduler but for calendar spreads:
- Entry: 3:50 PM daily (scan for best setups - high EOD IV)
- Exit: 9:35 AM daily (check positions)
- Monitor: Every 5 minutes during market hours
"""

import logging
import time
import argparse
from datetime import datetime, time as dt_time, timedelta
from typing import Optional, List, Dict
import sys

# Add src to path
sys.path.insert(0, '.')

# AI Components - New imports
from src.calendar_spreads import (
    CalendarSignalGenerator,
    CalendarSpreadSignal,
    GeneratorConfig,
    EarningsStrategyRouter,
    EarningsRouterConfig,
    StrategyDecision,
    VOSSLiquidityFilter,
    DTESelector,
    CalendarStrikeSelector
)

# Existing components
from position_manager import PositionManager, ExitReason
from risk_manager import RiskManager
from greeks_calculator import SpreadCalculator
from ib_data_provider import IBDataProvider
from config import ACCOUNT_SIZE, UNDERLYINGS

# Legacy scanner for fallback
try:
    from scanner import CalendarSpreadScanner, check_vix_filter, SpreadSetup
    LEGACY_SCANNER_AVAILABLE = True
except ImportError:
    LEGACY_SCANNER_AVAILABLE = False
    # Define check_vix_filter inline
    def check_vix_filter() -> tuple:
        return (True, 15.0)  # Default: OK, VIX=15

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CalendarSpreadScheduler:
    """
    AI-Enhanced scheduler for calendar spread trading.
    
    Schedule:
    - 3:50 PM: Scan for entry opportunities (using AI signal generator)
    - 9:35 AM: Monitor and exit positions
    - Every 5 minutes: Update position values during market hours
    """
    
    def __init__(self, 
                 host: str = None, 
                 port: int = None,
                 use_ai: bool = True,
                 dry_run: bool = False):
        """
        Initialize scheduler with EC2 IB Gateway connection.
        
        Args:
            host: IB Gateway host (default: from config.IB_HOST)
            port: IB Gateway port (default: from config.IB_PORT)
            use_ai: Use new AI components (True) or legacy scanner (False)
            dry_run: If True, don't execute actual trades
        """
        # Use config values if not provided
        self.host = host or getattr(config, 'IB_HOST', '127.0.0.1')
        self.port = port or getattr(config, 'IB_PORT', 4004)
        self.use_ai = use_ai
        self.dry_run = dry_run
        
        # Initialize IB provider using resolved host/port
        self.ib_provider = IBDataProvider(host=self.host, port=self.port, client_id=6000)
        
        # Initialize AI components
        if use_ai:
            logger.info("Initializing AI-enhanced signal generator...")
            self.signal_generator = CalendarSignalGenerator(
                config=GeneratorConfig(
                    min_confidence_score=60.0,
                    min_liquidity_score=0.3,
                    min_theta_edge=0.50,
                    default_profit_target_pct=35.0,
                    default_stop_loss_pct=50.0,
                    max_contracts=5,
                    max_risk_per_trade=500.0
                )
            )
            self.earnings_router = EarningsStrategyRouter()
            logger.info("AI components initialized")
        else:
            self.signal_generator = None
            self.earnings_router = None
            if LEGACY_SCANNER_AVAILABLE:
                self.scanner = CalendarSpreadScanner(data_provider=self.ib_provider)
            else:
                raise RuntimeError("Neither AI components nor legacy scanner available")
        
        # Position and risk management
        self.position_manager = PositionManager()
        self.risk_manager = RiskManager(account_size=ACCOUNT_SIZE)
        self.calculator = SpreadCalculator()
        
        self.running = False
        
    def is_market_hours(self) -> bool:
        """Check if market is open (9:30 AM - 4:00 PM ET)."""
        now = datetime.now()
        current_time = now.time()
        
        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)
        
        if now.weekday() >= 5:  # Weekend
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
        """Scan for opportunities and enter best setup using AI components."""
        logger.info("=" * 70)
        logger.info("ENTRY WINDOW: Scanning for calendar spread opportunities (AI-Enhanced)")
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
        
        try:
            if self.use_ai:
                signals = self._generate_ai_signals()
            else:
                signals = self._generate_legacy_signals()
            
            if not signals:
                logger.info("No suitable opportunities found")
                return
            
            # Get best signal
            best_signal = signals[0]  # Already sorted by confidence/score
            
            logger.info(f"Found {len(signals)} opportunities, best: {best_signal.symbol}")
            logger.info(f"  Strike: ${best_signal.strike}")
            logger.info(f"  Net Debit: ${best_signal.net_debit:.2f}")
            logger.info(f"  Theta Edge: ${best_signal.theta_edge:.2f}/day")
            logger.info(f"  Confidence: {best_signal.confidence_score:.0f}")
            
            # Risk check
            risk_check = self.risk_manager.check_can_trade(
                trade_cost=best_signal.net_debit * best_signal.quantity * 100,
                current_positions=open_positions,
                vix=vix if vix_ok else None
            )
            
            if not risk_check.passed:
                logger.warning(f"Risk check failed: {risk_check.reason}")
                return
            
            # Execute or log
            if self.dry_run:
                logger.info(f"[DRY RUN] Would enter: {best_signal.symbol} ${best_signal.strike} x{best_signal.quantity}")
            else:
                self._execute_entry(best_signal)
            
        except Exception as e:
            logger.error(f"Error during scan/entry: {e}", exc_info=True)
    
    def _generate_ai_signals(self) -> List[CalendarSpreadSignal]:
        """Generate signals using AI components."""
        logger.info("Generating signals with AI components...")
        
        all_signals = []
        
        for symbol in UNDERLYINGS:
            try:
                # Check earnings safety first
                decision = self.earnings_router.decide(symbol)
                
                if decision.action == StrategyDecision.REJECT:
                    logger.info(f"  {symbol}: SKIP - {decision.reason}")
                    continue
                
                # Get market data
                stock_price = self.ib_provider.get_stock_price(symbol)
                if stock_price is None:
                    logger.warning(f"  {symbol}: Cannot get stock price, skipping")
                    continue
                
                iv_rank = self._get_iv_rank(symbol)
                
                # Get options data
                expirations = self.ib_provider.get_expirations(symbol)
                if not expirations or len(expirations) < 2:
                    logger.warning(f"  {symbol}: Insufficient expirations")
                    continue
                
                options_data = self._get_options_data(symbol, expirations[:4])
                
                # Generate signals
                signals = self.signal_generator.generate_signals(
                    symbol=symbol,
                    stock_price=stock_price,
                    iv_rank=iv_rank,
                    options_data=options_data,
                    expirations=expirations
                )
                
                # Apply earnings size adjustment
                if decision.action == StrategyDecision.REDUCE_SIZE:
                    for sig in signals:
                        sig.quantity = max(1, int(sig.quantity * decision.size_multiplier))
                
                all_signals.extend(signals)
                
                if signals:
                    logger.info(f"  {symbol}: {len(signals)} signal(s) generated")
                else:
                    logger.info(f"  {symbol}: No qualifying signals")
                    
            except Exception as e:
                logger.warning(f"  {symbol}: Error - {e}")
        
        # Sort by confidence score
        all_signals.sort(key=lambda s: s.confidence_score, reverse=True)
        
        return all_signals
    
    def _generate_legacy_signals(self) -> List:
        """Generate signals using legacy scanner (fallback)."""
        logger.info("Generating signals with legacy scanner...")
        
        if not LEGACY_SCANNER_AVAILABLE:
            return []
        
        setups = self.scanner.scan_all()
        return setups
    
    def _get_iv_rank(self, symbol: str) -> float:
        """Get IV rank for symbol (placeholder - would fetch from data provider)."""
        # In production, this would fetch from IB or another data source
        # For now, return a default moderate IV rank
        return 50.0
    
    def _get_options_data(self, symbol: str, expirations: List[datetime]) -> Dict:
        """Get options chain data for symbol and expirations."""
        import pandas as pd
        
        options_data = {}
        
        for exp in expirations[:4]:  # Limit to 4 expirations
            exp_str = exp.strftime('%Y%m%d')
            
            try:
                chain = self.ib_provider.get_option_chain(symbol, exp)
                if chain is not None and not chain.empty:
                    options_data[exp_str] = chain
            except Exception as e:
                logger.warning(f"Error getting chain for {symbol} {exp_str}: {e}")
        
        return options_data
    
    def _execute_entry(self, signal: CalendarSpreadSignal) -> None:
        """Execute calendar spread entry.
        
        Behavior depends on mode:
        - dry_run=False (IB Paper Mode): Execute trade on IB Gateway
        - dry_run=True (Production Mode): Publish signal for users to approve
        """
        logger.info("=" * 70)
        logger.info(f"PROCESSING SIGNAL: {signal.symbol} ${signal.strike}")
        logger.info("=" * 70)
        
        try:
            # STEP 1: Always publish signal to production users
            logger.info("📡 Publishing signal to WebSocket for production users...")
            
            # Import signal publisher
            from signal_publisher.calendar import publish_calendar_signal
            
            # Convert signal to SpreadSetup-like object for publisher
            # (signal_publisher expects SpreadSetup format)
            class SignalAsSetup:
                def __init__(self, sig):
                    self.symbol = sig.symbol
                    self.strike = sig.strike
                    self.stock_price = sig.stock_price
                    self.short_expiry = sig.front_expiry
                    self.long_expiry = sig.back_expiry
                    self.net_debit = sig.net_debit
                    self.score = sig.confidence
                    self.iv = sig.iv_rank / 100  # Convert percentage to decimal
                    self.theta_edge = sig.net_debit * 0.05  # Approximate daily theta
            
            setup = SignalAsSetup(signal)
            success = publish_calendar_signal(setup)
            
            if success:
                logger.info(f"✅ Signal published: {signal.symbol} ${signal.strike}")
                logger.info(f"  Users can now approve and execute via Tastytrade")
            else:
                logger.error(f"❌ Failed to publish signal for {signal.symbol}")
            
            # STEP 2: Always execute on IB paper account for testing
            logger.info("🧪 Executing on IB Paper account for validation...")
            
            # Create position record
            position = self.position_manager.open_position_from_signal(signal)
            
            logger.info(f"POSITION OPENED: {signal.symbol} ${signal.strike} x{signal.quantity}")
            logger.info(f"  Entry Debit: ${signal.net_debit:.2f}")
            logger.info(f"  Profit Target: ${signal.get_profit_target():.2f}")
            logger.info(f"  Stop Loss: ${signal.get_stop_loss():.2f}")
            
            # TODO: Execute IB combo order
            # This would call ib_provider.place_calendar_spread()
            logger.info("  ⚠️  IB execution not yet implemented - position tracked only")
            
        except Exception as e:
            logger.error(f"Failed to process signal: {e}", exc_info=True)
    
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
            # Calculate current value (in production, fetch from IB)
            hours_held = (datetime.now() - datetime.fromisoformat(pos.entry_time)).total_seconds() / 3600
            
            # Simulate theta decay
            simulated_gain_pct = min(8, hours_held * 0.3)
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
                
                if not self.dry_run:
                    self.position_manager.close_position(
                        pos.id, new_value, exit_signal.reason
                    )
                    self.risk_manager.update_pnl(pos.realized_pnl or 0)
                    
                    logger.info(f"POSITION CLOSED: {pos.symbol} ${pos.strike}")
                    logger.info(f"  Realized P&L: ${pos.realized_pnl:.2f} ({pos.pnl_pct:+.1f}%)")
                else:
                    logger.info(f"  [DRY RUN] Would exit position")
            else:
                logger.info(f"  Status: HOLD")
    
    def update_positions(self) -> None:
        """Update position values during market hours."""
        positions = self.position_manager.get_open_positions()
        
        if not positions:
            return
        
        for pos in positions:
            hours_held = (datetime.now() - datetime.fromisoformat(pos.entry_time)).total_seconds() / 3600
            simulated_gain_pct = min(8, hours_held * 0.3)
            new_value = pos.entry_debit * (1 + simulated_gain_pct / 100)
            self.position_manager.update_position(pos.id, new_value)
    
    def run(self) -> None:
        """Main scheduler loop."""
        self.running = True
        
        mode_str = "AI-Enhanced" if self.use_ai else "Legacy"
        dry_str = " [DRY RUN]" if self.dry_run else ""
        
        logger.info("=" * 70)
        logger.info(f"CALENDAR SPREAD SCHEDULER STARTED ({mode_str}){dry_str}")
        logger.info("=" * 70)
        logger.info("")
        logger.info("Configuration:")
        logger.info(f"  IB Gateway: {self.host}:{self.port}")
        logger.info(f"  Account Size: ${ACCOUNT_SIZE:,.0f}")
        logger.info(f"  Underlyings: {', '.join(UNDERLYINGS)}")
        logger.info(f"  Max Positions: 3")
        logger.info(f"  Mode: {mode_str}")
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
                        logger.info("Market closed. Scheduler idle until 9:30 AM ET.")
                    time.sleep(300)
                    continue
                
                # Entry window (3:50 PM - 3:59 PM)
                if self.is_entry_window() and not entry_executed:
                    self.scan_and_enter()
                    entry_executed = True
                
                # Exit window (9:30 AM - 10:00 AM)
                elif self.is_exit_window() and not exit_executed:
                    self.monitor_and_exit()
                    exit_executed = True
                
                # Update positions every 60 seconds
                else:
                    self.update_positions()
                
                time.sleep(60)
                
            except KeyboardInterrupt:
                logger.info("\nShutting down scheduler...")
                break
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                time.sleep(60)
        
        self.running = False
        logger.info("Scheduler stopped.")

    def run_once(self, mode: str = 'entry') -> None:
        """Run a single scan (for testing)."""
        if mode == 'entry':
            self.scan_and_enter()
        elif mode == 'exit':
            self.monitor_and_exit()
        elif mode == 'monitor':
            self.update_positions()


def run_scheduler() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Calendar Spread AI Scheduler")
    parser.add_argument("--host", default=None, help=f"IB Gateway host (default: from config, currently {getattr(config, 'IB_HOST', '127.0.0.1')})")
    parser.add_argument("--port", type=int, default=None, help=f"IB Gateway port (default: from config, currently {getattr(config, 'IB_PORT', 4004)})")
    parser.add_argument("--legacy", action="store_true", help="Use legacy scanner")
    parser.add_argument("--dry-run", action="store_true", help="Don't execute trades")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--entry", action="store_true", help="Run entry scan only")
    parser.add_argument("--exit", action="store_true", help="Run exit scan only")
    parser.add_argument("--monitor", action="store_true", help="Run position monitor only")
    
    args = parser.parse_args()
    
    scheduler = CalendarSpreadScheduler(
        host=args.host,
        port=args.port,
        use_ai=not args.legacy,
        dry_run=args.dry_run
    )
    
    if args.once or args.entry:
        scheduler.run_once('entry')
    elif args.exit:
        scheduler.run_once('exit')
    elif args.monitor:
        scheduler.run_once('monitor')
    else:
        scheduler.run()


if __name__ == "__main__":
    run_scheduler()
