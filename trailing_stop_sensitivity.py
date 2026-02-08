"""
Trailing Stop Sensitivity Analysis
===================================
Monte Carlo simulation to analyze the impact of different trailing stop levels
on risk and return for Theta Sprint and Calendar Spread strategies.

Tests trailing stops from -20% to -70% to find optimal risk/reward balance.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

np.random.seed(42)

# Historical win rates and returns
THETA_BASE = {'win_rate': 0.75, 'avg_win': 0.55, 'avg_loss_no_stop': -0.80}
CALENDAR_BASE = {'win_rate': 0.67, 'avg_win': 0.40, 'avg_loss_no_stop': -0.70}


@dataclass
class TrailingStopResult:
    """Results for a specific trailing stop level."""
    strategy: str
    trailing_stop_pct: int
    
    # Performance
    avg_annual_return: float
    return_std: float
    sharpe_ratio: float
    
    # Risk
    max_drawdown_avg: float
    max_drawdown_95th: float
    max_drawdown_99th: float
    
    # Trade stats
    avg_loss_when_stopped: float
    avg_loss_when_not_stopped: float
    pct_stopped_early: float
    
    # Recovery
    avg_recovery_days: float


def simulate_with_trailing_stop(
    strategy: str,
    trailing_stop: float,  # e.g., -0.30 for -30%
    simulations: int = 500,
    weeks: int = 52,
    capital: float = 10000,
    trades_per_week: int = 3,
) -> TrailingStopResult:
    """
    Simulate strategy with specific trailing stop.
    
    Args:
        trailing_stop: Decimal (e.g., -0.30 for -30%)
    """
    stats = THETA_BASE if strategy == 'theta' else CALENDAR_BASE
    
    all_returns = []
    all_drawdowns = []
    all_equity_curves = []
    stopped_early_count = 0
    total_losses = 0
    stopped_losses = []
    unstoppable_losses = []
    
    for sim in range(simulations):
        equity = capital
        equity_curve = [capital]
        
        for week in range(weeks):
            for _ in range(trades_per_week):
                position_size = equity * 0.05  # 5% per trade
                
                if np.random.random() < stats['win_rate']:
                    # Winner
                    pnl_pct = np.random.uniform(0.1, stats['avg_win'])
                else:
                    # Loser - simulate price movement
                    total_losses += 1
                    
                    # Random loss severity
                    natural_loss = np.random.uniform(trailing_stop, stats['avg_loss_no_stop'])
                    
                    # Does trailing stop kick in?
                    if natural_loss <= trailing_stop:
                        # Trailing stop triggered
                        pnl_pct = trailing_stop + np.random.uniform(-0.05, 0.05)  # Some slippage
                        stopped_early_count += 1
                        stopped_losses.append(pnl_pct)
                    else:
                        # Loss smaller than trailing stop
                        pnl_pct = natural_loss
                        unstoppable_losses.append(pnl_pct)
                
                pnl = position_size * pnl_pct
                equity += pnl
                equity_curve.append(equity)
                all_returns.append(pnl_pct)
                
                if equity < capital * 0.05:  # Bankruptcy protection
                    break
            
            if equity < capital * 0.05:
                break
        
        # Calculate drawdown for this simulation
        peak = equity_curve[0]
        max_dd = 0
        for e in equity_curve:
            if e > peak:
                peak = e
            dd = (peak - e) / peak
            if dd > max_dd:
                max_dd = dd
        
        all_drawdowns.append(max_dd)
        all_equity_curves.append(equity_curve)
    
    # Aggregate metrics
    returns_array = np.array(all_returns)
    avg_return = np.mean(returns_array)
    return_std = np.std(returns_array)
    sharpe = (avg_return / return_std) * np.sqrt(52 * trades_per_week) if return_std > 0 else 0
    
    # Annualized return
    final_returns = [(curve[-1] - capital) / capital for curve in all_equity_curves]
    avg_annual_return = np.mean(final_returns)
    
    # Recovery time estimate
    avg_recovery = 0
    for curve in all_equity_curves:
        peak_idx = 0
        peak_val = curve[0]
        max_dd_idx = 0
        max_dd_val = 0
        
        for i, val in enumerate(curve):
            if val > peak_val:
                peak_val = val
                peak_idx = i
            dd = (peak_val - val) / peak_val
            if dd > max_dd_val:
                max_dd_val = dd
                max_dd_idx = i
        
        # Find recovery
        for i in range(max_dd_idx, len(curve)):
            if curve[i] >= peak_val:
                avg_recovery += (i - max_dd_idx) * 0.5  # ~2 days per trade
                break
    
    avg_recovery = avg_recovery / simulations if simulations > 0 else 0
    
    return TrailingStopResult(
        strategy=strategy,
        trailing_stop_pct=int(trailing_stop * 100),
        avg_annual_return=avg_annual_return,
        return_std=return_std,
        sharpe_ratio=sharpe,
        max_drawdown_avg=np.mean(all_drawdowns),
        max_drawdown_95th=np.percentile(all_drawdowns, 95),
        max_drawdown_99th=np.percentile(all_drawdowns, 99),
        avg_loss_when_stopped=np.mean(stopped_losses) if stopped_losses else 0,
        avg_loss_when_not_stopped=np.mean(unstoppable_losses) if unstoppable_losses else 0,
        pct_stopped_early=(stopped_early_count / total_losses * 100) if total_losses > 0 else 0,
        avg_recovery_days=avg_recovery,
    )


def run_sensitivity_analysis():
    """Test multiple trailing stop levels."""
    
    # Test trailing stops from -20% to -70%
    trailing_stops = [-0.20, -0.25, -0.30, -0.35, -0.40, -0.45, -0.50, -0.55, -0.60, -0.65, -0.70]
    
    all_results = []
    
    for strategy in ['theta', 'calendar']:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing {strategy.upper()} with different trailing stops")
        logger.info(f"{'='*60}")
        
        for stop in trailing_stops:
            result = simulate_with_trailing_stop(
                strategy=strategy,
                trailing_stop=stop,
                simulations=500,
                weeks=52,
            )
            all_results.append(result)
            logger.info(f"  {stop*100:.0f}%: Return={result.avg_annual_return*100:6.1f}%  "
                       f"MaxDD={result.max_drawdown_95th*100:5.1f}%  Sharpe={result.sharpe_ratio:5.2f}")
    
    print_analysis(all_results)
    export_results(all_results)
    
    return all_results


def print_analysis(results: List[TrailingStopResult]):
    """Print detailed analysis tables."""
    
    print("\n" + "="*110)
    print(" TRAILING STOP SENSITIVITY ANALYSIS - MONTE CARLO SIMULATION")
    print(" 500 simulations x 52 weeks x $10,000 capital")
    print("="*110)
    
    for strategy in ['theta', 'calendar']:
        strategy_results = [r for r in results if r.strategy == strategy]
        
        print(f"\n{'THETA SPRINT' if strategy == 'theta' else 'CALENDAR SPREAD'}")
        print("-"*110)
        print(f"{'Stop':<8} | {'Return':>8} | {'MaxDD 95%':>10} | {'MaxDD 99%':>10} | {'Sharpe':>8} | "
              f"{'Stopped':>8} | {'Recovery':>10}")
        print("-"*110)
        
        for r in strategy_results:
            print(f"{r.trailing_stop_pct:>4}%   | "
                  f"{r.avg_annual_return*100:>7.1f}% | "
                  f"{-r.max_drawdown_95th*100:>9.1f}% | "
                  f"{-r.max_drawdown_99th*100:>9.1f}% | "
                  f"{r.sharpe_ratio:>8.2f} | "
                  f"{r.pct_stopped_early:>7.1f}% | "
                  f"{r.avg_recovery_days:>7.0f} days")
    
    # Find optimal
    print("\n" + "="*110)
    print(" OPTIMAL TRAILING STOPS")
    print("="*110)
    
    for strategy in ['theta', 'calendar']:
        strategy_results = [r for r in results if r.strategy == strategy]
        
        best_sharpe = max(strategy_results, key=lambda r: r.sharpe_ratio)
        safest = min(strategy_results, key=lambda r: r.max_drawdown_99th)
        highest_return = max(strategy_results, key=lambda r: r.avg_annual_return)
        
        print(f"\n{strategy.upper()}:")
        print(f"  Best Risk-Adjusted (Sharpe): {best_sharpe.trailing_stop_pct}% "
              f"(Sharpe: {best_sharpe.sharpe_ratio:.2f}, Return: {best_sharpe.avg_annual_return*100:.1f}%)")
        print(f"  Safest (Min Drawdown):        {safest.trailing_stop_pct}% "
              f"(MaxDD: {-safest.max_drawdown_99th*100:.1f}%, Return: {safest.avg_annual_return*100:.1f}%)")
        print(f"  Highest Return:               {highest_return.trailing_stop_pct}% "
              f"(Return: {highest_return.avg_annual_return*100:.1f}%, MaxDD: {-highest_return.max_drawdown_99th*100:.1f}%)")


def export_results(results: List[TrailingStopResult]):
    """Export to JSON and CSV."""
    import json
    
    # JSON export
    data = {
        "analysis_type": "trailing_stop_sensitivity",
        "results": {}
    }
    
    for r in results:
        key = f"{r.strategy}_{r.trailing_stop_pct}"
        data["results"][key] = {
            "strategy": r.strategy,
            "trailing_stop_pct": r.trailing_stop_pct,
            "avg_annual_return": round(r.avg_annual_return * 100, 2),
            "sharpe_ratio": round(r.sharpe_ratio, 2),
            "max_drawdown_95th": round(r.max_drawdown_95th * 100, 2),
            "max_drawdown_99th": round(r.max_drawdown_99th * 100, 2),
            "pct_stopped_early": round(r.pct_stopped_early, 1),
        }
    
    with open("trailing_stop_sensitivity.json", 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info("Results exported to trailing_stop_sensitivity.json")
    
    # CSV export for Excel
    df = pd.DataFrame([{
        'Strategy': r.strategy,
        'Trailing Stop %': r.trailing_stop_pct,
        'Annual Return %': round(r.avg_annual_return * 100, 2),
        'Sharpe Ratio': round(r.sharpe_ratio, 2),
        'Max DD 95%': round(-r.max_drawdown_95th * 100, 2),
        'Max DD 99%': round(-r.max_drawdown_99th * 100, 2),
        'Pct Stopped Early': round(r.pct_stopped_early, 1),
        'Avg Recovery Days': round(r.avg_recovery_days, 0),
    } for r in results])
    
    df.to_csv("trailing_stop_sensitivity.csv", index=False)
    logger.info("Results exported to trailing_stop_sensitivity.csv")


if __name__ == "__main__":
    results = run_sensitivity_analysis()
