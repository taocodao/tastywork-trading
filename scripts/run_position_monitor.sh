#!/bin/bash
# Position Monitor Daemon
# Runs continuously during market hours (9:30 AM - 4:00 PM ET)
# Checks positions every 60 seconds

cd ~/tastywork-trading

LOG_FILE="logs/position_monitor.log"
PID_FILE="position_monitor.pid"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo "Position monitor already running (PID: $PID)"
        exit 0
    fi
fi

# Write PID
echo $$ > "$PID_FILE"

echo "=========================================="
echo "Position Monitor Started - $(date)"
echo "=========================================="

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run monitor loop
python3 -u position_monitor_daemon.py 2>&1 | tee -a "$LOG_FILE"

# Cleanup
rm -f "$PID_FILE"
