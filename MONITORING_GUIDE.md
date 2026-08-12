# Monitoring & Testing Theta Sprint Trades

## 📊 How to Monitor Trade Execution

### 1. Check Scheduler Logs (Real-time)

**Via SSH:**
```bash
ssh -i "path/to/key.pem" ubuntu@ec2-34-203-194-137.compute-1.amazonaws.com
cd ~/tastywork-trading
tail -f theta_scheduler.log
```

**What to look for:**
```
✅ IB Order #12345 placed successfully
  SELL SPY 580P x1 @ $5.00
  Premium: $500.00, Capital: $58,000.00
```

### 2. Check Cron Job Logs

```bash
tail -f ~/theta_cron.log
```

### 3. Check IB Gateway/TWS

- Open TWS or IB Gateway web interface
- Go to **Account** → **Orders**
- Go to **Account** → **Portfolio**
- Look for filled orders and positions

### 4. Check Position File (Local Storage)

```bash
cat ~/tastywork-trading/theta_positions.json
```

This file tracks all active positions with:
- Entry price, strike, expiration
- Current profit
- Exit targets (50%, 60%, 75%, 90%)
- Days in trade

---

## 🧪 **Testing the Full Lifecycle (Position + Risk Management)**

Since no trades were placed today (no signals met criteria), let's **manually place a test trade** to verify the full flow:

### Option 1: Lower the Entry Threshold (Quick Test)

Temporarily lower the confidence threshold to generate signals:

**On EC2:**
```bash
cd ~/tastywork-trading
# Edit run_theta_scheduler.py and change min confidence from 60 to 30
sed -i 's/MIN_CONFIDENCE_SCORE = 60/MIN_CONFIDENCE_SCORE = 30/g' run_theta_scheduler.py
python3 run_theta_scheduler.py --once
# Change it back
sed -i 's/MIN_CONFIDENCE_SCORE = 30/MIN_CONFIDENCE_SCORE = 60/g' run_theta_scheduler.py
```

### Option 2: Manually Place Test Trade via Script

Create a test script that places a trade and adds it to the position tracker:

**File: `manual_test_trade.py`**
```python
from ib_insync import *
from datetime import datetime
import json
import uuid

# Connect to IB Gateway
ib = IB()
ib.connect('127.0.0.1', 4004, clientId=120)

# Place a small test order
contract = Option('SPY', '20260320', 580, 'P', 'SMART')
ib.qualifyContracts(contract)

# Get market price
ticker = ib.reqMktData(contract)
ib.sleep(2)
bid = ticker.bid if ticker.bid and ticker.bid > 0 else 5.00

# Place order
order = LimitOrder('SELL', 1, bid)
trade = ib.placeOrder(contract, order)
ib.sleep(5)

print(f"Order ID: {trade.order.orderId}")
print(f"Status: {trade.orderStatus.status}")

# If filled, add to position tracker
if trade.orderStatus.filled > 0:
    position = {
        "id": str(uuid.uuid4()),
        "symbol": "SPY",
        "strike": 580.0,
        "expiration": "2026-03-20",
        "dte": 45,
        "contracts": 1,
        "entry_price": trade.orderStatus.avgFillPrice,
        "entry_date": datetime.now().isoformat(),
        "total_premium": trade.orderStatus.avgFillPrice * 100,
        "status": "open",
        "exit_targets": {
            "target_50": trade.orderStatus.avgFillPrice * 0.50,
            "target_60": trade.orderStatus.avgFillPrice * 0.60,
            "target_75": trade.orderStatus.avgFillPrice * 0.75,
            "target_90": trade.orderStatus.avgFillPrice * 0.90
        }
    }
    
    # Save to positions file
    try:
        with open('theta_positions.json', 'r') as f:
            positions = json.load(f)
    except:
        positions = {"positions": []}
    
    positions["positions"].append(position)
    
    with open('theta_positions.json', 'w') as f:
        json.dump(positions, f, indent=2)
    
    print(f"✅ Position tracked: {position['id']}")
    print(f"Entry: ${position['entry_price']}, Premium: ${position['total_premium']}")

ib.disconnect()
```

Upload and run:
```bash
scp -i "key.pem" manual_test_trade.py ubuntu@ec2:~/tastywork-trading/
ssh -i "key.pem" ubuntu@ec2
cd ~/tastywork-trading
python3 manual_test_trade.py
```

---

## 📈 **Monitoring Position & Risk Management**

### 1. Check Active Positions

```bash
ssh -i "key.pem" ubuntu@ec2
cd ~/tastywork-trading
python3 -c "
import json
with open('theta_positions.json', 'r') as f:
    data = json.load(f)
    for pos in data['positions']:
        if pos['status'] == 'open':
            print(f\"{pos['symbol']} {pos['strike']}P\")
            print(f\"  Entry: ${pos['entry_price']}\")
            print(f\"  Premium: ${pos['total_premium']}\")
            print(f\"  Targets: 50%=${pos['exit_targets']['target_50']:.2f}\")
"
```

### 2. Run Exit Monitor (Checks Profit Targets)

The scheduler has exit logic that runs automatically. To test it manually:

```bash
cd ~/tastywork-trading
# Run scheduler again - it will check existing positions for exit signals
python3 run_theta_scheduler.py --once
```

**What it does:**
1. Loads `theta_positions.json`
2. Checks current option prices
3. Calculates profit %
4. Places BUY TO CLOSE orders if profit targets hit (50%/60%/75%/90%)

### 3. Check Risk Dashboard (If Available)

If you have the TradeM frontend running:

```
http://your-frontend-url/dashboard
```

It should show:
- Active positions
- Current profit/loss
- Risk exposure ($heat)
- Exit targets

---

## 🔍 **What to Expect After a Trade Executes**

### Immediately After Entry:

1. **Log Entry:**
```
✅ IB Order #12 placed successfully
SELL SPY 580P x1 @ $5.25
Premium: $525.00
```

2. **Position File Updated** (`theta_positions.json`):
```json
{
  "positions": [{
    "id": "abc-123",
    "symbol": "SPY",
    "strike": 580.0,
    "entry_price": 5.25,
    "status": "open",
    "exit_targets": {
      "target_50": 2.625,
      "target_60": 3.15,
      "target_75": 3.9375,
      "target_90": 4.725
    }
  }]
}
```

3. **IB Portfolio Shows Position:**
- Short 1 SPY 580P
- Premium collected: $525

### During Monitoring (Every Scheduler Run):

The scheduler will:
1. Check current option price
2. Calculate profit %
3. If price drops to $2.625 (50% target) → Place BUY TO CLOSE order
4. Update position status to "closed"
5. Log the exit

### After Exit:

```
✅ Exit signal: SPY 580P - 50% profit target hit
Current price: $2.60, Entry: $5.25, Profit: 50.5%
✅ IB Order #15: BUY 1 SPY 580P @ $2.60
✅ Position closed - Profit: $265.00 (50.5%)
```

---

## 📊 **Quick Health Check Commands**

### Check if scheduler is working:
```bash
ssh ubuntu@ec2 "cd ~/tastywork-trading && python3 run_theta_scheduler.py --once | grep -E '(✅|❌|entry signals|Orders Placed)'"
```

### Check active positions:
```bash
ssh ubuntu@ec2 "cat ~/tastywork-trading/theta_positions.json | jq '.positions[] | select(.status==\"open\")'"
```

### Check recent log:
```bash
ssh ubuntu@ec2 "tail -20 ~/tastywork-trading/theta_scheduler.log"
```

### Check IB account positions:
```bash
ssh ubuntu@ec2 "cd ~/tastywork-trading && python3 check_ib_account.py"
```

---

## 🎯 **Recommended Testing Flow**

1. **Place Manual Test Trade** (using `manual_test_trade.py`)
2. **Verify Position Tracked** (`cat theta_positions.json`)
3. **Wait 5 minutes** (or manually update price in position file to simulate profit)
4. **Run Scheduler Again** (`python3 run_theta_scheduler.py --once`)
5. **Check Exit Logic Triggered** (should place BUY order if target hit)
6. **Verify Position Closed** (status changed to "closed")

---

## ⚡ **Real-time Monitoring Script**

Create a monitoring dashboard:

```bash
#!/bin/bash
# monitor_theta.sh
while true; do
  clear
  echo "=== THETA SPRINT MONITOR ==="
  echo "Time: $(date)"
  echo ""
  echo "ACTIVE POSITIONS:"
  ssh ubuntu@ec2 "python3 -c '
import json
try:
    with open(\"/home/ubuntu/tastywork-trading/theta_positions.json\") as f:
        data = json.load(f)
        open_pos = [p for p in data[\"positions\"] if p[\"status\"]==\"open\"]
        print(f\"Total: {len(open_pos)}\")
        for p in open_pos:
            print(f\"  {p[\"symbol\"]} {p[\"strike\"]}P - Entry: ${p[\"entry_price\"]}\")
except:
    print(\"No positions\")
'"
  echo ""
  echo "RECENT LOG:"
  ssh ubuntu@ec2 "tail -5 ~/tastywork-trading/theta_scheduler.log"
  sleep 60
done
```

Run: `bash monitor_theta.sh`

---

## 📝 **Summary**

**Monitoring Methods:**
1. ✅ SSH into EC2 and check `theta_scheduler.log`
2. ✅ Check `theta_positions.json` for active positions
3. ✅ Check IB Gateway/TWS for filled orders
4. ✅ Use `check_ib_account.py` to query IB API

**Testing Full Lifecycle:**
1. Place manual test trade via script
2. Verify position tracked in JSON
3. Run scheduler to check exit logic
4. Verify position closes when target hit

**The system is now ready and will:**
- Run automatically at 9:35 AM daily
- Place trades when opportunities arise
- Track positions in `theta_positions.json`
- Monitor for exit targets (50%/60%/75%/90%)
- Close positions automatically when targets hit
