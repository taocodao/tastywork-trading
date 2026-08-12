# IB Trading System - Complete Diagnosis

**Date:** February 5, 2026 @ 3:10 PM EST  
**Status:** 🎯 **TWO SEPARATE ISSUES IDENTIFIED**

---

## Executive Summary

| Issue | Root Cause | Fix Required |
|-------|------------|--------------|
| **Theta scheduler places 0 orders** | IB connection fails with `CancelledError` | Fix IB connection config |
| **Wrong individual stock trades** | IB-program-trading Docker container using `watchlist.csv` | Stop/reconfigure Docker container |

---

## 🔍 Issue #1: Theta Scheduler Not Placing Orders

### Evidence from Logs:
```
Connected       
Disconnected.   
ERROR - API connection failed: CancelledError()
❌ Failed to connect to IB:
  Total qualified puts: 0
  Generated 0 entry signals
  IB Orders Placed: 0/0
```

### Root Cause Analysis:

**What's Happening:**
1. Scheduler tries to connect to IB Gateway at `34.203.194.137:4004`
2. Connection succeeds briefly
3. Immediately disconnects with `CancelledError`
4. Cannot fetch market data → No qualified puts found

**Why It Fails:**

The config in [config.py](file:///d:/Projects/tastywork-trading-1/config.py) line 79:
```python
IB_HOST: str = "34.203.194.137"  # Public EC2 IP
```

But on EC2, the scheduler is connecting to **itself via public IP** instead of `127.0.0.1` (localhost). This can cause:
- NAT/firewall issues
- Timeout on self-connection through public network
- Client ID conflicts if multiple connections

**The CONFIG on EC2** may have a different `IB_HOST` value. Need to verify.

### Current Process Running:
```
ubuntu  562  /usr/bin/python3 /home/ubuntu/tastywork-trading/theta_monitor_continuous.py
```

This runs `run_theta_scheduler.py --once` from `/home/ubuntu/tastywork-trading/` every 5 minutes.

### THETA_UNIVERSE is Correct:
From EC2 logs, verified the config has only ETFs:
```python
THETA_UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "TLT", "IEF", ...]
```

---

## 🔍 Issue #2: Individual Stock Trades (NFLX, MSTR, etc.)

### Evidence:
IB Paper account shows trades for individual stocks at 9:30 AM:
- NFLX, MSTR, KTOS, MSFT, COST, ADBE, AEP, RKLI

### Root Cause:

**Separate Docker Container Running:**
```
root  3741  python -m uvicorn src.api_server:app --host 0.0.0.0 --port 8000
root  3773  python src/signal_service.py
root  3909  python src/dashboard.py
root  4067  python /app/src/dashboard.py
```

These processes run from **IB-program-trading** project (Docker container), not **tastywork-trading**.

**The watchlist.csv it uses contains 110 INDIVIDUAL STOCKS:**

From [watchlist.csv](file:///d:/Projects/IB-program-trading/watchlist.csv):
| Line | Symbol | Notes |
|------|--------|-------|
| 69 | NFLX | ✅ Found |
| 65 | MSTR | ✅ Found |
| 54 | KTOS | ✅ Found |
| 64 | MSFT | ✅ Found |
| 31 | COST | ✅ Found |
| 4 | ADBE | ✅ Found |
| 6 | AEP | ✅ Found |

This is a **completely different trading system** from the Theta strategy!

---

## 📊 System Architecture (Actual)

```
EC2 Server (34.203.194.137)
├── Port 4004: IB Gateway (Docker)
│
├── tastywork-trading/ (Theta Strategy - YOUR SYSTEM)
│   ├── theta_monitor_continuous.py (PID 562) ← Runs 24/7
│   ├── run_theta_scheduler.py ← Called every 5 min
│   ├── config.py ← THETA_UNIVERSE (ETFs only)
│   └── PROBLEM: IB connection fails immediately
│
└── IB-program-trading/ (Docker Container - DIFFERENT SYSTEM)
    ├── src/api_server.py (PID 3741)
    ├── src/signal_service.py (PID 3773)
    ├── src/dashboard.py (PID 3909)
    ├── watchlist.csv ← 110 INDIVIDUAL STOCKS
    └── trading_system.py ← Buys options based on AI signals
```

---

## 🔧 Recommended Fixes

### Fix #1: IB Connection for Theta Scheduler

**Option A: Update EC2 config to use localhost**
```bash
# On EC2
cd ~/tastywork-trading
nano config.py

# Change:
IB_HOST: str = "127.0.0.1"  # Use localhost on EC2
```

**Option B: Investigate CancelledError**
- Check IB Gateway container logs: `docker logs ib-gateway-paper`
- Check for client ID conflicts (scheduler uses ID 3000)
- Check if Docker is exposing port correctly

### Fix #2: Stop Individual Stock Trading

If you don't want the IB-program-trading Docker to place trades:

```bash
# Option A: Stop the Docker container
docker stop <container_name>

# Option B: Just disable trading
# Edit the watchlist.csv to empty or update trading_system.py

# Option C: Update watchlist to ETFs only
# Replace individual stocks with SPY, QQQ, IWM
```

---

## 🔍 Verification Commands

**Check IB Gateway status:**
```bash
docker ps | grep ib-gateway
docker logs ib-gateway-paper | tail -50
```

**Check what's connecting to IB Gateway:**
```bash
netstat -tulpn | grep 4004
```

**Test IB connection manually:**
```bash
cd ~/tastywork-trading
python3 -c "
from ib_insync import IB
ib = IB()
ib.connect('127.0.0.1', 4004, clientId=9999)
print('Connected!' if ib.isConnected() else 'Failed')
ib.disconnect()
"
```

---

## 📋 Summary

| Component | Status | Problem |
|-----------|--------|---------|
| **Theta Monitor** | ✅ Running | Works fine |
| **Theta Scheduler** | ❌ Failing | IB connection `CancelledError` |
| **IB Gateway** | ✅ Running | Port 4004 listening |
| **IB Connection** | ❌ Broken | Disconnects immediately |
| **Docker Container** | ⚠️ Running | Trades individual stocks |

**Two independent systems are running:**
1. **Your Theta Strategy** → Broken IB connection → 0 trades
2. **IB-program-trading Docker** → Working → Individual stock trades

The individual stock trades you saw are NOT bugs in the Theta system - they're from a completely separate trading application.
