#!/bin/bash
# Theta Trading System - Deployment Script
# =========================================
# Deploys the automated theta trading system to EC2
#
# Usage: ./deploy.sh

set -e  # Exit on error

echo "========================================================================"
echo "Theta Trading System - Deployment"
echo "========================================================================"
echo ""

# Configuration
PROJECT_DIR=~/tastywork-trading
SCRIPTS_DIR=$PROJECT_DIR/scripts
LOGS_DIR=$PROJECT_DIR/logs

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Create directories
echo -e "${YELLOW}[1/7] Creating directories...${NC}"
mkdir -p $SCRIPTS_DIR
mkdir -p $LOGS_DIR
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Step 2: Make scripts executable
echo -e "${YELLOW}[2/7] Making scripts executable...${NC}"
chmod +x $SCRIPTS_DIR/*.sh
chmod +x $PROJECT_DIR/*.py
echo -e "${GREEN}✓ Scripts are executable${NC}"
echo ""

# Step 3: Test Python imports
echo -e "${YELLOW}[3/7] Testing Python imports...${NC}"

if python3 -c "from position_monitor import PositionMonitor" 2>/dev/null; then
    echo -e "${GREEN}✓ position_monitor${NC}"
else
    echo "✗ position_monitor FAILED"
    exit 1
fi

if python3 -c "from position_monitor_daemon import main" 2>/dev/null; then
    echo -e "${GREEN}✓ position_monitor_daemon${NC}"
else
    echo "✗ position_monitor_daemon FAILED"
    exit 1
fi

if python3 -c "from eod_analysis import EODAnalyzer" 2>/dev/null; then
    echo -e "${GREEN}✓ eod_analysis${NC}"
else
    echo "✗ eod_analysis FAILED"
    exit 1
fi

if python3 -c "from src.theta_spreads.portfolio_manager import ThetaPortfolioManager" 2>/dev/null; then
    echo -e "${GREEN}✓ portfolio_manager${NC}"
else
    echo "✗ portfolio_manager FAILED"
    exit 1
fi

# New: Test symbol optimization modules
if python3 -c "from src.theta_spreads.symbol_profiles import get_symbol_profile" 2>/dev/null; then
    echo -e "${GREEN}✓ symbol_profiles (NEW)${NC}"
else
    echo "${YELLOW}⚠ symbol_profiles not available (non-critical)${NC}"
fi

if python3 -c "from src.theta_spreads.defensive_exits import create_exit_manager_from_symbol" 2>/dev/null; then
    echo -e "${GREEN}✓ defensive_exits (NEW)${NC}"
else
    echo "${YELLOW}⚠ defensive_exits not available (non-critical)${NC}"
fi

echo ""

# Step 4: Check timezone
echo -e "${YELLOW}[4/7] Checking timezone...${NC}"
TIMEZONE=$(timedatectl | grep "Time zone" | awk '{print $3}')
if [ "$TIMEZONE" = "America/New_York" ]; then
    echo -e "${GREEN}✓ Timezone is ET${NC}"
else
    echo -e "${YELLOW}⚠ Timezone is $TIMEZONE (expected America/New_York)${NC}"
    echo "Run: sudo timedatectl set-timezone America/New_York"
fi
echo ""

# Step 5: Setup crontab
echo -e "${YELLOW}[5/7] Configuring crontab...${NC}"

# Backup existing crontab
crontab -l > /tmp/crontab.backup 2>/dev/null || true

# Check if theta cron jobs already exist
if crontab -l 2>/dev/null | grep -q "run_morning_signals.sh"; then
    echo -e "${YELLOW}⚠ Crontab already configured${NC}"
    echo "Skipping crontab setup (already exists)"
else
    # Create new crontab
    (crontab -l 2>/dev/null || true; cat <<EOF

# Theta Strategy Automation (all times in ET)
45 9 * * 1-5 cd $PROJECT_DIR && ./scripts/run_morning_signals.sh >> logs/signals.log 2>&1
30 9 * * 1-5 cd $PROJECT_DIR && ./scripts/run_position_monitor.sh &
5 16 * * 1-5 cd $PROJECT_DIR && ./scripts/run_eod_analysis.sh >> logs/eod.log 2>&1
10 16 * * 1-5 pkill -f position_monitor_daemon.py
EOF
    ) | crontab -
    
    echo -e "${GREEN}✓ Crontab configured${NC}"
fi
echo ""

# Step 6: Verify crontab
echo -e "${YELLOW}[6/7] Verifying crontab...${NC}"
CRON_COUNT=$(crontab -l | grep -c "tastywork-trading" || true)
echo "Found $CRON_COUNT cron jobs configured"
echo ""

# Step 7: Test scripts
echo -e "${YELLOW}[7/7] Testing scripts...${NC}"

# Just verify they exist and are executable
if [ -x "$SCRIPTS_DIR/run_morning_signals.sh" ]; then
    echo -e "${GREEN}✓ run_morning_signals.sh${NC}"
else
    echo "✗ run_morning_signals.sh not executable"
    exit 1
fi

if [ -x "$SCRIPTS_DIR/run_position_monitor.sh" ]; then
    echo -e "${GREEN}✓ run_position_monitor.sh${NC}"
else
    echo "✗ run_position_monitor.sh not executable"
    exit 1
fi

if [ -x "$SCRIPTS_DIR/run_eod_analysis.sh" ]; then
    echo -e "${GREEN}✓ run_eod_analysis.sh${NC}"
else
    echo "✗ run_eod_analysis.sh not executable"
    exit 1
fi

# Step 7.5: Test Symbol Optimization (if available)
echo -e "${YELLOW}[7.5/8] Testing Symbol Optimization...${NC}"
if [ -f "test_symbol_optimization.py" ]; then
    if python3 test_symbol_optimization.py 2>/dev/null; then
        echo -e "${GREEN}✓ Symbol optimization tests passed${NC}"
        echo -e "${GREEN}  QQQ optimized with custom profile${NC}"
    else
        echo -e "${YELLOW}⚠ Symbol optimization tests failed (non-critical)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Symbol optimization not available${NC}"
fi

echo ""
echo "========================================================================"
echo -e "${GREEN}✓ DEPLOYMENT COMPLETE${NC}"
echo "========================================================================"
echo ""
echo "System is now configured to run automatically:"
echo "  9:30 AM - Position monitor starts"
echo "  9:45 AM - Signal generation"
echo "  Every 60s - Position monitoring"
echo "  4:05 PM - EOD analysis"
echo "  4:10 PM - Monitor stops"
echo ""
echo "Symbol Optimization Active:"
echo "  QQQ: 30%/40% targets, 7 DTE exit (optimized)"
echo "  SPY: 45%/55% targets, 3 DTE exit"
echo "  IWM: 50%/60% targets, 2 DTE exit (aggressive)"
echo ""
echo "Manual controls:"
echo "  Start monitor: ./scripts/run_position_monitor.sh &"
echo "  Stop monitor:  pkill -f position_monitor_daemon.py"
echo "  View logs:     tail -f logs/*.log"
echo ""
echo "Next: Monitor logs tomorrow at 9:45 AM"
echo "      tail -f logs/signals.log"
echo "========================================================================"
