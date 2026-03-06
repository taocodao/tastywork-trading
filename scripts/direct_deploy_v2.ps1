# direct_deploy_v2.ps1
# Direct deployment script v2 - pushes specific fixes to the 3/6 signal pipeline issues
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "🚀 Pushing backend fixes to EC2 ($HOST)..."

# 1. Copy Files
Write-Host ">> [1/3] Copying API logic..."
scp -i $PEM -o StrictHostKeyChecking=no api/routes/signals.py ubuntu@$HOST:~/tastywork-trading/api/routes/signals.py

Write-Host ">> [2/3] Copying Turbobounce publisher..."
scp -i $PEM -o StrictHostKeyChecking=no signal_publisher/turbobounce.py ubuntu@$HOST:~/tastywork-trading/signal_publisher/turbobounce.py

# 2. Restart Services
Write-Host ">> [3/3] Restarting API services..."
$RESTART = @'
sudo systemctl restart trademind-api
echo "trademind-api restarted."
systemctl is-active trademind-api
'@
$B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($RESTART.Replace("`r", "")))
ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64 | base64 -d | bash"

Write-Host "`n✅ Backend fixes deployed!"
Write-Host "👉 ACTION REQUIRED: Redeploy the frontend on Vercel to see the changes."
