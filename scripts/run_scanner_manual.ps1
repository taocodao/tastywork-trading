# Manually run scanner and check output
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "Manually running scanner..."

$CMD = @'
cd ~/tastywork-trading
echo "=== Running Scanner Manually ==="
python3 scheduled_scanner.py 2>&1 | tail -100
'@

$B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($CMD.Replace("`r", "")))
ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64 | base64 -d | bash"
