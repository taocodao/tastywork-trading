#!/bin/bash
# Deploy ZEBRA Strategy Monitor to EC2

echo "🦓 Deploying ZEBRA Monitor..."

# 1. Pull latest code
cd /home/ubuntu/tastywork-trading || exit 1
echo "📥 Pulling latest code..."
git pull origin main

# 2. Install Service File
echo "⚙️ Installing systemd service..."
if [ -f "zebra_monitor.service" ]; then
    sudo cp zebra_monitor.service /etc/systemd/system/
    sudo systemctl daemon-reload
    echo "✅ Service file installed."
else
    echo "❌ Error: zebra_monitor.service file not found in repository!"
    exit 1
fi

# 3. Install Dependencies (if any new ones)
echo "📦 Checking dependencies..."
pip3 install --user xgboost scikit-learn pandas numpy --quiet

# 4. Start Service
echo "🚀 Starting ZEBRA Monitor..."
sudo systemctl enable zebra_monitor
sudo systemctl restart zebra_monitor

# 5. Check Status
sleep 2
if systemctl is-active --quiet zebra_monitor; then
    echo "✅ ZEBRA Monitor is RUNNING!"
    sudo systemctl status zebra_monitor --no-pager | head -n 10
else
    echo "❌ ZEBRA Monitor failed to start."
    sudo journalctl -u zebra_monitor --no-pager -n 20
    exit 1
fi

echo "========================================"
echo "Deployment Complete."
echo "========================================"
