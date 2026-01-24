"""
Calendar Spreads Bot - Main Entry Point
========================================

Orchestrates the calendar spread trading system.

Usage:
    python main.py --mode scan      # Scan for opportunities
    python main.py --mode trade     # Full trading loop
    python main.py --mode monitor   # Monitor open positions
    python main.py --mode stats     # Show statistics
"""

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, time
from typing import Optional

from config import (
    ENTRY_TIME, EXIT_CHECK_TIME, UNDERLYINGS,
    ACCOUNT_SIZE, PROFIT_TARGET_PCT, STOP_LOSS_PCT,
    TASTYTRADE_USERNAME, TASTYTRADE_PASSWORD, TASTYTRADE_USE_SANDBOX,
    EARNINGS_ENABLED
)
from scanner import CalendarSpreadScanner, check_vix_filter, SpreadSetup
from position_manager import PositionManager, ExitReason
from risk_manager import RiskManager
from greeks_calculator import SpreadCalculator
from tastytrade_client import TastytradeClient
from tastytrade_data_provider import TastytradeDataProvider
from ib_data_provider import IBDataProvider
from src.earnings_intelligence.client import PerplexityClient
from src.earnings_intelligence.router import EarningsStrategyRouter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/calendar_spreads.log')
    ]
)
logger = logging.getLogger(__name__)


class CalendarSpreadsBot:
    """
    Main trading bot for calendar spreads.
    
    Workflow:
    1. 3:50 PM: Scan for opportunities
    2. 3:55 PM: Enter best spread
    3. 9:35 AM next day: Check positions
    4. Exit if target/stop hit
    5. Repeat
    """
    
    def __init__(self, use_tastytrade: bool = True):
        """
        Initialize the bot.
        
        Architecture:
            - Market Data: IB Gateway (via scanner's data provider)
            - Order Execution: Tastytrade API
        
        Args:
            use_tastytrade: If True, connect to Tastytrade for order execution.
                           If False, orders are logged but not sent to broker.
        """
        self.use_tastytrade = use_tastytrade
        self.tastytrade_client = None
        
        # Initialize IB Data Provider (AWS Gateway)
        self.ib_provider = IBDataProvider(host="34.235.119.67", port=4004, client_id=5000)
        
        # Scanner uses IB Gateway for market data
        self.scanner = CalendarSpreadScanner(data_provider=self.ib_provider)
        self.position_manager = PositionManager()
        self.risk_manager = RiskManager(account_size=ACCOUNT_SIZE)
        self.calculator = SpreadCalculator()

        # Initialize Earnings Intelligence
        self.earnings_client = PerplexityClient()
        self.strategy_router = EarningsStrategyRouter()
        
        # Initialize Tastytrade connection for order execution
        if use_tastytrade and TASTYTRADE_USERNAME and TASTYTRADE_PASSWORD:
            try:
                self.tastytrade_client = TastytradeClient(
                    username=TASTYTRADE_USERNAME,
                    password=TASTYTRADE_PASSWORD,
                    use_sandbox=TASTYTRADE_USE_SANDBOX
                )
                self.tastytrade_client.connect()
                logger.info(f"Connected to Tastytrade for order execution ({'sandbox' if TASTYTRADE_USE_SANDBOX else 'live'})")
                
                # Optionally sync account size from Tastytrade
                try:
                    balances = self.tastytrade_client.get_account_balance()
                    actual_balance = balances.get('net_liquidating_value', 0)
                    if actual_balance > 0:
                        self.risk_manager = RiskManager(account_size=actual_balance)
                        logger.info(f"Using Tastytrade account balance: ${actual_balance:,.2f}")
                except Exception as e:
                    logger.debug(f"Could not fetch Tastytrade balance: {e}")
            except Exception as e:
                logger.warning(f"Could not connect to Tastytrade: {e}")
                logger.info("Orders will be logged but not executed")
                self.use_tastytrade = False
        else:
            if use_tastytrade:
                logger.info("Tastytrade credentials not configured - orders will be logged only")
            self.use_tastytrade = False
        
        self._running = False
    
    def __del__(self):
        """Clean up connections."""
        if self.tastytrade_client:
            try:
                self.tastytrade_client.disconnect()
            except:
                pass
        if hasattr(self, 'ib_provider'):
            try:
                self.ib_provider.disconnect()
            except:
                pass
    
    def scan_opportunities(self) -> None:
        """Scan and display available opportunities."""
        print("\n" + "=" * 70)
        print("CALENDAR SPREAD SCANNER")
        print("=" * 70)
        
        # Check VIX
        vix_ok, vix = check_vix_filter()
        print(f"\nVIX: {vix:.1f} - {'✅ OK' if vix_ok else '❌ SKIP'}")
        
        if not vix_ok:
            print("Market conditions not suitable for calendar spreads.")
            return
        
        # Run scan
        setups = self.scanner.scan_all()
        
        if not setups:
            print("\nNo suitable opportunities found.")
            return
        
        print(f"\nFound {len(setups)} opportunities:")
        print("-" * 70)
        
        for i, setup in enumerate(setups[:5], 1):
            print(f"\n{i}. {setup.symbol} ${setup.strike} Calendar Spread")
            print(f"   SELL {setup.short_expiry.strftime('%b %d')} @ ${setup.short_bid:.2f}")
            print(f"   BUY  {setup.long_expiry.strftime('%b %d')} @ ${setup.long_ask:.2f}")
            print(f"   Net Debit: ${setup.net_debit:.2f}")
            print(f"   Profit Target: ${setup.profit_target_5pct:.2f} (+5%)")
            print(f"   Stop Loss: ${setup.stop_loss_10pct:.2f} (-10%)")
            print(f"   Theta Edge: ${setup.theta_edge:.2f}/day")
            print(f"   Score: {setup.score:.1f}")
    
    def enter_trade(self, setup: Optional[SpreadSetup] = None) -> bool:
        """Enter a calendar spread trade."""
        if setup is None:
            setup = self.scanner.get_best_setup()
        
        if not setup:
            logger.warning("No setup available for trade")
            return False
        
        # Earnings Intelligence Check
        earnings_decision = None
        if EARNINGS_ENABLED:
            logger.info(f"Checking earnings for {setup.symbol}...")
            context = self.earnings_client.get_earnings_context(setup.symbol)
            earnings_decision = self.strategy_router.decide(setup.symbol, context)
            
            if earnings_decision.action == "REJECT":
                logger.warning(f"⛔ Trade REJECTED by Earnings AI: {earnings_decision.reason}")
                return False
            
            logger.info(f"✅ Earnings Check: {earnings_decision.action} ({earnings_decision.reason})")

        # Risk checks
        open_positions = len(self.position_manager.get_open_positions())
        vix_ok, vix = check_vix_filter()
        
        risk_check = self.risk_manager.check_can_trade(
            trade_cost=setup.net_debit,
            current_positions=open_positions,
            vix=vix if vix_ok else None
        )
        
        if not risk_check.passed:
            logger.warning(f"Risk check failed: {risk_check.reason}")
            return False
        
        # Calculate position size
        contracts = self.risk_manager.calculate_position_size(setup.net_debit)
        
        # Apply Earnings Intelligence Sizing
        if EARNINGS_ENABLED and earnings_decision and earnings_decision.multiplier < 1.0:
            original_contracts = contracts
            contracts = max(1, int(contracts * earnings_decision.multiplier))
            logger.info(f"Position size reduced by Earnings AI: {original_contracts} -> {contracts} contracts")
        
        # Open position
        position = self.position_manager.open_position(setup, contracts)
        
        # Apply Earnings Intelligence Stop Widening
        if EARNINGS_ENABLED and earnings_decision and earnings_decision.risk_factor > 1.0:
            original_stop = position.stop_loss
            # Widen the stop loss by increasing the loss tolerance
            # stop_loss is value at which we exit. For a debit spread, lower is worse.
            # So we make stop_loss LOWER (wider) by the risk factor
            loss_pct = (position.entry_debit - original_stop) / position.entry_debit
            new_loss_pct = loss_pct * earnings_decision.risk_factor
            position.stop_loss = position.entry_debit * (1 - new_loss_pct)
            logger.info(f"Stop widened by Earnings AI: ${original_stop:.2f} -> ${position.stop_loss:.2f} ({earnings_decision.risk_factor}x)")
        
        logger.info(
            f"TRADE ENTERED: {setup.symbol} ${setup.strike} x{contracts}\n"
            f"  Debit: ${setup.net_debit:.2f}\n"
            f"  Target: ${position.profit_target:.2f}\n"
            f"  Stop: ${position.stop_loss:.2f}"
        )
        
        return True
    
    def monitor_positions(self) -> None:
        """Monitor and manage open positions."""
        print("\n" + "=" * 70)
        print("POSITION MONITOR")
        print("=" * 70)
        
        positions = self.position_manager.get_open_positions()
        
        if not positions:
            print("\nNo open positions.")
            return
        
        print(f"\n{len(positions)} open position(s):")
        print("-" * 70)
        
        for pos in positions:
            # Update current value (in production, fetch from market)
            # For demo, simulate based on theta decay
            hours_held = (datetime.now() - datetime.fromisoformat(pos.entry_time)).total_seconds() / 3600
            
            # Simulate ~5% gain overnight due to theta decay
            simulated_gain_pct = min(8, hours_held * 0.4)  # ~0.4%/hour
            new_value = pos.entry_debit * (1 + simulated_gain_pct / 100)
            
            self.position_manager.update_position(pos.id, new_value)
            
            print(f"\n{pos.id}: {pos.symbol} ${pos.strike}")
            print(f"  Entry: ${pos.entry_debit:.2f} @ {pos.entry_time[:16]}")
            print(f"  Current: ${new_value:.2f} ({pos.pnl_pct:+.1f}%)")
            print(f"  Target: ${pos.profit_target:.2f} | Stop: ${pos.stop_loss:.2f}")
            
            # Check exit conditions
            exit_signal = self.position_manager.check_exit_conditions(pos)
            
            if exit_signal.should_exit:
                print(f"  ⚠️  EXIT SIGNAL: {exit_signal.message}")
                self.position_manager.close_position(
                    pos.id, 
                    new_value, 
                    exit_signal.reason
                )
                self.risk_manager.update_pnl(pos.realized_pnl or 0)
            else:
                print(f"  Status: HOLD")
    
    def show_stats(self) -> None:
        """Display trading statistics."""
        print("\n" + "=" * 70)
        print("CALENDAR SPREADS STATISTICS")
        print("=" * 70)
        
        stats = self.position_manager.get_stats()
        risk_status = self.risk_manager.get_status()
        
        print("\n📊 Trading Performance:")
        print(f"  Total Trades: {stats['total_trades']}")
        print(f"  Wins: {stats['wins']} | Losses: {stats['losses']}")
        print(f"  Win Rate: {stats['win_rate']:.1f}%")
        print(f"  Total P&L: ${stats['total_pnl']:.2f}")
        print(f"  Avg Win: ${stats['avg_win']:.2f}")
        print(f"  Avg Loss: ${stats['avg_loss']:.2f}")
        
        print("\n💰 Account Status:")
        print(f"  Account Size: ${risk_status['account_size']:,.0f}")
        print(f"  Available Capital: ${risk_status['available_capital']:,.0f}")
        print(f"  Today's P&L: ${risk_status['today_pnl']:.2f}")
        print(f"  Open Positions: {risk_status['current_positions']}")
        print(f"  Can Trade: {'✅ Yes' if risk_status['can_trade'] else '❌ No'}")
        
        print("\n⚙️ Risk Settings:")
        print(f"  Max Risk/Trade: ${risk_status['max_risk_per_trade']:.0f}")
        print(f"  Max Daily Loss: ${risk_status['max_daily_loss']:.0f}")
    
    async def run_trading_loop(self) -> None:
        """
        Main trading loop.
        
        - 3:50 PM: Scan and enter trades
        - 9:35 AM: Monitor and exit trades
        """
        self._running = True
        logger.info("Calendar Spreads Bot starting...")
        
        while self._running:
            now = datetime.now()
            current_time = now.time()
            
            # Entry window: 3:50 PM - 3:59 PM
            if time(15, 50) <= current_time <= time(15, 59):
                logger.info("Entry window - scanning for opportunities")
                
                open_positions = len(self.position_manager.get_open_positions())
                if open_positions < 3:  # Max concurrent
                    self.scan_opportunities()
                    setup = self.scanner.get_best_setup()
                    if setup:
                        self.enter_trade(setup)
                else:
                    logger.info("Max positions reached, skipping entry")
            
            # Exit check window: 9:30 AM - 10:00 AM
            elif time(9, 30) <= current_time <= time(10, 0):
                logger.info("Exit window - checking positions")
                self.monitor_positions()
            
            # Sleep for 1 minute before next check
            await asyncio.sleep(60)
    
    def stop(self):
        """Stop the trading loop."""
        self._running = False
        logger.info("Calendar Spreads Bot stopping...")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Calendar Spreads Trading Bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode scan      # Scan for opportunities
  python main.py --mode trade     # Start trading loop
  python main.py --mode monitor   # Check open positions
  python main.py --mode stats     # Show statistics
        """
    )
    
    parser.add_argument(
        "--mode",
        choices=["scan", "trade", "monitor", "stats"],
        default="scan",
        help="Operating mode"
    )
    
    args = parser.parse_args()
    
    # Check if Tastytrade credentials are configured for order execution
    use_tastytrade = bool(TASTYTRADE_USERNAME and TASTYTRADE_PASSWORD)
    if not use_tastytrade:
        print("\n⚠️  Tastytrade credentials not configured.")
        print("   Set TASTYTRADE_USERNAME and TASTYTRADE_PASSWORD in .env file.")
        print("   Orders will be logged but not executed.\n")
    else:
        print(f"\n✅ Tastytrade configured ({'sandbox' if TASTYTRADE_USE_SANDBOX else 'LIVE'})")
        print("   Market Data: IB Gateway (or mock)")
        print("   Order Execution: Tastytrade\n")
    
    bot = CalendarSpreadsBot(use_tastytrade=use_tastytrade)
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\nShutting down...")
        bot.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    if args.mode == "scan":
        bot.scan_opportunities()
    
    elif args.mode == "trade":
        print("Starting trading loop...")
        print("Press Ctrl+C to stop.")
        asyncio.run(bot.run_trading_loop())
    
    elif args.mode == "monitor":
        bot.monitor_positions()
    
    elif args.mode == "stats":
        bot.show_stats()


if __name__ == "__main__":
    # Ensure logs directory exists
    from pathlib import Path
    Path("logs").mkdir(exist_ok=True)
    
    main()
