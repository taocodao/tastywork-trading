# Direct deployment script - bypasses GitHub
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "Deploying signal_publisher.py directly to EC2..."

# Copy updated file  
scp -i $PEM -o StrictHostKeyChecking=no signal_publisher.py ubuntu@$HOST:~/tastywork-trading/

# Restart scanner
$RESTART = @'
cd ~/tastywork-trading
echo "=== Restarting Scanner ==="
sudo systemctl restart trademind-scanner
sleep 8
echo ""
echo "=== Scanner Status ==="
systemctl status trademind-scanner --no-pager -n 0
echo ""
echo "=== Recent Scanner Logs ==="
journalctl -u trademind-scanner -n 50 --no-pager
'@

$B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($RESTART.Replace("`r", "")))
ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64 | base64 -d | bash"
