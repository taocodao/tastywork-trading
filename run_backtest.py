from src.zebra.backtest_engine import ZebraBacktestEngine
from src.zebra.ml_optimizer import ZebraMLOptimizer
import sys

# Flush output
sys.stdout.reconfigure(line_buffering=True)

print("Starting Enhanced ZEBRA Backtest...")

engine = ZebraBacktestEngine(verbose=True)
engine.fetch_data(["SPY", "NVDA", "IWM", "TSLA", "AMD"], start_date="2024-01-01")

# Baseline Run (Default params)
print("\n--- Running Baseline Simulation (Default Params) ---")
res = engine.run_simulation({
    'profit_target_pct': 0.50, 
    'stop_loss_pct': -0.40,
    'time_exit_days': 30,
    'min_score': 60
})

print(f"Baseline Result: P&L ${res['pnl']:.2f}, Win Rate {res.get('win_rate', 0):.1%}, Sharpe {res.get('sharpe', 0):.2f}")

# Optimized Run (Run optimizer then backtest)
print("\n--- Running ML Optimization ---")
optimizer = ZebraMLOptimizer(["SPY", "NVDA", "IWM", "TSLA", "AMD"], start_date="2024-01-01")
best_params = optimizer.run_optimization(n_calls=20)

if best_params:
    print("\n--- Running Optimized Simulation ---")
    opt_res = engine.run_simulation(best_params)
    print(f"Optimized Result: P&L ${opt_res['pnl']:.2f}, Win Rate {opt_res.get('win_rate', 0):.1%}, Sharpe {opt_res.get('sharpe', 0):.2f}")
    
    print("\n improvement:")
    pnl_imp = opt_res['pnl'] - res['pnl']
    print(f"P&L Improvement: ${pnl_imp:.2f}")
    win_imp = (opt_res['win_rate'] - res['win_rate']) * 100
    print(f"Win Rate Improvement: +{win_imp:.1f}%")
else:
    print("Optimization failed or skipped.")
