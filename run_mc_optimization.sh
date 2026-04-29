#!/bin/bash
# ============================================================
# OTM Naked Monte Carlo Optimizer — EC2 Deployment Script
# ============================================================
# Run this on the EC2 instance to execute the full optimization.
# Recommended: c5.4xlarge (16 vCPUs) or c5.2xlarge (8 vCPUs)
#
# Usage:
#   chmod +x run_mc_optimization.sh
#   ./run_mc_optimization.sh [quick|standard|full]
#
#   quick    — 50 trials, 30 paths  (test run, ~10 min)
#   standard — 200 trials, 100 paths (recommended, ~2 hrs)
#   full     — 500 trials, 300 paths (production, ~8 hrs)
# ============================================================

set -e

PROJECT_DIR="$HOME/tastywork-trading"
RESULTS_DIR="$PROJECT_DIR/mc_results"
MODE="${1:-standard}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="$RESULTS_DIR/mc_optimization_${TIMESTAMP}_${MODE}.json"

mkdir -p "$RESULTS_DIR"

echo "============================================================"
echo "  OTM Naked Monte Carlo Optimizer"
echo "  Mode: $MODE | Started: $(date)"
echo "============================================================"

cd "$PROJECT_DIR"
source venv/bin/activate 2>/dev/null || true

# Install / upgrade optimization dependencies
pip install -q optuna arch scipy numpy pandas yfinance 2>&1 | tail -3

case "$MODE" in
  quick)
    N_TRIALS=50
    N_PATHS=30
    N_JOBS=2
    IS_DAYS=504
    OOS_DAYS=63
    ;;
  full)
    N_TRIALS=500
    N_PATHS=300
    N_JOBS=$(nproc)
    IS_DAYS=1008
    OOS_DAYS=126
    ;;
  *)  # standard
    N_TRIALS=200
    N_PATHS=100
    N_JOBS=$(nproc)
    IS_DAYS=756
    OOS_DAYS=126
    ;;
esac

echo "  Config: trials=$N_TRIALS paths=$N_PATHS jobs=$N_JOBS IS=${IS_DAYS}d OOS=${OOS_DAYS}d"
echo "  Output: $OUTPUT_FILE"
echo ""

# Run the optimization
python -m src.otm_naked.optimization.optuna_study \
    --start 2018-01-01 \
    --end   2025-12-31 \
    --n-trials  "$N_TRIALS" \
    --n-paths   "$N_PATHS" \
    --n-jobs    "$N_JOBS" \
    --is-days   "$IS_DAYS" \
    --oos-days  "$OOS_DAYS" \
    --output    "$OUTPUT_FILE" \
    2>&1 | tee "$RESULTS_DIR/mc_optimization_${TIMESTAMP}_${MODE}.log"

echo ""
echo "============================================================"
echo "  Optimization Complete: $(date)"
echo "  Results: $OUTPUT_FILE"
echo "============================================================"

# Print a summary from the JSON
python -c "
import json, sys
with open('$OUTPUT_FILE') as f:
    data = json.load(f)
s = data.get('summary', {})
print()
print('  RECOMMENDED PARAMETERS:')
for k, v in s.get('recommended_params', {}).items():
    print(f'    {k:<22}: {v}')
print()
print(f'  OOS Sortino (avg): {s.get(\"avg_sortino\", 0):.2f}')
print(f'  OOS MaxDD   (avg): {s.get(\"avg_max_drawdown\", 0):.1%}')
print(f'  DSR pass rate    : {s.get(\"n_dsr_pass\", 0)}/{s.get(\"n_windows\", 0)} windows')
"
