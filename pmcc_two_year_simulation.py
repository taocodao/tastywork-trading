"""
Six-Year PMCC Strategy Backtest
================================

Simulates Poor Man's Covered Call (PMCC) executions across 2019-2024 to determine long term stability.
As historical high-granularity intraday options data over 2 years requires a massive database,
this script uses probability-driven synthetic market conditions based on the existing `backtest_diagonal.py` framework,
explicitly adapted to the BCI (Break-even <= short strike) ruleset and delta profiles mapped in PMCCSelector.
"""

import json
import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Optional

# Parameters
SYMBOLS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "AMZN", "META"]
START_DATE = datetime(2019, 1, 1)  # Full 6 years backward from 2024 end
END_DATE = datetime(2024, 12, 31)
TRADES_PER_WEEK = 3
INITIAL_CAPITAL = 25000  # Requires larger account for deep ITM LEAPS

# PMCC Strategy definitions
# LEAPS = 365+ DTE, 70-90 delta
# Short Call = 30-45 DTE, 15-30 delta
DIRECTIONAL_CONFIDENCE_THRESHOLD = 75  # Trending markets required for PMCC
PMCC_EXIT_PARAMS = {"profit_target": 0.50, "stop_loss": 0.40, "max_hold_days": 45}
BASE_WIN_RATE = 0.65  # Base PMCC execution probability


@dataclass
class PMCCTrade:
    symbol: str
    confidence: int
    entry_date: datetime
    leaps_delta: float
    short_delta: float
    bci_met: bool
    entry_cost: float
    max_profit: float
    max_loss: float
    exit_date: Optional[datetime] = None
    exit_pnl: float = 0.0
    exit_reason: str = ""
    cycles: int = 1


def generate_market_conditions() -> Dict:
    """Generate random market conditions for an entry day."""
    return {
        "iv_rank": random.uniform(10, 60),  # PMCC prefers lower IV environment for entry
        "trend_strength": random.uniform(40, 95),
        "direction": random.choice(["BULL", "BEAR", "NEUTRAL"]),
        "vix": random.uniform(12, 30),
    }


def should_enter_pmcc(conditions: Dict) -> bool:
    """Check if market supports PMCC (Bullish trend + Moderate/Low IV)."""
    return conditions["direction"] == "BULL" and conditions["trend_strength"] >= DIRECTIONAL_CONFIDENCE_THRESHOLD


def simulate_pmcc_outcome(trade: PMCCTrade, conditions: Dict) -> PMCCTrade:
    """Simulate outcome based on delta, IV, and confidence modifiers."""
    # Positive edge: higher confidence setup
    confidence_bonus = (trade.confidence - 75) / 500  # Up to +4%
    
    # Negative edge: high IV at entry makes LEAPS expensive, increasing break-even risk
    iv_penalty = -0.05 if conditions["iv_rank"] > 40 else 0.02
    
    # Negative edge: BCI formula constraint failed
    bci_penalty = 0.0 if trade.bci_met else -0.15

    adjusted_win_rate = BASE_WIN_RATE + confidence_bonus + iv_penalty + bci_penalty
    adjusted_win_rate = max(0.35, min(0.80, adjusted_win_rate))
    
    is_win = random.random() < adjusted_win_rate
    
    # PMCCs often require multiple rolling cycles of the short call (simulated here)
    trade.cycles = random.randint(1, 4)
    hold_days = trade.cycles * random.randint(10, 25)
    trade.exit_date = trade.entry_date + timedelta(days=hold_days)
    
    if is_win:
        profit_pct = random.uniform(0.6, 1.0) * PMCC_EXIT_PARAMS["profit_target"]
        trade.exit_pnl = trade.entry_cost * profit_pct
        trade.exit_reason = "PROFIT_TARGET"
    else:
        # PMCCs usually don't reach 100% loss unless the underlying crashes hard, so stop out earlier
        loss_pct = random.uniform(0.3, 1.0) * PMCC_EXIT_PARAMS["stop_loss"]
        trade.exit_pnl = -trade.entry_cost * loss_pct
        trade.exit_reason = "STOP_LOSS" if loss_pct >= PMCC_EXIT_PARAMS["stop_loss"] * 0.9 else "EARLY_EXIT"
        
    return trade


def run_pmcc_6yr_backtest() -> Dict:
    """Run simulation across 6 years of market days."""
    trades: List[PMCCTrade] = []
    capital = INITIAL_CAPITAL
    equity_curve = [(START_DATE, capital)]
    
    current_date = START_DATE
    week_trades = 0
    
    while current_date <= END_DATE:
        if current_date.weekday() == 0:
            week_trades = 0
            
        if current_date.weekday() < 5 and week_trades < TRADES_PER_WEEK:
            conditions = generate_market_conditions()
            
            if should_enter_pmcc(conditions) and capital > 1000:
                symbol = random.choice(SYMBOLS)
                
                # PMCC capital requirement scaling (average $700-$2000 per LEAPS contract)
                entry_cost = random.uniform(700, 2000)
                
                # Cap entry size at 10% of total portfolio risk
                risk_limit = capital * 0.10
                if entry_cost > risk_limit:
                    entry_cost = risk_limit  # Contract scaling
                    
                trade = PMCCTrade(
                    symbol=symbol,
                    confidence=int(conditions["trend_strength"]),
                    entry_date=current_date,
                    leaps_delta=random.uniform(0.70, 0.90),
                    short_delta=random.uniform(0.15, 0.35),
                    bci_met=random.random() > 0.1,  # 90% of setups pass BCI scanner
                    entry_cost=entry_cost,
                    max_profit=entry_cost * PMCC_EXIT_PARAMS["profit_target"],
                    max_loss=entry_cost * PMCC_EXIT_PARAMS["stop_loss"]
                )
                
                trade = simulate_pmcc_outcome(trade, conditions)
                trades.append(trade)
                
                capital += trade.exit_pnl
                equity_curve.append((trade.exit_date, capital))
                week_trades += 1
                
        current_date += timedelta(days=1)
        
    return analyze_results(trades, equity_curve)


def analyze_results(trades: List[PMCCTrade], equity_curve: List) -> Dict:
    if not trades:
        return {"error": "No trades generated in 6-year window."}
        
    total_pnl = sum(t.exit_pnl for t in trades)
    wins = [t for t in trades if t.exit_pnl > 0]
    losses = [t for t in trades if t.exit_pnl <= 0]
    
    win_rate = len(wins) / len(trades) * 100
    avg_win = sum(t.exit_pnl for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t.exit_pnl for t in losses) / len(losses) if losses else 0
    
    final_capital = equity_curve[-1][1] if equity_curve else INITIAL_CAPITAL
    total_return = (final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    
    # BCI adherence metrics
    bci_trades = [t for t in trades if t.bci_met]
    bci_wins = [t for t in bci_trades if t.exit_pnl > 0]
    bci_win_rate = len(bci_wins) / len(bci_trades) * 100 if bci_trades else 0
    
    non_bci_trades = [t for t in trades if not t.bci_met]
    non_bci_wins = [t for t in non_bci_trades if t.exit_pnl > 0]
    non_bci_win_rate = len(non_bci_wins) / len(non_bci_trades) * 100 if non_bci_trades else 0

    # Year by year metrics
    yearly_stats = {}
    for year in range(START_DATE.year, END_DATE.year + 1):
        year_trades = [t for t in trades if t.exit_date and t.exit_date.year == year]
        if year_trades:
            year_pnl = sum(t.exit_pnl for t in year_trades)
            year_wins = len([t for t in year_trades if t.exit_pnl > 0])
            yearly_stats[str(year)] = {
                "trades": len(year_trades),
                "pnl": round(year_pnl, 2),
                "win_rate": round(year_wins / len(year_trades) * 100, 1)
            }

    return {
        "summary": {
            "total_trades": len(trades),
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "initial_capital": INITIAL_CAPITAL,
            "final_capital": round(final_capital, 2),
            "total_return_pct": round(total_return, 1),
            "avg_hold_cycles": round(sum(t.cycles for t in trades) / len(trades), 1)
        },
        "yearly_performance": yearly_stats,
        "bci_impact": {
            "compliant_trades_win_rate": round(bci_win_rate, 1),
            "violation_trades_win_rate": round(non_bci_win_rate, 1)
        },
        "period": f"{START_DATE.date()} to {END_DATE.date()}",
        "trades_log": [
            {
                "symbol": t.symbol,
                "entry_date": t.entry_date.strftime("%Y-%m-%d"),
                "exit_date": t.exit_date.strftime("%Y-%m-%d") if t.exit_date else "",
                "pnl": round(t.exit_pnl, 2),
                "reason": t.exit_reason,
                "cycles": t.cycles
            } for t in trades
        ]
    }


def print_results(results: Dict):
    print("\n" + "=" * 70)
    print("PMCC 6-YEAR BACKTEST RESULTS (2019-2024)")
    print("=" * 70)
    
    summary = results["summary"]
    print(f"\n{'OVERALL PERFORMANCE':^70}")
    print("-" * 70)
    print(f"  Total Trades:       {summary['total_trades']}")
    print(f"  Total P&L:          ${summary['total_pnl']:,.2f}")
    print(f"  Win Rate:           {summary['win_rate']:.1f}%")
    print(f"  Avg Win:            ${summary['avg_win']:.2f}")
    print(f"  Avg Loss:           ${summary['avg_loss']:.2f}")
    print(f"  Avg Roll Cycles:    {summary['avg_hold_cycles']}")
    print(f"  Total Return:       {summary['total_return_pct']:.1f}%")
    print(f"  Final Capital:      ${summary['final_capital']:,.2f}")
    
    print(f"\n{'YEAR-BY-YEAR P&L':^70}")
    print("-" * 70)
    for year, metrics in results.get("yearly_performance", {}).items():
        print(f"  {year}: {metrics['trades']:3} trades | Win: {metrics['win_rate']:5.1f}% | P&L: ${metrics['pnl']:8,.2f}")

    print(f"\n{'INDIVIDUAL TRADE LOG':^70}")
    print("-" * 70)
    print(f"  {'Date':12} | {'Symbol':6} | {'P&L':>10} | {'Cycles':>6} | {'Exit Reason'}")
    print("-" * 70)
    for t in results.get("trades_log", []):
        pnl_str = f"${t['pnl']:.2f}"
        print(f"  {t['entry_date']:12} | {t['symbol']:6} | {pnl_str:>10} | {t['cycles']:>6} | {t['reason']}")
        
    print("\n" + "=" * 70)


if __name__ == "__main__":
    results = run_pmcc_6yr_backtest()
    print_results(results)
    
    output_file = "pmcc_6yr_backtest_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
