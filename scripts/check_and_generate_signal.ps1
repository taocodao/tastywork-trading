# Generate Test Signal
$ErrorActionPreference = "Stop"

$PEM_FILE = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST_IP = "34.235.119.67"

Write-Host "🔍 Checking scanner status and generating signal..."

# Check if scanner service is running
Write-Host "`n1. Checking scanner service..."
ssh -i $PEM_FILE ubuntu@$HOST_IP 'sudo systemctl status trademind-scanner --no-pager'

# Check IB Gateway
Write-Host "`n2. Checking IB Gateway..."
ssh -i $PEM_FILE ubuntu@$HOST_IP 'docker ps | grep ib-gateway'

# Check database
Write-Host "`n3. Checking existing signals..."
ssh -i $PEM_FILE ubuntu@$HOST_IP 'cd ~/tastywork-trading; sqlite3 earnings_intelligence.db "SELECT COUNT(*) FROM signals;"'

# Run scanner manually (force flag to run outside market hours)
Write-Host "`n4. Running scanner manually..."
ssh -i $PEM_FILE ubuntu@$HOST_IP 'cd ~/tastywork-trading; python3 scheduled_scanner.py --force'

# Check if signal was created
Write-Host "`n5. Checking for new signals..."
ssh -i $PEM_FILE ubuntu@$HOST_IP 'cd ~/tastywork-trading; sqlite3 earnings_intelligence.db "SELECT id, symbol, strategy, status, created_at FROM signals ORDER BY created_at DESC LIMIT 3;"'

Write-Host "`n✅ Signal generation check complete!"
