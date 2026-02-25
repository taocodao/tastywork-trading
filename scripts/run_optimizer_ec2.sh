#!/bin/bash
# Run Active Diagonal Parameter Optimizer on EC2
# Runs all 3 regimes in screen sessions so they survive SSH disconnect

set -e

EC2_PROJECT="/home/ubuntu/tastywork-trading"
LOG_DIR="$EC2_PROJECT/logs"
DATA_DIR="$EC2_PROJECT/data"

mkdir -p "$LOG_DIR" "$DATA_DIR"

cd "$EC2_PROJECT"

# Pull latest code
echo "[1/3] Pulling latest code..."
git pull origin main

# Install any missing python deps
echo "[2/3] Installing dependencies (if any missing)..."
pip3 install --user scipy yfinance xgboost pandas --quiet

# Kill any existing optimizer sessions
echo "[3/3] Launching optimizer sessions..."
screen -S diag_LOW_VOL  -X quit 2>/dev/null || true
screen -S diag_NORMAL   -X quit 2>/dev/null || true
screen -S diag_HIGH_VOL -X quit 2>/dev/null || true

# Run each regime in its own screen session
# maxiter=30, popsize=15 => ~450 backtests per regime, ~3-4 hrs each
# Results checkpoint to data/optimized_params_{regime}.json after every improvement

screen -S diag_LOW_VOL -dm bash -c '
  cd /home/ubuntu/tastywork-trading
  python3 -m diagonal_strategy.backtest.runner \
    --optimize --optimize-regime LOW_VOL \
    --maxiter 30 --popsize 15 \
    2>&1 | tee logs/optimizer_LOW_VOL.log
'

screen -S diag_NORMAL -dm bash -c '
  cd /home/ubuntu/tastywork-trading
  python3 -m diagonal_strategy.backtest.runner \
    --optimize --optimize-regime NORMAL \
    --maxiter 30 --popsize 15 \
    2>&1 | tee logs/optimizer_NORMAL.log
'

screen -S diag_HIGH_VOL -dm bash -c '
  cd /home/ubuntu/tastywork-trading
  python3 -m diagonal_strategy.backtest.runner \
    --optimize --optimize-regime HIGH_VOL \
    --maxiter 30 --popsize 15 \
    2>&1 | tee logs/optimizer_HIGH_VOL.log
'

echo ""
echo "======================================"
echo "  Optimizer launched in 3 screen sessions"
echo "======================================"
echo ""
echo "Check live logs:"
echo "  tail -f logs/optimizer_NORMAL.log"
echo "  tail -f logs/optimizer_LOW_VOL.log"
echo "  tail -f logs/optimizer_HIGH_VOL.log"
echo ""
echo "Attach to a session:"
echo "  screen -r diag_NORMAL"
echo "  (Ctrl+A, D to detach without stopping)"
echo ""
echo "Best params (updated as optimizer improves):"
echo "  cat data/optimized_params_NORMAL.json"
echo "  cat data/optimized_params_LOW_VOL.json"
echo "  cat data/optimized_params_HIGH_VOL.json"
echo ""
echo "List running screen sessions:"
echo "  screen -ls"
