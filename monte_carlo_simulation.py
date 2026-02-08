"""
Monte Carlo Risk Simulation
============================
Simulates max loss and risk metrics for Theta Sprint and Calendar Spread 
strategies across three risk levels: Safe, Smart, Bold.

Uses historical trade statistics and Monte Carlo sampling to estimate:
- Max Drawdown (95th percentile)
- Value at Risk (VaR)
- Expected Sharpe Ratio
- Recovery time from max loss
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Dict, Tuple
from datetime import date
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set seed for reproducibility
np.random.seed(42)

# ============================================================================
# RISK PRESETS (from StrategySettings)
# ============================================================================

RISK_PRESETS = {
    'safe': {
        'confidence': 85,
        'trailing_stop': -30,
        'max_heat': 10,
        'theta_dte_min': 28, 'theta_dte_max': 45, 'theta_delta': 0.15, 'theta_trades_week': 2,
        'calendar_dte_min': 7, 'calendar_dte_max': 14, 'calendar_trades_week': 3,
    },
    'smart': {
        'confidence': 75,
        'trailing_stop': -45,
        'max_heat': 15,
        'theta_dte_min': 21, 'theta_dte_max': 45, 'theta_delta': 0.20, 'theta_trades_week': 3,
        'calendar_dte_min': 5, 'calendar_dte_max': 14, 'calendar_trades_week': 5,
    },
    'bold': {
        'confidence': 60,
        'trailing_stop': -60,
        'max_heat': 25,
        'theta_dte_min': 14, 'theta_dte_max': 45, 'theta_delta': 0.30, 'theta_trades_week': 5,
        'calendar_dte_min': 3, 'calendar_dte_max': 14, 'calendar_trades_week': 8,
    },
}

# ============================================================================
# HISTORICAL TRADE STATISTICS (from backtest results)
# ============================================================================

# Theta Sprint - Cash-Secured Puts (from backtest_theta.py results)
THETA_STATS = {
    'safe': {'win_rate': 0.82, 'avg_win': 0.45, 'avg_loss': -0.25, 'avg_hold_days': 12},
    'smart': {'win_rate': 0.75, 'avg_win': 0.55, 'avg_loss': -0.35, 'avg_hold_days': 10},
    'bold': {'win_rate': 0.65, 'avg_win': 0.70, 'avg_loss': -0.55, 'avg_hold_days': 8},
}

# Calendar Spreads (from backtest_calendar_synthetic.py results)
CALENDAR_STATS = {
    'safe': {'win_rate': 0.72, 'avg_win': 0.30, 'avg_loss': -0.25, 'avg_hold_days': 10},
    'smart': {'win_rate': 0.67, 'avg_win': 0.40, 'avg_loss': -0.35, 'avg_hold_days': 8},
    'bold': {'win_rate': 0.58, 'avg_win': 0.55, 'avg_loss': -0.45, 'avg_hold_days': 6},
}


@dataclass
class SimulationResult:
    """Results from Monte Carlo simulation."""
    strategy: str
    risk_level: str
    simulations: int
    
    # Drawdown metrics
    avg_max_drawdown: float
    max_drawdown_95th: float  # 95th percentile worst case
    max_drawdown_99th: float  # 99th percentile extreme case
    
    # Return metrics
    avg_annual_return: float
    return_std: float
    sharpe_ratio: float
    
    # VaR metrics
    var_95: float  # 95% Value at Risk (daily)
    var_99: float  # 99% Value at Risk (daily)
    cvar_95: float  # Conditional VaR (expected shortfall)
    
    # Recovery metrics
    avg_recovery_days: float
    max_recovery_days: int
    
    # Win/Loss
    total_trades: int
    win_rate: float
    avg_profit_per_trade: float


def simulate_trades(
    strategy: str,
    risk_level: str,
    capital: float = 10000,
    weeks: int = 52,
) -> Tuple[List[float], List[float]]:
    """
    Simulate trades for a strategy/risk level over specified weeks.
    
    Returns:
        (equity_curve, individual_trade_returns)
    """
    preset = RISK_PRESETS[risk_level]
    stats = THETA_STATS[risk_level] if strategy == 'theta' else CALENDAR_STATS[risk_level]
    
    trades_per_week = preset['theta_trades_week'] if strategy == 'theta' else preset['calendar_trades_week']
    trailing_stop = preset['trailing_stop'] / 100  # Convert to decimal
    
    equity = capital
    equity_curve = [capital]
    trade_returns = []
    
    for week in range(weeks):
        for _ in range(trades_per_week):
            # Position size based on max heat
            position_size = equity * (preset['max_heat'] / 100) / 3  # Divide by avg positions
            
            # Determine if win or loss
            if np.random.random() < stats['win_rate']:
                # Winner - random return between 0 and avg_win
                pnl_pct = np.random.uniform(0.1, stats['avg_win'])
            else:
                # Loser - apply trailing stop logic
                # Some losses hit trailing stop, some hit max loss
                if np.random.random() < 0.7:  # 70% hit trailing stop
                    pnl_pct = trailing_stop
                else:
                    pnl_pct = np.random.uniform(trailing_stop, stats['avg_loss'])
            
            pnl = position_size * pnl_pct
            equity += pnl
            trade_returns.append(pnl_pct)
            equity_curve.append(equity)
            
            # Minimum equity check
            if equity < capital * 0.1:  # Stop if 90% loss
                break
        
        if equity < capital * 0.1:
            break
    
    return equity_curve, trade_returns


def calculate_max_drawdown(equity_curve: List[float]) -> Tuple[float, int]:
    """
    Calculate maximum drawdown and recovery time.
    
    Returns:
        (max_drawdown_pct, recovery_days)
    """
    peak = equity_curve[0]
    max_dd = 0
    max_dd_idx = 0
    peak_idx = 0
    
    for i, equity in enumerate(equity_curve):
        if equity > peak:
            peak = equity
            peak_idx = i
        dd = (peak - equity) / peak
        if dd > max_dd:
            max_dd = dd
            max_dd_idx = i
    
    # Estimate recovery (trades to recover)
    recovery = 0
    for i in range(max_dd_idx, len(equity_curve)):
        if equity_curve[i] >= peak:
            recovery = i - max_dd_idx
            break
    else:
        recovery = len(equity_curve) - max_dd_idx  # Still in drawdown
    
    return max_dd, recovery


def run_monte_carlo(
    strategy: str,
    risk_level: str,
    capital: float = 10000,
    simulations: int = 1000,
    weeks: int = 52,
) -> SimulationResult:
    """
    Run Monte Carlo simulation for strategy/risk combination.
    """
    logger.info(f"Running {simulations} simulations for {strategy.upper()} - {risk_level.upper()}")
    
    all_max_drawdowns = []
    all_final_returns = []
    all_recovery_times = []
    all_trade_returns = []
    
    for sim in range(simulations):
        equity_curve, trade_returns = simulate_trades(strategy, risk_level, capital, weeks)
        
        # Calculate metrics for this simulation
        max_dd, recovery = calculate_max_drawdown(equity_curve)
        final_return = (equity_curve[-1] - capital) / capital
        
        all_max_drawdowns.append(max_dd)
        all_final_returns.append(final_return)
        all_recovery_times.append(recovery)
        all_trade_returns.extend(trade_returns)
    
    # Aggregate results
    returns_array = np.array(all_trade_returns)
    drawdowns_array = np.array(all_max_drawdowns)
    final_returns_array = np.array(all_final_returns)
    
    # VaR calculations
    var_95 = np.percentile(returns_array, 5)  # 5th percentile for losses
    var_99 = np.percentile(returns_array, 1)
    cvar_95 = returns_array[returns_array <= var_95].mean() if len(returns_array[returns_array <= var_95]) > 0 else var_95
    
    # Return metrics
    avg_return = np.mean(returns_array)
    return_std = np.std(returns_array)
    sharpe = (avg_return / return_std) * np.sqrt(52) if return_std > 0 else 0  # Annualized
    
    stats = THETA_STATS[risk_level] if strategy == 'theta' else CALENDAR_STATS[risk_level]
    preset = RISK_PRESETS[risk_level]
    trades_per_week = preset['theta_trades_week'] if strategy == 'theta' else preset['calendar_trades_week']
    
    return SimulationResult(
        strategy=strategy,
        risk_level=risk_level,
        simulations=simulations,
        avg_max_drawdown=np.mean(drawdowns_array),
        max_drawdown_95th=np.percentile(drawdowns_array, 95),
        max_drawdown_99th=np.percentile(drawdowns_array, 99),
        avg_annual_return=np.mean(final_returns_array),
        return_std=np.std(final_returns_array),
        sharpe_ratio=sharpe,
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        avg_recovery_days=np.mean(all_recovery_times) * stats['avg_hold_days'],
        max_recovery_days=int(np.max(all_recovery_times) * stats['avg_hold_days']),
        total_trades=trades_per_week * weeks,
        win_rate=stats['win_rate'],
        avg_profit_per_trade=avg_return,
    )


def print_results(results: List[SimulationResult]):
    """Print formatted results table."""
    
    print("\n" + "="*90)
    print(" MONTE CARLO RISK SIMULATION RESULTS")
    print(" 1,000 simulations x 52 weeks x $10,000 capital")
    print("="*90)
    
    # Group by strategy
    for strategy in ['theta', 'calendar']:
        strategy_results = [r for r in results if r.strategy == strategy]
        
        print(f"\n{'THETA SPRINT (Cash-Secured Puts)' if strategy == 'theta' else 'CALENDAR SPREAD'}")
        print("-"*90)
        print(f"{'Risk Level':<12} | {'Max DD 95%':>10} | {'Max DD 99%':>10} | {'VaR 95%':>10} | {'Ann. Return':>12} | {'Sharpe':>8} | {'Recovery':>10}")
        print("-"*90)
        
        for r in strategy_results:
            print(f"{r.risk_level.upper():<12} | "
                  f"{-r.max_drawdown_95th*100:>9.1f}% | "
                  f"{-r.max_drawdown_99th*100:>9.1f}% | "
                  f"{r.var_95*100:>9.1f}% | "
                  f"{r.avg_annual_return*100:>11.1f}% | "
                  f"{r.sharpe_ratio:>8.2f} | "
                  f"{r.avg_recovery_days:>7.0f} days")
    
    print("\n" + "="*90)
    print(" KEY INSIGHTS")
    print("="*90)
    
    # Find safest and riskiest
    safest = min(results, key=lambda r: r.max_drawdown_99th)
    riskiest = max(results, key=lambda r: r.max_drawdown_99th)
    best_sharpe = max(results, key=lambda r: r.sharpe_ratio)
    
    print(f"""
SAFEST OPTION:     {safest.strategy.upper()} - {safest.risk_level.upper()}
                   Max Loss (99%): {-safest.max_drawdown_99th*100:.1f}%
                   Expected Return: {safest.avg_annual_return*100:.1f}%

HIGHEST RISK:      {riskiest.strategy.upper()} - {riskiest.risk_level.upper()}
                   Max Loss (99%): {-riskiest.max_drawdown_99th*100:.1f}%
                   Expected Return: {riskiest.avg_annual_return*100:.1f}%

BEST RISK-ADJUSTED: {best_sharpe.strategy.upper()} - {best_sharpe.risk_level.upper()}
                   Sharpe Ratio: {best_sharpe.sharpe_ratio:.2f}
                   Max Loss (95%): {-best_sharpe.max_drawdown_95th*100:.1f}%
""")


def export_to_json(results: List[SimulationResult], filename: str = "monte_carlo_results.json"):
    """Export results to JSON for frontend consumption."""
    import json
    
    data = {
        "simulation_params": {
            "simulations": 1000,
            "weeks": 52,
            "capital": 10000,
            "generated_at": date.today().isoformat(),
        },
        "results": {}
    }
    
    for r in results:
        key = f"{r.strategy}_{r.risk_level}"
        data["results"][key] = {
            "strategy": r.strategy,
            "risk_level": r.risk_level,
            "max_drawdown_95th": round(r.max_drawdown_95th * 100, 2),
            "max_drawdown_99th": round(r.max_drawdown_99th * 100, 2),
            "var_95": round(r.var_95 * 100, 2),
            "var_99": round(r.var_99 * 100, 2),
            "avg_annual_return": round(r.avg_annual_return * 100, 2),
            "sharpe_ratio": round(r.sharpe_ratio, 2),
            "avg_recovery_days": round(r.avg_recovery_days),
            "win_rate": round(r.win_rate * 100, 1),
        }
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"Results exported to {filename}")


def run_full_simulation():
    """Run Monte Carlo for all strategy/risk combinations."""
    
    results = []
    
    for strategy in ['theta', 'calendar']:
        for risk_level in ['safe', 'smart', 'bold']:
            result = run_monte_carlo(
                strategy=strategy,
                risk_level=risk_level,
                capital=10000,
                simulations=1000,
                weeks=52,
            )
            results.append(result)
    
    print_results(results)
    export_to_json(results)
    
    return results


if __name__ == "__main__":
    results = run_full_simulation()
