#!/bin/bash
set -e

echo "🚀 Setting up TradeMind Production Services..."

# 1. Determine Dynamic Paths
REPO_DIR=$(pwd)
IB_DIR="$HOME/IB-program-trading"
SYSTEMD_DIR="/etc/systemd/system"
USER=$(whoami)

echo "📍 Detected Repo Directory: $REPO_DIR"
echo "📍 Detected User: $USER"

# 2. Check Prerequisites
if [ ! -d "$IB_DIR" ]; then
    echo "❌ IB directory not found: $IB_DIR"
    exit 1
fi

# 3. Generate Service Files Dynamically
echo "📝 Generating systemd unit files..."

# IB Gateway Service
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
ExecStartPre=/usr/local/bin/docker-compose down
ExecStart=/usr/local/bin/docker-compose up ib-gateway-data
ExecStop=/usr/local/bin/docker-compose stop ib-gateway-data

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
Environment="PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
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
Environment="PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
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

# 4. Reload and Enable
echo "🔄 Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "🏗️ Starting Services..."
sudo systemctl enable ib-gateway.service
sudo systemctl restart ib-gateway.service

sleep 5

sudo systemctl enable trademind-api.service
sudo systemctl restart trademind-api.service

sudo systemctl enable trademind-scanner.timer
sudo systemctl start trademind-scanner.timer

echo "✅ Success! All services configured for path: $REPO_DIR"
