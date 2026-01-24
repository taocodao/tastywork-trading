# Patch signal_publisher.py directly on EC2
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "Patching signal_publisher.py on EC2..."

$PATCH = @'
cd ~/tastywork-trading

# Create backup
cp signal_publisher.py signal_publisher.py.bak

# Patch the file: add init_db import and call
sed -i's/from src\.earnings_intelligence\.database import SignalRepository, Signal$/from src.earnings_intelligence.database import SignalRepository, Signal, init_db/' signal_publisher.py

# Add init_db() call after repo = SignalRepository()
sed -i '/repo = SignalRepository()/a\        \n        # Ensure database tables exist\n        init_db()' signal_publisher.py

# Add better error logging
sed -i 's/logger\.error(f"Failed to save signal to DB: {e}")/import traceback\n        logger.error(f"❌ Failed to save signal to DB: {e}")\n        logger.error(traceback.format_exc())/' signal_publisher.py

echo "=== Patch Applied ===" 
echo ""
echo "=== Restarting Scanner ==="
sudo systemctl restart trademind-scanner
sleep 8

echo ""
echo "=== Scanner Logs (last 30 lines) ==="
journalctl -u trademind-scanner -n 30 --no-pager
'@

$B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($PATCH.Replace("`r", "")))
ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64 | base64 -d | bash"

Write-Host "`nDone!"
