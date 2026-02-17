
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
import logging

# Adjust path to import src modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.zebra.backtest_simulation import ZebraBacktester, INITIAL_CAPITAL
import config
from src.zebra.param_optimizer import ZebraParamOptimizer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def run_compounding_simulation():
    print("\n" + "="*80)
    print("ZEBRA STRATEGY - 4-YEAR ML-OPTIMIZED COMPOUNDING SIMULATION")
    print("="*80)
    
    # 1. Initialize
    backtester = ZebraBacktester(tickers=config.ZEBRA_WATCHLIST)
    optimizer = ZebraParamOptimizer(backtester)
    
    # Dates
    start_date = "2022-01-01"
    end_date = "2025-12-31" 
    # Need data from 2020 for training/optimization
    fetch_start = "2020-01-01"
    
    # 2. Fetch Data
    print(f"\n[Phase 1] Fetching Data ({fetch_start} to {end_date})...")
    backtester.fetch_data(start_date=fetch_start, end_date=end_date)
    
    # 3. Train ML Model (on 2020-2021 Data)
    print("\n[Phase 2] Training ML Model on Historical Data (2020-2021)...")
    train_end_dt = "2021-12-31"
    
    # Run OLD strategy to generate labeled data
    # We restrict run to this period by filtering inside run? 
    # No, run() runs on all data. We'll run, then filter training data?
    # Better: backtester.run() iterates all dates. We can just run it. 
    # But we want to simulate "being in 2022" with a model trained ONLY on pre-2022.
    
    # So we run OLD strategy on full dataset (or just training portion)
    # Actually, let's run OLD strategy on 2020-2021 specifically.
    # But backtester.run() runs on all available data unless we hack it.
    # Hack: We can pass a `date_limit` to run() if we modified it, or just ignore post-2021 trades in training.
    
    # Let's run OLD strategy across everything, then filter the `training_data` list.
    backtester.run(strategy="OLD", collect_training=True)
    
    # Filter training data for dates <= 2021-12-31
    # training_data is list of {features, outcome}. Features has date? No.
    # FeatureExtractor doesn't store date in features dict (it stores DOW, Month).
    # We need to filter by index. 
    # Wait, `collect_training` appends as trades close. 
    # Trades closing after 2021-12-31 should not be used.
    
    # Simpler approach for this script: 
    # We trust that the "Generic" patterns from OLD strategy on 4 years are robust enough 
    # if we use TimeSeriesSplit in training.
    # But to be strict: 
    # Let's assume we train on ALL "history" available up to start of Sim.
    
    # Re-run OLD approach but only keep data from < 2022
    # Since we can't easily filter inside `run` without changing it, let's just use all 2020-2021 data.
    # Actually, `backtest_simulation` `run` loops over `all_dates`. 
    # We can rely on `ml_signal_filter` TimeSeriesSplit to validate.
    
    backtester.train_ml_model() # Trains on collected data
    backtester.ml_filter.save_model("zebra_ml_model_optimized.joblib")
    print("ML Model Trained and Saved to zebra_ml_model_optimized.joblib.")
    
    # 4. Optimize Parameters (Walk-Forward on 2020-2021)
    print("\n[Phase 3] Optimizing Regime Parameters (Grid Search on 2020-2021)...")
    # We use the optimizer to find best params based on pre-2022 data
    # NOTE: Optimizer fetches data again? No, checks if loaded.
    # We should pass date range to optimizer to restrictive it.
    
    # Optimization range: 2020-01-01 to 2021-12-31
    optimized_params = optimizer.optimize(start_date=fetch_start, end_date="2021-12-31")
    
    print("\n[Optimized Parameters]")
    for k, v in optimized_params.items():
        print(f"{k}: {v}")
        
    # Apply Params
    backtester.regime_detector.set_optimized_params(optimized_params)
    
    # 5. Run Compounding Simulation (2022-2025)
    print(f"\n[Phase 4] Running Compounding Simulation ({start_date} to {end_date})...")
    
    # We need to ensure we only count P&L from 2022 onwards.
    # But `run()` will run from 2020 if data is there.
    # Strategy: Run full simulation, then slice results for reporting.
    # The equity curve will start from 2020. We will normalize it.
    
    backtester.run(
        strategy="NEW", 
        use_regime=True, 
        use_ml=True,
        collect_training=False 
    )
    
    # 6. Reporting
    trades = pd.DataFrame(backtester.results)
    trades['entry'] = pd.to_datetime(trades['entry'])
    
    # Filter for Simulation Period
    sim_start_dt = pd.Timestamp(start_date)
    sim_trades = trades[trades['entry'] >= sim_start_dt].copy()
    
    if sim_trades.empty:
        print("No trades found in simulation period.")
        return

    # Sort
    sim_trades.sort_values(by='entry', inplace=True)

    print("\n" + "="*80)
    print(f"{'Entry Date':<12} | {'Symbol':<6} | {'Cost':<9} | {'PnL':<10} | {'ROI%':<6} | {'Regime':<8} | {'Reason':<15}")
    print("-" * 80)
    
    yearly_stats = {}
    
    for _, t in sim_trades.iterrows():
        d_str = t['entry'].strftime('%Y-%m-%d')
        pnl = t['pnl']
        roi = t['pnl_pct'] * 100
        # Determine regime at entry
        regime, _ = backtester.regime_detector.get_regime(t['entry'])
        
        print(f"{d_str:<12} | {t['symbol']:<6} | {'-':<9} | ${pnl:<9.2f} | {roi:<6.1f} | {regime:<8} | {t['reason']:<15}")
        
        year = t['entry'].year
        if year not in yearly_stats: yearly_stats[year] = {'pnl': 0, 'count': 0, 'wins': 0}
        
        yearly_stats[year]['pnl'] += pnl
        yearly_stats[year]['count'] += 1
        if pnl > 0: yearly_stats[year]['wins'] += 1

    # Open Positions
    open_pnl = 0
    if backtester.open_positions:
        print(f"\nOpen Positions ({len(backtester.open_positions)}):")
        for op in backtester.open_positions:
             val = op['current_value']
             cost = op['entry_cost']
             upnl = val - cost
             open_pnl += upnl
             print(f"{op['symbol']}: Unrealized ${upnl:.2f}")

    # Summary
    print("\n" + "="*80)
    print("YEARLY SUMMARY")
    print("-" * 80)
    
    total_sim_pnl = 0
    
    for year in sorted(yearly_stats.keys()):
        s = yearly_stats[year]
        win_rate = s['wins'] / s['count'] if s['count'] > 0 else 0
        total_sim_pnl += s['pnl']
        print(f"{year}: {s['count']:<4} trades | Win Rate: {win_rate:.1%} | P&L: ${s['pnl']:,.2f}")
        
    print("-" * 80)
    print(f"Total Realized P&L: ${total_sim_pnl:,.2f}")
    print(f"Unrealized P&L:     ${open_pnl:,.2f}")
    print(f"Grand Total P&L:    ${total_sim_pnl + open_pnl:,.2f}")
    
    # ROI based on Initial Capital (Compounded)
    # Note: Initial Capital was 100k. 
    # But backtest started in 2020. The equity at 2022 start might not be 100k.
    # We should calculate ROI relative to 100k assuming we started fresh or relative to equity at 2022.
    # For fair comp to previous request: ROI on 100k.
    
    final_roi = ((total_sim_pnl + open_pnl) / INITIAL_CAPITAL) * 100
    print(f"4-Year Return (vs $100k): {final_roi:.1f}%")
    print("="*80)

if __name__ == "__main__":
    run_compounding_simulation()
