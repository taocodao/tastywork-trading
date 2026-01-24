# debug_ib_gateway.ps1
$ErrorActionPreference = "Stop"

$PEM_FILE = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST_IP = "34.235.119.67"
$USER = "ubuntu"

Write-Host "🔍 Debugging IB Gateway Service on $HOST_IP..."

$RAW_BASH = @'
echo "=== 1. CHECKING DOCKER COMPOSE ==="
which docker-compose
docker-compose --version || echo "docker-compose not found in path"

echo "=== 2. CHECKING IB DIRECTORY ==="
ls -F /home/ubuntu/IB-program-trading/

echo "=== 3. CHECKING SERVICE STATUS ==="
sudo systemctl status ib-gateway.service --no-pager -l

echo "=== 4. CHECKING LOGS ==="
sudo journalctl -u ib-gateway.service --no-pager -n 20

echo "=== 5. CHECKING DOCKER CONTAINERS ==="
docker ps -a | grep ib
'@

# Convert to Base64 (UTF8) to survive SSH CRLF issues
$BASH_CLEAN = $RAW_BASH.Replace("`r", "")
$BYTES = [System.Text.Encoding]::UTF8.GetBytes($BASH_CLEAN)
$B64_CMD = [Convert]::ToBase64String($BYTES)

# Execute
$REMOTE_EXEC = "echo $B64_CMD | base64 -d | bash"
ssh -T -i $PEM_FILE -o StrictHostKeyChecking=no $USER@$HOST_IP $REMOTE_EXEC
