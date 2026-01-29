"""
Comprehensive Theta Strategy Backtests
======================================
Tests across multiple time periods and securities to validate strategy robustness.
"""

import sys
sys.path.insert(0, '.')

from datetime import date
from backtest_theta import ThetaStrategyBacktester, run_theta_backtest
import config

print("\n" + "=" * 80)
print("COMPREHENSIVE THETA STRATEGY BACKTESTS")
print("=" * 80)
print("Testing multiple periods and securities for robustness validation")
print()

# Test configurations
test_configs = [
    # Original test (2024 - bull market)
    {
        "name": "2024 Bull Market (Original)",
        "symbols": ["SPY", "QQQ", "IWM"],
        "start": date(2024, 1, 1),
        "end": date(2025, 1, 1)
    },
    
    # 2023 - Recovery year after 2022 bear market
    {
        "name": "2023 Recovery Period",
        "symbols": ["SPY", "QQQ", "IWM"],
        "start": date(2023, 1, 1),
        "end": date(2024, 1, 1)
    },
    
    # 2022 - Bear market (high IV, challenging conditions)
    {
        "name": "2022 Bear Market",
        "symbols": ["SPY", "QQQ", "IWM"],
        "start": date(2022, 1, 1),
        "end": date(2023, 1, 1)
    },
    
    # Individual tech stocks (2024)
    {
        "name": "2024 Tech Stocks",
        "symbols": ["AAPL", "NVDA", "TSLA"],
        "start": date(2024, 1, 1),
        "end": date(2025, 1, 1)
    },
    
    # Sector ETFs (2024)
    {
        "name": "2024 Sector ETFs",
        "symbols": ["XLF", "XLE", "XLV"],  # Financials, Energy, Healthcare
        "start": date(2024, 1, 1),
        "end": date(2025, 1, 1)
    },
]

all_test_results = []

for test_config in test_configs:
    print("\n" + "=" * 80)
    print(f"TEST: {test_config['name']}")
    print("=" * 80)
    print(f"Period: {test_config['start']} to {test_config['end']}")
    print(f"Securities: {', '.join(test_config['symbols'])}")
    print()
    
    test_results = []
    
    for symbol in test_config['symbols']:
        try:
            print(f"\nBacktesting {symbol}...")
            
            backtester = ThetaStrategyBacktester(
                symbol=symbol,
                start_date=test_config['start'],
                end_date=test_config['end'],
                initial_capital=config.ACCOUNT_SIZE
            )
            
            result = backtester.run_backtest()
            result.print_summary()
            test_results.append(result)
            
        except Exception as e:
            print(f"ERROR testing {symbol}: {e}")
            continue
    
    # Combined summary for this test
    if test_results:
        print("\n" + "=" * 80)
        print(f"COMBINED RESULTS: {test_config['name']}")
        print("=" * 80)
        
        total_trades = sum(r.total_trades for r in test_results)
        total_pnl = sum(r.total_pnl for r in test_results)
        total_wins = sum(r.wins for r in test_results)
        overall_win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0
        
        avg_sharpe = sum(r.sharpe_ratio for r in test_results) / len(test_results) if test_results else 0
        max_dd = max(r.max_drawdown for r in test_results) if test_results else 0
        
        print(f"\n  Total Trades: {total_trades}")
        print(f"  Overall Win Rate: {overall_win_rate:.1f}%")
        print(f"  Total P&L: ${total_pnl:+,.2f}")
        print(f"  Return on Capital: {total_pnl / config.ACCOUNT_SIZE * 100:+.2f}%")
        print(f"  Avg Sharpe Ratio: {avg_sharpe:.2f}")
        print(f"  Max Drawdown (worst): {max_dd:.1f}%")
        
        print("\n  Per Symbol:")
        for r in test_results:
            print(f"    {r.symbol}: {r.total_trades} trades, "
                  f"{r.win_rate:.0f}% WR, "
                  f"${r.total_pnl:+,.0f} ({r.return_on_capital:+.1f}%)")
        
        all_test_results.append({
            "config": test_config,
            "results": test_results,
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "win_rate": overall_win_rate,
            "return_pct": total_pnl / config.ACCOUNT_SIZE * 100,
            "sharpe": avg_sharpe,
            "max_dd": max_dd
        })

# Final comparison across all tests
print("\n\n" + "=" * 80)
print("CROSS-PERIOD & ASSET CLASS COMPARISON")
print("=" * 80)

print(f"\n{'Test Name':<30} {'Return':<12} {'Win Rate':<12} {'Sharpe':<10} {'Max DD':<10}")
print("-" * 80)

for test in all_test_results:
    print(f"{test['config']['name']:<30} "
          f"{test['return_pct']:>10.1f}% "
          f"{test['win_rate']:>10.1f}% "
          f"{test['sharpe']:>8.2f} "
          f"{test['max_dd']:>8.1f}%")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)

if all_test_results:
    avg_return = sum(t['return_pct'] for t in all_test_results) / len(all_test_results)
    avg_win_rate = sum(t['win_rate'] for t in all_test_results) / len(all_test_results)
    avg_sharpe = sum(t['sharpe'] for t in all_test_results) / len(all_test_results)
    
    print(f"\nAverage across all tests:")
    print(f"  Annual Return: {avg_return:.1f}%")
    print(f"  Win Rate: {avg_win_rate:.1f}%")
    print(f"  Sharpe Ratio: {avg_sharpe:.2f}")
    print()
    print("Strategy robustness validated!" if avg_return > 15 else "Strategy needs refinement for different conditions")
