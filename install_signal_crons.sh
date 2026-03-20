#!/bin/bash
# =============================================================
# install_signal_crons.sh
# Run ONCE on EC2 to set up cron jobs for all three strategy
# scanners at 3:00 PM Eastern Time, Monday through Friday.
#
# EC2 Usage:
#   cd ~/tastywork-trading
#   bash install_signal_crons.sh
# =============================================================

set -e

PROJECT_DIR=~/tastywork-trading
LOGS_DIR=$PROJECT_DIR/logs

echo "=== TradeMind Signal Cron Installer ==="
echo ""

# 1. Ensure log directory exists
mkdir -p "$LOGS_DIR"
echo "✓ Log directory: $LOGS_DIR"

# 2. Detect python3
PYTHON_BIN=$(which python3)
if [ -z "$PYTHON_BIN" ]; then
    echo "❌ python3 not found. Aborting."
    exit 1
fi
echo "✓ Python: $PYTHON_BIN"

# 3. Verify timezone
TIMEZONE=$(timedatectl 2>/dev/null | grep "Time zone" | awk '{print $3}')
if [ "$TIMEZONE" != "America/New_York" ]; then
    echo "⚠  Timezone is '$TIMEZONE' — should be America/New_York"
    echo "   Fix: sudo timedatectl set-timezone America/New_York"
    echo "   Cron times will be offset until fixed!"
else
    echo "✓ Timezone: America/New_York (correct)"
fi

# 4. Backup existing crontab
crontab -l > /tmp/crontab.backup 2>/dev/null || true
echo "✓ Existing crontab backed up to /tmp/crontab.backup"

# 5. Strip any old TradeMind signal cron entries (idempotent)
CLEAN_CRON=$(crontab -l 2>/dev/null | grep -v "run_turbocore_scheduler\|run_turbocore_pro_scheduler\|run_turbobounce_scheduler\|TradeMind Signal" || true)

# 6. Build new cron block
# 0 15 * * 1-5  = 3:00 PM ET, Monday-Friday
# Stagger by 1 min to avoid resource contention at startup
NEW_CRON=$(cat <<EOF

# TradeMind Signal Generators — 3:00 PM ET, Mon-Fri (installed $(date))
0 15 * * 1-5 cd $PROJECT_DIR && $PYTHON_BIN run_turbocore_scheduler.py --once >> $LOGS_DIR/run_turbocore_scheduler.log 2>&1
1 15 * * 1-5 cd $PROJECT_DIR && $PYTHON_BIN run_turbocore_pro_scheduler.py --once >> $LOGS_DIR/run_turbocore_pro_scheduler.log 2>&1
EOF
)

# 7. Install combined crontab
(echo "$CLEAN_CRON"; echo "$NEW_CRON") | crontab -

echo ""
echo "✅ Cron jobs installed. Active TradeMind entries:"
echo "----------------------------------------------"
crontab -l | grep -E "TradeMind|turbocore|turbobounce"
echo "----------------------------------------------"
echo ""
echo "Signals will be generated Monday-Friday at 3:00 PM ET."
echo "Logs: $LOGS_DIR/"
echo ""
echo "To verify: crontab -l"
echo "To test now: cd $PROJECT_DIR && $PYTHON_BIN run_turbocore_pro_scheduler.py --once"
