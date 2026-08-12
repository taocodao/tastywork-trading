import subprocess, sys

KEY = r"D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
IPS = ["34.203.194.137", "54.89.159.18", "34.235.119.76"]

CMD = """
echo '=== HOME ==='
ls ~
echo '=== DIR CHECK ==='
[ -d ~/tastywork-trading-1 ] && echo 'FOUND: tastywork-trading-1' || echo 'MISSING: tastywork-trading-1'
[ -d ~/tastywork-trading ] && echo 'FOUND: tastywork-trading' || echo 'MISSING: tastywork-trading'
echo '=== GIT LOG ==='
(cd ~/tastywork-trading-1 2>/dev/null || cd ~/tastywork-trading 2>/dev/null) && git log --oneline -5
echo '=== TQQQ FILES ==='
ls -la ~/tastywork-trading-1/tqqq_status.json ~/tastywork-trading-1/tqqq_signals.json 2>&1
ls -la ~/tastywork-trading/tqqq_status.json ~/tastywork-trading/tqqq_signals.json 2>&1
echo '=== SCHEDULER CHECK ==='
grep -n '_persist_status\|_persist_signal' ~/tastywork-trading-1/run_tqqq_scheduler.py 2>/dev/null | head -5
echo '=== SERVICES ==='
sudo systemctl is-active trademind-api tqqq-scheduler 2>&1
echo '=== API PORT ==='
curl -s http://localhost:8002/api/tqqq/status 2>&1 || echo 'API not reachable'
"""

for ip in IPS:
    print(f"\nTrying {ip}...")
    r = subprocess.run(
        ["ssh", "-i", KEY, "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=no",
         f"ubuntu@{ip}", CMD],
        capture_output=True, text=True, timeout=30
    )
    print(f"EXIT CODE: {r.returncode}")
    output = r.stdout.strip()
    err = r.stderr.strip()
    if output:
        print("STDOUT:\n", output)
        break
    if err:
        print("STDERR:\n", err)
print("\nDone.")
