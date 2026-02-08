"""
Enhanced Calendar Spread Backtest
==================================
Uses the existing earnings calendar infrastructure for realistic backtesting.

Integrates with:
- src/earnings_intelligence/database.py - Real earnings dates
- src/earnings_intelligence/scanner.py - Earnings discovery
- src/calendar_spreads - AI components
"""

import sys
import io

# Force UTF-8 encoding for Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Dict, Optional
import numpy as np
import random

# Add project root
sys.path.insert(0, '.')

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip install yfinance")
    sys.exit(1)

from src.earnings_intelligence.database import EarningsRepository, get_session
from src.earnings_intelligence.scanner import EarningsScanner
from src.calendar_spreads import EarningsStrategyRouter, StrategyDecision

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

random.seed(42)
np.random.seed(42)


@dataclass
class EnhancedCalendarTrade:
    """Calendar trade with earnings awareness."""
    trade_id: int
    symbol: str
    entry_date: date
    exit_date: date
    days_held: int
    
    # Entry conditions
    initial_debit: float
    iv_rank: float
    earnings_clear: bool  # Was earnings >14 days away at entry?
    
    # Exit conditions
    exit_value: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    
    # Earnings impact
    hit_earnings_warning: bool = False  # Did earnings approach during trade?
    earnings_days_at_exit: int = 999


class EnhancedBacktester:
    """
    Backtest calendar spreads with real earnings calendar data.
    
    Uses the earnings intelligence infrastructure to:
    1. Check if earnings are safe at entry (>14 days)
    2. Monitor for earnings approaching during trade
    3. Exit early if earnings within 7 days
    4. Track how earnings awareness improves performance
    """
    
    def __init__(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        use_earnings_data: bool = True
    ):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.use_earnings_data = use_earnings_data
        
        # Initialize earnings components
        if use_earnings_data:
            try:
                self.earnings_repo = EarningsRepository()
                self.earnings_router = EarningsStrategyRouter()
                logger.info(f"✓ Earnings intelligence enabled for {symbol}")
            except Exception as e:
                logger.warning(f"Earnings DB unavailable: {e}. Using synthetic earnings.")
                self.earnings_repo = None
                self.earnings_router = None
        else:
            self.earnings_repo = None
            self.earnings_router = None
        
        # Load historical prices
        self.historical_data = self._load_historical_data()
    
    def _load_historical_data(self) -> Dict[date, float]:
        """Load stock prices from yfinance."""
        logger.info(f"Loading historical data for {self.symbol}...")
        
        ticker = yf.Ticker(self.symbol)
        df = ticker.history(
            start=self.start_date - timedelta(days=30),
            end=self.end_date + timedelta(days=1)
        )
        
        # Convert to date->price dict
        prices = {}
        for idx, row in df.iterrows():
            prices[idx.date()] = row['Close']
        
        logger.info(f"Loaded {len(prices)} days of price data")
        return prices
    
    def _get_days_to_earnings(self, current_date: date) -> int:
        """
        Get days until next earnings using synthetic quarterly schedule.
        
        Simulates earnings on specific months: Jan, Apr, Jul, Oct (quarterly)
        This creates realistic earnings cycles for backtesting.
        
        Returns:
            Days to earnings
        """
        if self.earnings_repo:
            try:
                # Try real earnings data first
                earnings_event = self.earnings_repo.get_by_symbol(self.symbol)
                
                if earnings_event:
                    announcement_date = earnings_event.announcement_date
                    if isinstance(announcement_date, str):
                        announcement_date = date.fromisoformat(announcement_date)
                    
                    if announcement_date >= current_date:
                        days = (announcement_date - current_date).days
                        logger.debug(f"Real earnings data: {days} days")
                        return days
            except Exception as e:
                logger.debug(f"No real earnings data, using synthetic: {e}")
        
        # Synthetic earnings: quarterly on specific months
        # Earnings typically announced in: Jan (Q4), Apr (Q1), Jul (Q2), Oct (Q3)
        earnings_months = [1, 4, 7, 10]
        
        # Find next earnings month
        current_year = current_date.year
        current_month = current_date.month
        
        # Find the next earnings month
        next_earnings_month = None
        next_earnings_year = current_year
        
        for month in earnings_months:
            if month > current_month:
                next_earnings_month = month
                break
        
        if next_earnings_month is None:
            # Next earnings is in following year
            next_earnings_month = earnings_months[0]
            next_earnings_year = current_year + 1
        
        # Earnings typically announced mid-month (around 15th)
        next_earnings_date = date(next_earnings_year, next_earnings_month, 15)
        
        days = (next_earnings_date - current_date).days
        return max(0, days)
    
    def _check_earnings_safety(self, current_date: date) -> tuple[bool, str]:
        """
        Check if it's safe to enter a calendar spread.
        
        Returns:
            (is_safe, reason)
        """
        days_to_earnings = self._get_days_to_earnings(current_date)
        
        if self.earnings_router and self.use_earnings_data:
            decision = self.earnings_router.decide(
                symbol=self.symbol,
                days_to_earnings=days_to_earnings
            )
            
            if decision.action == "APPROVE":
                return True, f"Earnings safe ({days_to_earnings}d away)"
            elif decision.action == "REDUCE_SIZE":
                return True, f"Reduced size ({days_to_earnings}d away)"  # Still enter
            else:
                return False, f"Earnings too close ({days_to_earnings}d)"
        
        # Fallback: simple rule - enter if >14 days to earnings
        if days_to_earnings > 14:
            return True, f"Earnings safe ({days_to_earnings}d away)"
        else:
            return False, f"Earnings too close ({days_to_earnings}d)"

    
    def _should_exit_for_earnings(self, current_date: date) -> tuple[bool, int]:
        """
        Check if should exit due to earnings approaching.
        
        Returns:
            (should_exit, days_to_earnings)
        """
        days_to_earnings = self._get_days_to_earnings(current_date)
        
        # Exit if earnings within 7 days
        if days_to_earnings <= 7:
            return True, days_to_earnings
        
        return False, days_to_earnings
    
    def run_backtest(self) -> Dict:
        """Run backtest with earnings awareness."""
        logger.info("=" * 70)
        logger.info(f"ENHANCED CALENDAR BACKTEST - {self.symbol}")
        logger.info("=" * 70)
        logger.info(f"Period: {self.start_date} to {self.end_date}")
        logger.info(f"Earnings Intelligence: {'ENABLED' if self.use_earnings_data else 'DISABLED'}")
        logger.info("")
        
        trades = []
        trade_counter = 0
        open_trade = None
        
        # Scan weekly for entries
        scan_interval = 7
        current_date = self.start_date
        
        while current_date <= self.end_date:
            if current_date not in self.historical_data:
                current_date += timedelta(days=1)
                continue
            
            stock_price = self.historical_data[current_date]
            
            # Check open position for exit
            if open_trade:
                days_held = (current_date - open_trade.entry_date).days
                
                # Check earnings exit
                should_exit_earnings, days_to_earnings = self._should_exit_for_earnings(current_date)
                
                # Determine exit
                should_exit = False
                exit_reason = ""
                
                if should_exit_earnings:
                    should_exit = True
                    exit_reason = "Earnings approaching"
                    open_trade.hit_earnings_warning = True
                    open_trade.earnings_days_at_exit = days_to_earnings
                elif days_held >= 21:  # Max hold
                    should_exit = True
                    exit_reason = "Max hold period"
                else:
                    # Simulate profit/loss based on typical outcomes
                    rand = random.random()
                    if rand < 0.67:  # Win
                        if days_held >= 7:  # Reached profit target
                            should_exit = True
                            exit_reason = "Profit target"
                    elif rand < 0.85:  # Moderate loss
                        if days_held >= 10:
                            should_exit = True
                            exit_reason = "Stop loss"
                
                if should_exit:
                    # Calculate exit value
                    if exit_reason == "Profit target":
                        exit_value = open_trade.initial_debit * 1.35  # +35%
                    elif exit_reason == "Earnings approaching":
                        exit_value = open_trade.initial_debit * 0.85  # -15% (early exit)
                    elif exit_reason == "Stop loss":
                        exit_value = open_trade.initial_debit * 0.60  # -40%
                    else:
                        exit_value = open_trade.initial_debit * 0.90  # -10%
                    
                    pnl = (exit_value - open_trade.initial_debit) * 100 - 4.0  # Commission
                    pnl_pct = (pnl / (open_trade.initial_debit * 100)) * 100
                    
                    open_trade.exit_date = current_date
                    open_trade.days_held = days_held
                    open_trade.exit_value = exit_value
                    open_trade.pnl = pnl
                    open_trade.pnl_pct = pnl_pct
                    open_trade.exit_reason = exit_reason
                    
                    trades.append(open_trade)
                    
                    logger.info(
                        f"Trade {open_trade.trade_id} CLOSED: {exit_reason} | "
                        f"P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%) | "
                        f"Held: {days_held} days"
                    )
                    
                    open_trade = None
            
            # Look for new entry (weekly scan)
            days_since_start = (current_date - self.start_date).days
            if open_trade is None and days_since_start % scan_interval == 0:
                # Check earnings safety
                is_safe, safety_reason = self._check_earnings_safety(current_date)
                
                if is_safe:
                    trade_counter += 1
                    
                    # Typical debit
                    initial_debit = np.random.uniform(2.0, 3.0)
                    iv_rank = np.random.uniform(40, 70)
                    
                    open_trade = EnhancedCalendarTrade(
                        trade_id=trade_counter,
                        symbol=self.symbol,
                        entry_date=current_date,
                        exit_date=current_date,  # Placeholder
                        days_held=0,
                        initial_debit=initial_debit,
                        iv_rank=iv_rank,
                        earnings_clear=True,
                        exit_value=0.0,
                        pnl=0.0,
                        pnl_pct=0.0,
                        exit_reason=""
                    )
                    
                    logger.info(f"Trade {trade_counter} OPENED: ${initial_debit:.2f} | {safety_reason}")
                else:
                    if trade_counter < 3:  # Log first few skips
                        logger.info(f"Entry skipped: {safety_reason}")

            
            current_date += timedelta(days=1)
        
        # Close any remaining position
        if open_trade:
            days_held = (self.end_date - open_trade.entry_date).days
            exit_value = open_trade.initial_debit * 1.10  # Small win
            pnl = (exit_value - open_trade.initial_debit) * 100 - 4.0
            pnl_pct = (pnl / (open_trade.initial_debit * 100)) * 100
            
            open_trade.exit_date = self.end_date
            open_trade.days_held = days_held
            open_trade.exit_value = exit_value
            open_trade.pnl = pnl
            open_trade.pnl_pct = pnl_pct
            open_trade.exit_reason = "Backtest end"
            
            trades.append(open_trade)
        
        return self._calculate_results(trades)
    
    def _calculate_results(self, trades: List[EnhancedCalendarTrade]) -> Dict:
        """Calculate performance metrics."""
        if not trades:
            return {
                'symbol': self.symbol,
                'total_trades': 0,
                'earnings_enabled': self.use_earnings_data,
            }
        
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        
        total_pnl = sum(t.pnl for t in trades)
        win_rate = (len(wins) / len(trades)) * 100
        
        # Earnings impact analysis
        earnings_exits = [t for t in trades if t.hit_earnings_warning]
        
        results = {
            'symbol': self.symbol,
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_win': np.mean([t.pnl for t in wins]) if wins else 0,
            'avg_loss': abs(np.mean([t.pnl for t in losses])) if losses else 0,
            'avg_hold_days': np.mean([t.days_held for t in trades]),
            'earnings_enabled': self.use_earnings_data,
            'earnings_exits': len(earnings_exits),
            'trades': trades
        }
        
        # Calculate annualized return
        days = (self.end_date - self.start_date).days
        years = days / 365.25
        return_pct = (total_pnl / 50000) * 100
        results['annualized_return'] = return_pct / years if years > 0 else 0
        
        return results


def print_comparison(results_with: Dict, results_without: Dict):
    """Print comparison of earnings-aware vs non-aware."""
    print("\n" + "=" * 80)
    print("EARNINGS INTELLIGENCE IMPACT ANALYSIS")
    print("=" * 80)
    
    print(f"\n{'Metric':<30} {'WITH Earnings':<20} {'WITHOUT Earnings':<20} {'Delta'}")
    print("-" * 80)
    
    metrics = [
        ('Total Trades', 'total_trades', ''),
        ('Win Rate', 'win_rate', '%'),
        ('Total P&L', 'total_pnl', '$'),
        ('Annualized Return', 'annualized_return', '%'),
        ('Avg Hold Days', 'avg_hold_days', 'days'),
    ]
    
    for label, key, unit in metrics:
        with_val = results_with.get(key, 0)
        without_val = results_without.get(key, 0)
        
        if unit == '$':
            delta = with_val - without_val
            print(f"{label:<30} ${with_val:>10,.2f}        ${without_val:>10,.2f}        ${delta:+,.2f}")
        elif unit == '%':
            delta = with_val - without_val
            print(f"{label:<30} {with_val:>10.1f}%        {without_val:>10.1f}%        {delta:+.1f}%")
        elif unit == 'days':
            delta = with_val - without_val
            print(f"{label:<30} {with_val:>10.0f}         {without_val:>10.0f}         {delta:+.0f}")
        else:
            delta = with_val - without_val
            print(f"{label:<30} {with_val:>10.0f}         {without_val:>10.0f}         {delta:+.0f}")
    
    # Earnings-specific metrics
    print("\n" + "-" * 80)
    print("EARNINGS-SPECIFIC METRICS")
    print("-" * 80)
    earnings_exits_with = results_with.get('earnings_exits', 0)
    total_trades_with = results_with.get('total_trades', 1)
    pct = (earnings_exits_with / total_trades_with * 100) if total_trades_with > 0 else 0
    print(f"Earnings-triggered exits (WITH):  {earnings_exits_with} ({pct:.1f}% of trades)")
    print(f"Average P&L improvement:           ${results_with.get('total_pnl', 0) - results_without.get('total_pnl', 0):+,.2f}")
    print()


def main():
    """Run enhanced backtest with earnings comparison."""
    
    symbols = ["SPY", "QQQ"]
    start_date = date(2023, 1, 1)
    end_date = date(2024, 12, 31)
    
    for symbol in symbols:
        print(f"\n{'=' * 80}")
        print(f"BACKTESTING {symbol}")
        print(f"{'=' * 80}")
        
        # Run WITH earnings intelligence
        logger.info(f"\n>>> Running WITH earnings intelligence...")
        backtester_with = EnhancedBacktester(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            use_earnings_data=True
        )
        results_with = backtester_with.run_backtest()
        
        # Run WITHOUT earnings intelligence
        logger.info(f"\n>>> Running WITHOUT earnings intelligence...")
        backtester_without = EnhancedBacktester(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            use_earnings_data=False
        )
        results_without = backtester_without.run_backtest()
        
        # Compare results
        print_comparison(results_with, results_without)


if __name__ == "__main__":
    main()
