import optuna
import logging
import sys
import os
import pandas as pd
import numpy as np

# Add src to path to import backtester
sys.path.append(os.path.dirname(__file__))

# Import Backtester
try:
    from backtest_simulation import ZebraBacktester, SIM_START_DATE, SIM_END_DATE, config
except ImportError:
    # Handle case where config is in parent
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
    from backtest_simulation import ZebraBacktester, SIM_START_DATE, SIM_END_DATE, config

# Silence intrusive logs
logging.getLogger('backtest_simulation').setLevel(logging.WARNING)
logging.getLogger('regime_detector').setLevel(logging.WARNING)
logging.getLogger('ml_signal_filter').setLevel(logging.WARNING)

def objective(trial):
    # 1. Suggest Parameters
    param_drop_pct = trial.suggest_float('drop_pct_min', 3.0, 8.0, step=0.5)
    param_rsi_max = trial.suggest_int('rsi_max', 30, 60)
    param_trend_factor = trial.suggest_float('trend_sma_factor', 0.95, 1.02, step=0.01)
    
    # 2. Setup Backtester
    # We use a subset of tickers for speed if needed, but let's try full list first
    # Or maybe just top 10 liquid ones to fail fast?
    # Let's use full list but maybe suppress output
    backtester = ZebraBacktester(config.ZEBRA_WATCHLIST)
    
    # We need to fetch data once preferably, but Backtester fetches internal. 
    # To avoid re-fetching 50 times, we should cache data.
    # Hack: check if data exists in a global or similar?
    # The Backtester class doesn't support passing data in __init__.
    # We'll just instantiate logic to fetch once outside valid loop?
    # For now, let's just let it be inefficient or rely on OS file cache if it was using disk (it uses memory).
    # actually yfinance has caching.
    
    # Actually, optimization loop re-instantiating backtester 50 times and re-downloading is bad.
    # Let's modify Backtester to allow setting data externally or singleton?
    # For this script, I will subclass or just hack it.
    # Better: Instantiate ONE backtester outside, fetch data ONCE.
    # Then inside objective, just run `backtester.run(...)`.
    # `backtester.run` resets results/equity curve so it IS reusable!
    
    # Pass params
    strategy_params = {
        'drop_pct_min': param_drop_pct,
        'rsi_max': param_rsi_max,
        'trend_sma_factor': param_trend_factor
    }
    
    # Run Full Stack: Regime + ML + Dynamic Sizing
    # Note: ML Model needs to be trained.
    # If we re-use the same backtester instance, we need to ensure 'train_ml_model' is called once.
    
    global GLOBAL_BACKTESTER
    if not hasattr(GLOBAL_BACKTESTER, 'is_ready'):
        GLOBAL_BACKTESTER.fetch_data()
        # Train ML once
        print("Training ML Model for Optimization...")
        GLOBAL_BACKTESTER.run(strategy="OLD", collect_training=True)
        GLOBAL_BACKTESTER.train_ml_model()
        GLOBAL_BACKTESTER.is_ready = True
        
    GLOBAL_BACKTESTER.run(
        strategy="NEW",
        use_regime=True,
        use_ml=True,
        strategy_params=strategy_params
    )
    
    # 3. Calculate Metric (Total P&L)
    trades = pd.DataFrame(GLOBAL_BACKTESTER.results)
    if trades.empty:
        return -100000.0 # Penalty for no trades
        
    total_pnl = trades['pnl'].sum()
    
    # Optional: Penalty for low trade count?
    if len(trades) < 50:
        total_pnl *= 0.5 # Penalize overfitting to few trades
        
    return total_pnl

if __name__ == "__main__":
    # Initialize Global Backtester
    tickers = config.ZEBRA_WATCHLIST
    GLOBAL_BACKTESTER = ZebraBacktester(tickers)
    
    print("Starting Bayesian Optimization...")
    study = optuna.create_study(direction='maximize')
    study.optimize(objective, n_trials=50, n_jobs=1) # Single thread to avoid yfinance race conditions/bans
    
    print("\n=== OPTIMIZATION RESULTS ===")
    print(f"Best P&L: ${study.best_value:,.2f}")
    print("Best Parameters:")
    for key, value in study.best_params.items():
        print(f"  {key}: {value}")
        
    # Save best params to file or just print
