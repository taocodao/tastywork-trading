import os
import sys
import logging
import pandas as pd
import numpy as np
import optuna

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.tqqq_turbocore.data_pipeline import TurboCoreDataPipeline
from src.tqqq_turbocore.base_strategy import BaseStrategy
from src.tqqq_turbocore.ml.regime_detector import TurboCoreRegimeDetector
from src.tqqq_turbocore.ml.signal_scorer import TurboCoreSignalScorer
from src.tqqq_turbocore.allocation_optimizer import AllocationOptimizer

import warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.WARNING) # Keep logs quiet during optimization
logger = logging.getLogger("TurboCoreOptimizer")

# Global data cache to avoid recomputing ML predictions for every Optuna trial
GLOBAL_DF = None

def prepare_optimization_data(start_date="2019-01-01", end_date="2025-12-31"):
    print("Preparing base data and ML features for Optuna...")
    pipeline = TurboCoreDataPipeline(tickers=['QQQ', 'TQQQ', 'QLD', 'SGOV', '^VIX'])
    pipeline.fetch_data("10y") 
    raw_df = pipeline.prepare_core_features()
    
    df = raw_df[(raw_df.index >= start_date) & (raw_df.index <= end_date)].copy()
    
    strategy = BaseStrategy(df)
    df = strategy.evaluate()
    
    detector = TurboCoreRegimeDetector()
    try:
        detector.fit(raw_df) 
        df = detector.predict_regimes(df)
    except:
        df['final_regime'] = 'SIDEWAYS'
        
    scorer = TurboCoreSignalScorer()
    try:
        scorer.fit(raw_df) 
        df = scorer.predict_confidence(df)
    except:
        df['ml_confidence'] = 0.5
        
    for ticker in ['QQQ', 'TQQQ', 'QLD', 'SGOV']:
        if ticker == 'QQQ':
            df[f'{ticker}_return'] = df['qqq_close'].pct_change()
        elif ticker == 'TQQQ':
            df[f'{ticker}_return'] = df['tqqq_close'].pct_change()
        elif ticker == 'SGOV': 
            if 'SGOV' in pipeline.data:
                df[f'{ticker}_return'] = pipeline.data['SGOV']['Close'].reindex(df.index).ffill().pct_change().fillna(0.0001) 
            else:
                df[f'{ticker}_return'] = 0.0001
        elif ticker == 'QLD':
            if 'QLD' in pipeline.data:
                df[f'{ticker}_return'] = pipeline.data['QLD']['Close'].reindex(df.index).ffill().pct_change()
            else:
                df[f'{ticker}_return'] = df['qqq_close'].pct_change() * 2
                
    for ticker in ['QQQ', 'TQQQ', 'QLD', 'SGOV']:
        df[f'{ticker}_return'] = df[f'{ticker}_return'].fillna(0)
        
    print(f"Data prepared! Shape: {df.shape}")
    return df

def objective(trial):
    # Setup Hyperparameters 
    
    # 1. Confidence Thresholds
    bull_high_conf_thresh = trial.suggest_float("bull_high_conf_thresh", 0.60, 0.90)
    bull_med_conf_thresh = trial.suggest_float("bull_med_conf_thresh", 0.40, bull_high_conf_thresh - 0.05)
    
    # helper for weight normalizing
    def _normalize(weights):
        total = sum(weights)
        if total == 0: return [0, 0, 0, 1]
        return [w/total for w in weights]
        
    # 2. Bull High Weights (Aggressive)
    bh_q = trial.suggest_int("bh_qqq_w", 0, 50)
    bh_ql = trial.suggest_int("bh_qld_w", 0, 50)
    bh_tq = trial.suggest_int("bh_tqqq_w", 20, 100) # Force some TQQQ exposure here
    bh_s = trial.suggest_int("bh_sgov_w", 0, 10)
    bh_norm = _normalize([bh_q, bh_ql, bh_tq, bh_s])
    
    # 3. Bull Med Weights (Moderate)
    bm_q = trial.suggest_int("bm_qqq_w", 20, 80)
    bm_ql = trial.suggest_int("bm_qld_w", 0, 50)
    bm_tq = trial.suggest_int("bm_tqqq_w", 0, 30)
    bm_s = trial.suggest_int("bm_sgov_w", 0, 20)
    bm_norm = _normalize([bm_q, bm_ql, bm_tq, bm_s])
    
    # 4. Defensive Weights (Sideways / Wait)
    def_q = trial.suggest_int("def_qqq_w", 0, 80)
    def_ql = trial.suggest_int("def_qld_w", 0, 20)
    def_tq = trial.suggest_int("def_tqqq_w", 0, 0) # No TQQQ in defense
    def_s = trial.suggest_int("def_sgov_w", 20, 100)
    def_norm = _normalize([def_q, def_ql, def_tq, def_s])

    params = {
        'bull_high_conf_thresh': bull_high_conf_thresh,
        'bull_med_conf_thresh': bull_med_conf_thresh,
        
        'bh_qqq': bh_norm[0], 'bh_qld': bh_norm[1], 'bh_tqqq': bh_norm[2], 'bh_sgov': bh_norm[3],
        'bm_qqq': bm_norm[0], 'bm_qld': bm_norm[1], 'bm_tqqq': bm_norm[2], 'bm_sgov': bm_norm[3],
        'def_qqq': def_norm[0], 'def_qld': def_norm[1], 'def_tqqq': def_norm[2], 'def_sgov': def_norm[3],
    }
    
    allocator = AllocationOptimizer(params=params)
    
    capital = 25000.0
    current_alloc = {'QQQ': 0.0, 'QLD': 0.0, 'TQQQ': 0.0, 'SGOV': 1.0}
    
    df = GLOBAL_DF
    
    port_vals = []
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        if i > 0:
            daily_port_return = (
                current_alloc['QQQ'] * row['QQQ_return'] +
                current_alloc['QLD'] * row['QLD_return'] +
                current_alloc['TQQQ'] * row['TQQQ_return'] +
                current_alloc['SGOV'] * row['SGOV_return']
            )
            # Subtract 0.005% slip per day for continuous rebalancing simulation
            capital = capital * (1 + daily_port_return - 0.00005) 
            
        port_vals.append(capital)
            
        regime = str(row.get('final_regime', 'SIDEWAYS'))
        base_signal = int(row.get('base_signal', 0))
        confidence = float(row.get('ml_confidence', 0.5))
        
        target_allocation = allocator.get_target_allocation(
            regime=regime,
            signal=base_signal,
            ml_confidence=confidence
        )
        current_alloc = {k: v for k, v in target_allocation.items() if k in current_alloc}
        
    total_return = (capital / 25000.0) - 1
    
    # Penalize extreme drawdowns using a modified Sharpe/Return metric
    port_series = pd.Series(port_vals)
    roll_max = port_series.cummax()
    drawdown = (port_series - roll_max) / roll_max
    max_dd = abs(drawdown.min())
    
    # Score: we want high return, but brutally penalize drawdowns over 35% (QQQ's max DD)
    score = total_return
    if max_dd > 0.35:
        score -= (max_dd - 0.35) * 10  # Steep penalty for exceeding benchmark risk
        
    return score

if __name__ == "__main__":
    GLOBAL_DF = prepare_optimization_data()
    
    print("\nStarting Optuna ML Optimization for TurboCore...")
    study = optuna.create_study(direction="maximize")
    
    # Run 500 trials to find the global maximum within the param space
    study.optimize(objective, n_trials=500, n_jobs=1, show_progress_bar=True)
    
    print("\n" + "="*50)
    print("🏆 OPTIMIZATION COMPLETE 🏆")
    print("="*50)
    print(f"Best Score (Return penalized for risk): {study.best_value:.4f}")
    
    best = study.best_params
    
    # Reconstruct normalized weights to print cleanly
    def _norm(w_list):
        t = sum(w_list)
        return [w/t for w in w_list] if t>0 else [0,0,0,1]
        
    bh = _norm([best['bh_qqq_w'], best['bh_qld_w'], best['bh_tqqq_w'], best['bh_sgov_w']])
    bm = _norm([best['bm_qqq_w'], best['bm_qld_w'], best['bm_tqqq_w'], best['bm_sgov_w']])
    df = _norm([best['def_qqq_w'], best['def_qld_w'], best['def_tqqq_w'], best['def_sgov_w']])
    
    print("\nOptimal Machine Learning Parameters:")
    print(f"Bull High Confidence Thresh: > {best['bull_high_conf_thresh']:.3f} (Wait if below)")
    print(f"Bull Med Confidence Thresh : > {best['bull_med_conf_thresh']:.3f}")
    print("-" * 50)
    print("Optimal Allocation Tiers (QQQ / QLD / TQQQ / SGOV):")
    print(f"Aggressive (High Conf): [{bh[0]:.2f},  {bh[1]:.2f},  {bh[2]:.2f},  {bh[3]:.2f}]")
    print(f"Moderate   (Med Conf) : [{bm[0]:.2f},  {bm[1]:.2f},  {bm[2]:.2f},  {bm[3]:.2f}]")
    print(f"Defensive  (Wait/Side): [{df[0]:.2f},  {df[1]:.2f},  {df[2]:.2f},  {df[3]:.2f}]")
    print("="*50)
