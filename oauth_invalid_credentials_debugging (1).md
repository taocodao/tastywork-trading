# Debugging Persistent OAuth Invalid_Credentials - Comprehensive Troubleshooting Guide

## Quick Diagnosis Flowchart

Before diving into 8 detailed questions, run this quick test:

```bash
# 1. Check if service is actually running the new code
sudo systemctl stop trademind-api
sudo rm -rf /home/ubuntu/tastywork-trading/__pycache__
sudo systemctl start trademind-api

# 2. Immediately check logs for environment loading
sudo journalctl -u trademind-api -f

# 3. Look for these lines:
# "✅ Environment loaded from /home/ubuntu/tastywork-trading/.env"
# "✅ TASTYTRADE_CLIENT_ID: ABC123xyz..."
# "✅ TASTYTRADE_CLIENT_SECRET: XYZ7..."

# If you DON'T see these lines, environment isn't loading
# If you DO see them, environment loaded but OAuth still failing
```

---

## Question 1: Why Might Systemd Still Run Old Code After Restart?

### Answer: Multiple Causes

#### Cause 1A: Python Bytecode Caching (.pyc files)

**What happens:**
- Python compiles `.py` files to `.pyc` bytecode in `__pycache__/`
- Systemd restarts the process but `.pyc` files still exist
- Python uses cached bytecode instead of reading new `.py` file
- Your code changes are completely ignored

**How to verify:**
```bash
# Check if __pycache__ exists
find /home/ubuntu/tastywork-trading -name "__pycache__" -type d

# List what's in it
ls -la /home/ubuntu/tastywork-trading/__pycache__/

# Check modification times
stat /home/ubuntu/tastywork-trading/tasty_api_server.py
stat /home/ubuntu/tastywork-trading/__pycache__/tasty_api_server*.pyc
```

**If .pyc is older than .py:** Bytecode cache is stale

**Solution:**
```bash
# ALWAYS do this before restarting after code changes
sudo systemctl stop trademind-api
sudo rm -rf /home/ubuntu/tastywork-trading/__pycache__
sudo find /home/ubuntu/tastywork-trading -name "*.pyc" -delete
sudo systemctl start trademind-api

# Verify files are gone
ls -la /home/ubuntu/tastywork-trading/__pycache__  # Should not exist
```

#### Cause 1B: systemctl daemon-reload Not Run

**What happens:**
- You edit `/etc/systemd/system/trademind-api.service`
- Run `systemctl restart trademind-api`
- Changes to service file are ignored (systemd has cached the old version)
- The Python code may have the right credentials but service file doesn't use them

**When to use daemon-reload:**
```bash
# ALWAYS run this if you modify the .service file
sudo systemctl daemon-reload

# Then restart
sudo systemctl restart trademind-api
```

**When NOT needed:**
- If you only change Python code (.py files)
- If you only change .env file
- daemon-reload is only for /etc/systemd/system/*.service changes

#### Cause 1C: Python Module Import Caching

**What happens:**
```python
# In file A: tasty_api_server.py
from dotenv import load_dotenv
load_dotenv()
TASTYTRADE_CLIENT_SECRET = os.getenv('TASTYTRADE_CLIENT_SECRET')

# In file B: tastytrade_utils.py
import os
def create_user_session(refresh_token):
    client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')  # ← Gets same value as file A
```

If file A loads credentials, file B can access them.

**But this fails if:**
```python
# ❌ WRONG - tastytrade_utils.py loaded BEFORE load_dotenv() in main file
import tastytrade_utils  # This imports and caches os module

# Then later:
load_dotenv()  # Too late! tastytrade_utils already imported os
```

**Solution: Verify import order**
```python
# ✅ CORRECT - tasty_api_server.py
from dotenv import load_dotenv
import os

# Load IMMEDIATELY at module level
load_dotenv('/home/ubuntu/tastywork-trading/.env')

# NOW import other modules (they'll see loaded variables)
from tastytrade_utils import create_user_session
from fastapi import FastAPI

app = FastAPI()
```

### Verification Steps for Question 1

```bash
# 1. Delete bytecode cache
sudo rm -rf /home/ubuntu/tastywork-trading/__pycache__
find /home/ubuntu/tastywork-trading -name "*.pyc" -delete

# 2. Check service file hasn't changed recently
ls -la /etc/systemd/system/trademind-api.service

# 3. If you edited service file, reload
sudo systemctl daemon-reload

# 4. Stop, clean, start
sudo systemctl stop trademind-api
sleep 2
sudo systemctl start trademind-api

# 5. Check logs immediately
sudo journalctl -u trademind-api -n 20
```

---

## Question 2: How Can I Verify the Running Process Is Using New Code?

### Method 1: Inspect Running Process Environment Variables

**Get the PID:**
```bash
# Find Python process PID
PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)
echo "Process PID: $PID"
```

**Read environment variables the process sees:**
```bash
# Show all environment variables the process has
sudo cat /proc/$PID/environ | tr '\0' '\n' | sort

# Filter for Tastytrade variables
sudo cat /proc/$PID/environ | tr '\0' '\n' | grep TASTYTRADE
```

**Expected output:**
```
TASTYTRADE_CLIENT_ID=ABC123xyz
TASTYTRADE_CLIENT_SECRET=XYZ789abc
```

**If you see empty or wrong values:**
- Environment wasn't loaded
- load_dotenv() failed silently
- .env file wasn't read

### Method 2: Check Running Python File Path

```bash
# See what Python process is running
sudo ps aux | grep python3 | grep tasty_api_server

# Check the actual file being executed
sudo lsof -p $PID | grep tasty_api_server.py

# Verify modification time of running file
stat /home/ubuntu/tastywork-trading/tasty_api_server.py
```

### Method 3: Add Health Endpoint That Returns Credentials Status

```python
# In tasty_api_server.py - Add this endpoint for debugging

from fastapi import FastAPI
import os

app = FastAPI()

@app.get("/health/debug")
async def health_debug():
    """Debug endpoint to verify environment variables are loaded."""
    return {
        "status": "ok",
        "environment_loaded": {
            "TASTYTRADE_CLIENT_ID": os.getenv('TASTYTRADE_CLIENT_ID') is not None,
            "TASTYTRADE_CLIENT_SECRET": os.getenv('TASTYTRADE_CLIENT_SECRET') is not None,
        },
        "client_id_prefix": os.getenv('TASTYTRADE_CLIENT_ID', '')[:10] if os.getenv('TASTYTRADE_CLIENT_ID') else 'NOT SET',
        "client_secret_prefix": os.getenv('TASTYTRADE_CLIENT_SECRET', '')[:4] if os.getenv('TASTYTRADE_CLIENT_SECRET') else 'NOT SET',
        "env_file_exists": os.path.exists('/home/ubuntu/tastywork-trading/.env'),
        "env_file_readable": os.access('/home/ubuntu/tastywork-trading/.env', os.R_OK),
    }

# Now test it
# curl http://localhost:8000/health/debug
```

**Test it:**
```bash
# From your local machine (or server)
curl http://localhost:8000/health/debug

# Expected output:
# {"status":"ok","environment_loaded":{"TASTYTRADE_CLIENT_ID":true,"TASTYTRADE_CLIENT_SECRET":true},"client_id_prefix":"ABC123xyz","client_secret_prefix":"XYZ7",...}

# If shows false for either variable: Environment not loaded!
```

### Method 3B: Log Environment at Startup

```python
# In tasty_api_server.py - Add comprehensive logging

import os
import logging
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment
ENV_FILE = '/home/ubuntu/tastywork-trading/.env'
logger.info(f"=== STARTUP DEBUG ===")
logger.info(f"Loading .env from: {ENV_FILE}")
logger.info(f".env exists: {os.path.exists(ENV_FILE)}")
logger.info(f".env readable: {os.access(ENV_FILE, os.R_OK)}")

result = load_dotenv(ENV_FILE, override=True)  # Use override=True to force reload
logger.info(f"load_dotenv() returned: {result}")

# Check variables
client_id = os.getenv('TASTYTRADE_CLIENT_ID')
client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')

logger.info(f"TASTYTRADE_CLIENT_ID loaded: {client_id is not None}")
if client_id:
    logger.info(f"TASTYTRADE_CLIENT_ID value (first 10 chars): {client_id[:10]}")
    logger.info(f"TASTYTRADE_CLIENT_ID length: {len(client_id)}")

logger.info(f"TASTYTRADE_CLIENT_SECRET loaded: {client_secret is not None}")
if client_secret:
    logger.info(f"TASTYTRADE_CLIENT_SECRET value (first 4 chars): {client_secret[:4]}")
    logger.info(f"TASTYTRADE_CLIENT_SECRET length: {len(client_secret)}")

logger.info(f"=== END STARTUP DEBUG ===")

# Now check logs
# sudo journalctl -u trademind-api -f
```

### Verification Steps for Question 2

```bash
# 1. Get PID
PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)

# 2. Check environment variables
echo "=== Environment Variables ==="
sudo cat /proc/$PID/environ | tr '\0' '\n' | grep TASTYTRADE

# 3. Check running file
echo "=== Running File ==="
sudo lsof -p $PID | grep tasty_api_server

# 4. Call health endpoint
echo "=== Health Check ==="
curl http://localhost:8000/health/debug

# 5. Check logs
echo "=== Logs ==="
sudo journalctl -u trademind-api -n 50 | grep -E "STARTUP|TASTYTRADE|Environment"
```

---

## Question 3: Why Would load_dotenv() Still Fail With Absolute Path?

### Cause 3A: File Permissions Issue

**Problem:**
```
Service runs as: ubuntu user
.env file owned by: root user
Result: ubuntu can't read the file!
```

**Verify permissions:**
```bash
# Check .env file permissions
ls -la /home/ubuntu/tastywork-trading/.env

# Should show something like:
# -rw-r--r-- 1 ubuntu ubuntu 500 Dec 25 12:00 .env
#  ^^^ Owner has read/write
#      ^^^ Group can read
#          ^^^ Others can read

# If shows "root root" instead of "ubuntu ubuntu", that's the problem!
```

**Fix permissions:**
```bash
# Make sure ubuntu owns the file
sudo chown ubuntu:ubuntu /home/ubuntu/tastywork-trading/.env

# Make file readable by owner (600 = rw-------)
sudo chmod 600 /home/ubuntu/tastywork-trading/.env

# Verify
ls -la /home/ubuntu/tastywork-trading/.env
# Should show: -rw------- 1 ubuntu ubuntu ...
```

**Test as ubuntu user:**
```bash
# Can the ubuntu user read it?
sudo -u ubuntu cat /home/ubuntu/tastywork-trading/.env

# If you get permission denied, fix permissions above
```

### Cause 3B: File Not Actually Saved

**Problem:**
You edited the file but it wasn't actually saved.

**Verify:**
```bash
# Check file size
ls -la /home/ubuntu/tastywork-trading/.env

# View contents
cat /home/ubuntu/tastywork-trading/.env

# Check modification time
stat /home/ubuntu/tastywork-trading/.env | grep Modify

# If Modify time is old, file wasn't updated!
```

**If file is empty or old:**
```bash
# Recreate it
echo "TASTYTRADE_CLIENT_ID=ABC123xyz" > /home/ubuntu/tastywork-trading/.env
echo "TASTYTRADE_CLIENT_SECRET=XYZ789abc" >> /home/ubuntu/tastywork-trading/.env

# Verify
cat /home/ubuntu/tastywork-trading/.env

# Fix permissions
sudo chmod 600 /home/ubuntu/tastywork-trading/.env
sudo chown ubuntu:ubuntu /home/ubuntu/tastywork-trading/.env
```

### Cause 3C: load_dotenv() Called Before Path is Valid

**Problem:**
```python
# ❌ WRONG - load_dotenv() called before variables are set up
load_dotenv('/home/ubuntu/tastywork-trading/.env')

# But this could fail if:
# 1. .env file hasn't been synced yet
# 2. File system hasn't mounted yet (rare in systemd)
# 3. Working directory not set in systemd
```

**Solution: Add error handling**
```python
import os
from dotenv import load_dotenv

ENV_FILE = '/home/ubuntu/tastywork-trading/.env'

# Verify file exists and is readable BEFORE loading
if not os.path.exists(ENV_FILE):
    raise FileNotFoundError(f"CRITICAL: .env file not found at {ENV_FILE}")

if not os.access(ENV_FILE, os.R_OK):
    raise PermissionError(f"CRITICAL: Cannot read .env file at {ENV_FILE}")

# Now safe to load
result = load_dotenv(ENV_FILE)
if not result:
    raise RuntimeError(f"load_dotenv() failed to load from {ENV_FILE}")

# Verify variables loaded
required_vars = ['TASTYTRADE_CLIENT_ID', 'TASTYTRADE_CLIENT_SECRET']
for var in required_vars:
    if not os.getenv(var):
        raise ValueError(f"CRITICAL: {var} not loaded from {ENV_FILE}")

print(f"✅ All environment variables loaded successfully")
```

### Cause 3D: Working Directory Doesn't Matter For Absolute Paths

**Clarification:**
```bash
# These are different:
load_dotenv()  # Searches relative to current working directory
load_dotenv('/absolute/path/.env')  # Uses absolute path (WorkingDirectory= doesn't matter)
```

If you're using absolute path (`/home/ubuntu/tastywork-trading/.env`), `WorkingDirectory=` in systemd doesn't matter.

### Verification Steps for Question 3

```bash
# 1. Check file permissions
ls -la /home/ubuntu/tastywork-trading/.env
sudo -u ubuntu cat /home/ubuntu/tastywork-trading/.env

# 2. Check file modification time (should be recent)
stat /home/ubuntu/tastywork-trading/.env

# 3. Check file contents
cat /home/ubuntu/tastywork-trading/.env

# 4. Fix permissions if needed
sudo chown ubuntu:ubuntu /home/ubuntu/tastywork-trading/.env
sudo chmod 600 /home/ubuntu/tastywork-trading/.env

# 5. Restart and check logs
sudo systemctl restart trademind-api
sudo journalctl -u trademind-api -n 50 | grep -E "CRITICAL|load_dotenv|Error"
```

---

## Question 4: Alternative Ways to Pass Credentials to Systemd Service

### Option A: EnvironmentFile Directive

```ini
# /etc/systemd/system/trademind-api.service
[Service]
EnvironmentFile=/home/ubuntu/tastywork-trading/.env
ExecStart=/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py
```

**Pros:**
- ✅ Systemd reads .env directly
- ✅ Variables in environment before Python starts
- ✅ Simple and clean

**Cons:**
- ❌ Format limitations (no variable expansion, no inline comments)
- ❌ Python doesn't know which values came from where

**Test it:**
```python
# In tasty_api_server.py
import os

client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
print(f"CLIENT_SECRET from environment: {client_secret is not None}")
# Will be set if EnvironmentFile works
```

**Limitations:**
```bash
# These WORK:
TASTYTRADE_CLIENT_SECRET=abc123

# These DON'T WORK with systemd EnvironmentFile:
MY_VAR=$HOME/path  # Variable expansion not supported
MY_VAR=value # inline comment not allowed
```

---

### Option B: Direct Environment Directive

```ini
# /etc/systemd/system/trademind-api.service
[Service]
Environment="TASTYTRADE_CLIENT_SECRET=XYZ789abc"
Environment="TASTYTRADE_CLIENT_ID=ABC123xyz"
ExecStart=/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py
```

**Pros:**
- ✅ No .env file needed
- ✅ Variables visible to systemd (can check with `systemctl show-environment`)

**Cons:**
- ❌ **SECURITY RISK** - Secrets visible in service file
- ❌ `systemctl cat trademind-api` shows secrets
- ❌ If service file in git, secrets are exposed

**Never use this for production!**

---

### Option C: ExecStartPre to Source .env

```ini
# /etc/systemd/system/trademind-api.service
[Service]
ExecStartPre=/bin/bash -c 'set -a; source /home/ubuntu/tastywork-trading/.env; set +a'
ExecStart=/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py
```

**What this does:**
- `set -a` - Export all variables
- `source .env` - Read .env file
- `set +a` - Stop exporting

**Pros:**
- ✅ Loads .env with variable expansion
- ✅ Supports comments in .env

**Cons:**
- ⚠️ Slightly more complex
- ⚠️ Requires bash (systemd might not have it)

---

### Recommendation: **Use Option A + Python Fallback**

**Most reliable approach:**

```ini
# /etc/systemd/system/trademind-api.service
[Unit]
Description=TradeMind API Server
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/tastywork-trading

# Pre-flight checks
ExecStartPre=/bin/bash -c 'test -f /home/ubuntu/tastywork-trading/.env || (echo "ERROR: .env not found"; exit 1)'

# Use systemd EnvironmentFile
EnvironmentFile=/home/ubuntu/tastywork-trading/.env

# Also have Python load it as backup
ExecStart=/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py

Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Python code (handles both cases):**
```python
import os
from dotenv import load_dotenv

# Check if variables are already in environment (from systemd EnvironmentFile)
if os.getenv('TASTYTRADE_CLIENT_SECRET'):
    print("✅ Variables loaded from systemd EnvironmentFile")
else:
    # Fallback: Load from .env file (in case systemd method fails)
    print("ℹ️  Variables not in environment, loading from .env...")
    load_dotenv('/home/ubuntu/tastywork-trading/.env')

# Verify either way
if not os.getenv('TASTYTRADE_CLIENT_SECRET'):
    raise Exception("CRITICAL: TASTYTRADE_CLIENT_SECRET not available!")

print("✅ Credentials loaded successfully")
```

---

## Question 5: Tastytrade OAuth Debugging

### Three Possible Causes of invalid_credentials

#### Cause 5A: Backend client_secret ≠ Frontend client_secret (MOST COMMON)

**Symptom:**
- All users get invalid_credentials
- Error occurs immediately when creating Session
- No network delay

**How to verify:**
```python
# Add logging to tasty_api_server.py
import logging
import os

logger = logging.getLogger(__name__)

@app.post("/execute-trade")
async def execute_trade(request: TradeRequest):
    user_id = request.user_id
    refresh_token = request.refresh_token
    
    client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
    
    # Log for debugging
    logger.info(f"Backend client_secret (last 4 chars): ...{client_secret[-4:] if client_secret else 'NOT SET'}")
    logger.info(f"Refresh token length: {len(refresh_token)}")
    
    try:
        session = Session(client_secret=client_secret, refresh_token=refresh_token)
        logger.info(f"✅ Session created for user {user_id}")
    except Exception as e:
        logger.error(f"❌ Session creation failed: {str(e)}")
        if "invalid_credentials" in str(e):
            logger.critical(
                f"PROBABLE CAUSE: Credential mismatch\n"
                f"Backend secret (last 4): ...{client_secret[-4:] if client_secret else 'NOT SET'}\n"
                f"This must match frontend's during OAuth exchange"
            )
        raise
```

**Verification:**
```bash
# 1. Get backend secret
grep TASTYTRADE_CLIENT_SECRET /home/ubuntu/tastywork-trading/.env

# 2. Check Vercel frontend secret
# Go to Vercel dashboard → Settings → Environment Variables
# Compare them character-by-character

# 3. If they don't match:
#    - Update one to match the other (use the CORRECT value from my.tastytrade.com)
#    - Redeploy both services
#    - Delete old tokens from Redis
#    - Have user reconnect
```

#### Cause 5B: Refresh Token Was Revoked (LESS COMMON)

**Symptom:**
- Only one user gets invalid_credentials
- Other users work fine
- Error is consistent (not intermittent)

**How to verify:**
```bash
# 1. Check when token was created
redis-cli
> GET "tastytrade:{user_id}"
# Look at linkedAt timestamp

# 2. Check if user revoked access
# User goes to: https://my.tastytrade.com/settings/api/connected-apps
# If your app is not listed, token is revoked

# 3. Solution: User must reconnect account
```

**Code to handle revocation:**
```python
@app.post("/execute-trade")
async def execute_trade(request: TradeRequest):
    user_id = request.user_id
    refresh_token = request.refresh_token
    
    try:
        session = Session(client_secret=client_secret, refresh_token=refresh_token)
        # Execute trade...
    except Exception as e:
        if "invalid_credentials" in str(e):
            # Could be revocation
            logger.error(f"Token invalid for user {user_id}")
            # Mark token as invalid in database
            await mark_token_revoked(user_id)
            # Notify user
            return {
                "status": "failed",
                "error": "Your Tastytrade connection was revoked. Please reconnect.",
                "action": "reconnect_required"
            }
        raise
```

#### Cause 5C: Token Format Corrupted (RARE)

**Symptom:**
- Error happens sometimes, not always
- Different users affected randomly
- Network issues or encoding problems

**How to verify:**
```python
import logging

logger = logging.getLogger(__name__)

@app.post("/execute-trade")
async def execute_trade(request: TradeRequest):
    refresh_token = request.refresh_token
    
    # Log token format
    logger.info(f"Token length: {len(refresh_token)}")
    logger.info(f"Token starts with: {refresh_token[:20]}")
    logger.info(f"Token encoding: {type(refresh_token)}")
    
    # Check for common corruptions
    if not refresh_token or len(refresh_token) < 50:
        logger.error(f"Token too short: {len(refresh_token)} chars")
        return {"status": "failed", "error": "Invalid token format"}
    
    if refresh_token.startswith("b'"):  # Bytes representation leak
        logger.error("Token has bytes representation leak")
        refresh_token = refresh_token[2:-1]  # Remove b'...'
    
    try:
        session = Session(client_secret=client_secret, refresh_token=refresh_token)
    except Exception as e:
        logger.error(f"Token error: {str(e)}")
        raise
```

---

## Question 6: Systemd Service Troubleshooting Commands

### Complete Debugging Checklist

```bash
# ============================================
# 1. CHECK SERVICE STATUS
# ============================================

# Is service running?
sudo systemctl status trademind-api

# What's the actual status?
sudo systemctl is-active trademind-api  # Should print "active"

# Get process ID
PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)
echo "PID: $PID"

# Is process actually running?
ps aux | grep $PID


# ============================================
# 2. CHECK FILE MODIFICATIONS
# ============================================

# When was Python file last modified?
stat /home/ubuntu/tastywork-trading/tasty_api_server.py

# When was .env last modified?
stat /home/ubuntu/tastywork-trading/.env

# When was .service file last modified?
stat /etc/systemd/system/trademind-api.service

# If Python file is older than your edit, it wasn't uploaded!


# ============================================
# 3. CHECK PYTHON BYTECODE
# ============================================

# Remove all cached bytecode
sudo rm -rf /home/ubuntu/tastywork-trading/__pycache__
find /home/ubuntu/tastywork-trading -name "*.pyc" -delete

# Verify it's gone
find /home/ubuntu/tastywork-trading -name "__pycache__"  # Should be empty


# ============================================
# 4. CHECK ENVIRONMENT VARIABLES
# ============================================

# Get PID
PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)

# See all env vars the process has
sudo cat /proc/$PID/environ | tr '\0' '\n' | sort

# Filter for Tastytrade
sudo cat /proc/$PID/environ | tr '\0' '\n' | grep TASTYTRADE

# Expected output:
# TASTYTRADE_CLIENT_ID=ABC123xyz
# TASTYTRADE_CLIENT_SECRET=XYZ789abc


# ============================================
# 5. CHECK .ENV FILE
# ============================================

# Does file exist?
ls -la /home/ubuntu/tastywork-trading/.env

# Can ubuntu user read it?
sudo -u ubuntu cat /home/ubuntu/tastywork-trading/.env

# Check exact contents
cat /home/ubuntu/tastywork-trading/.env

# Check for hidden characters or formatting issues
od -c /home/ubuntu/tastywork-trading/.env | head -20


# ============================================
# 6. CHECK LOGS
# ============================================

# View recent logs
sudo journalctl -u trademind-api -n 100

# Follow logs in real-time
sudo journalctl -u trademind-api -f

# Filter for errors
sudo journalctl -u trademind-api | grep -i error

# Filter for environment loading
sudo journalctl -u trademind-api | grep -i "environment\|load_dotenv\|TASTYTRADE"

# View logs from last 5 minutes
sudo journalctl -u trademind-api --since "5 minutes ago"

# View startup sequence (first 30 lines)
sudo journalctl -u trademind-api -n 30 --no-pager


# ============================================
# 7. FORCE CLEAN RESTART
# ============================================

# Stop service
sudo systemctl stop trademind-api
echo "Waiting 2 seconds..."
sleep 2

# Remove bytecode
sudo rm -rf /home/ubuntu/tastywork-trading/__pycache__
find /home/ubuntu/tastywork-trading -name "*.pyc" -delete

# Reload systemd (if service file changed)
sudo systemctl daemon-reload

# Start service
sudo systemctl start trademind-api
echo "Waiting 3 seconds for startup..."
sleep 3

# Check status
sudo systemctl status trademind-api

# Monitor logs
echo "=== STARTUP LOGS ==="
sudo journalctl -u trademind-api -n 30 --no-pager


# ============================================
# 8. TEST ENDPOINTS
# ============================================

# Call health endpoint
curl http://localhost:8000/health/debug

# Check response for environment variables


# ============================================
# 9. COMPREHENSIVE DIAGNOSTIC SCRIPT
# ============================================

# Run this to get all debug info at once:
cat > /tmp/diagnose.sh << 'EOF'
#!/bin/bash
echo "=== SERVICE STATUS ==="
sudo systemctl status trademind-api

echo -e "\n=== FILE MODIFICATION TIMES ==="
stat /home/ubuntu/tastywork-trading/tasty_api_server.py | grep Modify
stat /home/ubuntu/tastywork-trading/.env | grep Modify

echo -e "\n=== PYTHON FILE CONTENTS ==="
head -30 /home/ubuntu/tastywork-trading/tasty_api_server.py

echo -e "\n=== .ENV FILE ==="
cat /home/ubuntu/tastywork-trading/.env

echo -e "\n=== PROCESS ID & ENVIRONMENT ==="
PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)
echo "PID: $PID"
echo "Tastytrade environment:"
sudo cat /proc/$PID/environ | tr '\0' '\n' | grep TASTYTRADE

echo -e "\n=== RECENT LOGS ==="
sudo journalctl -u trademind-api -n 50 --no-pager

EOF

chmod +x /tmp/diagnose.sh
/tmp/diagnose.sh
```

---

## Question 7: Python Module Import Boundaries

### Key Principle

**Environment variables loaded by `load_dotenv()` are GLOBAL to the entire Python process.**

They become part of `os.environ` which is shared across all modules.

```python
# File A: tasty_api_server.py
from dotenv import load_dotenv
import os

load_dotenv('/home/ubuntu/tastywork-trading/.env')
# Now os.environ has TASTYTRADE_CLIENT_SECRET

# File B: tastytrade_utils.py (imported after File A)
import os

def create_user_session(refresh_token: str):
    client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')  # ✅ Will get the value
    return Session(client_secret=client_secret, refresh_token=refresh_token)

# File C: another_module.py
import os

my_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')  # ✅ Also works
```

### CRITICAL REQUIREMENT: Order of Imports

**This WORKS:**
```python
# ✅ CORRECT - tasty_api_server.py
from dotenv import load_dotenv
load_dotenv('/home/ubuntu/tastywork-trading/.env')  # Load FIRST

# Import modules that need credentials
from tastytrade_utils import create_user_session
from fastapi import FastAPI
```

**This FAILS:**
```python
# ❌ WRONG - tastytrade_utils.py loads before load_dotenv()
import tastytrade_utils

# Now load_dotenv() (too late!)
from dotenv import load_dotenv
load_dotenv()

# tastytrade_utils might have cached the missing value
```

### Answer to "Should I Call load_dotenv() in Every File?"

**NO - Call it ONCE at startup, in the main file:**

```python
# ✅ CORRECT - Only in main file
# tasty_api_server.py
from dotenv import load_dotenv
load_dotenv()

# Then import everything else
from fastapi import FastAPI
import tastytrade_utils
```

**NOT this:**
```python
# ❌ WRONG - Calling in every file wastes resources and causes confusion
# tastytrade_utils.py
from dotenv import load_dotenv
load_dotenv()

# models.py
from dotenv import load_dotenv
load_dotenv()

# auth.py
from dotenv import load_dotenv
load_dotenv()
```

### Verify Import Order

```python
# Add this to tasty_api_server.py to verify order

import sys

print("=== IMPORT ORDER DEBUG ===")

# 1. Load environment
from dotenv import load_dotenv
import os

ENV_FILE = '/home/ubuntu/tastywork-trading/.env'
load_dotenv(ENV_FILE)
print(f"1. Loaded environment from {ENV_FILE}")

# 2. Check env vars
client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
print(f"2. TASTYTRADE_CLIENT_SECRET in os.environ: {client_secret is not None}")

# 3. Now import other modules
print("3. Importing other modules...")
from tastytrade_utils import create_user_session
print("   - tastytrade_utils imported")

from fastapi import FastAPI
print("   - FastAPI imported")

# 4. Verify modules can see env vars
from tastytrade_utils import test_env_var
result = test_env_var()
print(f"4. tastytrade_utils can see TASTYTRADE_CLIENT_SECRET: {result}")

print("=== END IMPORT ORDER DEBUG ===\n")

# In tastytrade_utils.py, add:
def test_env_var():
    import os
    return os.getenv('TASTYTRADE_CLIENT_SECRET') is not None
```

---

## Question 8: Verification & Health Check Strategy

### Add Comprehensive Health Endpoint

```python
# In tasty_api_server.py

from fastapi import FastAPI
import os
from datetime import datetime

app = FastAPI()

@app.get("/health")
async def health():
    """Basic health check."""
    return {"status": "ok"}

@app.get("/health/debug")
async def health_debug():
    """Debug health check - shows environment and system status."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "environment": {
            "client_id_set": os.getenv('TASTYTRADE_CLIENT_ID') is not None,
            "client_secret_set": os.getenv('TASTYTRADE_CLIENT_SECRET') is not None,
            "client_id_length": len(os.getenv('TASTYTRADE_CLIENT_ID', '')),
            "client_secret_length": len(os.getenv('TASTYTRADE_CLIENT_SECRET', '')),
            "client_id_prefix": os.getenv('TASTYTRADE_CLIENT_ID', '')[:10],
            "client_secret_prefix": os.getenv('TASTYTRADE_CLIENT_SECRET', '')[:4],
        },
        "files": {
            "env_file_exists": os.path.exists('/home/ubuntu/tastywork-trading/.env'),
            "env_file_readable": os.access('/home/ubuntu/tastywork-trading/.env', os.R_OK),
            "env_file_size": os.path.getsize('/home/ubuntu/tastywork-trading/.env') if os.path.exists('/home/ubuntu/tastywork-trading/.env') else 0,
        },
        "working_directory": os.getcwd(),
    }

@app.get("/health/detailed")
async def health_detailed():
    """Very detailed debug - includes actual module state."""
    import sys
    
    # Get loaded modules
    tastytrade_modules = [m for m in sys.modules.keys() if 'tastytrade' in m.lower()]
    
    return {
        "status": "ok",
        "environment": {
            "TASTYTRADE_CLIENT_ID": os.getenv('TASTYTRADE_CLIENT_ID', 'NOT SET'),
            "TASTYTRADE_CLIENT_SECRET": os.getenv('TASTYTRADE_CLIENT_SECRET', 'NOT SET'),
        },
        "loaded_modules": tastytrade_modules,
        "python_version": sys.version,
        "process_id": os.getpid(),
    }
```

**Test it:**
```bash
# Basic health
curl http://localhost:8000/health

# Debug health
curl http://localhost:8000/health/debug

# Detailed health
curl http://localhost:8000/health/detailed
```

---

### Create Startup Verification Script

```python
# create_test_script.py

import os
import sys
from dotenv import load_dotenv
from pathlib import Path

def test_environment_setup():
    """Test if environment is properly set up."""
    
    print("=" * 60)
    print("ENVIRONMENT SETUP VERIFICATION")
    print("=" * 60)
    
    # Test 1: .env file exists
    env_file = Path('/home/ubuntu/tastywork-trading/.env')
    print(f"\n1. .env file exists: {env_file.exists()}")
    if not env_file.exists():
        print("   ERROR: File not found!")
        return False
    
    # Test 2: File is readable
    readable = os.access(env_file, os.R_OK)
    print(f"2. .env file readable: {readable}")
    if not readable:
        print("   ERROR: File is not readable!")
        return False
    
    # Test 3: Load environment
    result = load_dotenv(env_file)
    print(f"3. load_dotenv() succeeded: {result}")
    
    # Test 4: Check variables
    client_id = os.getenv('TASTYTRADE_CLIENT_ID')
    client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
    
    print(f"4. TASTYTRADE_CLIENT_ID set: {client_id is not None}")
    if client_id:
        print(f"   Value (first 10): {client_id[:10]}")
    
    print(f"5. TASTYTRADE_CLIENT_SECRET set: {client_secret is not None}")
    if client_secret:
        print(f"   Value (first 4): {client_secret[:4]}")
    
    # Test 5: Try creating session
    print("\n6. Testing OAuth Session creation...")
    try:
        from tastytrade import Session
        
        # Don't use real token, just test if Session can be imported
        print("   ✅ Session class imported successfully")
        print(f"   Session class: {Session}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False
    
    # Final result
    print("\n" + "=" * 60)
    if client_id and client_secret:
        print("✅ ALL TESTS PASSED - Environment is properly configured")
        return True
    else:
        print("❌ TESTS FAILED - Check errors above")
        return False

if __name__ == '__main__':
    success = test_environment_setup()
    sys.exit(0 if success else 1)
```

**Run it:**
```bash
cd /home/ubuntu/tastywork-trading
python3 create_test_script.py
```

---

## Final Comprehensive Debugging Procedure

### Run This Exact Sequence:

```bash
#!/bin/bash

echo "============================================"
echo "STEP 1: Stop service and clean"
echo "============================================"
sudo systemctl stop trademind-api
sleep 2
sudo rm -rf /home/ubuntu/tastywork-trading/__pycache__
find /home/ubuntu/tastywork-trading -name "*.pyc" -delete
echo "✅ Cleaned"

echo -e "\n============================================"
echo "STEP 2: Verify .env file"
echo "============================================"
echo "Contents:"
cat /home/ubuntu/tastywork-trading/.env
echo -e "\nPermissions:"
ls -la /home/ubuntu/tastywork-trading/.env
echo "Readable by ubuntu user:"
sudo -u ubuntu cat /home/ubuntu/tastywork-trading/.env | head -1

echo -e "\n============================================"
echo "STEP 3: Reload systemd if service file changed"
echo "============================================"
sudo systemctl daemon-reload
echo "✅ Reloaded"

echo -e "\n============================================"
echo "STEP 4: Start service"
echo "============================================"
sudo systemctl start trademind-api
sleep 3

echo -e "\n============================================"
echo "STEP 5: Get PID and check environment"
echo "============================================"
PID=$(sudo systemctl show -p MainPID trademind-api | cut -d= -f2)
echo "PID: $PID"
echo "Environment variables:"
sudo cat /proc/$PID/environ | tr '\0' '\n' | grep TASTYTRADE

echo -e "\n============================================"
echo "STEP 6: Check logs"
echo "============================================"
sudo journalctl -u trademind-api -n 50 --no-pager | grep -E "Environment|TASTYTRADE|load|ERROR"

echo -e "\n============================================"
echo "STEP 7: Test health endpoint"
echo "============================================"
curl -s http://localhost:8000/health/debug | python3 -m json.tool

echo -e "\n============================================"
echo "STEP 8: Test trade (with real user data)"
echo "============================================"
echo "Ready to test. Check logs in real-time:"
echo "sudo journalctl -u trademind-api -f"

```

Save as `/tmp/full_debug.sh` and run:
```bash
chmod +x /tmp/full_debug.sh
/tmp/full_debug.sh
```

---

## Summary Checklist

```markdown
✅ Delete __pycache__ before every restart
✅ Call systemctl daemon-reload if service file changed
✅ Verify .env file exists and is readable by ubuntu user
✅ Check os.getenv() returns values in running process
✅ Look for "Environment loaded" in logs
✅ Verify frontend & backend client_secret match
✅ Delete old tokens from Redis after credential change
✅ Have users reconnect their Tastytrade accounts
✅ Add comprehensive logging to OAuth code
✅ Use health endpoints to verify environment
✅ Check for Python bytecode staleness
✅ Verify file modification times are recent
```

If you run through this sequence and still have issues, the problem is likely one of:
1. Credentials don't match between frontend/backend
2. Old tokens in Redis bound to different credentials
3. User needs to reconnect their Tastytrade account
4. Network/firewall issue (not environment loading)
