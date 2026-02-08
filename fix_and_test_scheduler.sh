#!/bin/bash
# Fix cron job and test theta scheduler

echo "==================================================================="
echo "🔧 FIXING CRON JOB DIRECTORY"
echo "==================================================================="

# Backup current crontab
crontab -l > /tmp/crontab.bak
echo "✅ Backed up current crontab to /tmp/crontab.bak"

# Update directory in crontab
sed 's|~/tastywork-trading|~/tastywork-trading-1|g' /tmp/crontab.bak | crontab -
echo "✅ Updated cron directory from ~/tastywork-trading to ~/tastywork-trading-1"

# Verify the change
echo ""
echo "📋 Current cron job:"
crontab -l | grep theta

echo ""
echo "==================================================================="
echo "🚀 MANUALLY RUNNING THETA SCHEDULER"
echo "==================================================================="
echo "Starting at: $(date)"
echo ""

# Change to correct directory
cd ~/tastywork-trading-1

# Run scheduler with full output
python3 run_theta_scheduler.py --once

echo ""
echo "==================================================================="
echo "✅ SCHEDULER RUN COMPLETE"
echo "==================================================================="
echo "Finished at: $(date)"

# Check if log file was created
if [ -f ~/theta_cron.log ]; then
    echo ""
    echo "📋 Last 20 lines of ~/theta_cron.log:"
    tail -n 20 ~/theta_cron.log
fi
