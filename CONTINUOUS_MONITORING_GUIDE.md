# Continuous Monitoring Service - Deployment Guide

## Overview

The continuous monitoring service runs **24/7** and provides:

- ✅ **Morning analysis at 9:35 AM ET** - Scans for new trades
- ✅ **Position monitoring every 5 minutes** - Checks exit targets
- ✅ **Real-time profit-taking** - Closes winners immediately
- ✅ **Auto-restart on failure** - Systemd keeps it running
- ✅ **Runs all the time** - No market hours detection (flexible for any market)

---

## Files Created

1. **`theta_monitor_continuous.py`** - Main continuous monitoring script
2. **`theta-monitor.service`** - Systemd service definition
3. **`deploy_continuous_monitor.sh`** - Deployment automation script

---

## Quick Deployment

### Option 1: Automated Deployment

```bash
# Upload files to EC2
scp -i "key.pem" theta_monitor_continuous.py theta-monitor.service deploy_continuous_monitor.sh ubuntu@ec2:~/tastywork-trading/

# SSH and deploy
ssh -i "key.pem" ubuntu@ec2
cd ~/tastywork-trading
chmod +x deploy_continuous_monitor.sh
./deploy_continuous_monitor.sh
```

### Option 2: Manual Step-by-Step

```bash
# 1. Upload files
scp -i "key.pem" theta_monitor_continuous.py theta-monitor.service ubuntu@ec2:~/tastywork-trading/

# 2. SSH to EC2
ssh -i "key.pem" ubuntu@ec2

# 3. Install service
cd ~/tastywork-trading
sudo cp theta-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable theta-monitor
sudo systemctl start theta-monitor

# 4. Check status
sudo systemctl status theta-monitor
```

---

## How It Works

### Main Loop

```
┌─────────────────────────────────────┐
│   Continuous Monitoring Loop        │
│   (Runs 24/7)                       │
└─────────────────────────────────────┘
          │
          ├──> Check time
          │
          ├──> Is it 9:35 AM ET?
          │    ├─ YES → Run morning analysis
          │    │         - Scan option chains
          │    │         - Generate entry signals
          │    │         - Place new orders
          │    │
          │    └─ NO  → Skip
          │
          ├──> Has 5 minutes passed?
          │    ├─ YES → Monitor positions
          │    │         - Load theta_positions.json
          │    │         - Check current prices
          │    │         - Calculate profit %
          │    │         - Close if targets hit
          │    │
          │    └─ NO  → Skip
          │
          ├──> Sleep 10-60 seconds
          │
          └──> REPEAT (forever)
```

### Example Day

```
9:30 AM  - Market opens
9:35 AM  - ⭐ MORNING ANALYSIS runs
           - Scans SPY, QQQ, IWM, etc.
           - Finds 3 qualified puts
           - Places 3 orders
9:40 AM  - Position check (all positions tracked)
9:45 AM  - Position check
...
10:20 AM - Position check
           - SPY 580P hit 50% profit target
           - 🎯 AUTO-CLOSES position
10:25 AM - Position check
...
4:00 PM  - Market closes
4:05 PM  - Position check (continues monitoring)
...
Next day 9:35 AM - Morning analysis runs again
```

---

## Management Commands

### Check Status
```bash
sudo systemctl status theta-monitor
```

### View Live Logs
```bash
tail -f ~/theta_monitor.log
```

### Restart Service
```bash
sudo systemctl restart theta-monitor
```

### Stop Service
```bash
sudo systemctl stop theta-monitor
```

### Start Service
```bash
sudo systemctl start theta-monitor
```

### Disable Auto-Start
```bash
sudo systemctl disable theta-monitor
```

---

## Monitoring & Debugging

### Check if service is running
```bash
ps aux | grep theta_monitor
```

### View recent logs
```bash
tail -50 ~/theta_monitor.log
```

### View error logs
```bash
tail -50 ~/theta_monitor_error.log
```

### Check systemd journal
```bash
sudo journalctl -u theta-monitor -f
```

---

## Configuration

### Change Position Check Interval

Edit `theta_monitor_continuous.py`:

```python
POSITION_CHECK_INTERVAL = 300  # Change from 300s (5 min) to desired value
```

### Change Morning Analysis Time

```python
MORNING_ANALYSIS_TIME = dt_time(9, 35)  # Change to desired time (ET)
```

After changes:
```bash
sudo systemctl restart theta-monitor
```

---

## Comparison: Cron vs Continuous

| Feature | Cron (Old) | Continuous (New) |
|---------|------------|------------------|
| **Entry analysis** | Once/day at 9:35 AM | Once/day at 9:35 AM |
| **Exit monitoring** | Once/day | Every 5 minutes |
| **Profit taking** | Next day | Real-time |
| **Running** | On schedule only | 24/7 |
| **Auto-restart** | No | Yes |
| **Market hours** | Hardcoded | Flexible |
| **Resource usage** | Lower | Slightly higher |
| **Response time** | Slow (24h) | Fast (5min) |

---

## Benefits of Continuous

1. **Faster Profit-Taking**
   - Old: Check once/day at 9:35 AM
   - New: Check every 5 minutes
   - Result: Lock in gains faster, reduce risk

2. **Better Risk Management**
   - Respond to adverse moves within 5 minutes
   - Can catch intraday volatility spikes

3. **More Opportunities**
   - Can add afternoon entry scans (future)
   - Flexible for extended hours trading

4. **Production-Ready**
   - Auto-restart on crashes
   - Systemd monitoring
   - Proper logging

---

## Troubleshooting

### Service won't start

```bash
# Check logs
sudo journalctl -u theta-monitor -n 50

# Check file permissions
ls -l ~/tastywork-trading/theta_monitor_continuous.py

# Test script manually
cd ~/tastywork-trading
python3 theta_monitor_continuous.py
```

### Service crashes repeatedly

```bash
# Check error log
cat ~/theta_monitor_error.log

# Check IB Gateway connection
docker ps | grep ib-gateway

# Test IB connection manually
python3 check_ib_account.py
```

### Positions not being monitored

```bash
# Check position file exists
cat ~/tastywork-trading/theta_positions.json

# Check logs for monitoring messages
grep "MONITORING POSITIONS" ~/theta_monitor.log

# Verify 5 minute intervals
tail -f ~/theta_monitor.log
```

---

## Migration from Cron

The deployment script automatically:
1. ✅ Removes old cron job
2. ✅ Installs systemd service
3. ✅ Starts continuous monitor

**No manual migration needed!**

---

## Next Steps

1. **Deploy the service:**
   ```bash
   ./deploy_continuous_monitor.sh
   ```

2. **Monitor the logs:**
   ```bash
   tail -f ~/theta_monitor.log
   ```

3. **Wait for 9:35 AM** to see morning analysis

4. **Watch it monitor positions** every 5 minutes

5. **Verify real-time exits** when targets hit

---

## Success Indicators

After deployment, you should see:

```
✅ systemctl status shows "active (running)"
✅ theta_monitor.log shows regular "Iteration X" messages
✅ Morning analysis runs at 9:35 AM ET
✅ Position checks every 5 minutes
✅ Exit signals processed immediately
```

**The service is now running 24/7 with real-time position management!** 🚀
