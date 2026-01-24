# Verify patch was applied and check for errors
$PEM = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST = "34.235.119.67"

Write-Host "Checking if patch was applied..."

$CMD = @'
cd ~/tastywork-trading

echo "=== Check if init_db is imported ==="
grep "from src.earnings_intelligence.database import.*init_db" signal_publisher.py

echo ""
echo "=== Check if init_db() is called ==="
grep -A 2 "def save_signal_to_db" signal_publisher.py | head -20

echo ""
echo "=== Run scanner and capture output ==="
timeout 30 python3 scheduled_scanner.py 2>&1 | grep -E "(Signal|saved|Failed|Error)" | tail -50
'@

$B64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($CMD.Replace("`r", "")))
$output = ssh -i $PEM -o StrictHostKeyChecking=no ubuntu@$HOST "echo $B64 | base64 -d | bash" 2>&1
Write-Output $output
