import sys, os, json
import numpy as np
from scipy.optimize import differential_evolution
import warnings
warnings.filterwarnings('ignore')

# Add parent directory to path to import backtest script
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from tqqq_multithreshold_backtest import run_3layer_simulation
except ImportError as e:
    print(f"Error importing backtest: {e}")
    sys.exit(1)

RISK_PROFILES = {
    "Low":    {"w_sharpe": 60.0, "w_totr": 0.5, "w_mdd": 4.0},
    "Medium": {"w_sharpe": 50.0, "w_totr": 1.0, "w_mdd": 2.0},
    "High":   {"w_sharpe": 30.0, "w_totr": 2.0, "w_mdd": 1.0}
}

def fitness(params, tranche_name, risk_level):
    """
    params = [anchor_dte, hedge_dte, anchor_k_pct, hedge_k_pct, exit_rsi, time_stop]
    """
    swing_params = {
        "anchor_dte": int(round(params[0])),
        "hedge_dte": int(round(params[1])),
        "anchor_k_pct": float(params[2]),
        "hedge_k_pct": float(params[3]),
        "exit_rsi": float(params[4]),
        "time_stop": int(round(params[5]))
    }
    
    # Enforce logical constraints to narrow search space
    if swing_params["anchor_dte"] <= swing_params["hedge_dte"]:
        return 99999.0  # Calendars not allowed, heavily penalize
        
    metrics = run_3layer_simulation(optimize_tranche=tranche_name, optimize_params=swing_params, return_metrics=True)
    
    sharpe = metrics["sharpe"]
    totr = metrics["totr"]
    mdd = abs(metrics["mdd"])
    swing_trades = len(metrics["trades"])
    
    # Minimum trade count
    if swing_trades < 10 or sharpe <= 0:
        return 99999.0
        
    prof = RISK_PROFILES[risk_level]
    score = (prof["w_sharpe"] * sharpe) + (prof["w_totr"] * totr) - (prof["w_mdd"] * mdd)
    
    # Invert to minimize
    return -score

def optimize():
    print("Starting Multi-Tier differential Evolution Optimization (Low/Medium/High Risk)...")
    
    tranches = ["Deep", "Mod", "Light"]
    risk_levels = ["Low", "Medium", "High"]
    
    bounds = [   
        (25, 60),      # anchor_dte
        (5, 25),       # hedge_dte 
        (0.00, 0.08),  # anchor_k_pct 
        (0.02, 0.15),  # hedge_k_pct 
        (55, 80),      # exit_rsi 
        (5, 20)        # time_stop
    ]
    
    final_params = {rl: {} for rl in risk_levels}
    out_path = os.path.join(os.path.dirname(__file__), "optimized_swing_params.json")
    
    for rl in risk_levels:
        print(f"\n========================================================")
        print(f"  Starting Risk Level: {rl.upper()}")
        print(f"  Weights: Sharpe={RISK_PROFILES[rl]['w_sharpe']}x, Return={RISK_PROFILES[rl]['w_totr']}x, MDD=-{RISK_PROFILES[rl]['w_mdd']}x")
        print(f"========================================================")
        
        for tr in tranches:
            print(f"\n  --- Optimizing Tranche: {tr} ---")
            
            # Reduce maxiter to 10 for faster full-grid solving (~10 min total)
            result = differential_evolution(
                fitness, bounds, args=(tr, rl), strategy='best1bin', 
                maxiter=10, popsize=5, mutation=(0.5, 1.0), 
                recombination=0.7, seed=42, disp=True, workers=-1
            )
            
            p = result.x
            params_dict = {
                "anchor_dte": int(round(p[0])),
                "hedge_dte": int(round(p[1])),
                "anchor_k_pct": round(float(p[2]), 3),
                "hedge_k_pct": round(float(p[3]), 3),
                "exit_rsi": round(float(p[4]), 1),
                "time_stop": int(round(p[5]))
            }
            final_params[rl][tr] = params_dict
            
            print(f">>> Best Fitness Score: {-result.fun:.2f}")
            print(f">>> Parameters: {params_dict}")
            
            # Save progressively
            with open(out_path, "w") as f:
                json.dump(final_params, f, indent=4)

    print(f"\nOptimization Complete! Saved 9x multi-tier parameters to: {out_path}")

if __name__ == "__main__":
    optimize()
