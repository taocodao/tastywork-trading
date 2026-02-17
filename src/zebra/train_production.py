
import sys
import os
import pandas as pd
import json
import logging
from datetime import datetime

# Adjust path to import src modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.zebra.backtest_simulation import ZebraBacktester
import config
from src.zebra.param_optimizer import ZebraParamOptimizer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def train_production_model():
    print("\n" + "="*80)
    print("ZEBRA STRATEGY - PRODUCTION TRAINING (FULL HISTORY)")
    print("="*80)
    
    # 1. Initialize
    backtester = ZebraBacktester(tickers=config.ZEBRA_WATCHLIST)
    optimizer = ZebraParamOptimizer(backtester)
    
    # Dates
    start_date = "2020-01-01"
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"\n[Phase 1] Fetching Full History ({start_date} to {end_date})...")
    backtester.fetch_data(start_date=start_date, end_date=end_date)
    
    # 2. Train ML Model
    print(f"\n[Phase 2] Training ML Model on {start_date} to {end_date}...")
    # Run strategy to collect all trade opportunities
    backtester.run(strategy="OLD", collect_training=True)
    
    # Train and Save
    if backtester.train_ml_model():
        model_path = "zebra_ml_model_prod.joblib"
        backtester.ml_filter.save_model(model_path)
        print(f"SUCCESS: Production Model saved to {model_path}")
    else:
        print("ERROR: ML Model Training Failed.")
        return

    # 3. Optimize Regime Parameters
    print(f"\n[Phase 3] Optimizing Regime Parameters...")
    # Use data up to 3 months ago to avoid overfitting recent noise? 
    # Or just full history. User said "all historic data". We use full history.
    optimized_params = optimizer.optimize(start_date=start_date, end_date=end_date)
    
    if optimized_params:
        params_path = "zebra_regime_params_prod.json"
        with open(params_path, 'w') as f:
            json.dump(optimized_params, f, indent=4)
        print(f"SUCCESS: Optimized Parameters saved to {params_path}")
        
        print("\n[Optimized Parameters]")
        for k, v in optimized_params.items():
            print(f"{k}: {v}")
    else:
        print("WARNING: No parameters optimized.")

if __name__ == "__main__":
    train_production_model()
