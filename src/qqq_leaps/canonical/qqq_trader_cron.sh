#!/bin/bash
# Hourly cron wrapper for QQQ LEAPS Live Paper Trader
# Runs Mon-Fri during US market hours; executes real paper orders
set -euo pipefail

STRAT_DIR="/home/ubuntu/qqq-live-strategy"
LOG_DIR="$STRAT_DIR/logs"
mkdir -p "$LOG_DIR"

TS=$(date -u +%Y%m%dT%H%M%SZ)
ACTION_LOG="$LOG_DIR/actions.log"

cd "$STRAT_DIR"
source .venv/bin/activate

# Rotate clientId per-hour to avoid IBKR "duplicate clientId" collisions
export IB_CLIENT_ID=$((250 + $(date +%H) ))
export QQQ_CAPITAL=1000000
export LIVE_TRADE=1

timeout 600 python qqq_live_trader.py > "$LOG_DIR/trader_run_${TS}.log" 2>&1
EXIT=$?

# Extract summary from log
LOG="$LOG_DIR/trader_run_${TS}.log"
REGIME=$(grep -oP 'regime=\K[A-Z_]+' "$LOG" | head -1 || echo "?")
GATE=$(grep -oP 'Entry gate: \K[^ ]+' "$LOG" | head -1 || echo "?")
ORDER_COUNT=$(grep -c "BUY_TO_OPEN\|SELL_TO_OPEN\|SELL_TO_CLOSE\|BUY_TO_CLOSE" "$LOG" || echo 0)
NAV=$(grep -oP 'Account NAV: \$\K[0-9,.]+' "$LOG" | head -1 || echo "?")

echo "[$TS] exit=$EXIT regime=$REGIME entry=$GATE orders=$ORDER_COUNT NAV=\$$NAV" >> "$ACTION_LOG"

# Retain last 500 logs
ls -t "$LOG_DIR"/trader_run_*.log 2>/dev/null | tail -n +501 | xargs -r rm --

exit $EXIT
