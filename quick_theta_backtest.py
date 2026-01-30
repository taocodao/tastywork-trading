"""
Quick Theta Backtest - Trailing Stop vs Time-Based
==================================================

Compare performance of trailing stop exits vs pure time-based exits.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import date, timedelta

@dataclass
class Trade:
    entry_price: float
    days: int
    peak_pnl: float
    exit_pnl: float
    exit_reason: str

def simulate_trade(use_trailing=True):
    """Simulate one trade with realistic P&L movement."""
    entry = 4.50  # Premium received
    
    # Simulate daily P&L (option price decay + noise)
    days = []
    pnls = []
    
    for day in range(1, 35):  # Up to 35 days
        # Base decay (options lose value over time - good for seller)
        time_decay = day / 35.0  # Linear decay for simplicity
        base_pnl_pct = time_decay * 80  # Can go up to 80% profit
        
        # Add noise
        noise = np.random.normal(0, 15)
        pnl_pct = base_pnl_pct + noise
        
        days.append(day)
        pnls.append(pnl_pct)
    
    # Find exit point
    peak_pnl = 0
    for i, (day, pnl) in enumerate(zip(days, pnls)):
        peak_pnl = max(peak_pnl, pnl)
        
        # TIME-BASED EXITS (always checked)
        if day <= 7 and pnl >= 50:
            return Trade(entry, day, peak_pnl, pnl, "Week1_50%")
        elif day <= 14 and pnl >= 60:
            return Trade(entry, day, peak_pnl, pnl, "Week2_60%")
        elif day <= 21 and pnl >= 75:
            return Trade(entry, day, peak_pnl, pnl, "Week3_75%")
        elif day >= 22 and pnl >= 90:
            return Trade(entry, day, peak_pnl, pnl, "Week4_90%")
        
        # TRAILING STOP (only if enabled)
        if use_trailing and peak_pnl >= 30:  # Activated at 30% profit
            drawdown_from_peak = peak_pnl - pnl
            if drawdown_from_peak >= 50:  # 50% retracement from peak
                return Trade(entry, day, peak_pnl, pnl, "Trailing_Stop")
        
        # MAX LOSS
        if pnl <= -200:
            return Trade(entry, day, peak_pnl, pnl, "Max_Loss")
    
    # Hold to end
    return Trade(entry, 35, peak_pnl, pnls[-1], "Expiration")


def run_backtest(num_trades=300, use_trailing=True):
    """Run backtest with multiple simulated trades."""
    trades = []
    
    for _ in range(num_trades):
        trade = simulate_trade(use_trailing)
        trades.append(trade)
    
    df = pd.DataFrame([{
        'days_held': t.days,
        'peak_pnl_pct': t.peak_pnl,
        'exit_pnl_pct': t.exit_pnl,
        'exit_reason': t.exit_reason,
        'pnl_dollars': (t.exit_pnl / 100) * (t.entry_price * 100 * 10),  # 10 contracts
    } for t in trades])
    
    return df


def print_results(df, title):
    """Print backtest results."""
    print(f"\n{'=' * 70}")
    print(f"{title}")
    print("=" * 70)
    
    # Overall stats
    total_pnl = df['pnl_dollars'].sum()
    avg_pnl = df['pnl_dollars'].mean()
    win_rate = (df['pnl_dollars'] > 0).sum() / len(df) * 100
    avg_days = df['days_held'].mean()
    
    print(f"Total Trades: {len(df)}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Total P&L: ${total_pnl:,.2f}")
    print(f"Average P&L per Trade: ${avg_pnl:,.2f}")
    print(f"Average Hold Time: {avg_days:.1f} days")
    print(f"Average Exit P&L%: {df['exit_pnl_pct'].mean():.1f}%")
    print(f"Average Peak P&L%: {df['peak_pnl_pct'].mean():.1f}%")
    print()
    
    # Exit reason breakdown
    print("Exit Reasons:")
    exit_counts = df['exit_reason'].value_counts()
    for reason in exit_counts.index:
        count = exit_counts[reason]
        pct = (count / len(df)) * 100
        avg_pnl_reason = df[df['exit_reason'] == reason]['pnl_dollars'].mean()
        print(f"  {reason}: {count} ({pct:.1f}%) - Avg P&L: ${avg_pnl_reason:,.2f}")
    
    print("=" * 70)
    
    return {
        'total_pnl': total_pnl,
        'win_rate': win_rate,
        'avg_days': avg_days,
        'avg_pnl': avg_pnl
    }


if __name__ == "__main__":
    # Set random seed for reproducibility
    np.random.seed(42)
    
    print("\n" + "=" * 70)
    print("THETA STRATEGY BACKTEST: Trailing Stop Comparison")
    print("=" * 70)
    print("\nSimulating 300 trades per strategy...")
    print("Entry: Sell 10 contracts @ $4.50 premium")
    print("Capital Required per Trade: $59,500 (595 strike)")
    
    # Test WITH trailing stop
    df_with = run_backtest(300, use_trailing=True)
    results_with = print_results(df_with, "WITH TRAILING STOP (30% activation, 50% stop)")
    
    # Test WITHOUT trailing stop
    df_without = run_backtest(300, use_trailing=False)
    results_without = print_results(df_without, "WITHOUT TRAILING STOP (Time-Based Only)")
    
    # Comparison
    print("\n" + "=" * 70)
    print("COMPARISON")
    print("=" * 70)
    print(f"{'Metric':<30} {'With Trailing':<20} {'Without Trailing':<15} {'Difference'}")
    print("-" * 70)
    
    metrics = [
        ('Total P&L', 'total_pnl', '$'),
        ('Win Rate', 'win_rate', '%'),
        ('Avg Hold Time', 'avg_days', ' days'),
        ('Avg P&L/Trade', 'avg_pnl', '$'),
    ]
    
    for label, key, unit in metrics:
        val1 = results_with[key]
        val2 = results_without[key]
        diff = val1 - val2
        
        if unit == '$':
            print(f"{label:<30} ${val1:>18,.2f} ${val2:>13,.2f} ${diff:>12.2f}")
        elif unit == '%':
            print(f"{label:<30} {val1:>18.1f}% {val2:>13.1f}% {diff:>12.1f}%")
        elif unit == ' days':
            print(f"{label:<30} {val1:>15.1f} days {val2:>10.1f} days {diff:>9.1f} days")
    
    print("=" * 70)
    
    # Key insight
    print("\nKEY INSIGHTS:")
    pnl_diff = results_with['total_pnl'] - results_without['total_pnl']
    if pnl_diff > 0:
        improvement = (pnl_diff / abs(results_without['total_pnl'])) * 100
        print(f"✅ Trailing stop IMPROVED P&L by ${pnl_diff:,.2f} ({improvement:+.1f}%)")
        print(f"   Captures more profit by locking in gains before full reversal")
    else:
        decline = (pnl_diff / abs(results_without['total_pnl'])) * 100
        print(f"⚠️  Trailing stop REDUCED P&L by ${abs(pnl_diff):,.2f} ({decline:.1f}%)")
        print(f"   May exit too early, missing additional time decay")
    
    days_diff = results_with['avg_days'] - results_without['avg_days']
    if days_diff < 0:
        print(f"✅ Trailing stop REDUCED hold time by {abs(days_diff):.1f} days")
        print(f"   Faster capital turnover = more trades per year")
    
    print()
