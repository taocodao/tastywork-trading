"""
Enhanced Theta Backtest with Symbol Profiles
==============================================
Tests new symbol profiles (bonds, commodities, sectors) to validate optimizations.
"""

import sys
sys.path.insert(0, '.')

from backtest_theta import ThetaStrategyBacktester, logger
from src.theta_spreads.symbol_profiles import get_symbol_profile, SYMBOL_PROFILES
from datetime import date
import config

def run_profile_validation_backtest():
    """Run backtest on ETFs with new symbol profiles."""
    print("\n" + "=" * 80)
    print("THETA PROFILE VALIDATION BACKTEST")
    print("=" * 80)
    print(f"Testing {len(SYMBOL_PROFILES)} ETFs with optimized symbol profiles")
    print(f"Period: 2024-01-01 to 2025-01-01")
    print()
    
    # Test ETFs across all asset classes
    test_symbols = [
        # Core Equity (already tested)
        ("SPY", "Core Equity"),
        ("QQQ", "Core Equity - High Beta"),
        ("IWM", "Core Equity - Small Cap"),
        
        # Bonds (NEW)
        ("TLT", "Bonds - Long-term Treasury"),
        ("AGG", "Bonds - Aggregate"),
        
        # Commodities (NEW)
        ("GLD", "Commodity - Gold"),
        ("SLV", "Commodity - Silver"),
        
        # Tech Sector (NEW)
        ("XLK", "Sector - Technology"),
        
        # Defensive Sector (NEW)
        ("XLV", "Sector - Healthcare"),
        ("XLP", "Sector - Consumer Staples"),
        
        # Cyclical Sector (NEW)
        ("XLF", "Sector - Financials"),
        ("XLE", "Sector - Energy"),
    ]
    
    results = []
    
    for symbol, category in test_symbols:
        print(f"\n{'='*80}")
        print(f"Testing: {symbol} ({category})")
        print('='*80)
        
        # Get profile for this symbol
        if symbol in SYMBOL_PROFILES:
            profile = get_symbol_profile(symbol)
            print(f"✅ Using optimized profile:")
            print(f"   Week1 Target: {profile.week1_profit_pct}%")
            print(f"   Breach Threshold: {profile.breach_threshold_pct*100}%")
            print(f"   Confirmation Days: {profile.breach_confirmation_days}")
            print(f"   DTE Exit: {profile.dte_exit_threshold}")
        else:
            print(f"⚠️  Using default MEDIUM profile (no optimization)")
        
        print()
        
        try:
            backtester = ThetaStrategyBacktester(
                symbol=symbol,
                start_date=date(2024, 1, 1),
                end_date=date(2025, 1, 1),
                initial_capital=50000
            )
            
            result = backtester.run_backtest()
            result.print_summary()
            results.append((symbol, category, result))
            
        except Exception as e:
            print(f"❌ ERROR testing {symbol}: {e}")
            logger.error(f"Backtest failed for {symbol}", exc_info=True)
            continue
    
    # Summary comparison
    print("\n" + "=" * 80)
    print("PROFILE VALIDATION SUMMARY")
    print("=" * 80)
    print()
    
    print(f"{'Symbol':<8} {'Category':<25} {'Trades':<8} {'WR':<8} {'P&L':<12} {'ROC':<8}")
    print("-" * 80)
    
    for symbol, category, res in results:
        print(f"{symbol:<8} {category:<25} {res.total_trades:<8} "
              f"{res.win_rate:>6.1f}% {res.total_pnl:>+10.0f} {res.return_on_capital:>+6.1f}%")
    
    print()
    
    # Asset class comparison
    print("\nASSET CLASS PERFORMANCE:")
    print("-" * 80)
    
    asset_classes = {}
    for symbol, category, res in results:
        asset_class = category.split(' - ')[0]
        if asset_class not in asset_classes:
            asset_classes[asset_class] = []
        asset_classes[asset_class].append(res)
    
    for ac, res_list in asset_classes.items():
        total_trades = sum(r.total_trades for r in res_list)
        avg_wr = sum(r.win_rate for r in res_list) / len(res_list)
        total_pnl = sum(r.total_pnl for r in res_list)
        avg_roc = sum(r.return_on_capital for r in res_list) / len(res_list)
        
        print(f"\n{ac}:")
        print(f"  Symbols: {len(res_list)}")
        print(f"  Total Trades: {total_trades}")
        print(f"  Avg Win Rate: {avg_wr:.1f}%")
        print(f"  Total P&L: ${total_pnl:+,.0f}")
        print(f"  Avg ROC: {avg_roc:+.1f}%")
    
    print()
    print("=" * 80)
    
    # Identify best/worst performers
    if results:
        best = max(results, key=lambda x: x[2].return_on_capital)
        worst = min(results, key=lambda x: x[2].return_on_capital)
        
        print("\n🏆 BEST PERFORMER:")
        print(f"   {best[0]} ({best[1]}): {best[2].return_on_capital:+.1f}% ROC, {best[2].win_rate:.0f}% WR")
        
        print("\n⚠️  WORST PERFORMER:")
        print(f"   {worst[0]} ({worst[1]}): {worst[2].return_on_capital:+.1f}% ROC, {worst[2].win_rate:.0f}% WR")
        
        if worst[2].return_on_capital < 0:
            print(f"\n   💡 Recommendation: Consider excluding {worst[0]} or tightening profit targets")
    
    return results


if __name__ == "__main__":
    results = run_profile_validation_backtest()
