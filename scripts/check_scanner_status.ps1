# Check scanner status and logs
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "Checking scanner status..."

$CMD = @'
echo "=== Scanner Service Status ==="
systemctl status trademind-scanner.service --no-pager -n 0
echo ""
echo "=== Scanner Timer Status ==="
systemctl status trademind-scanner.timer --no-pager -n 0
echo ""
echo "=== Last Scanner Run (50 lines) ==="
journalctl -u trademind-scanner -n 50 --no-pager
echo ""
echo "=== Check if DB has signals ==="
cd ~/tastywork-trading
python3 << 'PYEOF'
from src.earnings_intelligence.database import SignalRepository
repo = SignalRepository()
signals = repo.get_pending_signals()
print(f"Pending signals in DB: {len(signals)}")
if len(signals) > 0:
    for s in signals[:5]:
        print(f"  {s.id[:8]}... {s.symbol} {s.status}")
PYEOF
'@

$B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($CMD.Replace("`r", "")))
ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64 | base64 -d | bash"
