#!/bin/bash
# Start Position Monitor Service

USER_HOME="/home/ubuntu"
REPO_DIR="$USER_HOME/tastywork-trading"

echo "🚀 Starting Position Monitor Service..."

cd $REPO_DIR

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Start the position monitor
nohup python3 -m src.calendar_spreads.position_monitor --interval 60 > logs/position_monitor.log 2>&1 &
echo $! > /tmp/position_monitor.pid

echo "✅ Position Monitor started with PID: $(cat /tmp/position_monitor.pid)"
echo "📋 Logs: $REPO_DIR/logs/position_monitor.log"
