# Quick redeploy script - pulls latest code and restarts scanner
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

$CMD = @'
cd ~/tastywork-trading
echo "=== Git Pull ==="
git pull 2>&1
echo ""
echo "=== Restart Scanner ==="
sudo systemctl restart trademind-scanner.service
echo ""  
echo "=== Scanner Logs ==="
sleep 5
journalctl -u trademind-scanner -n 30 --no-pager 2>&1
'@

$B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($CMD.Replace("`r", "")))
ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64 | base64 -d | bash"
