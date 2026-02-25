"""
Parameter Optimizer
===================
Uses Differential Evolution to find optimal strategy parameters.
Reuses the optimizer pattern established in the existing vertical spread backtest.

Runtime estimate (per regime):
  popsize=10, maxiter=10  =>  ~80 backtests   ~2.5 min  (quick scan)
  popsize=10, maxiter=20  =>  ~160 backtests  ~5 min
  popsize=15, maxiter=30  =>  ~450 backtests  ~15 min   (full production)
"""

import scipy.optimize as opt
import numpy as np
import logging
import json
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ParamOptimizer:
    def __init__(self, backtest_engine):
        self.engine = backtest_engine
        
    def optimize(
        self,
        regime: str,
        start_date: str,
        end_date: str,
        maxiter: int = 10,
        popsize: int = 10,
        checkpoint_dir: str = "data"
    ) -> Dict[str, Any]:
        """
        Run SCIPY differential evolution.

        The optimizer writes a checkpoint JSON file after each generation,
        so you can safely stop and inspect partial results.

        Params bounded for sensible diagonal construction:
        0: anchor_dte        (30-75)
        1: anchor_delta      (-0.30 to -0.12)
        2: hedge_dte         (7-21)
        3: hedge_delta       (-0.18 to -0.05)
        4: profit_target     (0.30 to 0.70)
        5: stop_loss_mult    (1.0 to 3.5)
        6: hedge_close_decay (0.30 to 0.70)
        7: max_naked_hours   (12-72)
        """
        bounds = [
            (30, 75),       # 0: anchor_dte
            (-0.30, -0.12), # 1: anchor_delta
            (7, 21),        # 2: hedge_dte
            (-0.18, -0.05), # 3: hedge_delta
            (0.30, 0.70),   # 4: profit target
            (1.0, 3.5),     # 5: stop loss
            (0.30, 0.70),   # 6: hedge_close_decay_pct
            (12, 72),       # 7: max_naked_hours
        ]
        
        os.makedirs(checkpoint_dir, exist_ok=True)
        checkpoint_path = os.path.join(checkpoint_dir, f"optimized_params_{regime}.json")
        
        # Track best seen across all evaluations
        best_seen = {'score': -999.0, 'params': None}
        generation_count = [0]

        def objective(x):
            test_config = {
                'anchor_dte': int(x[0]),
                'anchor_delta': float(x[1]),
                'hedge_dte': int(x[2]),
                'hedge_delta': float(x[3]),
                'anchor_profit_target_pct': float(x[4]),
                'anchor_stop_loss_mult': float(x[5]),
                'hedge_close_decay_pct': float(x[6]),
                'max_naked_hours': int(x[7]),
                # static defaults
                'max_cycles': 4,
                'vix_spike_close': 3.0,
            }
            
            metrics = self.engine.run_scenario(test_config, start_date, end_date, regime_filter=regime)
            
            sharpe = metrics.get('sharpe', 0.0)
            ret = metrics.get('total_return', 0.0)
            mdd = metrics.get('max_drawdown', 0.0)
            
            # Composite objective: weighted Sharpe + Return
            score = (0.6 * sharpe) + (0.4 * ret)
            
            # Harsh penalty for excessive drawdown
            if mdd > 0.05: 
                score -= (mdd - 0.05) * 20
                
            # Track best & checkpoint immediately
            if score > best_seen['score']:
                best_seen['score'] = score
                best_seen['params'] = _params_from_x(x)
                # Write to disk so it survives early termination
                with open(checkpoint_path, 'w') as f:
                    json.dump({
                        **best_seen['params'],
                        '_sharpe': round(sharpe, 3),
                        '_return': round(ret, 4),
                        '_max_drawdown': round(mdd, 4),
                        '_score': round(score, 4),
                    }, f, indent=2)
                logger.info(
                    f"  [CHECKPOINT] {regime} score={score:.3f}  "
                    f"sharpe={sharpe:.2f}  ret={ret:.1%}  mdd={mdd:.1%}  "
                    f"(saved to {checkpoint_path})"
                )
                
            return -score

        def callback(xk, convergence=None):
            generation_count[0] += 1
            logger.info(f"  [{regime}] Generation {generation_count[0]}/{maxiter} complete. Convergence: {convergence:.4f}")
            
        def _params_from_x(x) -> Dict[str, Any]:
            return {
                'anchor_dte': int(x[0]),
                'anchor_delta': round(float(x[1]), 3),
                'hedge_dte': int(x[2]),
                'hedge_delta': round(float(x[3]), 3),
                'anchor_profit_target_pct': round(float(x[4]), 2),
                'anchor_stop_loss_mult': round(float(x[5]), 2),
                'hedge_close_decay_pct': round(float(x[6]), 2),
                'max_naked_hours': int(x[7]),
            }
            
        logger.info(
            f"Starting DE optimization for {regime}  "
            f"(maxiter={maxiter}, popsize={popsize}, ~{maxiter*popsize*8} backtests)..."
        )
        
        try:
            res = opt.differential_evolution(
                objective,
                bounds,
                strategy='best1bin',
                maxiter=maxiter,
                popsize=popsize,
                tol=0.01,
                mutation=(0.5, 1.0),
                recombination=0.7,
                seed=42,
                disp=False,
                callback=callback,
            )
            # Return the DE best (should match checkpoint)
            return _params_from_x(res.x)
            
        except KeyboardInterrupt:
            logger.warning(f"Optimization interrupted. Best result saved to: {checkpoint_path}")
            # Return whatever partial best we have
            if best_seen['params']:
                return best_seen['params']
            raise
