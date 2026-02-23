import logging
import pandas as pd
from typing import Dict, Optional
import os

try:
    import optuna
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False

logger = logging.getLogger(__name__)

class PMCCBayesianOptimizer:
    """
    Uses Optuna TPE (Tree-structured Parzen Estimator) to optimize PMCC parameters:
    - profit_target_pct (0.30-0.70)
    - stop_loss_pct (0.20-0.60)
    - short_call_delta (0.15-0.40)
    - short_dte_max (21-45)
    - leaps_roll_dte (60-120)
    
    Replaces brute force grid search with Bayesian Optimization for 3x+ faster convergence.
    """
    def __init__(self, backtester_class, data_df: pd.DataFrame, n_trials: int = 200):
        self.backtester_class = backtester_class
        self.data_df = data_df
        self.n_trials = n_trials
        
        if not OPTUNA_AVAILABLE:
            logger.warning("Optuna not installed. Cannot run Bayesian Optimization.")
            
    def _objective(self, trial) -> float:
        """
        The objective function to maximize. Runs the backtest with suggested parameters.
        Returns the risk-adjusted return (or total return).
        """
        # 1. Suggest parameters using Bayesian logic
        params = {
            # Existing PMCC parameters
            'profit_target_pct': trial.suggest_float('profit_target_pct', 0.30, 0.70, step=0.05),
            'stop_loss_pct': trial.suggest_float('stop_loss_pct', 0.20, 0.60, step=0.05),
            'short_call_delta': trial.suggest_float('short_call_delta', 0.15, 0.40, step=0.05),
            'short_dte_max': trial.suggest_int('short_dte_max', 21, 45, step=5),
            'leaps_roll_dte': trial.suggest_int('leaps_roll_dte', 60, 120, step=10),
            
            # New Dual-Core Allocation parameters
            'vix_csp_heavy_threshold': trial.suggest_float('vix_csp_heavy_threshold', 20.0, 35.0, step=2.5),
            'vix_pmcc_heavy_threshold': trial.suggest_float('vix_pmcc_heavy_threshold', 12.0, 20.0, step=2.0),
            'vix_defensive_threshold': trial.suggest_float('vix_defensive_threshold', 30.0, 45.0, step=2.5),
            'csp_profit_close_pct': trial.suggest_float('csp_profit_close_pct', 0.40, 0.65, step=0.05),
            'csp_roll_dte': trial.suggest_int('csp_roll_dte', 5, 14, step=3),
            'lstm_confidence_threshold': trial.suggest_float('lstm_confidence_threshold', 0.60, 0.85, step=0.05),
            'ppo_confidence_threshold': trial.suggest_float('ppo_confidence_threshold', 0.55, 0.80, step=0.05),
            'rebalance_cooldown_days': trial.suggest_int('rebalance_cooldown_days', 3, 21, step=3)
        }
        
        # 2. Run the backtest (Mock implementation for integration)
        # Note: Depending on the specific backtester api, this might require instantiation
        # or a run() method. We assume a generic run() that returns a final PnL or metrics dict.
        try:
            backtester_instance = self.backtester_class(self.data_df, **params)
            metrics = backtester_instance.run()
            
            # 3. Calculate objective score. 
            # We want to maximize Total Return, but heavily penalize deep drawdowns.
            total_return = metrics.get('total_return_pct', 0.0)
            max_dd = metrics.get('max_drawdown_pct', 1.0) # 1.0 is 100% loss
            
            if max_dd == 0:
                max_dd = 0.01 # Prevent div/0
                
            # Score formula: Total Return / Max Drawdown (Calmar-esque)
            score = total_return / max_dd
            
            # Optional: Return multiple values for Multi-Objective optimization (return vs drawdown)
            return score
            
        except Exception as e:
            logger.error(f"Backtest trial failed: {e}")
            return -float('inf')  # Penalize failed runs heavily

    def optimize(self) -> Dict[str, float]:
        """
        Run the Optuna optimization study.
        Returns the best parameter dictionary found.
        """
        if not OPTUNA_AVAILABLE:
            logger.error("Optuna is not installed.")
            return {}
            
        logger.info(f"Starting PMCC Bayesian Optimization ({self.n_trials} trials)...")
        
        # TPE is the default sampler in Optuna and works extremely well for trading params
        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
        
        # Run the trials
        try:
            study.optimize(self._objective, n_trials=self.n_trials, n_jobs=1) # n_jobs=-1 for parallel
        except KeyboardInterrupt:
            logger.info("Optimization interrupted by user. Returning best parameters found so far.")
            
        logger.info("Optimization Complete.")
        if len(study.trials) > 0:
            best_params = study.best_params
            best_value = study.best_value
            logger.info(f"Best Target Score: {best_value:.4f}")
            logger.info(f"Best Parameters: {best_params}")
            return best_params
        else:
            logger.warning("No successful trials completed.")
            return {}
