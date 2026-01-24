# discover_server_state.ps1
$ErrorActionPreference = "Stop"

$PEM_FILE = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST_IP = "34.235.119.67"
$USER = "ubuntu"

Write-Host "Connecting to EC2 ($HOST_IP) to discover system state..."

# Diagnostic Command
# 1. List home dir
# 2. Find scanner script
# 3. Check docker containers
$REMOTE_COMMAND = @'
echo "=== HOME DIRECTORY ==="
ls -F ~

echo ""
echo "=== SEARCHING FOR SCANNER ==="
find ~ -maxdepth 3 -name "scheduled_scanner.py" 2>/dev/null

echo ""
echo "=== DOCKER STATUS ==="
docker ps -a
'@

# Execute via SSH
# CRITICAL: We replace `r (Carriage Return) with empty string to ensure Unix-style LF only
$REMOTE_COMMAND.Replace("`r", "") | ssh -T -i $PEM_FILE -o StrictHostKeyChecking=no $USER@$HOST_IP "bash -s"

Write-Host "--- Discovery Complete ---"
