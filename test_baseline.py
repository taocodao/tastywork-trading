import sys
sys.stdout = open('comparison_results.txt', 'w', buffering=1)

from src.zebra.backtest import ZebraBacktester

print("="*60)
print("BASELINE BACKTEST (Original Simple Logic)")
print("="*60)

tester = ZebraBacktester()
tester.run(["SPY", "NVDA", "IWM", "TSLA", "AMD"], start_date="2024-01-01")

print("\n" + "="*60)
print("Test Complete")
print("="*60)

sys.stdout.close()
