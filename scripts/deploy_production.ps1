# deploy_production.ps1
$ErrorActionPreference = "Stop"

$PEM_FILE = "D:\Projects\IB-program-trading\tradecoin-bot-key.pem"
$HOST_IP = "34.235.119.67"
$USER = "ubuntu"

Write-Host "Connecting to EC2 ($HOST_IP)..."

# ==========================================
# EMBEDDED SETUP SCRIPT (Dynamic Systemd)
# ==========================================
$SETUP_SCRIPT = @'
#!/bin/bash
set -e

echo "🚀 Setting up TradeMind Production Services..."

# 1. Define Paths (Hardcoded for ubuntu user)
USER="ubuntu"
HOME_DIR="/home/ubuntu"
REPO_DIR="$HOME_DIR/tastywork-trading"
IB_DIR="$HOME_DIR/IB-program-trading"
SYSTEMD_DIR="/etc/systemd/system"

echo "📍 Target User: $USER"
echo "📍 Repo Directory: $REPO_DIR"

# 2. Check Prerequisites
if [ ! -d "$IB_DIR" ]; then
    echo "❌ IB directory not found: $IB_DIR"
    exit 1
fi

# 3. Detect or Install Docker Compose
echo "📍 Checking Docker Compose..."
COMPOSE_CMD=""

# Check for plugin syntax first (docker compose)
if docker compose version &>/dev/null; then
    COMPOSE_CMD="docker compose"
    echo "   Found: docker compose (plugin)"
# Check for standalone docker-compose
elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
    echo "   Found: docker-compose (standalone)"
else
    echo "⚠️ Docker Compose not found. Installing..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-compose
    COMPOSE_CMD="docker-compose"
    echo "   Installed: docker-compose"
fi

# 4. Generate Service Files Dynamically
echo "📝 Generating systemd unit files..."

# IB Gateway Service (Using detected command)
# Note: For plugin, we use "docker compose" as the command
cat <<EOF | sudo tee $SYSTEMD_DIR/ib-gateway.service > /dev/null
[Unit]
Description=IB Gateway Docker Container
Requires=docker.service
After=docker.service network.target

[Service]
Restart=always
User=$USER
Group=docker
WorkingDirectory=$IB_DIR
ExecStartPre=/bin/bash -c '$COMPOSE_CMD down'
ExecStart=/bin/bash -c '$COMPOSE_CMD up ib-gateway-data'
ExecStop=/bin/bash -c '$COMPOSE_CMD stop ib-gateway-data'

[Install]
WantedBy=multi-user.target
EOF

# API Server Service
cat <<EOF | sudo tee $SYSTEMD_DIR/trademind-api.service > /dev/null
[Unit]
Description=TradeMind API & WebSocket Server
After=network.target ib-gateway.service

[Service]
User=$USER
WorkingDirectory=$REPO_DIR
Environment="PATH=$HOME_DIR/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/bin/bash -c 'python3 tasty_api_server.py & python3 websocket_server.py'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Scanner Service
cat <<EOF | sudo tee $SYSTEMD_DIR/trademind-scanner.service > /dev/null
[Unit]
Description=TradeMind Signal Scanner
After=network.target trademind-api.service

[Service]
Type=oneshot
User=$USER
WorkingDirectory=$REPO_DIR
Environment="PATH=$HOME_DIR/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/usr/bin/python3 scheduled_scanner.py
EOF

# Scanner Timer
cat <<EOF | sudo tee $SYSTEMD_DIR/trademind-scanner.timer > /dev/null
[Unit]
Description=Run TradeMind Scanner every 5 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
Unit=trademind-scanner.service

[Install]
WantedBy=timers.target
EOF

# 5. Reload and Enable
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "🏗️ Starting Services..."
sudo systemctl unmask ib-gateway.service 2>/dev/null || true
sudo systemctl enable ib-gateway.service
sudo systemctl restart ib-gateway.service

sleep 5

sudo systemctl enable trademind-api.service
sudo systemctl restart trademind-api.service

sudo systemctl enable trademind-scanner.timer
sudo systemctl start trademind-scanner.timer

echo "✅ Success! All services configured."
'@

# ==========================================
# REMOTE EXECUTION LOGIC
# ==========================================
$RAW_BASH = @"
set -e
echo ">> [1/6] Updating System..."
sudo apt-get update -qq
sudo apt-get install -y -qq git dos2unix

echo ">> [2/6] Setting up Directory..."
DIR="tastywork-trading"
if [ ! -d "`$DIR" ]; then
    git clone https://github.com/taocodao/tastywork-trading.git `$DIR
else
    cd `$DIR
    git pull
    cd ..
fi

echo ">> [3/6] Migrating Config..."
if [ -f ".env" ]; then
    cp .env `$DIR/
fi

echo ">> [4/6] Writing Embedded Setup Script..."
cat << 'END_OF_SETUP_SCRIPT' > `$DIR/setup_production_dynamic.sh
$SETUP_SCRIPT
END_OF_SETUP_SCRIPT

echo ">> [5/6] Running Setup..."
cd `$DIR
dos2unix setup_production_dynamic.sh
chmod +x setup_production_dynamic.sh
sudo ./setup_production_dynamic.sh

echo ">> [6/6] Done!"
"@

# Base64 Encode to clean CRLF
$BASH_CLEAN = $RAW_BASH.Replace("`r", "")
$BYTES = [System.Text.Encoding]::UTF8.GetBytes($BASH_CLEAN)
$B64_CMD = [Convert]::ToBase64String($BYTES)

# Execute via SSH
$REMOTE_EXEC = "echo $B64_CMD | base64 -d | bash"
ssh -T -i $PEM_FILE -o StrictHostKeyChecking=no $USER@$HOST_IP $REMOTE_EXEC

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[SUCCESS] Deployment Complete!"
} else {
    Write-Host "`n[FAILURE] Exit Code: $LASTEXITCODE"
    exit $LASTEXITCODE
}
