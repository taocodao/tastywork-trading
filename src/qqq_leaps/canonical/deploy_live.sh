#!/bin/bash
# Deploy QQQ LEAPS live trader to EC2 with all fixes (NAV wiring + ml_confidence model + ADX=16)
# Run from your local machine (requires SSH key at ~/.ssh/tradecoin-bot-key.pem)
set -euo pipefail

SSH_KEY="${HOME}/.ssh/tradecoin-bot-key.pem"
EC2_HOST="ubuntu@54.80.47.153"
REMOTE_DIR="/home/ubuntu/qqq-live-strategy"

echo "=== Deploying QQQ LEAPS live trader to EC2 ==="
echo "Target: ${EC2_HOST}:${REMOTE_DIR}"
echo ""

# 1. Copy updated files
echo "[1/4] Copying updated files..."
scp -i "$SSH_KEY" \
    live/qqq_live_trader.py \
    live/qqq_trader_cron.sh \
    strategy/enhanced_multiwindow/qqq_leaps_enhanced_2y_hourly.py \
    strategy/enhanced_multiwindow/ml_confidence_model.py \
    "$EC2_HOST:$REMOTE_DIR/"

echo "[2/4] Making cron script executable..."
ssh -i "$SSH_KEY" "$EC2_HOST" "chmod +x $REMOTE_DIR/qqq_trader_cron.sh"

echo "[3/4] Installing scikit-learn if missing (ml_confidence_model depends on it)..."
ssh -i "$SSH_KEY" "$EC2_HOST" "cd $REMOTE_DIR && source .venv/bin/activate && pip install scikit-learn -q 2>/dev/null; python3 -c 'import sklearn; print(\"sklearn OK:\", sklearn.__version__)'"

echo "[4/4] Verifying imports work..."
ssh -i "$SSH_KEY" "$EC2_HOST" "cd $REMOTE_DIR && source .venv/bin/activate && python3 -c '
import sys
sys.path.insert(0, \".\")
from qqq_leaps_enhanced_2y_hourly import Config, build_enhanced_features
from ml_confidence_model import compute_ml_confidence_walkforward
print(\"All imports OK\")
print(\"ADX threshold:\", Config().pmcc_skip_adx_min)
print(\"VRP threshold:\", Config().pmcc_skip_vrp_max)
print(\"max_contracts:\", Config().max_contracts)
print(\"max_position_pct:\", Config().max_position_pct)
'"

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Cron is already configured (Mon-Fri, 13:30-20:00 UTC = 9:30 AM - 4:00 PM ET)."
echo "Market opens Monday at 9:30 AM ET. First cron run at 13:30 UTC (9:30 AM ET)."
echo ""
echo "To verify cron is still active:"
echo "  ssh -i $SSH_KEY $EC2_HOST 'crontab -l | grep qqq'"
echo ""
echo "To do a manual dry-run test before market open:"
echo "  ssh -i $SSH_KEY $EC2_HOST 'cd $REMOTE_DIR && source .venv/bin/activate && QQQ_CAPITAL=1000000 LIVE_TRADE=0 python qqq_live_trader.py --dry-run'"
echo ""
echo "To watch the first live run at market open:"
echo "  ssh -i $SSH_KEY $EC2_HOST 'tail -f $REMOTE_DIR/logs/trader_run_*.log'"
