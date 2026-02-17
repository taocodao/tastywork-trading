#!/bin/bash
# EC2 Deployment Script for Symbol Optimization
# Run this on EC2 instance to update with latest code

echo "========================================="
echo "  Deploying Symbol Optimization to EC2"
echo "========================================="
echo ""

# Navigate to project directory
cd /home/ubuntu/tastywork-trading || exit 1

echo "[1/6] Stopping running services..."
# Stop any running processes
pkill -f "python.*theta" || true
pkill -f "python.*position_monitor" || true
sleep 2

echo "[2/6] Pulling latest code from GitHub..."
git pull origin main

echo "[3/6] Installing new dependencies..."
# Install stable-baselines3 and gymnasium for RL (won't break anything if already there)
pip3 install --user gymnasium stable-baselines3 tensorboard --quiet || echo "  (Dependencies may already be installed)"

echo "[4/6] Testing symbol optimization..."
# Run integration test
python3 test_symbol_optimization.py

if [ $? -eq 0 ]; then
    echo "  ✓ Symbol optimization tests passed!"
else
    echo "  ✗ Tests failed! Rolling back..."
    git reset --hard HEAD~1
    exit 1
fi

echo "[5/6] Restarting services..."
# Restart theta scheduler (if using systemd)
if systemctl list-units --type=service | grep -q theta; then
    sudo systemctl restart theta-scheduler || echo "  (No systemd service found)"
else
    # Start manually if no systemd
    echo "  Starting theta scheduler manually..."
    nohup python3 run_theta_scheduler.py > logs/theta_scheduler.log 2>&1 &
fi

echo "[6/6] Verifying deployment..."
sleep 5
if pgrep -f "python.*theta"; then
    echo "  ✓ Theta scheduler is running"
else
    echo "  ✗ Warning: Theta scheduler not detected"
fi

echo ""
echo "========================================="
echo "  ✓ Deployment Complete!"
echo "========================================="
echo ""
echo "Symbol-specific optimization is now active:"
echo "  - QQQ: Optimized (30%/40% targets, 7 DTE)"
echo "  - SPY: Balanced (45%/55% targets, 3 DTE)"
echo "  - IWM: Aggressive (50%/60% targets, 2 DTE)"
echo ""
echo "Monitor logs:"
echo "  tail -f logs/theta_scheduler.log"
echo ""
