#!/bin/bash
# End-of-Day P&L Analysis
# Runs at 4:05 PM ET to analyze daily results

cd ~/tastywork-trading

echo "=========================================="
echo "End-of-Day P&L Analysis - $(date)"
echo "=========================================="

# Activate virtual environment if exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run EOD analysis
python3 eod_analysis.py

echo "EOD analysis complete"
echo ""
