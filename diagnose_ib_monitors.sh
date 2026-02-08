#!/bin/bash
# IB Monitor Diagnostic Script
# Run this on EC2 to diagnose calendar scheduler timeouts

echo "======================================================================"
echo "IB MONITOR DIAGNOSTIC - $(date)"
echo "======================================================================"
echo ""

# 1. Check if monitors are running
echo "[1/8] Checking Monitor Processes"
echo "----------------------------------------------------------------------"
ps aux | grep -E "theta_monitor|calendar_monitor" | grep -v grep
echo ""

# 2. Check IB Gateway Docker container
echo "[2/8] Checking IB Gateway Status"
echo "----------------------------------------------------------------------"
if command -v docker &> /dev/null; then
    docker ps -a | grep ib-gateway || echo "No IB Gateway container found"
    echo ""
    echo "IB Gateway Logs (last 20 lines):"
    docker logs ib-gateway --tail 20 2>&1 || echo "Could not fetch logs"
else
    echo "Docker not installed or not in PATH"
fi
echo ""

# 3. Check for 9:35 AM morning analysis
echo "[3/8] Checking Morning Analysis Execution"
echo "----------------------------------------------------------------------"
echo "=== THETA MONITOR ==="
grep -i "morning\|9:35" ~/tastywork-trading/theta_monitor.log 2>/dev/null | tail -10 || echo "No morning analysis found"
echo ""
echo "=== CALENDAR MONITOR ==="
grep -i "exit scan\|9:35" ~/tastywork-trading/calendar_monitor.log 2>/dev/null | tail -10 || echo "No exit scan found"
echo ""

# 4. Recent errors in monitors
echo "[4/8] Recent Errors in Monitors"
echo "----------------------------------------------------------------------"
echo "=== THETA ERRORS ==="
tail -200 ~/tastywork-trading/theta_monitor.log 2>/dev/null | grep -i "error\|fail\|timeout" | tail -10
echo ""
echo "=== CALENDAR ERRORS ==="
tail -200 ~/tastywork-trading/calendar_monitor.log 2>/dev/null | grep -i "error\|fail\|timeout" | tail -10
echo ""

# 5. Check detailed scheduler logs
echo "[5/8] Detailed Scheduler Logs"
echo "----------------------------------------------------------------------"
echo "=== THETA SCHEDULER (last 50 lines) ==="
tail -50 ~/tastywork-trading/theta_scheduler.log 2>/dev/null || echo "Log file not found"
echo ""
echo "=== CALENDAR SCHEDULER (last 50 lines) ==="
tail -50 ~/tastywork-trading/logs/calendar_spreads.log 2>/dev/null || echo "Log file not found"
echo ""

# 6. Check what's currently hanging
echo "[6/8] Currently Running Processes"
echo "----------------------------------------------------------------------"
ps aux | grep -E "run_theta_scheduler|run_calendar_scheduler|main.py" | grep -v grep
echo ""

# 7. Check database locks
echo "[7/8] Database Status"
echo "----------------------------------------------------------------------"
if [ -f ~/tastywork-trading/data/signals.db ]; then
    ls -lh ~/tastywork-trading/data/signals.db
    echo ""
    echo "Database processes:"
    lsof ~/tastywork-trading/data/signals.db 2>&1 || echo "lsof not available or no processes"
else
    echo "Database file not found"
fi
echo ""

# 8. Network connectivity to IB Gateway
echo "[8/8] Network Connectivity"
echo "----------------------------------------------------------------------"
echo "Checking connection to IB Gateway (127.0.0.1:4002)..."
nc -zv 127.0.0.1 4002 2>&1 || echo "Cannot connect to IB Gateway"
echo ""

echo "======================================================================"
echo "DIAGNOSTIC COMPLETE"
echo "======================================================================"
echo ""
echo "RECOMMENDATIONS:"
echo "1. If IB Gateway is not running: Start it with docker-compose"
echo "2. If monitors are hanging: Kill and restart them"
echo "3. If database is locked: Check for zombie processes"
echo "4. If morning analysis didn't run: Check VIX filter and IB connection"
