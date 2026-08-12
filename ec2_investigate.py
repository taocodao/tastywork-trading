"""Simplified EC2 investigation - writes all output to a single file."""
import subprocess, os

KEY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tradecoin-bot-key.pem")
HOST = "ubuntu@34.203.194.137"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ec2_diag.txt")

def ssh(cmd):
    try:
        r = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
             "-i", KEY, HOST, cmd],
            capture_output=True, text=True, timeout=30
        )
        return f"STDOUT: {r.stdout.strip()}\nSTDERR: {r.stderr.strip()}\nRC: {r.returncode}"
    except subprocess.TimeoutExpired:
        return "TIMEOUT (30s)"
    except Exception as e:
        return f"ERROR: {e}"

checks = [
    ("Service Status", "sudo systemctl is-active trademind-api; sudo systemctl is-active trademind-ws"),
    ("Port Listeners", "sudo ss -tlnp | grep -E '800[234]'"),
    ("API Logs", "sudo journalctl -u trademind-api --no-pager -n 30"),
    ("WS Logs", "sudo journalctl -u trademind-ws --no-pager -n 10"),
    ("Health Check", "curl -s -m 3 http://localhost:8002/health || echo CURL_FAILED"),
    ("httpx installed", "python3 -c 'import httpx; print(httpx.__version__)'"),
    ("Config google check", "grep -n 'GOOGLE_CLOUD_PROJECT' /home/ubuntu/tastywork-trading/config.py"),
    ("Server import test", "cd /home/ubuntu/tastywork-trading && timeout 10 python3 -c 'from tasty_api_server import TastyHandler; print(\"IMPORT_OK\")' 2>&1"),
]

lines = []
for name, cmd in checks:
    lines.append(f"=== {name} ===")
    lines.append(ssh(cmd))
    lines.append("")

with open(OUT, "w") as f:
    f.write("\n".join(lines))

print(f"Done. Wrote to {OUT}")
