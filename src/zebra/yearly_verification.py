
import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Adjust path to import src modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.zebra.backtest_simulation import ZebraBacktester, INITIAL_CAPITAL
import config

def run_yearly_verification():
    periods = [
        ("2023", "2023-01-01", "2023-12-31"),
        ("2024", "2024-01-01", "2024-12-31"),
        ("2025-2026", "2025-01-01", datetime.now().strftime('%Y-%m-%d')) # Till now
    ]
    
    backtester = ZebraBacktester(tickers=config.ZEBRA_WATCHLIST)
    
    print("\n" + "="*80)
    print("ZEBRA STRATEGY - YEARLY VERIFICATION (PRODUCTION CODE)")
    print("="*80)
    
    # --- PRE-TRAINING PHASE ---
    print("\n[Phase 0] Training ML Model on Historical Data (2021-2022)...")
    # Fetch 2 years of history for training
    train_start = (datetime.strptime("2021-01-01", "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
    train_end = "2022-12-31"
    
    backtester.fetch_data(start_date=train_start, end_date=train_end)
    # Run OLD strategy to generate labeled data
    backtester.run(strategy="OLD", collect_training=True)
    backtester.train_ml_model()
    print("Model Training Complete.\n")

    for label, start_date, end_date in periods:
        print(f"\nrunning Simulation for: {label} ({start_date} to {end_date})")
        print("-" * 60)
        
        # Add padding for indicators (e.g. 250 days)
        fetch_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")
        
        # 1. Fetch Data
        backtester.fetch_data(start_date=fetch_start, end_date=end_date)
        
        # 2. Run Production Strategy (Full Stack)
        # use_regime=True, use_ml=True. Sizing is automatic in run()
        stats = backtester.run(strategy="NEW", use_regime=True, use_ml=True)
        
        # 3. Filter Trades for the specific year
        all_trades = pd.DataFrame(backtester.results)
        if all_trades.empty:
            print("No trades found in this period.")
            continue
            
        # Filter by entry date being within the requested period
        # Note: fetch_data got extra history, simulation might have processed earlier dates if we didn't gate run()
        # But run() iterates all available dates in data.
        # We must filter results.
        # Key in results is 'entry', not 'entry_date'
        all_trades['entry'] = pd.to_datetime(all_trades['entry'])
        period_start = pd.Timestamp(start_date)
        period_end = pd.Timestamp(end_date)
        
        trades = all_trades[(all_trades['entry'] >= period_start) & (all_trades['entry'] <= period_end)]
        
        if trades.empty:
            print("No trades found in this specific year range.")
            continue
            
        # 4. Print Trade Details (Closed Trades)
        print(f"\nClosed Trades ({len(trades)}):")
        print(f"{'Entry Date':<12} | {'Symbol':<6} | {'Type':<5} | {'Cost':<9} | {'PnL':<10} | {'ROI%':<6} | {'Reason':<10}")
        print("-" * 80)
        
        realized_pnl = 0.0
        
        for _, t in trades.iterrows():
            date_str = pd.to_datetime(t['entry']).strftime('%Y-%m-%d')
            cost = 0 # Not stored in results, implies PnL is raw. In backtest cost is roughly 100k * alloc
            pnl = t['pnl']
            roi = t.get('pnl_pct', 0) * 100
            reason = t.get('reason', '-')
            
            realized_pnl += pnl
            
            print(f"{date_str:<12} | {t['symbol']:<6} | {'LONG':<5} | {'-':<9} | ${pnl:<9.2f} | {roi:<6.1f} | {reason:<10}")

        # 5. Open Positions (Unrealized)
        open_pos_pnl = 0.0
        open_trades = backtester.open_positions
        if open_trades:
            print(f"\nOpen Trades ({len(open_trades)}) [Unrealized]:")
            print(f"{'Entry Date':<12} | {'Symbol':<6} | {'Cost':<9} | {'Cur Val':<9} | {'Unreal PnL':<10}")
            print("-" * 80)
            
            for op in open_trades:
                # Check if entry date is within period (likely yes if verified above, but good to check)
                # Actually open positions by definition are still open at end_date.
                # We should only count them if they were OPENED during the period? 
                # Yes, or if they exist at end_day.
                # We'll just list them all as "Ending Open Positions"
                
                entry_dt = op['entry_date']
                if isinstance(entry_dt, str): entry_dt = datetime.strptime(entry_dt, "%Y-%m-%d")
                
                # Format
                d_str = entry_dt.strftime('%Y-%m-%d')
                cost = op['entry_cost']
                val = op['current_value']
                u_pnl = val - cost
                
                open_pos_pnl += u_pnl
                
                print(f"{d_str:<12} | {op['symbol']:<6} | ${cost:<8.0f} | ${val:<8.0f} | ${u_pnl:<9.2f}")
                
        # 6. Summary
        total_pnl = realized_pnl + open_pos_pnl
        win_rate = len(trades[trades['pnl'] > 0]) / len(trades) if len(trades) > 0 else 0
        
        period_roi = (total_pnl / INITIAL_CAPITAL) * 100
        
        print("\nSummary:")
        print(f"Total Trades:     {len(trades)} Closed + {len(open_trades)} Open")
        print(f"Win Rate (Closed):{win_rate:.1%}")
        print(f"Realized P&L:     ${realized_pnl:,.2f}")
        print(f"Unrealized P&L:   ${open_pos_pnl:,.2f}")
        print(f"Total P&L:        ${total_pnl:,.2f}")
        print(f"Period ROI:       {period_roi:.1f}%")
        print("="*80)

if __name__ == "__main__":
    run_yearly_verification()
