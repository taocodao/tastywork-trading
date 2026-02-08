"""
Diagonal Spread Backtest
========================

Backtests the unified Diagonal Spread strategy which handles:
- BULL_DIAGONAL: Strong bullish conviction (70%+) -> PMCC
- BEAR_DIAGONAL: Strong bearish conviction (70%+) -> PMCP
- NEUTRAL_DIAGONAL: Lower conviction -> Calendar-like (ATM strikes)

Uses synthetic data similar to calendar_trailing_backtest.py
"""

import json
import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Optional
import os

# Parameters
SYMBOLS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "AMZN", "META"]
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2024, 12, 31)
TRADES_PER_WEEK = 3
INITIAL_CAPITAL = 10000

# Strategy parameters
DIRECTIONAL_CONFIDENCE_THRESHOLD = 70  # Above this = PMCC/PMCP
NEUTRAL_CONFIDENCE_THRESHOLD = 50      # Below this = no trade

# Exit parameters for each mode
EXIT_PARAMS = {
    "BULL_DIAGONAL": {"profit_target": 0.50, "stop_loss": 0.40, "max_dte": 21},
    "BEAR_DIAGONAL": {"profit_target": 0.50, "stop_loss": 0.40, "max_dte": 21},
    "NEUTRAL_DIAGONAL": {"profit_target": 0.35, "stop_loss": 0.40, "max_dte": 14},
}

# Win rate assumptions based on strategy research
WIN_RATES = {
    "BULL_DIAGONAL": 0.68,   # PMCC in trending market
    "BEAR_DIAGONAL": 0.62,   # PMCP slightly lower
    "NEUTRAL_DIAGONAL": 0.66, # Calendar-like ATM
}


@dataclass
class DiagonalTrade:
    symbol: str
    strategy: str  # BULL_DIAGONAL, BEAR_DIAGONAL, NEUTRAL_DIAGONAL
    confidence: int
    entry_date: datetime
    entry_cost: float
    max_profit: float
    max_loss: float
    exit_date: Optional[datetime] = None
    exit_pnl: float = 0.0
    exit_reason: str = ""


def generate_market_conditions() -> Dict:
    """Generate random market conditions for a day."""
    return {
        "iv_rank": random.uniform(20, 80),
        "trend_strength": random.uniform(30, 90),
        "direction": random.choice(["BULL", "BEAR", "NEUTRAL"]),
        "vix": random.uniform(12, 35),
    }


def select_strategy(conditions: Dict) -> Optional[str]:
    """Select strategy based on market conditions."""
    confidence = int(conditions["trend_strength"])
    direction = conditions["direction"]
    
    if confidence >= DIRECTIONAL_CONFIDENCE_THRESHOLD:
        if direction == "BULL":
            return "BULL_DIAGONAL"
        elif direction == "BEAR":
            return "BEAR_DIAGONAL"
        else:
            return "NEUTRAL_DIAGONAL"
    elif confidence >= NEUTRAL_CONFIDENCE_THRESHOLD:
        return "NEUTRAL_DIAGONAL"
    else:
        return None  # No trade


def calculate_trade_size(capital: float, strategy: str) -> float:
    """Calculate position size based on risk management."""
    # Risk 5-10% per trade
    risk_percent = 0.05 if strategy == "NEUTRAL_DIAGONAL" else 0.08
    return capital * risk_percent


def simulate_trade_outcome(trade: DiagonalTrade, conditions: Dict) -> DiagonalTrade:
    """Simulate trade outcome based on win rates and market conditions."""
    strategy = trade.strategy
    params = EXIT_PARAMS[strategy]
    base_win_rate = WIN_RATES[strategy]
    
    # Adjust win rate based on conditions
    iv_bonus = 0.05 if conditions["iv_rank"] > 50 else -0.02
    confidence_bonus = (trade.confidence - 50) / 500  # Up to +8%
    
    adjusted_win_rate = base_win_rate + iv_bonus + confidence_bonus
    adjusted_win_rate = max(0.45, min(0.85, adjusted_win_rate))
    
    # Determine outcome
    is_win = random.random() < adjusted_win_rate
    
    # Calculate P&L
    if is_win:
        # Winning trades: 60-100% of max profit
        profit_pct = random.uniform(0.6, 1.0) * params["profit_target"]
        trade.exit_pnl = trade.entry_cost * profit_pct
        trade.exit_reason = "PROFIT_TARGET" if profit_pct >= params["profit_target"] * 0.9 else "DTE_EXIT"
    else:
        # Losing trades: 20-100% of max loss
        loss_pct = random.uniform(0.2, 1.0) * params["stop_loss"]
        trade.exit_pnl = -trade.entry_cost * loss_pct
        trade.exit_reason = "STOP_LOSS" if loss_pct >= params["stop_loss"] * 0.9 else "DTE_EXIT"
    
    # Exit date
    days_held = random.randint(3, params["max_dte"])
    trade.exit_date = trade.entry_date + timedelta(days=days_held)
    
    return trade


def run_backtest() -> Dict:
    """Run full backtest simulation."""
    trades: List[DiagonalTrade] = []
    capital = INITIAL_CAPITAL
    equity_curve = [(START_DATE, capital)]
    
    current_date = START_DATE
    week_trades = 0
    
    while current_date <= END_DATE:
        # Reset weekly counter on Monday
        if current_date.weekday() == 0:
            week_trades = 0
        
        # Only trade on weekdays
        if current_date.weekday() < 5 and week_trades < TRADES_PER_WEEK:
            conditions = generate_market_conditions()
            strategy = select_strategy(conditions)
            
            if strategy and capital > 500:  # Min capital check
                symbol = random.choice(SYMBOLS)
                position_size = calculate_trade_size(capital, strategy)
                
                # Entry cost varies by strategy
                if strategy == "NEUTRAL_DIAGONAL":
                    entry_cost = random.uniform(150, 400)  # Calendar-like
                else:
                    entry_cost = random.uniform(300, 800)  # PMCC/PMCP
                
                entry_cost = min(entry_cost, position_size)
                
                trade = DiagonalTrade(
                    symbol=symbol,
                    strategy=strategy,
                    confidence=int(conditions["trend_strength"]),
                    entry_date=current_date,
                    entry_cost=entry_cost,
                    max_profit=entry_cost * EXIT_PARAMS[strategy]["profit_target"],
                    max_loss=entry_cost * EXIT_PARAMS[strategy]["stop_loss"],
                )
                
                # Simulate outcome
                trade = simulate_trade_outcome(trade, conditions)
                trades.append(trade)
                
                # Update capital
                capital += trade.exit_pnl
                equity_curve.append((trade.exit_date, capital))
                
                week_trades += 1
        
        current_date += timedelta(days=1)
    
    return analyze_results(trades, equity_curve)


def analyze_results(trades: List[DiagonalTrade], equity_curve: List) -> Dict:
    """Analyze backtest results."""
    if not trades:
        return {"error": "No trades generated"}
    
    # Overall stats
    total_pnl = sum(t.exit_pnl for t in trades)
    wins = [t for t in trades if t.exit_pnl > 0]
    losses = [t for t in trades if t.exit_pnl <= 0]
    
    win_rate = len(wins) / len(trades) * 100
    avg_win = sum(t.exit_pnl for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.exit_pnl for t in losses) / len(losses) if losses else 0
    
    # Calculate Sharpe (simplified)
    returns = [t.exit_pnl for t in trades]
    avg_return = sum(returns) / len(returns)
    std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
    sharpe = (avg_return / std_return * (252 ** 0.5)) if std_return > 0 else 0
    
    # By strategy
    strategy_stats = {}
    for strategy in ["BULL_DIAGONAL", "BEAR_DIAGONAL", "NEUTRAL_DIAGONAL"]:
        strat_trades = [t for t in trades if t.strategy == strategy]
        if strat_trades:
            strat_wins = [t for t in strat_trades if t.exit_pnl > 0]
            strategy_stats[strategy] = {
                "trades": len(strat_trades),
                "total_pnl": sum(t.exit_pnl for t in strat_trades),
                "win_rate": len(strat_wins) / len(strat_trades) * 100,
                "avg_pnl": sum(t.exit_pnl for t in strat_trades) / len(strat_trades),
            }
    
    # By exit reason
    exit_stats = {}
    for reason in ["PROFIT_TARGET", "STOP_LOSS", "DTE_EXIT"]:
        reason_trades = [t for t in trades if t.exit_reason == reason]
        if reason_trades:
            exit_stats[reason] = {
                "count": len(reason_trades),
                "avg_pnl": sum(t.exit_pnl for t in reason_trades) / len(reason_trades),
            }
    
    final_capital = equity_curve[-1][1] if equity_curve else INITIAL_CAPITAL
    total_return = (final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    
    return {
        "summary": {
            "total_trades": len(trades),
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "sharpe_ratio": round(sharpe, 2),
            "initial_capital": INITIAL_CAPITAL,
            "final_capital": round(final_capital, 2),
            "total_return_pct": round(total_return, 1),
        },
        "by_strategy": strategy_stats,
        "by_exit_reason": exit_stats,
        "parameters": {
            "directional_threshold": DIRECTIONAL_CONFIDENCE_THRESHOLD,
            "neutral_threshold": NEUTRAL_CONFIDENCE_THRESHOLD,
            "symbols": SYMBOLS,
            "period": f"{START_DATE.date()} to {END_DATE.date()}",
        }
    }


def print_results(results: Dict):
    """Print formatted results."""
    print("\n" + "=" * 70)
    print("DIAGONAL SPREAD BACKTEST RESULTS")
    print("=" * 70)
    
    summary = results["summary"]
    print(f"\n{'OVERALL PERFORMANCE':^70}")
    print("-" * 70)
    print(f"  Total Trades:       {summary['total_trades']}")
    print(f"  Total P&L:          ${summary['total_pnl']:,.2f}")
    print(f"  Win Rate:           {summary['win_rate']:.1f}%")
    print(f"  Avg Win:            ${summary['avg_win']:.2f}")
    print(f"  Avg Loss:           ${summary['avg_loss']:.2f}")
    print(f"  Sharpe Ratio:       {summary['sharpe_ratio']:.2f}")
    print(f"  Total Return:       {summary['total_return_pct']:.1f}%")
    print(f"  Final Capital:      ${summary['final_capital']:,.2f}")
    
    print(f"\n{'BY STRATEGY':^70}")
    print("-" * 70)
    for strategy, stats in results["by_strategy"].items():
        print(f"  {strategy:20} | {stats['trades']:3} trades | "
              f"Win: {stats['win_rate']:5.1f}% | P&L: ${stats['total_pnl']:8.2f} | "
              f"Avg: ${stats['avg_pnl']:6.2f}")
    
    print(f"\n{'BY EXIT REASON':^70}")
    print("-" * 70)
    for reason, stats in results["by_exit_reason"].items():
        print(f"  {reason:20} | {stats['count']:3} trades | Avg P&L: ${stats['avg_pnl']:8.2f}")
    
    print("\n" + "=" * 70)
    print("CONCLUSION: Unified Diagonal Spread strategy performance")
    print("=" * 70)


if __name__ == "__main__":
    print("Running Diagonal Spread Backtest...")
    print(f"Symbols: {SYMBOLS}")
    print(f"Period: {START_DATE.date()} to {END_DATE.date()}")
    
    results = run_backtest()
    print_results(results)
    
    # Save results
    output_file = "diagonal_spread_backtest_results.json"
    with open(output_file, "w") as f:
        # Convert datetime to string for JSON
        json_results = results.copy()
        json.dump(json_results, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_file}")
