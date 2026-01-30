"""
Trailing Defensive Exit Backtest by Risk Category
==================================================
Compares the Theta strategy performance across LOW, MEDIUM, and HIGH risk profiles
using trailing defensive exits with confirmation days.

Run: python backtest_trailing_exits.py
"""

import sys
sys.path.insert(0, '.')

import logging
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import numpy as np

try:
    import yfinance as yf
except ImportError:
    print("Installing yfinance...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

from src.theta_spreads.risk_profiles import (
    RiskLevel, RiskProfile, 
    LOW_RISK_PROFILE, MEDIUM_RISK_PROFILE, HIGH_RISK_PROFILE,
    RISK_PROFILES
)
from greeks_calculator import BlackScholesCalculator
import config

logging.basicConfig(level=logging.WARNING)  # Suppress detailed logs
logger = logging.getLogger(__name__)


@dataclass
class TrailingExitTrade:
    """Individual trade record with trailing exit tracking."""
    trade_id: int
    symbol: str
    entry_date: date
    exit_date: date
    stock_price_entry: float
    strike: float
    dte_entry: int
    premium_collected: float
    iv_entry: float
    delta_entry: float
    stock_price_exit: float
    premium_paid: float
    dte_exit: int
    exit_reason: str
    breach_days: int = 0  # Days in breach before exit
    
    # Calculated in __post_init__
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    pnl_pct: float = 0.0
    hold_days: int = 0
    capital_required: float = 0.0
    
    def __post_init__(self):
        self.gross_pnl = (self.premium_collected - self.premium_paid) * 100  # Per contract
        self.net_pnl = self.gross_pnl - 2.0  # Commission
        self.hold_days = (self.exit_date - self.entry_date).days
        self.capital_required = self.strike * 100
        self.pnl_pct = (self.net_pnl / self.capital_required) * 100 if self.capital_required else 0


@dataclass
class RiskProfileResult:
    """Aggregated results for a specific risk profile."""
    profile_name: str
    risk_level: RiskLevel
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    return_on_capital: float
    avg_hold_days: float
    max_drawdown: float
    sharpe_ratio: float
    profit_factor: float
    
    # Exit reason breakdown
    profit_target_exits: int = 0
    trailing_defensive_exits: int = 0
    dte_exits: int = 0
    expiration_exits: int = 0
    
    # Trailing exit specific
    avg_breach_days_before_exit: float = 0.0
    immediate_exits_avoided: int = 0  # Would have been exits without confirmation
    
    trades: List[TrailingExitTrade] = field(default_factory=list)


class TrailingExitBacktester:
    """
    Backtests Theta strategy with trailing defensive exits.
    
    Key difference from standard backtest:
    - Instead of exiting immediately on breach, tracks consecutive breach days
    - Only exits after breach_confirmation_days consecutive breaches
    - Resets counter when price recovers
    """
    
    def __init__(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        risk_profile: RiskProfile,
        initial_capital: float = None
    ):
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.profile = risk_profile
        self.initial_capital = initial_capital or config.ACCOUNT_SIZE
        
        # Risk profile parameters
        self.breach_threshold_pct = risk_profile.breach_threshold_pct
        self.confirmation_days = risk_profile.breach_confirmation_days
        self.dte_exit_threshold = risk_profile.dte_exit_threshold
        self.week1_profit = risk_profile.week1_profit_pct / 100
        self.week2_profit = risk_profile.week2_profit_pct / 100
        self.week3_profit = risk_profile.week3_profit_pct / 100
        self.week4_profit = risk_profile.week4_profit_pct / 100
        
        # Load data
        self._load_data()
        
    def _load_data(self):
        """Load historical price data."""
        ticker = yf.Ticker(self.symbol)
        hist = ticker.history(start=self.start_date - timedelta(days=60), end=self.end_date + timedelta(days=1))
        
        if hist.empty:
            raise ValueError(f"No data available for {self.symbol}")
        
        self.prices = hist[['Close']].copy()
        self.prices.columns = ['close']
        self.prices.index = self.prices.index.date
        
        # Simulate IV (using 20-day rolling volatility * sqrt(252))
        returns = np.log(hist['Close'] / hist['Close'].shift(1))
        self.iv_series = returns.rolling(20).std() * np.sqrt(252)
        self.iv_series = self.iv_series.fillna(0.20)  # Default 20% IV
        self.iv_series.index = self.iv_series.index.date
        
    def _calculate_put_price(
        self, stock_price: float, strike: float, dte: int, iv: float
    ) -> Tuple[float, float]:
        """Calculate put option price and delta using Black-Scholes."""
        if dte <= 0:
            intrinsic = max(0, strike - stock_price)
            return intrinsic, -1.0 if stock_price < strike else 0.0
            
        calculator = BlackScholesCalculator(risk_free_rate=0.05)
        
        T = dte / 365  # Time in years
        sigma = max(0.05, iv)  # Volatility
        
        # Calculate put price and delta
        put_price = calculator.put_price(S=stock_price, K=strike, T=T, sigma=sigma)
        put_delta = calculator.delta(S=stock_price, K=strike, T=T, sigma=sigma, option_type="put")
        
        return put_price, put_delta
    
    def _find_target_strike(
        self, stock_price: float, dte: int, iv: float, target_delta: float = 0.30
    ) -> Optional[float]:
        """Find strike that gives approximately target delta."""
        best_strike = None
        best_delta_diff = float('inf')
        
        # Search range: 80% to 100% of stock price
        for pct in np.arange(0.80, 1.01, 0.01):
            strike = round(stock_price * pct, 2)
            _, delta = self._calculate_put_price(stock_price, strike, dte, iv)
            delta_diff = abs(abs(delta) - target_delta)
            
            if delta_diff < best_delta_diff:
                best_delta_diff = delta_diff
                best_strike = strike
        
        if best_delta_diff <= 0.05:  # Within tolerance
            return round(best_strike, 2)
        return None
    
    def _get_profit_target(self, days_held: int) -> float:
        """Get profit target percentage based on days held."""
        if days_held <= 7:
            return self.week1_profit
        elif days_held <= 14:
            return self.week2_profit
        elif days_held <= 21:
            return self.week3_profit
        else:
            return self.week4_profit
    
    def run_backtest(self) -> RiskProfileResult:
        """Run backtest with trailing defensive exits."""
        trades: List[TrailingExitTrade] = []
        trade_id = 0
        
        # Track stats
        immediate_exits_avoided = 0
        
        # Filter to backtest period
        trading_days = [d for d in self.prices.index if self.start_date <= d <= self.end_date]
        
        i = 0
        while i < len(trading_days) - 35:
            entry_date = trading_days[i]
            stock_price_entry = self.prices.loc[entry_date, 'close']
            iv_entry = self.iv_series.loc[entry_date]
            
            # Skip if IV too low
            if iv_entry < 0.10:
                i += 1
                continue
            
            dte_entry = 30
            strike = self._find_target_strike(stock_price_entry, dte_entry, iv_entry)
            
            if strike is None:
                i += 1
                continue
            
            premium_entry, delta_entry = self._calculate_put_price(
                stock_price_entry, strike, dte_entry, iv_entry
            )
            
            if premium_entry < 0.50:  # Min premium
                i += 1
                continue
            
            # Track position with trailing exit logic
            exit_date = None
            exit_reason = ""
            breach_days = 0
            consecutive_breach_days = 0
            would_have_exited_immediately = False
            
            for j in range(i + 1, min(i + 35, len(trading_days))):
                current_date = trading_days[j]
                days_held = (current_date - entry_date).days
                dte_current = dte_entry - days_held
                
                stock_price_current = self.prices.loc[current_date, 'close']
                iv_current = self.iv_series.loc[current_date]
                
                premium_current, _ = self._calculate_put_price(
                    stock_price_current, strike, dte_current, iv_current
                )
                
                # Calculate breach level
                breach_level = strike * (1 - self.breach_threshold_pct)
                is_in_breach = stock_price_current < breach_level
                
                if is_in_breach:
                    consecutive_breach_days += 1
                    breach_days += 1
                    
                    # Check if this would have triggered immediate exit
                    if consecutive_breach_days == 1:
                        would_have_exited_immediately = True
                    
                    # TRAILING EXIT: Only exit after confirmation days
                    if consecutive_breach_days >= self.confirmation_days:
                        exit_date = current_date
                        exit_reason = f"TRAILING_DEFENSIVE_{self.confirmation_days}D"
                        premium_exit = premium_current
                        break
                else:
                    # Price recovered - reset counter
                    if consecutive_breach_days > 0:
                        consecutive_breach_days = 0  # Reset!
                
                # Time-based profit target
                target_pct = self._get_profit_target(days_held)
                target_close = premium_entry * (1 - target_pct)
                
                if premium_current <= target_close:
                    exit_date = current_date
                    week_num = (days_held // 7) + 1
                    exit_reason = f"PROFIT_TARGET_W{week_num}"
                    premium_exit = premium_current
                    break
                
                # DTE exit
                if dte_current <= self.dte_exit_threshold:
                    exit_date = current_date
                    exit_reason = "DTE_EXIT"
                    premium_exit = premium_current
                    break
            
            # Handle end of simulation
            if exit_date is None:
                exit_date = trading_days[min(i + 34, len(trading_days) - 1)]
                days_held = (exit_date - entry_date).days
                dte_current = max(0, dte_entry - days_held)
                stock_price_exit = self.prices.loc[exit_date, 'close']
                iv_exit = self.iv_series.loc[exit_date]
                premium_exit, _ = self._calculate_put_price(
                    stock_price_exit, strike, dte_current, iv_exit
                )
                exit_reason = "EXPIRATION"
            else:
                stock_price_exit = self.prices.loc[exit_date, 'close']
            
            # Track avoided immediate exits
            if would_have_exited_immediately and "PROFIT" in exit_reason:
                immediate_exits_avoided += 1
            
            trade = TrailingExitTrade(
                trade_id=trade_id,
                symbol=self.symbol,
                entry_date=entry_date,
                exit_date=exit_date,
                stock_price_entry=stock_price_entry,
                strike=strike,
                dte_entry=dte_entry,
                premium_collected=premium_entry,
                iv_entry=iv_entry,
                delta_entry=delta_entry,
                stock_price_exit=stock_price_exit,
                premium_paid=premium_exit,
                dte_exit=max(0, dte_entry - (exit_date - entry_date).days),
                exit_reason=exit_reason,
                breach_days=breach_days
            )
            
            trades.append(trade)
            trade_id += 1
            
            i += 7  # Weekly trading
        
        return self._calculate_results(trades, immediate_exits_avoided)
    
    def _calculate_results(
        self, trades: List[TrailingExitTrade], immediate_exits_avoided: int
    ) -> RiskProfileResult:
        """Calculate aggregate results."""
        if not trades:
            return RiskProfileResult(
                profile_name=self.profile.name,
                risk_level=self.profile.level,
                total_trades=0, wins=0, losses=0, win_rate=0,
                total_pnl=0, return_on_capital=0, avg_hold_days=0,
                max_drawdown=0, sharpe_ratio=0, profit_factor=0,
                trades=[]
            )
        
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        
        win_rate = len(wins) / len(trades) * 100
        total_pnl = sum(t.net_pnl for t in trades)
        avg_hold = np.mean([t.hold_days for t in trades])
        
        # Exit reason counts
        profit_exits = len([t for t in trades if "PROFIT" in t.exit_reason])
        defensive_exits = len([t for t in trades if "DEFENSIVE" in t.exit_reason])
        dte_exits = len([t for t in trades if "DTE" in t.exit_reason])
        expiration_exits = len([t for t in trades if "EXPIRATION" in t.exit_reason])
        
        # Avg breach days for defensive exits
        defensive_trades = [t for t in trades if "DEFENSIVE" in t.exit_reason]
        avg_breach_days = (
            np.mean([t.breach_days for t in defensive_trades]) 
            if defensive_trades else 0
        )
        
        # Profit factor
        total_wins = sum(t.net_pnl for t in wins)
        total_losses = abs(sum(t.net_pnl for t in losses))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Drawdown
        equity_curve = np.cumsum([t.net_pnl for t in trades])
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (peak - equity_curve) / (self.initial_capital + peak) * 100
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0
        
        # Sharpe
        returns = [t.net_pnl / t.capital_required for t in trades if t.capital_required > 0]
        if len(returns) > 1:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(52)
        else:
            sharpe = 0
        
        return_pct = (total_pnl / self.initial_capital) * 100
        
        return RiskProfileResult(
            profile_name=self.profile.name,
            risk_level=self.profile.level,
            total_trades=len(trades),
            wins=len(wins),
            losses=len(losses),
            win_rate=win_rate,
            total_pnl=total_pnl,
            return_on_capital=return_pct,
            avg_hold_days=avg_hold,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            profit_factor=profit_factor,
            profit_target_exits=profit_exits,
            trailing_defensive_exits=defensive_exits,
            dte_exits=dte_exits,
            expiration_exits=expiration_exits,
            avg_breach_days_before_exit=avg_breach_days,
            immediate_exits_avoided=immediate_exits_avoided,
            trades=trades
        )


def run_risk_comparison_backtest():
    """Run backtest comparing all three risk profiles."""
    print("\n" + "=" * 80)
    print("TRAILING DEFENSIVE EXIT BACKTEST - RISK PROFILE COMPARISON")
    print("=" * 80)
    print("\nComparing LOW vs MEDIUM vs HIGH risk profiles with trailing exits")
    print("Trailing exits require confirmation days before exiting on breach\n")
    
    # Configuration
    symbols = ["SPY", "QQQ", "IWM"]
    start_date = date(2024, 1, 1)
    end_date = date(2025, 1, 1)
    
    profiles = [
        ("🛡️ LOW", LOW_RISK_PROFILE),
        ("⚖️ MEDIUM", MEDIUM_RISK_PROFILE), 
        ("🚀 HIGH", HIGH_RISK_PROFILE)
    ]
    
    all_results: Dict[str, List[RiskProfileResult]] = {
        "LOW": [], "MEDIUM": [], "HIGH": []
    }
    
    # Run backtests for each profile
    for profile_name, profile in profiles:
        print(f"\n{'='*80}")
        print(f"TESTING: {profile_name} Risk Profile")
        print(f"{'='*80}")
        print(f"  Breach Threshold: {profile.breach_threshold_pct*100:.0f}%")
        print(f"  Confirmation Days: {profile.breach_confirmation_days}")
        print(f"  DTE Exit: {profile.dte_exit_threshold} days")
        print()
        
        for symbol in symbols:
            print(f"  📊 Backtesting {symbol}...", end=" ")
            
            try:
                backtester = TrailingExitBacktester(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    risk_profile=profile
                )
                
                result = backtester.run_backtest()
                all_results[profile.level.value.upper()].append(result)
                
                print(f"{result.total_trades} trades, "
                      f"{result.win_rate:.0f}% WR, "
                      f"${result.total_pnl:+,.0f}")
                
            except Exception as e:
                print(f"ERROR: {e}")
    
    # Print comparison table
    print("\n\n" + "=" * 80)
    print("RISK PROFILE COMPARISON RESULTS")
    print("=" * 80)
    
    print(f"\n{'Profile':<12} {'Trades':<8} {'Win Rate':<10} {'P&L':<12} {'Return':<10} "
          f"{'Sharpe':<8} {'Max DD':<8} {'Def Exits':<10}")
    print("-" * 90)
    
    for level in ["LOW", "MEDIUM", "HIGH"]:
        results = all_results[level]
        if not results:
            continue
            
        total_trades = sum(r.total_trades for r in results)
        total_wins = sum(r.wins for r in results)
        win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0
        total_pnl = sum(r.total_pnl for r in results)
        return_pct = total_pnl / config.ACCOUNT_SIZE * 100
        avg_sharpe = np.mean([r.sharpe_ratio for r in results])
        max_dd = max(r.max_drawdown for r in results)
        def_exits = sum(r.trailing_defensive_exits for r in results)
        
        emoji = {"LOW": "🛡️", "MEDIUM": "⚖️", "HIGH": "🚀"}[level]
        print(f"{emoji} {level:<10} {total_trades:<8} {win_rate:>6.1f}%   "
              f"${total_pnl:>+9,.0f} {return_pct:>+7.1f}%   "
              f"{avg_sharpe:>6.2f} {max_dd:>7.1f}% {def_exits:>6}")
    
    # Detailed breakdown
    print("\n\n" + "=" * 80)
    print("TRAILING EXIT EFFECTIVENESS")
    print("=" * 80)
    
    print(f"\n{'Profile':<12} {'Profit Exits':<14} {'Trailing Exits':<16} "
          f"{'DTE Exits':<12} {'Avoided Immed':<14}")
    print("-" * 70)
    
    for level in ["LOW", "MEDIUM", "HIGH"]:
        results = all_results[level]
        if not results:
            continue
            
        profit_exits = sum(r.profit_target_exits for r in results)
        trailing_exits = sum(r.trailing_defensive_exits for r in results)
        dte_exits = sum(r.dte_exits for r in results)
        avoided = sum(r.immediate_exits_avoided for r in results)
        
        emoji = {"LOW": "🛡️", "MEDIUM": "⚖️", "HIGH": "🚀"}[level]
        print(f"{emoji} {level:<10} {profit_exits:<14} {trailing_exits:<16} "
              f"{dte_exits:<12} {avoided}")
    
    print("\n" + "=" * 80)
    print("KEY INSIGHTS")
    print("=" * 80)
    
    # Find best profile
    profile_pnl = {}
    for level in ["LOW", "MEDIUM", "HIGH"]:
        results = all_results[level]
        if results:
            profile_pnl[level] = sum(r.total_pnl for r in results)
    
    if profile_pnl:
        best_profile = max(profile_pnl, key=profile_pnl.get)
        worst_profile = min(profile_pnl, key=profile_pnl.get)
        
        print(f"\n  📈 Best Performing: {best_profile} (${profile_pnl[best_profile]:+,.0f})")
        print(f"  📉 Lowest Return: {worst_profile} (${profile_pnl[worst_profile]:+,.0f})")
        
        # Calculate improvement from trailing exits
        low_avoided = sum(r.immediate_exits_avoided for r in all_results["LOW"])
        med_avoided = sum(r.immediate_exits_avoided for r in all_results["MEDIUM"])
        
        print(f"\n  ✅ Trailing exits converted {low_avoided + med_avoided} potential losses to profits")
        print(f"  ✅ By waiting for confirmation, avoided premature defensive closes")
    
    print("\n" + "=" * 80)
    
    return all_results


if __name__ == "__main__":
    results = run_risk_comparison_backtest()
