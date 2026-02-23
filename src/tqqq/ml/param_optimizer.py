"""
Bayesian Strategy Parameter Optimizer
=====================================
Uses scikit-optimize (Gaussian Processes) to find the optimal
TQQQ spread parameters per VIX regime (LOW_VOL, NORMAL, HIGH_VOL, CRISIS).

Optimizes:
- target_dte (14 to 60)
- short_put_delta (-0.40 to -0.15)
- spread_width (3 to 10)
- profit_target (30% to 80%)
- loss_limit_mult (1.0x to 3.0x)
- legout_short_threshold (5% to 30%)
- long_put_profit_target (1.5x to 4.0x)
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Protect against missing scikit-optimize in prod env
try:
    from skopt import gp_minimize
    from skopt.space import Real, Integer
    from skopt.utils import use_named_args
    SKOPT_AVAILABLE = True
except ImportError:
    logger.warning("scikit-optimize not installed. Bayesian Optimizer will return dummy params.")
    gp_minimize = None
    Real = Integer = use_named_args = None
    SKOPT_AVAILABLE = False


class StrategyParamOptimizer:
    """
    Runs Bayesian Optimization to tune strategy parameters for max Sharpe ratio.
    Called externally (e.g. monthly cron job).
    """
    
    def __init__(self, objective_backtest_fn=None):
        """
        `objective_backtest_fn` must be a callable:
            def backtest_eval(params_dict, regime: str) -> float (Sharpe Ratio)
        """
        self.objective_fn = objective_backtest_fn
        
        if SKOPT_AVAILABLE:
            self.search_space = [
                Integer(14, 60, name='target_dte'),
                Real(-0.40, -0.15, name='short_put_delta'),
                Integer(3, 10, name='spread_width'),
                Real(0.30, 0.80, name='profit_target'),
                Real(1.0, 3.0, name='loss_limit_mult'),
                Real(0.05, 0.30, name='legout_short_threshold'),
                Real(1.5, 4.0, name='long_put_profit_target')
            ]

    def optimize_all_regimes(self, n_calls: int = 50) -> Dict[str, Dict[str, Any]]:
        """
        Runs gp_minimize on all 4 regimes. Returns nested dict of optimal params.
        """
        regimes = ["LOW_VOL", "NORMAL", "HIGH_VOL", "CRISIS"]
        optimal_params = {}

        if not SKOPT_AVAILABLE or not self.objective_fn:
            logger.error("Cannot run Bayesian Optimization (missing library or objective_fn).")
            # Return plausible defaults
            return {
                "LOW_VOL":  {"dte": 35, "delta": -0.25, "width": 3, "profit_target": 0.60, "loss_limit_mult": 2.0, "legout_short_threshold": 0.15, "long_put_profit_target": 2.0},
                "NORMAL":   {"dte": 30, "delta": -0.30, "width": 5, "profit_target": 0.50, "loss_limit_mult": 2.0, "legout_short_threshold": 0.15, "long_put_profit_target": 2.0},
                "HIGH_VOL": {"dte": 21, "delta": -0.35, "width": 5, "profit_target": 0.40, "loss_limit_mult": 2.0, "legout_short_threshold": 0.20, "long_put_profit_target": 2.5},
                "CRISIS":   {"dte": 14, "delta": -0.20, "width": 3, "profit_target": 0.75, "loss_limit_mult": 3.0, "legout_short_threshold": 0.10, "long_put_profit_target": 3.0},
            }

        for regime in regimes:
            logger.info(f"Starting BO tuning for regime: {regime} ({n_calls} calls)")
            
            @use_named_args(self.search_space)
            def _objective(**params):
                # gp_minimize minimizes the objective, so we return negative Sharpe
                sharpe = self.objective_fn(params, regime)
                return -sharpe
                
            res = gp_minimize(_objective, self.search_space, n_calls=n_calls, random_state=42)
            
            best = res.x
            optimal_params[regime] = {
                "dte": int(best[0]),
                "delta": float(best[1]),
                "width": int(best[2]),
                "profit_target": float(best[3]),
                "loss_limit_mult": float(best[4]),
                "legout_short_threshold": float(best[5]),
                "long_put_profit_target": float(best[6]),
            }
            logger.info(f"Optimal {regime}: {optimal_params[regime]}")

        return optimal_params
