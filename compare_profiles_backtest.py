"""
Profile Comparison Backtest
============================
Compare performance with and without symbol-specific profiles.
"""

import sys
sys.path.insert(0, '.')

from backtest_theta import ThetaStrategyBacktester
from src.theta_spreads.symbol_profiles import SYMBOL_PROFILES
from datetime import date
import pandas as pd

def run_comparison_backtest():
    """Run backtest comparing default vs optimized profiles."""
    
    print("\n" + "=" * 90)
    print("PROFILE OPTIMIZATION COMPARISON BACKTEST")
    print("=" * 90)
    print("Testing symbol profiles against default parameters")
    print("Period: 2024-01-01 to 2025-01-01")
    print()
    
    # Test key ETFs from each asset class
    test_symbols = [
        ("SPY", "Core Equity"),
        ("QQQ", "Tech/High Beta"),
        ("IWM", "Small Cap"),
        ("TLT", "Bonds"),
        ("GLD", "Commodities"),
        ("XLK", "Tech Sector"),
        ("XLF", "Financials"),
        ("XLE", "Energy"),
    ]
    
    results_default = []
    results_optimized = []
    
    for symbol, category in test_symbols:
        print(f"\n{'='*90}")
        print(f"Testing: {symbol} ({category})")
        print('='*90)
        
        if symbol not in SYMBOL_PROFILES:
            print(f"⚠️  {symbol} has no custom profile - skipping comparison")
            continue
        
        try:
            # Test 1: WITHOUT profile (default config)
            print(f"\n[1/2] Running with DEFAULT parameters...")
            backtester_default = ThetaStrategyBacktester(
                symbol=symbol,
                start_date=date(2024, 1, 1),
                end_date=date(2025, 1, 1),
                initial_capital=50000,
                use_profile=False  # Disable profile
            )
            result_default = backtester_default.run_backtest()
            results_default.append((symbol, category, result_default))
            
            # Test 2: WITH profile (optimized)
            print(f"\n[2/2] Running with OPTIMIZED profile...")
            backtester_optimized = ThetaStrategyBacktester(
                symbol=symbol,
                start_date=date(2024, 1, 1),
                end_date=date(2025, 1, 1),
                initial_capital=50000,
                use_profile=True  # Use profile
            )
            result_optimized = backtester_optimized.run_backtest()
            results_optimized.append((symbol, category, result_optimized))
            
            # Quick comparison
            print(f"\n{'─'*90}")
            print(f"COMPARISON for {symbol}:")
            print(f"{'─'*90}")
            print(f"{'Metric':<25} {'Default':<20} {'Optimized':<20} {'Change':<15}")
            print(f"{'─'*90}")
            
            def compare(name, default_val, opt_val, is_pct=False, reverse=False):
                if is_pct:
                    change = opt_val - default_val
                    change_str = f"{change:+.1f}%"
                else:
                    if default_val != 0:
                        change_pct = ((opt_val - default_val) / abs(default_val)) * 100
                        change_str = f"{change_pct:+.1f}%"
                    else:
                        change_str = "N/A"
                
                symbol_map = {True: "✅", False: "❌"}
                if reverse:
                    is_better = opt_val < default_val
                else:
                    is_better = opt_val > default_val
                
                status = "✅" if is_better else ("❌" if opt_val != default_val else "─")
                
                print(f"{name:<25} {default_val:<20} {opt_val:<20} {change_str:<15} {status}")
            
            compare("Win Rate", f"{result_default.win_rate:.1f}%", f"{result_optimized.win_rate:.1f}%")
            compare("Total P&L", f"${result_default.total_pnl:,.0f}", f"${result_optimized.total_pnl:,.0f}")
            compare("Avg Win", f"${result_default.avg_win:.0f}", f"${result_optimized.avg_win:.0f}")
            compare("Avg Loss", f"${result_default.avg_loss:.0f}", f"${result_optimized.avg_loss:.0f}", reverse=True)
            compare("Max Drawdown", f"{result_default.max_drawdown:.1f}%", f"{result_optimized.max_drawdown:.1f}%", reverse=True)
            compare("Sharpe Ratio", f"{result_default.sharpe_ratio:.2f}", f"{result_optimized.sharpe_ratio:.2f}")
            compare("ROC", f"{result_default.return_on_capital:.1f}%", f"{result_optimized.return_on_capital:.1f}%")
            
            print(f"{'─'*90}\n")
            
        except Exception as e:
            print(f"❌ ERROR testing {symbol}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Summary Table
    print("\n\n" + "=" * 90)
    print("OVERALL COMPARISON SUMMARY")
    print("=" * 90)
    print()
    
    print(f"{'Symbol':<8} {'Category':<20} {'Default P&L':<15} {'Optimized P&L':<15} {'Improvement':<15} {'Status'}")
    print("─" * 90)
    
    total_improvement = 0
    wins = 0
    losses = 0
    
    for i, (symbol, category, res_def) in enumerate(results_default):
        _, _, res_opt = results_optimized[i]
        
        improvement = res_opt.total_pnl - res_def.total_pnl
        if res_def.total_pnl != 0:
            improvement_pct = (improvement / abs(res_def.total_pnl)) * 100
        else:
            improvement_pct = 0
        
        status = "✅ Better" if improvement > 0 else ("❌ Worse" if improvement < 0 else "─ Same")
        
        if improvement > 0:
            wins += 1
        elif improvement < 0:
            losses += 1
        
        total_improvement += improvement
        
        print(f"{symbol:<8} {category:<20} ${res_def.total_pnl:>12,.0f} ${res_opt.total_pnl:>13,.0f} "
              f"{improvement_pct:>+12.1f}% {status}")
    
    print("─" * 90)
    print(f"{'TOTAL':<8} {'All Symbols':<20} ${sum(r.total_pnl for _, _, r in results_default):>12,.0f} "
          f"${sum(r.total_pnl for _, _, r in results_optimized):>13,.0f} "
          f"{total_improvement:>+12,.0f}")
    print()
    print(f"Symbols Improved: {wins}")
    print(f"Symbols Degraded: {losses}")
    print(f"Net Improvement: ${total_improvement:+,.0f}")
    
    if wins > losses:
        print("\n✅ VERDICT: Symbol profiles IMPROVE performance overall")
    elif wins < losses:
        print("\n⚠️ VERDICT: Symbol profiles DEGRADE performance - needs review")
    else:
        print("\n─ VERDICT: Symbol profiles show MIXED results")
    
    print("\n" + "=" * 90)
    
    return results_default, results_optimized


if __name__ == "__main__":
    results = run_comparison_backtest()
