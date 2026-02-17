
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# Adjust path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.zebra.backtest_simulation import ZebraBacktester, INITIAL_CAPITAL
import config

def run_compound_simulation():
    print("\n" + "="*80)
    print("ZEBRA STRATEGY - COMPOUND SIMULATION (2023-Present)")
    print("="*80)
    
    backtester = ZebraBacktester(tickers=config.ZEBRA_WATCHLIST)
    
    # --- 1. TRAIN MODEL (2020-2021) ---
    print("\n[Phase 0] Training Model on 2020-2021 Data...")
    # Fetch 2y history before 2022
    train_start = "2020-01-01"
    train_end = "2021-12-31"
    
    backtester.fetch_data(start_date=train_start, end_date=train_end)
    backtester.run(strategy="OLD", collect_training=True) # Collect features
    backtester.train_ml_model()
    
    # --- 2. RUN COMPOUND SIMULATION (2022-2026) ---
    sim_start = "2022-01-01"
    sim_end = datetime.now().strftime('%Y-%m-%d')
    print(f"\n[Phase 1] Running Simulation: {sim_start} to {sim_end}")
    
    # Fetch all data at once
    # Need padding for indicators (e.g. since 2021)
    fetch_start = "2021-01-01" 
    backtester.fetch_data(start_date=fetch_start, end_date=sim_end)
    
    # Run Continuous Simulation
    # Capital will compound because we run ONCE over the whole period
    stats = backtester.run(strategy="NEW", use_regime=True, use_ml=True)
    
    # --- 3. ANALYSIS ---
    trades = pd.DataFrame(backtester.results)
    if trades.empty:
        print("No trades generated.")
        return

    # Filter trades that started within the sim period
    trades['entry'] = pd.to_datetime(trades['entry'])
    trades['entry'] = pd.to_datetime(trades['entry'])
    trades = trades[trades['entry'] >= pd.Timestamp(sim_start)]
    
    if trades.empty:
        print("No trades found in the simulation period.")
        return

    # --- 4. DETAILED TRADE LOG ---
    print("\n" + "="*80)
    print(f"{'ENTRY':<12} | {'SYMBOL':<6} | {'PnL':<10} | {'ROI%':<6} | {'SCORE':<5} | {'CONF':<4} | {'RSI':<4} | {'DROP':<5} | {'REASON':<10}")
    print("-" * 80)
    
    for _, t in trades.iterrows():
        date_str = pd.to_datetime(t['entry']).strftime('%Y-%m-%d')
        pnl = t['pnl']
        roi = t.get('pnl_pct', 0) * 100
        score = t.get('score', 0)
        conf = t.get('ml_conf', 0)
        reason = t.get('reason', '-')
        
        # safely get features
        feats = t.get('features', {})
        rsi = feats.get('RSI', 0)
        drop = feats.get('Drop_Pct', 0)
        
        # Color coding (if terminal supports it, otherwise just text)
        print(f"{date_str:<12} | {t['symbol']:<6} | ${pnl:<9.2f} | {roi:<6.1f} | {score:<5.1f} | {conf:<4.2f} | {rsi:<4.1f} | {drop:<5.1f} | {reason:<10}")

    print("-" * 80)

    print("\n" + "="*80)
    print("COMPOUNDING RESULTS")
    print("="*80)
    
    total_trades = len(trades)
    win_rate = len(trades[trades['pnl'] > 0]) / total_trades * 100 if total_trades > 0 else 0
    total_pnl = trades['pnl'].sum()
    final_equity = backtester.equity_curve[-1]
    total_return = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    
    print(f"Total Trades:    {total_trades}")
    print(f"Win Rate:        {win_rate:.1f}%")
    print(f"Initial Capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"Final Equity:    ${final_equity:,.2f}")
    print(f"Total P&L:       ${total_pnl:,.2f}")
    print(f"Total Return:    {total_return:.1f}%")
    
    # Yearly Breakdown (approximate)
    trades['year'] = trades['entry'].dt.year
    yearly = trades.groupby('year')['pnl'].sum()
    
    print("\nYearly P&L Breakdown (Realized):")
    for year, pnl in yearly.items():
        print(f"{year}: ${pnl:,.2f}")
        
    # Drawdown Analysis
    equity_series = pd.Series(backtester.equity_curve)
    peak = equity_series.cummax()
    drawdown = (equity_series - peak) / peak
    max_dd = drawdown.min() * 100
    
    print(f"\nMax Drawdown:    {max_dd:.1f}%")

if __name__ == "__main__":
    run_compound_simulation()
