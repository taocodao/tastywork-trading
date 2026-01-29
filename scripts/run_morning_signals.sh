#!/bin/bash
# Theta Strategy - Signal Generation
# Runs at 9:45 AM to generate entry signals

cd ~/tastywork-trading

echo "=========================================="
echo "Theta Signal Generation - $(date)"
echo "=========================================="

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run signal generation
python3 run_theta_scheduler.py --once

echo "Signal generation complete"
echo ""
