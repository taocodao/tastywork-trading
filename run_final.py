from src.zebra.backtest_engine import ZebraBacktestEngine
import sys

# Log to terminal
def file_log(msg):
    print(str(msg))

engine = ZebraBacktestEngine(verbose=True)
engine.log = file_log

engine.fetch_data(["SPY", "QQQ", "IWM", "AAPL", "NVDA", "TSLA", "AMD", "MSFT", "AMZN", "META", "GOOGL"], start_date="2023-01-01")

print("\nSimulation started...")
res = engine.run_simulation({
    'profit_target_pct': 0.50,  # Restore baseline profit target
    'stop_loss_pct': -0.35,      # Restore baseline stop loss
    'min_score': 35,             # Restore baseline selectivity
    'min_dte_threshold': 21,     # Moderate DTE avoidance
    'stagnation_days': 30        # Standard time exit
}, simulation_start_date="2024-01-01")

print("\n" + "="*30)
print("=== FINAL RESULTS ===")
print("="*30)
print(f"P&L: ${res['pnl']:.2f}")
print(f"Win Rate: {res.get('win_rate', 0):.1%}")
print(f"Trades: {res.get('trades', 0)}")
print(f"Sharpe: {res.get('sharpe', 0):.2f}")
print("="*30)
