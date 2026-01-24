# Check signal database status
$PEM_FILE = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST_IP = "34.235.119.67"
$USER = "ubuntu"

# Script to run on server
$SCRIPT = @'
#!/bin/bash
echo "=== Database Files ==="
find /home/ubuntu -name "*.db" -type f 2>/dev/null

echo ""
echo "=== Scanner Logs (last 15 lines) ==="
journalctl -u trademind-scanner -n 15 --no-pager 2>&1 | tail -15

echo ""
echo "=== API Server Logs (last 15 lines) ==="  
journalctl -u trademind-api -n 15 --no-pager 2>&1 | tail -15

echo ""
echo "=== Check Signals in DB ==="
cd /home/ubuntu/tastywork-trading
python3 -c "
from src.earnings_intelligence.database import SignalRepository
repo = SignalRepository()
signals = repo.get_pending_signals()
print(f'Pending signals in DB: {len(signals)}')
for s in signals[:3]:
    print(f'  {s.id[:8]}... {s.symbol} {s.status}')
" 2>&1
'@

# Write script, execute, capture output
$B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($SCRIPT.Replace("`r", "")))
$CMD = "echo $B64 | base64 -d | bash"

Write-Host "Running diagnostic..."
ssh -i $PEM_FILE -o StrictHostKeyChecking=no $USER@$HOST_IP $CMD
