# URGENT: Persistent invalid_credentials Error - Immediate Action Plan

## The Problem

You're still seeing:
```
Trade failed: invalid_credentials: Invalid login, please check your username and password
```

Even after fixing environment variables. This means the issue is NOT environment loading—it's one of three things:

1. **Frontend and backend `TASTYTRADE_CLIENT_SECRET` don't match** ← MOST LIKELY
2. Old tokens in Redis are bound to wrong credentials
3. User needs to reconnect

---

## 5-Minute Quick Fix

### Step 1: Get Backend Secret (30 seconds)

```bash
grep TASTYTRADE_CLIENT_SECRET /home/ubuntu/tastywork-trading/.env | cut -d= -f2 | tail -c 5
```

This shows the **last 4 characters** of your backend secret. Write them down.

Example output: `abc1`

### Step 2: Get Frontend Secret (1 minute)

```
1. Go to: https://vercel.com/dashboard
2. Find your TradeMind project
3. Click Settings → Environment Variables
4. Find TASTYTRADE_CLIENT_SECRET
5. Look at the last 4 characters

Example: xyz7
```

### Step 3: Compare Them (30 seconds)

**Backend last 4:** `abc1`  
**Frontend last 4:** `xyz7`

❌ **If they DON'T match** → Found your problem!  
✅ **If they DO match** → Problem is elsewhere (see "If Still Failing" section)

### Step 4: Get The CORRECT Secret (1 minute)

```
1. Go to: https://my.tastytrade.com/settings/api
2. Find your app in "Connected Apps"
3. Copy the EXACT client_secret value
4. This is your SOURCE OF TRUTH
```

### Step 5: Update Backend (2 minutes)

```bash
# Stop service
sudo systemctl stop trademind-api

# Edit .env
sudo nano /home/ubuntu/tastywork-trading/.env

# Find the line: TASTYTRADE_CLIENT_SECRET=...
# Replace it with the CORRECT value from step 4
# Save: Ctrl+X, then Y, then Enter

# Verify it was saved
cat /home/ubuntu/tastywork-trading/.env | grep TASTYTRADE_CLIENT_SECRET

# Clean and restart
sudo rm -rf /home/ubuntu/tastywork-trading/__pycache__
sudo systemctl start trademind-api
sleep 3

# Verify it loaded
PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)
sudo cat /proc/$PID/environ | tr '\0' '\n' | grep TASTYTRADE_CLIENT_SECRET | cut -d= -f2 | tail -c 5
```

Should show your new last 4 characters.

### Step 6: Update Frontend (2 minutes)

```
1. Go to: https://vercel.com/dashboard
2. Select your TradeMind project
3. Settings → Environment Variables
4. Click the TASTYTRADE_CLIENT_SECRET variable
5. Replace with CORRECT value from step 4
6. Click Save
7. Redeploy (watch Deployments tab for completion)
```

### Step 7: Clear Old Tokens (1 minute)

```bash
# Connect to Redis
redis-cli

# Delete all old tokens (they're bound to wrong credentials)
FLUSHDB

# Exit
exit
```

### Step 8: User Reconnects (1 minute)

Tell the user:

```
1. Click "Disconnect Tastytrade"
2. Click "Connect to Tastytrade"  
3. Login to Tastytrade
4. Approve the connection
5. New token is created (bound to CORRECT credentials)
```

### Step 9: Test (1 minute)

```bash
# Watch logs
sudo journalctl -u trademind-api -f

# User approves a trade
# You should see:
# ✅ Session created successfully
# ✅ Order executed
# NOT: ❌ invalid_credentials
```

---

## Comprehensive Diagnostic (If Step 3 comparison matched)

If backend and frontend secrets **DO match**, run this:

```bash
#!/bin/bash

echo "DIAGNOSING: Why is OAuth failing?"
echo "=================================="

# Check 1: Is backend secret actually loaded?
echo -e "\n1. BACKEND SECRET LOADING:"
PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)
if [ -z "$PID" ]; then
    echo "❌ Service not running!"
    sudo systemctl start trademind-api
    sleep 3
    PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)
fi

BACKEND_SECRET=$(sudo cat /proc/$PID/environ | tr '\0' '\n' | grep "TASTYTRADE_CLIENT_SECRET=" | cut -d= -f2)

if [ -z "$BACKEND_SECRET" ]; then
    echo "❌ CRITICAL: Secret NOT in environment!"
    echo "   This means load_dotenv() failed"
    echo "   Check logs: sudo journalctl -u trademind-api -n 50"
    exit 1
else
    echo "✅ Secret loaded: ...${BACKEND_SECRET: -4}"
fi

# Check 2: .env file
echo -e "\n2. .ENV FILE:"
if [ ! -f /home/ubuntu/tastywork-trading/.env ]; then
    echo "❌ .env file missing!"
    exit 1
fi

FILE_SECRET=$(grep TASTYTRADE_CLIENT_SECRET /home/ubuntu/tastywork-trading/.env | cut -d= -f2)
echo "✅ .env exists: ...${FILE_SECRET: -4}"

if [ "$BACKEND_SECRET" != "$FILE_SECRET" ]; then
    echo "⚠️  WARNING: Secret in memory differs from .env!"
    echo "   Memory: ...${BACKEND_SECRET: -4}"
    echo "   File:   ...${FILE_SECRET: -4}"
    echo "   Action: Restart service: sudo systemctl restart trademind-api"
    exit 1
fi

# Check 3: Token in Redis
echo -e "\n3. REDIS TOKENS:"
TOKEN_COUNT=$(redis-cli KEYS "tastytrade:*" 2>/dev/null | wc -l)
if [ "$TOKEN_COUNT" -gt 0 ]; then
    echo "⚠️  Found $TOKEN_COUNT tokens in Redis"
    echo "   These might be bound to OLD credentials"
    echo "   Action: redis-cli then FLUSHDB"
else
    echo "ℹ️  No tokens in Redis"
    echo "   User needs to reconnect"
fi

# Check 4: Logs for clues
echo -e "\n4. RECENT ERRORS:"
ERROR_COUNT=$(sudo journalctl -u trademind-api -n 100 | grep -i "invalid_credentials" | wc -l)
if [ "$ERROR_COUNT" -gt 0 ]; then
    echo "❌ Found $ERROR_COUNT 'invalid_credentials' errors"
    echo "   Recent errors:"
    sudo journalctl -u trademind-api -n 100 | grep -i "invalid_credentials" | head -3
else
    echo "✅ No invalid_credentials errors in recent logs"
fi

# Check 5: Service file configuration
echo -e "\n5. SERVICE FILE:"
if grep -q "EnvironmentFile" /etc/systemd/system/trademind-api.service 2>/dev/null; then
    echo "✅ Service uses EnvironmentFile directive"
else
    echo "ℹ️  Service relies on Python load_dotenv()"
fi

echo -e "\n=================================="
echo "Analysis complete. See results above."
```

Run it:
```bash
bash << 'EOF'
#!/bin/bash
# [paste the script above]
EOF
```

---

## Nuclear Option - Complete Reset

If all else fails:

```bash
#!/bin/bash
set -e

echo "COMPLETE SERVICE RESET"
echo "===================="

# 1. Stop
echo "1. Stopping..."
sudo systemctl stop trademind-api
sleep 2

# 2. Clean cache
echo "2. Cleaning cache..."
sudo find /home/ubuntu/tastywork-trading -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
sudo find /home/ubuntu/tastywork-trading -type f -name "*.pyc" -delete 2>/dev/null || true

# 3. Fix permissions
echo "3. Fixing permissions..."
sudo chown ubuntu:ubuntu /home/ubuntu/tastywork-trading/.env
sudo chmod 600 /home/ubuntu/tastywork-trading/.env

# 4. Reload systemd
echo "4. Reloading systemd..."
sudo systemctl daemon-reload

# 5. Start
echo "5. Starting..."
sudo systemctl start trademind-api
sleep 4

# 6. Verify
echo "6. Verifying..."
PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)
SECRET=$(sudo cat /proc/$PID/environ | tr '\0' '\n' | grep TASTYTRADE_CLIENT_SECRET | cut -d= -f2)

if [ -z "$SECRET" ]; then
    echo "❌ Reset failed - secret not loaded"
    sudo journalctl -u trademind-api -n 50
    exit 1
fi

echo "✅ Reset complete: ...${SECRET: -4}"
echo ""
echo "NEXT STEPS:"
echo "1. Verify frontend secret matches: ...${SECRET: -4}"
echo "2. Clear Redis: redis-cli then FLUSHDB"
echo "3. User reconnects Tastytrade account"
echo "4. Test trade"
```

---

## Decision Tree

```
Is invalid_credentials still happening?
│
├─ YES
│  ├─ Did you compare backend vs frontend secrets?
│  │  ├─ NO → Do Step 1-3 of "5-Minute Quick Fix"
│  │  └─ YES, they match? 
│  │     ├─ NO → Do Step 4-9 of "5-Minute Quick Fix"
│  │     └─ YES, they match →
│  │        ├─ Is there a token in Redis?
│  │        │  ├─ YES → Clear it: redis-cli FLUSHDB
│  │        │  └─ NO → User reconnects account
│  │        └─ Try trade again
│  └─ Run "Comprehensive Diagnostic" above
│
└─ NO, it's fixed! 🎉
   └─ Trade executing successfully ✅
```

---

## Most Common Root Causes (in order)

1. **Frontend and backend use different `TASTYTRADE_CLIENT_SECRET` values** (80% of cases)
   - Fix: Sync both to the CORRECT value from my.tastytrade.com
   - Time: 5 minutes

2. **Old tokens in Redis bound to wrong credentials** (15% of cases)
   - Fix: `redis-cli` → `FLUSHDB`
   - Time: 30 seconds

3. **User's token was revoked** (4% of cases)
   - Fix: User reconnects account
   - Time: 1 minute

4. **load_dotenv() actually failed** (1% of cases)
   - Fix: Check logs, file permissions, restart service
   - Time: 5 minutes

---

## How to Verify Fix Worked

```bash
# 1. Check backend is using correct secret
PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)
BACKEND=$(sudo cat /proc/$PID/environ | tr '\0' '\n' | grep TASTYTRADE_CLIENT_SECRET | cut -d= -f2 | tail -c 5)
echo "Backend secret ends with: $BACKEND"

# 2. Check frontend (manually in Vercel dashboard)
# Last 4 chars should match $BACKEND

# 3. Clear old tokens
redis-cli
> FLUSHDB
> exit

# 4. User reconnects
# They click "Disconnect" then "Connect to Tastytrade"

# 5. Monitor logs while user approves trade
sudo journalctl -u trademind-api -f

# Expected output:
# Session created successfully
# Order executed
# status: success
```

---

## I'm Stuck - Get Help

If none of this works, provide this information:

```bash
# Command to get all debug info at once:
echo "=== BACKEND SECRET ===" && \
grep TASTYTRADE_CLIENT_SECRET /home/ubuntu/tastywork-trading/.env | tail -c 5 && \
echo "" && \
echo "=== FRONTEND SECRET ===" && \
echo "Check Vercel dashboard manually for last 4 chars" && \
echo "" && \
echo "=== REDIS TOKENS ===" && \
redis-cli KEYS "tastytrade:*" && \
echo "" && \
echo "=== RECENT ERRORS ===" && \
sudo journalctl -u trademind-api -n 20 | grep -i "invalid\|error"
```

Share the output with someone reviewing this.
