# direct_deploy_v2.ps1
# Direct deployment script v2 - pushes specific fixes to the 3/6 signal pipeline issues
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "🚀 Pushing backend fixes to EC2 ($HOST)..."

# 1. Copy Files
Write-Host ">> [1/4] Copying API logic..."
scp -i $PEM -o StrictHostKeyChecking=no tasty_api_server.py ubuntu@${HOST}:~/tastywork-trading/tasty_api_server.py

Write-Host ">> [2/4] Copying Tastytrade client..."
scp -i $PEM -o StrictHostKeyChecking=no tastytrade_client.py ubuntu@${HOST}:~/tastywork-trading/tastytrade_client.py

Write-Host ">> [3/4] Copying TurboCore executor..."
scp -i $PEM -o StrictHostKeyChecking=no src/tqqq_turbocore/executor.py ubuntu@${HOST}:~/tastywork-trading/src/tqqq_turbocore/executor.py

# 2. Restart Services
Write-Host ">> [4/4] Restarting API services..."
$RESTART = @'
sudo systemctl restart tastytrade_api
echo "tastytrade_api restarted."
systemctl is-active tastytrade_api
'@
$B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($RESTART.Replace("`r", "")))
ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64 | base64 -d | bash"

Write-Host "`n✅ Backend fixes deployed!"
Write-Host "👉 ACTION REQUIRED: Redeploy the frontend on Vercel to see the changes."
