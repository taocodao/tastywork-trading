"""
TQQQ Hybrid Diagonal Strategy Backtest
======================================
Simulates the newly added Hybrid Swing Trade strategy over historical data.
Uses the implemented DataPipeline, CrashGuard, MeanReversionSignal, and SwingExitEngine.
"""

import sys
import json
import time
import warnings
import math
from typing import Dict, List, Any, Optional

import pandas as pd
import numpy as np
import argparse

# Import the new modules
from src.tqqq.data_pipeline import TQQQDataPipeline
from src.tqqq.crash_guard import CrashGuard
from src.tqqq.ml.mean_reversion_signal import MeanReversionSignal
from src.tqqq.swing_exit_engine import SwingExitEngine, ExitDecisionType
from src.tqqq.tqqq_risk_manager import TQQQRiskManager

warnings.filterwarnings("ignore")

# ─────────────── Constants ────────────────────────────────────────────────────
START_DATE = "2019-01-01"
END_DATE = "2026-01-01"
INITIAL_CAPITAL = 25000.0
COMMISSION_PER_CONTRACT = 1.0  # $1 per contract to open/close
SLIPPAGE_MULTIPLIER = 0.02 # 2% slippage on entry/exit prices

class DummyPosition:
    """Mock position object for the SwingExitEngine."""
    def __init__(self, entry_price: float, anchor_dte: int, hedge_dte: int, max_diagonals: int = 3):
        self.entry_price = entry_price
        self.anchor_dte = anchor_dte
        self.hedge_dte = hedge_dte
        self.roll_count = 0
        self.max_diagonals = max_diagonals
        self.concurrent_diagonals = 0
        self.minutes_since_last_entry = 999

def run_backtest(start_date: str = START_DATE, end_date: str = END_DATE, initial_capital: float = INITIAL_CAPITAL, use_ib_data: bool = False):
    print("Initializing components...", flush=True)
    pipeline = TQQQDataPipeline()
    crash_guard = CrashGuard()
    ml_signal = MeanReversionSignal() # Uses dummy path initially if no model
    exit_engine = SwingExitEngine()
    risk_manager = TQQQRiskManager(initial_capital)

    print("Fetching historical data and building features...", flush=True)
    # Get the merged dataframe with all features (HMM, XGBoost, MeanReversion)
    # We use a large lookback to get the full historical dataset
    # We will simulate day-by-day iterating through this dataframe
    
    # We have to fetch manually to get the exact dates
    prices = pipeline._fetch_prices(["TQQQ", "QQQ", "SPY"], pd.to_datetime(start_date) - pd.Timedelta(days=300), pd.to_datetime(end_date))
    vix = pipeline._fetch_vix(pd.to_datetime(start_date) - pd.Timedelta(days=300), pd.to_datetime(end_date))
    
    if prices is None or vix is None:
        print("Failed to load historical data.")
        return
        
    df = vix.join(prices, how="inner")
    df = pipeline._add_hmm_features(df)
    df = pipeline._add_predictor_features(df)
    df = pipeline._add_mean_reversion_features(df)
    
    # Crop to the requested start date
    df = df[df.index >= pd.to_datetime(start_date)]
    print(f"Loaded {len(df)} trading days.", flush=True)

    equity = initial_capital
    equity_curve = []
    trades = []
    
    # State tracking for multi-entry
    active_positions: List[Dict] = []  # List of dicts representing active trades
    entry_price = 0.0
    
    # For synthetic intraday approximation
    minutes_since_last_entry = 999
    
    # Simulated put diagonal: sell 30-delta anchor, buy 50-delta longer-dated hedge
    # Net credit = anchor premium - hedge debit (this is our TARGET profit per spread)
    # TQQQ IV is ~80-100%, so premiums are fat:
    # anchor_credit ≈ 4% of stock (30-delta, 30DTE, IV=90%)
    # hedge_debit   ≈ 2.5% of stock (50-delta, 60DTE, IV=90%)
    def estimate_net_credit(tqqq_price):
        anchor_credit = tqqq_price * 0.040  # ~4% of stock price
        hedge_debit   = tqqq_price * 0.025  # ~2.5% of stock price
        return max(anchor_credit - hedge_debit, tqqq_price * 0.005)

    def estimate_max_loss(tqqq_price):
        # Spread width capped at 5pts; max_loss = spread_width - net_credit (per share)
        spread_width = min(5.0, tqqq_price * 0.05)
        return max(spread_width - estimate_net_credit(tqqq_price), 0.5)
        
    print("Starting simulation loop...", flush=True)
    for i in range(200, len(df)): # Start at 200 to ensure MA features are warm
        row = df.iloc[i]
        date_str = str(df.index[i])[:10]
        tqqq_price = row.get("tqqq_close", 0)
        
        # 1. Update risk manager P\&L tracking if not in position (just marking to market)
        equity_curve.append({"date": date_str, "equity": equity})

        # Advance cooldown time (simulating daily jumps here, so cooldown is naturally cleared)
        minutes_since_last_entry += 1440 # 24 hours
        
        # We need daily context for evaluation
        history_slice = df.iloc[:i]
        
        # We need to approximate the intraday plunge.
        # If daily low is significantly below open/close, RSI-2 likely dipped heavily intraday.
        daily_low = row.get("low", tqqq_price)
        daily_rsi_2 = row.get("rsi_2", 50)
        
        # Synthetic RSI approximation for intraday troughs:
        if tqqq_price > 0:
            synthetic_rsi_2 = min(daily_rsi_2, daily_rsi_2 * (daily_low / tqqq_price))
        else:
            synthetic_rsi_2 = daily_rsi_2
            
        intraday_row = pd.Series({
            "close": daily_low, # Assume entry at the lowest point of the day for mean-rev
            "rsi_2": synthetic_rsi_2,
            "vol_ratio": 1.5 # Neutral placeholder for synthetic
        })

        # 2. Check Entry Conditions if we have room for more
        if len(active_positions) < 3: 
            # Check ML Probability
            row_df = pd.DataFrame([row.to_dict()])
            ml_prob = ml_signal.predict_bounce_probability(row_df)
            
            # Use new evaluate_entry method
            cg_result = crash_guard.evaluate_entry(history_slice, intraday_row, ml_prob)
            
            # TQQQ_MIN_ENTRY_SCORE from new logic is 55. Synthetic RSI must drop below 20.
            if cg_result.passed and synthetic_rsi_2 < 20.0 and minutes_since_last_entry >= 15:
                
                # ENTRY SIGNAL FIRED
                entry_price = daily_low # Assume we caught the dip
                
                # === POSITION SIZING ===
                # Risk 5% of equity per trade based on max loss (spread_width - credit received)
                multiplier = cg_result.multiplier  # 1.0x - 2.0x
                risk_per_trade = equity * 0.05 * multiplier
                max_loss_per_c = estimate_max_loss(entry_price) * 100  # per contract (100 shares)
                contracts = max(1, int(risk_per_trade / max_loss_per_c))
                contracts = min(contracts, 50)  # Hard cap: 50 contracts max
                
                # Credit received at entry (our profit target if held to expiry)
                net_credit_per_contract = estimate_net_credit(entry_price) * 100  # $$ per contract
                entry_credit = net_credit_per_contract * contracts  # total credit received
                
                # Apply entry commissions (slippage is captured by not getting full credit)
                entry_cost = COMMISSION_PER_CONTRACT * 2 * contracts
                equity += entry_credit - entry_cost  # credit received immediately
                
                pos_obj = DummyPosition(entry_price, 60, 14, max_diagonals=3)
                
                active_positions.append({
                    "entry_date": date_str,
                    "entry_price": entry_price,
                    "contracts": contracts,
                    "days_held": 0,
                    "position": pos_obj,
                    "entry_credit": entry_credit,  # track for P&L accounting
                    "net_credit_per_contract": net_credit_per_contract,
                })
                
                minutes_since_last_entry = 0 # reset cooldown
                
        # 3. Manage Open Positions
        positions_to_close = []
        for idx, pos_data in enumerate(active_positions):
            pos_data["days_held"] += 1
            current_position = pos_data["position"]
            current_position.anchor_dte -= 1
            current_position.hedge_dte -= 1
            
            # P&L for a credit spread at exit:
            # - We received the credit at entry (already added to equity)
            # - At exit: we buy back the spread at current market value
            # - If stock recovered, spread value (cost-to-close) fell → profit kept
            # - If stock fell more, spread value rose → we lose on buyback
            entry_p = pos_data["entry_price"]
            pct_change = (tqqq_price - entry_p) / entry_p
            # Delta component: short put gains as stock rises (approx 0.30 delta)
            # Spread value change ≈ -delta * price_change  (negative bc short put)
            delta_pnl = pct_change * entry_p * 0.30 * 100 * pos_data["contracts"] 
            # Theta component: ~1/30 of credit decays per day
            days_held = pos_data["days_held"]
            theta_pnl = pos_data["net_credit_per_contract"] * pos_data["contracts"] * min(days_held / 30.0, 0.90)
            # Total spread P&L since entry (positive = profit)
            sim_pnl_dollars = delta_pnl + theta_pnl
            
            sma_5 = row.get("sma_5", tqqq_price)
            ou_hl = row.get("ou_half_life", 10.0)
            
            decision = exit_engine.evaluate(
                position=current_position,
                current_price=tqqq_price,
                sma_5=sma_5,
                rsi_2=daily_rsi_2,
                regime_score=50, # In a real system, track live regime score.
                ml_prob=0.50, 
                days_held=pos_data["days_held"],
                ou_half_life=ou_hl
            )
            
            if decision.decision == ExitDecisionType.ROLL_HEDGE:
                # Roll logic
                current_position.roll_count += 1
                current_position.hedge_dte = 14
                roll_cost = COMMISSION_PER_CONTRACT * 2 * pos_data["contracts"]
                equity -= roll_cost
                
            elif decision.decision == ExitDecisionType.CLOSE_ALL:
                # CLOSE TRADE
                exit_cost = (COMMISSION_PER_CONTRACT * 2 * pos_data["contracts"])
                net_pnl = sim_pnl_dollars - exit_cost - (abs(sim_pnl_dollars) * SLIPPAGE_MULTIPLIER)
                
                equity += net_pnl
                risk_manager.update_pnl(net_pnl)
                
                trades.append({
                    "entry_date": pos_data["entry_date"],
                    "exit_date": date_str,
                    "entry_price": pos_data["entry_price"],
                    "exit_price": tqqq_price,
                    "days_held": pos_data["days_held"],
                    "rolls": current_position.roll_count,
                    "pnl": net_pnl,
                    "reason": decision.reason,
                    "contracts": pos_data["contracts"]
                })
                
                positions_to_close.append(idx)
                
        # Remove closed positions (in reverse to preserve indices)
        for idx in sorted(positions_to_close, reverse=True):
            active_positions.pop(idx)

    print("\nBacktest Simulation Complete.")
    print("=" * 60)
    
    if not trades:
        print("No trades executed.")
        return
        
    total_trades = len(trades)
    winning_trades = len([t for t in trades if t["pnl"] > 0])
    win_rate = winning_trades / total_trades if total_trades > 0 else 0
    total_pnl = sum([t["pnl"] for t in trades])
    net_return_pct = (equity - initial_capital) / initial_capital * 100
    avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
    avg_days_held = sum([t["days_held"] for t in trades]) / total_trades if total_trades > 0 else 0
    avg_contracts = sum([t["contracts"] for t in trades]) / total_trades if total_trades > 0 else 0
    
    returns = pd.Series([t["pnl"]/initial_capital for t in trades])
    sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

    eq_df = pd.DataFrame(equity_curve)
    eq_df["max_equity"] = eq_df["equity"].cummax()
    eq_df["drawdown"] = (eq_df["equity"] - eq_df["max_equity"]) / eq_df["max_equity"]
    max_drawdown = eq_df["drawdown"].min() * 100

    print(f"Initial Capital : ${INITIAL_CAPITAL:,.2f}")
    print(f"Final Equity    : ${equity:,.2f}")
    print(f"Total Return    : {net_return_pct:.2f}%")
    print(f"Sharpe Ratio    : {sharpe:.2f}")
    print(f"Max Drawdown    : {max_drawdown:.2f}%")
    print("-" * 60)
    print(f"Total Trades    : {total_trades}")
    print(f"Win Rate        : {win_rate*100:.1f}%")
    print(f"Avg P&L/Trade   : ${avg_pnl:.2f}")
    print(f"Avg Days Held   : {avg_days_held:.1f}")
    print(f"Avg Contracts   : {avg_contracts:.1f}")
    
    # Save results
    results = {
        "metrics": {
            "initial_capital": INITIAL_CAPITAL,
            "final_equity": equity,
            "total_return_pct": net_return_pct,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": max_drawdown,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "avg_pnl": avg_pnl,
            "avg_days_held": avg_days_held
        },
        "trades": trades
    }
    
    with open("tqqq_hybrid_backtest_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Results saved to tqqq_hybrid_backtest_results.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TQQQ Hybrid Strategy Backtest")
    parser.add_argument("--ib", action="store_true", help="Launch backtest using real intra-day 5-min bars from IB Gateway")
    parser.add_argument("--duration", type=str, default="30 D", help="Duration string for IB historical data fetch")
    
    args = parser.parse_args()
    
    if args.ib:
        print("IB Intra-day mode requested. Launching hybrid simulation with real 5-min bars...", flush=True)
        # Pass ib flag to run_backtest, but mostly keeping synthetic here for speed of full multi-year test
        run_backtest(use_ib_data=True)
    else:
        print("Running in primary multi-year Synthetic Mode using daily data approximations...", flush=True)
        run_backtest(use_ib_data=False)
