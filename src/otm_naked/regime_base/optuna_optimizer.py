"""
RegimeBase Dynamic Ladder Strategy - Optuna Optimizer
===============================================
Bayesian parameter search for walk-forward windows.
"""
import optuna
import math
import pandas as pd
import logging
import copy

logger = logging.getLogger(__name__)

def run_optuna_optimization(backtest_engine, df_train: pd.DataFrame, n_trials: int = 100) -> dict:
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    def objective(trial):
        dte          = trial.suggest_categorical("dte_target", [14, 21, 30])
        delta        = trial.suggest_categorical("initial_delta", [0.20, 0.25, 0.30, 0.35])
        delta_trend  = trial.suggest_categorical("delta_trending", [0.20, 0.25, 0.30])
        profit_pct   = trial.suggest_categorical("profit_take_pct", [0.30, 0.40, 0.50])
        profit_short = trial.suggest_categorical("profit_take_pct_short", [0.20, 0.25, 0.30])
        sl_mult      = trial.suggest_categorical("stop_loss_credit_mult", [3.0, 4.0, 5.0])  # Higher stops for volatile stocks
        trigger_pct  = trial.suggest_categorical("entry_trigger_pct", [0.5, 1.0])
        ivr_min      = trial.suggest_categorical("ivr_min", [0, 10])
        
        # Override config temporarily
        old_config = copy.deepcopy(backtest_engine.config)
        backtest_engine.config.dte_target = dte
        backtest_engine.config.initial_delta = delta
        backtest_engine.config.delta_trending = delta_trend
        backtest_engine.config.profit_take_pct = profit_pct
        backtest_engine.config.profit_take_pct_short = profit_short
        backtest_engine.config.stop_loss_credit_mult = sl_mult
        backtest_engine.config.entry_trigger_pct = trigger_pct
        backtest_engine.config.ivr_min = ivr_min
        
        # Run simulation without ML for Optuna
        pnls = backtest_engine.simulate_strategy(df_train, use_ml=False)
        
        # Restore config
        backtest_engine.config = old_config
        
        if len(pnls) < 5:
            return -999.0
            
        returns = pd.Series(pnls)
        sharpe = returns.mean() / (returns.std() + 1e-9) * math.sqrt(252) if returns.std() > 0 else -999.0
        return float(sharpe)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    
    logger.info(f"Optuna Best Params: {study.best_params} | Sharpe: {study.best_value:.3f}")
    return study.best_params
