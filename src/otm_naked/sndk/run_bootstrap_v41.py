import os
import sys
import pandas as pd
import numpy as np
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from block_bootstrap_engine import BlockBootstrapEngine
from proxy_data_loader import load_proxy_data
from backtest_strangle_v41 import BacktestEngineV41, _calc_adx

# Load config
with open(os.path.join(os.path.dirname(__file__), 'config_v41.yaml')) as f:
    cfg = yaml.safe_load(f)

def run_bootstrap_path(path_df):
    """
    Adapter to convert the synthetic daily path_df into the format
    expected by BacktestEngineV41, simulating intraday gap risks.
    """
    daily_df = path_df.copy()
    daily_df.set_index('date', inplace=True)
    daily_df.index = pd.to_datetime(daily_df.index)
    
    # We need a proper high/low to calculate ADX and true range properly.
    daily_df['high'] = np.maximum(daily_df['open'], daily_df['close']) * 1.015
    daily_df['low'] = np.minimum(daily_df['open'], daily_df['close']) * 0.985
    
    bars_5min = []
    
    for dt, row in daily_df.iterrows():
        # Open bar (10:00) - models gap risk vs limit orders
        bars_5min.append({
            'date': dt.replace(hour=10, minute=0),
            'open': row['open'],
            'high': row['open'],
            'low': row['open'],
            'close': row['open'],
            'volume': row['volume'] / 2
        })
        # Close bar (15:55)
        bars_5min.append({
            'date': dt.replace(hour=15, minute=55),
            'open': row['close'],
            'high': row['close'],
            'low': row['close'],
            'close': row['close'],
            'volume': row['volume'] / 2
        })
        
    df_5min = pd.DataFrame(bars_5min)
    df_5min.set_index('date', inplace=True)
    
    data = _calc_adx(df_5min, daily_df)
    
    engine = BacktestEngineV41(cfg)
    r = engine.run(data)
    
    return {
        'cagr': r.get('cagr', np.nan),
        'win_rate': r.get('win_rate', np.nan),
        'max_drawdown': r.get('max_drawdown', np.nan),
        'total_trades': r.get('total_leg_exits', 0),
        'total_pnl': r.get('total_pnl', np.nan)
    }

if __name__ == '__main__':
    print("Loading 4-year proxy data (2020-2024)...")
    wdc_df = load_proxy_data("WDC", "2020-01-01", "2024-12-31")
    
    engine = BlockBootstrapEngine(
        daily_returns=wdc_df['daily_return_scaled'],
        base_price=100.0,
        block_len_mean=50,
        n_paths=50,
        seed=42
    )
    
    print("\nRunning 50-path bootstrap on v4.1 engine (approx 6 mins)...")
    results_df = engine.run_full_validation(
        backtest_fn=run_bootstrap_path,
        target_days=1008
    )
    
    results_df.to_csv("bootstrap_results_v41.csv", index=False)
    print("Saved bootstrap results to bootstrap_results_v41.csv")
