import subprocess
import random
import re

# Our dataset reliably starts feature building around 2016-2017, so valid testing years are 2018-2025.
valid_years = list(range(2018, 2026))
selected_years = random.sample(valid_years, 4)
selected_years.sort()

print(f"Randomly selected years for independent backtests: {selected_years}\n")

print(f"{'Year':<6} | {'CAGR (%)':<10} | {'Max DD (%)':<12} | {'Trades':<8} | {'Win Rate (%)':<12}")
print("-" * 55)

for year in selected_years:
    cmd = f"python backtest_otm_naked.py --start {year}-01-01 --end {year}-12-31 --capital 50000 --no-ml"
    try:
        out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode('utf-8', errors='ignore')
        
        cagr_m = re.search(r"CAGR\s*:\s*([-\d\.]+)%", out)
        dd_m = re.search(r"Max Drawdown\s*:\s*([-\d\.]+)%", out)
        trades_m = re.search(r"Total Trades\s*:\s*(\d+)", out)
        win_m = re.search(r"Win Rate\s*:\s*([-\d\.]+)%", out)
        
        cagr = cagr_m.group(1) if cagr_m else "N/A"
        dd = dd_m.group(1) if dd_m else "N/A"
        trades = trades_m.group(1) if trades_m else "N/A"
        win = win_m.group(1) if win_m else "N/A"
        
        print(f"{year:<6} | {cagr:>10} | {dd:>12} | {trades:>8} | {win:>12}")
    except Exception as e:
        print(f"{year:<6} | Error: {e}")
