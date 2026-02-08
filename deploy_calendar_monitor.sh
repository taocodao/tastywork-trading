#!/bin/bash
# ============================================================================
# Calendar Monitor Deployment Script
# ============================================================================
# Deploys the calendar spread continuous monitoring service to EC2
#
# Usage:
#   ./deploy_calendar_monitor.sh
#
# Requirements:
#   - SSH access to EC2
#   - Files already synced to ~/tastywork-trading/
# ============================================================================

set -e

echo "=============================================="
echo "  Calendar Monitor Deployment"
echo "=============================================="
echo ""

# Configuration
SERVICE_NAME="calendar-monitor"
WORKING_DIR="/home/ubuntu/tastywork-trading"
SERVICE_FILE="$WORKING_DIR/calendar-monitor.service"

# Step 1: Stop existing service if running
echo "[1/5] Stopping existing service..."
sudo systemctl stop $SERVICE_NAME 2>/dev/null || echo "   Service not running"

# Step 2: Copy service file
echo "[2/5] Installing service file..."
sudo cp $SERVICE_FILE /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/$SERVICE_NAME.service
echo "   ✓ Service file installed"

# Step 3: Reload systemd
echo "[3/5] Reloading systemd..."
sudo systemctl daemon-reload
echo "   ✓ Systemd reloaded"

# Step 4: Enable service for boot
echo "[4/5] Enabling service..."
sudo systemctl enable $SERVICE_NAME
echo "   ✓ Service enabled for boot"

# Step 5: Start service
echo "[5/5] Starting service..."
sudo systemctl start $SERVICE_NAME

# Wait for startup
sleep 3

# Check status
echo ""
echo "=============================================="
echo "  Service Status"
echo "=============================================="
sudo systemctl status $SERVICE_NAME --no-pager

echo ""
echo "=============================================="
echo "  Useful Commands"
echo "=============================================="
echo "Check status:   sudo systemctl status $SERVICE_NAME"
echo "View logs:      tail -f $WORKING_DIR/calendar_monitor.log"
echo "View errors:    tail -f $WORKING_DIR/calendar_monitor_error.log"
echo "Stop service:   sudo systemctl stop $SERVICE_NAME"
echo "Restart:        sudo systemctl restart $SERVICE_NAME"
echo ""
echo "Deployment complete!"
