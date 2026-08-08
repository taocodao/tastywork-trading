#!/bin/bash
# Deploy TurboCore Pro paper trader to EC2 alongside existing LEAPS trader
# Target: ubuntu@54.80.47.153:/home/ubuntu/turbocore-pro-live/
#
# Prerequisites on EC2:
#   - IBKR Gateway running (paper, port 4002)
#   - Python 3.10+ with pip
#   - Existing LEAPS trader should already be running (shares the Gateway)

set -e

EC2_HOST="ubuntu@54.80.47.153"
REMOTE_DIR="/home/ubuntu/turbocore-pro-live"

echo "=== TurboCore Pro Paper Trader Deployment ==="
echo "Target: $EC2_HOST:$REMOTE_DIR"
echo ""

# 1. Create remote directory
echo "[1/5] Creating remote directory..."
ssh "$EC2_HOST" "mkdir -p $REMOTE_DIR/{config,logs}"

# 2. Copy live trading code
echo "[2/5] Copying live trading code..."
scp -r live/ "$EC2_HOST:$REMOTE_DIR/"

# 3. Copy model artifacts (fold-10 v3.2-final)
echo "[3/5] Copying model artifacts..."
ssh "$EC2_HOST" "mkdir -p $REMOTE_DIR/models"
scp models/turbocore_hmm_v2_v32final_fold10.joblib \
    models/turbocore_hmm_v2_v32final_fold10_scaler.joblib \
    models/turbocore_xgboost_v2_v32final_fold10.joblib \
    models/turbocore_msgarch.joblib \
    "$EC2_HOST:$REMOTE_DIR/models/"

# 4. Copy source code
echo "[4/5] Copying strategy source code..."
scp -r src/ "$EC2_HOST:$REMOTE_DIR/"
scp -r backtest/walk_forward_hourly_backtest.py "$EC2_HOST:$REMOTE_DIR/"
scp -r tools/data_pipeline.py "$EC2_HOST:$REMOTE_DIR/src/turbocore_pro/"
scp requirements.txt "$EC2_HOST:$REMOTE_DIR/"

# 5. Install dependencies on EC2
echo "[5/5] Installing Python dependencies..."
ssh "$EC2_HOST" << 'EOF'
    cd /home/ubuntu/turbocore-pro-live
    python3 -m pip install --user ib_async pyyaml joblib scikit-learn xgboost hmmlearn arch pandas numpy scipy requests
    echo "Dependencies installed."
    echo ""
    echo "=== Deployment Complete ==="
    echo "Config: $REMOTE_DIR/live/config/paper_web3aistore.yaml"
    echo "Models: $REMOTE_DIR/models/"
    echo ""
    echo "To test (dry-run, no IBKR needed):"
    echo "  cd $REMOTE_DIR && python3 live/paper_trader.py"
    echo ""
    echo "To run with live IBKR paper orders:"
    echo "  cd $REMOTE_DIR && python3 live/paper_trader.py --live"
    echo ""
    echo "To set up cron (hourly, market hours only):"
    echo "  crontab $REMOTE_DIR/live/deploy/crontab.example"
EOF

echo ""
echo "Done. Verify the deployment with:"
echo "  ssh $EC2_HOST 'cd $REMOTE_DIR && python3 live/paper_trader.py'"
