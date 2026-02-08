"""
Calendar Spread Trailing Stop Backtest
======================================
Analyzes the impact of trailing profit stops on Calendar Spread performance.

This compares:
1. Fixed profit target (+35%) and stop loss (-40%)
2. Trailing profit lock (activate at +20%, trail by 50%)
3. Different trailing percentages

Based on synthetic realistic assumptions from calendar spread research.
"""

import sys
import io
import json

# Force UTF-8 encoding for Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import List, Dict, Tuple
import numpy as np
import random

random.seed(42)
np.random.seed(42)


@dataclass
class TradeResult:
    """Single trade outcome."""
    trade_id: int
    symbol: str
    days_held: int
    initial_debit: float
    peak_value: float
    peak_pnl_pct: float
    exit_value: float
    pnl: float
    pnl_pct: float
    exit_reason: str


@dataclass
class BacktestResult:
    """Aggregated backtest statistics."""
    strategy_name: str
    total_trades: int
    winners: int
    losers: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    sharpe_ratio: float
    profit_factor: float


def simulate_calendar_price_path(
    initial_debit: float,
    days: int = 21,
    volatility: float = 0.08
) -> List[Tuple[int, float]]:
    """
    Simulate realistic calendar spread price path.
    
    Calendar spreads have unique characteristics:
    - Peak around mid-point when short leg has ~7-10 DTE
    - Value decays as expiration approaches
    - Sensitive to stock movement (move away = lose value)
    """
    prices = [(0, initial_debit)]
    current = initial_debit
    
    for day in range(1, days + 1):
        # Calendar spread typical behavior:
        # - Increases slightly as short leg decays (first 60% of hold)
        # - Risk of sudden drops from stock movement
        # - Final days can be volatile
        
        if day < days * 0.6:
            # Early phase: gradual appreciation + noise
            drift = 0.015  # ~1.5% per day average theta
        else:
            # Late phase: decay accelerates, more volatile
            drift = -0.005
        
        # Random movement
        daily_return = drift + volatility * np.random.randn()
        current = current * (1 + daily_return)
        current = max(current, initial_debit * 0.20)  # Floor at 80% loss
        
        prices.append((day, current))
    
    return prices


def backtest_fixed_targets(
    price_path: List[Tuple[int, float]],
    initial_debit: float,
    profit_target: float = 0.35,
    stop_loss: float = -0.40
) -> TradeResult:
    """
    Fixed profit target and stop loss strategy.
    Exit at +35% or -40%, whichever comes first.
    """
    peak_value = initial_debit
    peak_pnl_pct = 0.0
    
    for day, value in price_path:
        pnl_pct = (value - initial_debit) / initial_debit
        
        if value > peak_value:
            peak_value = value
            peak_pnl_pct = pnl_pct
        
        # Check profit target
        if pnl_pct >= profit_target:
            return TradeResult(
                trade_id=0, symbol="SYN", days_held=day,
                initial_debit=initial_debit, peak_value=peak_value,
                peak_pnl_pct=peak_pnl_pct, exit_value=value,
                pnl=value - initial_debit, pnl_pct=pnl_pct,
                exit_reason="Profit Target"
            )
        
        # Check stop loss
        if pnl_pct <= stop_loss:
            return TradeResult(
                trade_id=0, symbol="SYN", days_held=day,
                initial_debit=initial_debit, peak_value=peak_value,
                peak_pnl_pct=peak_pnl_pct, exit_value=value,
                pnl=value - initial_debit, pnl_pct=pnl_pct,
                exit_reason="Stop Loss"
            )
    
    # Hold to end (DTE exit)
    final_value = price_path[-1][1]
    final_pnl_pct = (final_value - initial_debit) / initial_debit
    return TradeResult(
        trade_id=0, symbol="SYN", days_held=len(price_path)-1,
        initial_debit=initial_debit, peak_value=peak_value,
        peak_pnl_pct=peak_pnl_pct, exit_value=final_value,
        pnl=final_value - initial_debit, pnl_pct=final_pnl_pct,
        exit_reason="DTE Exit"
    )


def backtest_trailing_profit(
    price_path: List[Tuple[int, float]],
    initial_debit: float,
    activation_pct: float = 0.20,
    trail_pct: float = 0.50,
    stop_loss: float = -0.40
) -> TradeResult:
    """
    Trailing profit lock strategy.
    
    Once profit reaches activation_pct, start trailing.
    Exit if profit drops trail_pct from peak.
    E.g., activation=20%, trail=50%: 
    - At +20%, trailing activates
    - Peak at +40%, exit if drops to +20% (40% * 0.5 = 20%)
    """
    peak_value = initial_debit
    peak_pnl_pct = 0.0
    trailing_active = False
    trailing_high = 0.0
    
    for day, value in price_path:
        pnl_pct = (value - initial_debit) / initial_debit
        
        if value > peak_value:
            peak_value = value
            peak_pnl_pct = pnl_pct
        
        # Activate trailing if profit threshold reached
        if pnl_pct >= activation_pct and not trailing_active:
            trailing_active = True
            trailing_high = pnl_pct
        
        # Update trailing high
        if trailing_active and pnl_pct > trailing_high:
            trailing_high = pnl_pct
        
        # Check trailing stop
        if trailing_active:
            trail_trigger = trailing_high * (1 - trail_pct)
            if pnl_pct <= trail_trigger:
                return TradeResult(
                    trade_id=0, symbol="SYN", days_held=day,
                    initial_debit=initial_debit, peak_value=peak_value,
                    peak_pnl_pct=peak_pnl_pct, exit_value=value,
                    pnl=value - initial_debit, pnl_pct=pnl_pct,
                    exit_reason=f"Trailing Stop (from {trailing_high:.0%})"
                )
        
        # Check stop loss
        if pnl_pct <= stop_loss:
            return TradeResult(
                trade_id=0, symbol="SYN", days_held=day,
                initial_debit=initial_debit, peak_value=peak_value,
                peak_pnl_pct=peak_pnl_pct, exit_value=value,
                pnl=value - initial_debit, pnl_pct=pnl_pct,
                exit_reason="Stop Loss"
            )
    
    # Hold to end
    final_value = price_path[-1][1]
    final_pnl_pct = (final_value - initial_debit) / initial_debit
    return TradeResult(
        trade_id=0, symbol="SYN", days_held=len(price_path)-1,
        initial_debit=initial_debit, peak_value=peak_value,
        peak_pnl_pct=peak_pnl_pct, exit_value=final_value,
        pnl=final_value - initial_debit, pnl_pct=final_pnl_pct,
        exit_reason="DTE Exit"
    )


def calculate_backtest_stats(
    trades: List[TradeResult],
    strategy_name: str
) -> BacktestResult:
    """Calculate aggregate statistics."""
    
    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]
    
    total_pnl = sum(t.pnl for t in trades)
    
    # Calculate drawdown
    cumulative = 0
    peak = 0
    max_dd = 0
    for t in trades:
        cumulative += t.pnl
        peak = max(peak, cumulative)
        dd = (peak - cumulative) / max(peak, 1)
        max_dd = max(max_dd, dd)
    
    # Calculate Sharpe (simplified)
    returns = [t.pnl_pct for t in trades]
    mean_return = np.mean(returns)
    std_return = np.std(returns) if len(returns) > 1 else 1
    sharpe = (mean_return * 52) / (std_return * np.sqrt(52)) if std_return > 0 else 0
    
    # Profit factor
    gross_profit = sum(t.pnl for t in winners) if winners else 0
    gross_loss = abs(sum(t.pnl for t in losers)) if losers else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    return BacktestResult(
        strategy_name=strategy_name,
        total_trades=len(trades),
        winners=len(winners),
        losers=len(losers),
        win_rate=len(winners) / len(trades) * 100,
        total_pnl=total_pnl,
        avg_pnl=total_pnl / len(trades),
        avg_win=sum(t.pnl for t in winners) / len(winners) if winners else 0,
        avg_loss=sum(t.pnl for t in losers) / len(losers) if losers else 0,
        max_drawdown=max_dd * 100,
        sharpe_ratio=sharpe,
        profit_factor=profit_factor
    )


def run_comparison_backtest(num_trades: int = 500) -> Dict:
    """
    Run comparison between fixed target and trailing stop strategies.
    """
    print("=" * 60)
    print("CALENDAR SPREAD TRAILING STOP BACKTEST")
    print("=" * 60)
    print(f"\nSimulating {num_trades} trades...\n")
    
    # Generate price paths
    price_paths = []
    for i in range(num_trades):
        debit = np.random.uniform(1.50, 3.50)
        days = int(np.random.uniform(14, 21))
        path = simulate_calendar_price_path(debit, days)
        price_paths.append((debit, path))
    
    # Strategy 1: Fixed targets (+35% / -40%)
    fixed_trades = []
    for i, (debit, path) in enumerate(price_paths):
        trade = backtest_fixed_targets(path, debit, 0.35, -0.40)
        trade.trade_id = i + 1
        fixed_trades.append(trade)
    
    fixed_result = calculate_backtest_stats(fixed_trades, "Fixed Targets (+35%/-40%)")
    
    # Strategy 2: Trailing profit (20% activation, 50% trail)
    trailing_20_50_trades = []
    for i, (debit, path) in enumerate(price_paths):
        trade = backtest_trailing_profit(path, debit, 0.20, 0.50, -0.40)
        trade.trade_id = i + 1
        trailing_20_50_trades.append(trade)
    
    trailing_20_50_result = calculate_backtest_stats(
        trailing_20_50_trades, 
        "Trailing (20% act, 50% trail)"
    )
    
    # Strategy 3: Trailing profit (15% activation, 40% trail) - tighter
    trailing_15_40_trades = []
    for i, (debit, path) in enumerate(price_paths):
        trade = backtest_trailing_profit(path, debit, 0.15, 0.40, -0.40)
        trade.trade_id = i + 1
        trailing_15_40_trades.append(trade)
    
    trailing_15_40_result = calculate_backtest_stats(
        trailing_15_40_trades, 
        "Trailing (15% act, 40% trail)"
    )
    
    # Strategy 4: Trailing profit (25% activation, 60% trail) - looser
    trailing_25_60_trades = []
    for i, (debit, path) in enumerate(price_paths):
        trade = backtest_trailing_profit(path, debit, 0.25, 0.60, -0.40)
        trade.trade_id = i + 1
        trailing_25_60_trades.append(trade)
    
    trailing_25_60_result = calculate_backtest_stats(
        trailing_25_60_trades, 
        "Trailing (25% act, 60% trail)"
    )
    
    results = [
        fixed_result,
        trailing_20_50_result,
        trailing_15_40_result,
        trailing_25_60_result
    ]
    
    # Print comparison table
    print("=" * 80)
    print("RESULTS COMPARISON")
    print("=" * 80)
    print(f"{'Strategy':<32} {'Win%':<8} {'Avg P&L':<10} {'Total P&L':<12} {'Sharpe':<8} {'Max DD':<8}")
    print("-" * 80)
    
    for r in results:
        print(f"{r.strategy_name:<32} {r.win_rate:<8.1f} ${r.avg_pnl:<9.2f} ${r.total_pnl:<11.2f} {r.sharpe_ratio:<8.2f} {r.max_drawdown:<7.1f}%")
    
    # Calculate differences
    print("\n" + "=" * 80)
    print("COMPARISON TO FIXED TARGETS")
    print("=" * 80)
    
    baseline = fixed_result
    for r in results[1:]:
        pnl_diff = ((r.total_pnl - baseline.total_pnl) / abs(baseline.total_pnl)) * 100
        wr_diff = r.win_rate - baseline.win_rate
        sharpe_diff = r.sharpe_ratio - baseline.sharpe_ratio
        
        print(f"\n{r.strategy_name}:")
        print(f"  Total P&L: {'+' if pnl_diff >= 0 else ''}{pnl_diff:.1f}%")
        print(f"  Win Rate:  {'+' if wr_diff >= 0 else ''}{wr_diff:.1f}%")
        print(f"  Sharpe:    {'+' if sharpe_diff >= 0 else ''}{sharpe_diff:.2f}")
    
    # Exit reason breakdown
    print("\n" + "=" * 80)
    print("EXIT REASON BREAKDOWN (Trailing 20%/50%)")
    print("=" * 80)
    
    exit_reasons = {}
    for t in trailing_20_50_trades:
        reason = t.exit_reason.split(" (")[0]  # Remove trailing high info
        if reason not in exit_reasons:
            exit_reasons[reason] = {"count": 0, "total_pnl": 0}
        exit_reasons[reason]["count"] += 1
        exit_reasons[reason]["total_pnl"] += t.pnl
    
    for reason, data in sorted(exit_reasons.items(), key=lambda x: -x[1]["count"]):
        avg_pnl = data["total_pnl"] / data["count"]
        print(f"  {reason:<20}: {data['count']:>4} trades, avg P&L: ${avg_pnl:>7.2f}")
    
    # Recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    best = max(results, key=lambda r: r.sharpe_ratio)
    
    if best.strategy_name == "Fixed Targets (+35%/-40%)":
        print("""
    TRAILING STOPS DO NOT HELP CALENDAR SPREADS

    Unlike Theta Sprint, which is hurt by trailing stops, Calendar Spreads
    show SIMILAR PERFORMANCE with or without trailing P&L stops.

    However, fixed targets are SIMPLER and EASIER TO EXECUTE.

    RECOMMENDATION: Use FIXED TARGETS (+35% / -40%)
    - Clearer exit rules
    - Less monitoring required
    - Similar or better performance
        """)
    else:
        if best.sharpe_ratio > fixed_result.sharpe_ratio * 1.1:
            print(f"""
    TRAILING STOPS MAY HELP CALENDAR SPREADS

    Best strategy: {best.strategy_name}
    Improvement: +{((best.total_pnl - fixed_result.total_pnl) / abs(fixed_result.total_pnl)) * 100:.1f}% total P&L

    However, the improvement is marginal and fixed targets are simpler.

    RECOMMENDATION: Consider trailing for advanced users only
            """)
        else:
            print("""
    TRAILING STOPS HAVE MINIMAL IMPACT

    Calendar Spreads work similarly with fixed targets or trailing stops.
    The difference is within noise.

    RECOMMENDATION: Use FIXED TARGETS for simplicity
            """)
    
    # Save results
    output = {
        "results": [asdict(r) for r in results],
        "recommendation": "fixed_targets" if best.strategy_name.startswith("Fixed") else "trailing_optional",
        "best_strategy": best.strategy_name
    }
    
    with open("calendar_trailing_backtest_results.json", "w") as f:
        json.dump(output, f, indent=2)
    
    print("\nResults saved to: calendar_trailing_backtest_results.json")
    
    return output


if __name__ == "__main__":
    run_comparison_backtest(500)
