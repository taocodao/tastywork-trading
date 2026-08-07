#!/bin/bash
# Hourly cron wrapper for QQQ LEAPS live signal service
# Runs during US market hours (Mon-Fri 9:30am-4pm ET)
# Writes JSON snapshots to /home/ubuntu/qqq-live-strategy/signals/
# Appends action lines to /home/ubuntu/qqq-live-strategy/logs/actions.log

set -euo pipefail

STRAT_DIR="/home/ubuntu/qqq-live-strategy"
LOG_DIR="$STRAT_DIR/logs"
SIGNAL_DIR="$STRAT_DIR/signals"
mkdir -p "$LOG_DIR" "$SIGNAL_DIR"

TS=$(date -u +%Y%m%dT%H%M%SZ)
RUN_LOG="$LOG_DIR/run_${TS}.log"
ACTION_LOG="$LOG_DIR/actions.log"

cd "$STRAT_DIR"
source .venv/bin/activate

# Run the signal service with --save flag
# Env vars: IB_HOST=127.0.0.1, IB_PORT=4005, IB_CLIENT_ID varies to avoid collision
export IB_CLIENT_ID=$((200 + $(date +%H) ))  # 200-223 hourly rotation
export QQQ_CAPITAL=75000

# Run with 5-min timeout; save JSON; capture stdout+stderr
timeout 300 python qqq_live_signal.py --save --quiet > "$RUN_LOG" 2>&1
EXIT=$?

# Extract key fields from most recent signal JSON
LATEST_SIGNAL=$(ls -t "$SIGNAL_DIR"/signal_*.json 2>/dev/null | head -1 || true)
if [ -n "$LATEST_SIGNAL" ]; then
    ACTION=$(python -c "import json; print(json.load(open('$LATEST_SIGNAL'))['action'])" 2>/dev/null || echo "PARSE_ERR")
    REGIME=$(python -c "import json; print(json.load(open('$LATEST_SIGNAL'))['features']['regime'])" 2>/dev/null || echo "?")
    QQQ=$(python -c "import json; print(f\"\${json.load(open('$LATEST_SIGNAL'))['spot']['qqq']:.2f}\")" 2>/dev/null || echo "?")
    VIX=$(python -c "import json; print(f\"{json.load(open('$LATEST_SIGNAL'))['spot']['vix']:.2f}\")" 2>/dev/null || echo "?")
    echo "[$TS] exit=$EXIT | QQQ=$QQQ VIX=$VIX regime=$REGIME | $ACTION" >> "$ACTION_LOG"

    # Alert if entry triggered (contains "BUY")
    if echo "$ACTION" | grep -q "^BUY"; then
        echo "[$TS] 🚨 ENTRY SIGNAL: $ACTION" >> "$ACTION_LOG"
        # Placeholder for notification hook — will wire Slack/email next
    fi
else
    echo "[$TS] exit=$EXIT | NO SIGNAL FILE PRODUCED — check $RUN_LOG" >> "$ACTION_LOG"
fi

# Retain only last 500 run logs
ls -t "$LOG_DIR"/run_*.log 2>/dev/null | tail -n +501 | xargs -r rm --

exit $EXIT
