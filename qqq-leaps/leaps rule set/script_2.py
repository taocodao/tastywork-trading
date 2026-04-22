
# Quick smoke test with the synthetic data
import subprocess
result = subprocess.run(["python3", "/root/qqq_pmcc_backtest_v2.py"], 
                        capture_output=True, text=True, timeout=120)
print("STDOUT:", result.stdout[-3000:] if result.stdout else "")
print("STDERR:", result.stderr[-2000:] if result.stderr else "")
