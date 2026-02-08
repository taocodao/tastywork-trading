#!/bin/bash

# Deploy Continuous Monitoring Service

echo "=========================================="
echo "Deploying Theta Sprint Continuous Monitor"
echo "=========================================="

# 1. Stop existing cron job (if any)
echo ""
echo "[1/5] Removing old cron job..."
crontab -l 2>/dev/null | grep -v "run_theta_scheduler.py" | crontab -
echo "✅ Cron job removed"

# 2. Copy service file to systemd
echo ""
echo "[2/5] Installing systemd service..."
sudo cp theta-monitor.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/theta-monitor.service
echo "✅ Service file installed"

# 3. Reload systemd
echo ""
echo "[3/5] Reloading systemd..."
sudo systemctl daemon-reload
echo "✅ Systemd reloaded"

# 4. Enable service (start on boot)
echo ""
echo "[4/5] Enabling service..."
sudo systemctl enable theta-monitor.service
echo "✅ Service enabled (will start on boot)"

# 5. Start service
echo ""
echo "[5/5] Starting service......"
sudo systemctl start theta-monitor.service
sleep 2

# Check status
echo ""
echo "=========================================="
echo "SERVICE STATUS"
echo "=========================================="
sudo systemctl status theta-monitor.service --no-pager

echo ""
echo "=========================================="
echo "DEPLOYMENT COMPLETE"
echo "=========================================="
echo ""
echo "The continuous monitoring service is now running!"
echo ""
echo "Useful commands:"
echo "  - Check status:  sudo systemctl status theta-monitor"
echo "  - View logs:     tail -f ~/theta_monitor.log"
echo "  - Stop service:  sudo systemctl stop theta-monitor"
echo "  - Start service: sudo systemctl start theta-monitor"
echo "  - Restart:       sudo systemctl restart theta-monitor"
echo ""
echo "The service will:"
echo "  ✅ Run 24/7 continuously"
echo "  ✅ Do morning analysis at 9:35 AM ET (new entries)"
echo "  ✅ Monitor positions every 5 minutes (exits)"
echo "  ✅ Auto-restart if it crashes"
echo "  ✅ Start automatically on server reboot"
echo ""
echo "=========================================="
