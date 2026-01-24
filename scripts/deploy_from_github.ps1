# Pull latest code from GitHub and restart scanner
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "Pulling latest code from GitHub and restarting services..."

$CMD = @'
cd ~/tastywork-trading
echo "=== Git Pull ==="
git pull

echo ""
echo "=== Restarting Scanner ==="
sudo systemctl restart trademind-scanner

echo ""
echo "Waiting 10 seconds..."
sleep 10

echo ""
echo "=== Scanner Status ==="
systemctl status trademind-scanner --no-pager -n 0

echo ""
echo "=== Recent Scanner Logs ==="
journalctl -u trademind-scanner -n 40 --no-pager | grep -E "(Signal|saved|DB|Failed|Error)" | tail -20
'@

$B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($CMD.Replace("`r", "")))
ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64 | base64 -d | bash" 2>&1 | Out-Host

Write-Host "`n✅ Done! The fix is now deployed from GitHub."
Write-Host "Wait 30 seconds for scanner to run, then test signal approval."
