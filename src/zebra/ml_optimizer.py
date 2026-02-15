import sys
import numpy as np
import logging
import pandas as pd
from typing import List, Dict
import json
import traceback
import random

# PATCH for newer NumPy and older Skopt
if not hasattr(np, 'int'):
    np.int = int

try:
    from skopt import gp_minimize
    from skopt.space import Real, Integer
    from skopt.utils import use_named_args
    HAS_SKOPT = True
except ImportError:
    HAS_SKOPT = False
    print("Skopt not found.")

from src.zebra.backtest_engine import ZebraBacktestEngine

class ZebraMLOptimizer:
    def __init__(self, symbols: List[str], start_date="2024-01-01"):
        self.symbols = symbols
        self.start_date = start_date
        self.engine = ZebraBacktestEngine()
        self.has_skopt = HAS_SKOPT  # Store as instance variable
        print(f"Initializing Optimizer with {len(symbols)} symbols...")
        self.engine.fetch_data(symbols, start_date=start_date)
        
        # Define ranges for simple random search fallback
        self.ranges = {
            'profit_target_pct': (0.25, 0.80),
            'stop_loss_pct': (-0.60, -0.15),
            'time_exit_days': (15, 60),
            'trailing_activation_pct': (0.10, 0.40),
            'trailing_pct': (0.05, 0.20),
            'atr_multiplier': (1.5, 4.0)
        }
        
        if self.has_skopt:
            self.space = [
                Real(0.25, 0.80, name='profit_target_pct'),
                Real(-0.60, -0.15, name='stop_loss_pct'),
                Integer(15, 60, name='time_exit_days'),
                Real(0.10, 0.40, name='trailing_activation_pct'),
                Real(0.05, 0.20, name='trailing_pct'),
                Real(1.5, 4.0, name='atr_multiplier')
            ]

    def objective(self, params):
        # Allow params dict or list
        if isinstance(params, list):
            p_dict = {
                'profit_target_pct': params[0],
                'stop_loss_pct': params[1],
                'time_exit_days': int(params[2]),
                'trailing_activation_pct': params[3],
                'trailing_pct': params[4],
                'atr_multiplier': params[5],
                'min_score': 40  # Lower threshold to allow trades
            }
        else:
            p_dict = params
            if 'min_score' not in p_dict:
                p_dict['min_score'] = 40

        result = self.engine.run_simulation(p_dict)
        sharpe = result.get('sharpe', -999)
        pnl = result.get('pnl', 0)
        trades = result.get('trades', 0)
        
        print(f"Eval: Sharpe={sharpe:.2f}, P&L={pnl:.2f}, Trades={trades}")
        
        if trades < 5: return 999 
        return -sharpe

    def run_optimization(self, n_calls=20):
        print(f"Starting optimization (Skopt={self.has_skopt})...")
        
        best_result = None
        best_score = 999
        best_params = None  # Initialize to avoid UnboundLocalError
        use_random_fallback = not self.has_skopt

        if self.has_skopt:
            @use_named_args(self.space)
            def objective_wrapper(**params):
                return self.objective([
                    params['profit_target_pct'],
                    params['stop_loss_pct'],
                    params['time_exit_days'],
                    params['trailing_activation_pct'],
                    params['trailing_pct'],
                    params['atr_multiplier']
                ])

            try:
                res = gp_minimize(objective_wrapper, self.space, n_calls=n_calls, random_state=42)
                best_params = {
                    'profit_target_pct': res.x[0],
                    'stop_loss_pct': res.x[1],
                    'time_exit_days': int(res.x[2]),
                    'trailing_activation_pct': res.x[3],
                    'trailing_pct': res.x[4],
                    'atr_multiplier': res.x[5],
                    'min_score': 40,  # Lower threshold to get more trades
                    'score': -res.fun
                }
                print("Bayesian Optimization Success.")
            except Exception as e:
                print(f"Bayesian Optimization Failed: {e}")
                use_random_fallback = True
        
        if use_random_fallback:
            print("Running Random Search Fallback...")
            for i in range(n_calls):
                p_dict = {
                    'profit_target_pct': random.uniform(*self.ranges['profit_target_pct']),
                    'stop_loss_pct': random.uniform(*self.ranges['stop_loss_pct']),
                    'time_exit_days': int(random.uniform(*self.ranges['time_exit_days'])),
                    'trailing_activation_pct': random.uniform(*self.ranges['trailing_activation_pct']),
                    'trailing_pct': random.uniform(*self.ranges['trailing_pct']),
                    'atr_multiplier': random.uniform(*self.ranges['atr_multiplier']),
                    'min_score': 40  # Lower threshold
                }
                score = self.objective(p_dict)
                if score < best_score:
                    best_score = score
                    best_params = p_dict
                    best_params['score'] = -score
        
        # If still no params (all failed), use defaults
        if best_params is None:
            best_params = {
                'profit_target_pct': 0.50,
                'stop_loss_pct': -0.35,
                'time_exit_days': 25,
                'trailing_activation_pct': 0.20,
                'trailing_pct': 0.12,
                'atr_multiplier': 2.5,
                'min_score': 40,
                'score': 0
            }
            print("No successful optimization, using defaults.")
        
        # Save results
        with open('optimization_results.json', 'w') as f:
            json.dump(best_params, f, indent=4)
        print("Results saved.")
        return best_params

if __name__ == "__main__":
    try:
        opt = ZebraMLOptimizer(["SPY", "NVDA", "IWM", "TSLA", "AMD"], start_date="2024-01-01")
        opt.run_optimization(n_calls=20)
    except Exception as e:
        print(f"Main Error: {e}")
        traceback.print_exc()
