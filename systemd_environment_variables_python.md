# Systemd Environment Variables for Python Applications - Complete Guide

## The Problem You're Experiencing

**Symptom:**
```
Running locally: python3 tasty_api_server.py → Works ✅
Running via systemd: sudo systemctl start trademind-api → Fails ❌
Error: os.getenv('TASTYTRADE_CLIENT_SECRET') returns None
```

**Root Cause:** `load_dotenv()` defaults to searching for `.env` relative to the **Python source file's directory**, not the **working directory**. When systemd runs the service, the context is different, and relative path resolution fails.

---

## Why load_dotenv() Fails in Systemd (Technical Deep Dive)

### How load_dotenv() Works

```python
# Default behavior of load_dotenv()
from dotenv import load_dotenv

load_dotenv()  # Without arguments, calls find_dotenv()
```

**Behind the scenes:**
```python
# python-dotenv source code flow
def load_dotenv(dotenv_path=None, ...):
    f = dotenv_path or stream or find_dotenv()  # ← If no path given, find it
    return DotEnv(f, ...).set_as_environment_variables()

def find_dotenv():
    # Searches from the file that called load_dotenv() upward through parent dirs
    # Uses: inspect.currentframe() to get caller's __file__ location
```

**The Issue:**
- `load_dotenv()` searches from **the location of the Python file** (`tasty_api_server.py`)
- When you run `python3 tasty_api_server.py` directly, it finds `.env` in the same directory ✅
- When systemd runs it, the search context is different ✅ (but still should work)
- **The real issue:** Systemd changes working directory, but `find_dotenv()` relies on file location, not working directory
- If `.env` is not in the same directory as the Python file (or parent directories), it won't be found ❌

### Why Systemd Makes This Worse

Systemd runs services in a **minimal environment**:
1. **Minimal PATH** - Only includes system paths, not your custom paths
2. **Minimal working directory** - Defaults to `/` (root), even if you set `WorkingDirectory`
3. **No shell** - Doesn't process `.bashrc`, `.bash_profile`, or other shell configs
4. **No login environment** - Doesn't load `/etc/environment` or `/etc/profile`

When your service starts:
```
systemd executes: python3 /home/ubuntu/tastywork-trading/tasty_api_server.py

Working directory: /home/ubuntu/tastywork-trading (set by WorkingDirectory=)

find_dotenv() searches:
  1. /home/ubuntu/tastywork-trading/.env  ← Should find this
  2. /home/ubuntu/.env
  3. /home/.env
  4. /.env
```

If `.env` is exactly at `/home/ubuntu/tastywork-trading/.env`, it SHOULD work. If it's not being found, the issue is likely:
- `.env` file permissions
- Path mismatch in `ExecStart=`
- Typo in file location

---

## Answer to Your Specific Questions

### Q1: Why does load_dotenv() not work in systemd services?

**Answer:** It usually DOES work if you set `WorkingDirectory=` correctly. The confusion comes from `find_dotenv()` behavior:

```python
# WHAT WORKS in systemd:
# 1. .env is in the same directory as tasty_api_server.py
# 2. You call load_dotenv() with no arguments
# Result: find_dotenv() finds it ✅

# WHAT FAILS:
# 1. .env is NOT in the same directory
# 2. You call load_dotenv() with no arguments
# Result: find_dotenv() doesn't find it ❌
```

**Solution:** Use **absolute paths** instead of relying on search:

```python
# In tasty_api_server.py
import os
from dotenv import load_dotenv

# Option A: Absolute path
env_path = '/home/ubuntu/tastywork-trading/.env'
load_dotenv(env_path)

# Option B: Relative to this file
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)

# Verify it loaded
print(f"Loaded from: {env_path}")
print(f"Client secret loaded: {os.getenv('TASTYTRADE_CLIENT_SECRET') is not None}")
```

### Q2: Does systemd change the working directory?

**Answer:** YES - This is controlled by `WorkingDirectory=` in your service file.

```ini
# Without WorkingDirectory=, it defaults to /
# Default: os.getcwd() returns '/'

# With WorkingDirectory=, it sets the working dir
# This: WorkingDirectory=/home/ubuntu/tastywork-trading
# Result: os.getcwd() returns '/home/ubuntu/tastywork-trading'
```

**Verification:**
```python
import os

# Add this to tasty_api_server.py to debug
print(f"Working directory: {os.getcwd()}")
print(f"Script location: {__file__}")
print(f"Script directory: {os.path.dirname(os.path.abspath(__file__))}")

# Check if .env exists at expected location
env_path = os.path.join(os.getcwd(), '.env')
print(f".env exists at {env_path}: {os.path.exists(env_path)}")
```

### Q3: Do environment variables loaded by load_dotenv() persist?

**Answer:** YES - They persist for the entire service lifetime.

```python
# At startup
load_dotenv()
client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')  # ✅ Set

# Later in the same process
client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')  # ✅ Still set

# After 1 hour of running
client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')  # ✅ Still set
```

**Important:** Once set, environment variables **don't change** unless:
1. Code explicitly calls `os.environ['KEY'] = 'new_value'`
2. Process restarts
3. External signal modifies environment (rare)

### Q4: Are there timing issues with when load_dotenv() is called?

**Answer:** YES - Call it as early as possible, at **module import time**:

```python
# ✅ CORRECT - At top of file, before other imports
from dotenv import load_dotenv
import os

load_dotenv()  # Called immediately on import

from fastapi import FastAPI
import requests

# Now safe to use os.getenv() in FastAPI routes

# ❌ WRONG - Called later
from fastapi import FastAPI
import os

app = FastAPI()

@app.on_event("startup")
async def startup():
    from dotenv import load_dotenv
    load_dotenv()  # Too late! FastAPI may have already tried to read config
```

**Why this matters:**
- Other modules may read environment variables during import
- FastAPI config loading happens during app initialization
- OAuth credentials needed immediately

---

## Question 5: Recommended Approach for Systemd Services

### ✅ RECOMMENDED: Option C (Absolute Path + Systemd Verification)

Combine three approaches:

#### Step 1: Update Python code

```python
# tasty_api_server.py
import os
import sys
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# Strategy: Try multiple locations, absolute path wins
def load_environment():
    """Load environment variables with fallback strategy."""
    
    # Strategy 1: Absolute path (most reliable for systemd)
    absolute_path = '/home/ubuntu/tastywork-trading/.env'
    
    # Strategy 2: Relative to this file
    file_directory = Path(__file__).parent.absolute()
    relative_path = file_directory / '.env'
    
    # Strategy 3: Try find_dotenv with cwd
    found_path = find_dotenv(usecwd=True)
    
    # Try each in order
    for env_file in [absolute_path, relative_path, found_path]:
        if env_file and os.path.exists(env_file):
            print(f"Loading .env from: {env_file}")
            result = load_dotenv(env_file, override=False)
            if result:
                return env_file
    
    print("WARNING: No .env file found! Relying on environment variables.")
    return None

# Call at module import time
loaded_from = load_environment()

# Verify critical variables are loaded
required_vars = ['TASTYTRADE_CLIENT_SECRET', 'TASTYTRADE_CLIENT_ID']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print(f"CRITICAL ERROR: Missing environment variables: {missing_vars}")
    print(f".env loaded from: {loaded_from}")
    sys.exit(1)

# Now safe to use
TASTYTRADE_CLIENT_SECRET = os.getenv('TASTYTRADE_CLIENT_SECRET')
TASTYTRADE_CLIENT_ID = os.getenv('TASTYTRADE_CLIENT_ID')

print(f"✅ Environment loaded successfully")
print(f"   Client ID: {TASTYTRADE_CLIENT_ID[:10]}...")
```

#### Step 2: Update Systemd Service File

```ini
# /etc/systemd/system/trademind-api.service

[Unit]
Description=TradeMind API Server
After=network.target
StartLimitInterval=60
StartLimitBurst=3

[Service]
Type=simple
User=ubuntu
Group=ubuntu

# CRITICAL: Use absolute paths everywhere
WorkingDirectory=/home/ubuntu/tastywork-trading
ExecStart=/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py

# Environment verification script (optional but recommended)
ExecStartPre=/bin/bash -c 'test -f /home/ubuntu/tastywork-trading/.env || (echo ".env file not found"; exit 1)'

# Restart policy
Restart=always
RestartSec=5

# Security and permissions
StandardOutput=journal
StandardError=journal
SyslogIdentifier=trademind-api

# Resource limits
Limit Processes=1024
LimitNoFile=1024

# Set minimum environment (if needed)
# These override any system defaults
# Environment="PATH=/home/ubuntu/tastywork-trading/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin"

[Install]
WantedBy=multi-user.target
```

#### Step 3: Verify & Deploy

```bash
# 1. Verify .env file exists and is readable
ls -la /home/ubuntu/tastywork-trading/.env
# Should show: -rw-r--r-- 1 ubuntu ubuntu XXXX Dec 25 12:00 .env

# 2. Check file permissions (ubuntu user must be able to read)
sudo -u ubuntu cat /home/ubuntu/tastywork-trading/.env | head -5

# 3. Reload systemd configuration
sudo systemctl daemon-reload

# 4. Enable service (optional, for auto-start on boot)
sudo systemctl enable trademind-api

# 5. Start the service
sudo systemctl start trademind-api

# 6. Check status
sudo systemctl status trademind-api

# 7. View logs
sudo journalctl -u trademind-api -f

# 8. Verify environment variables loaded
sudo journalctl -u trademind-api | grep "Environment loaded"
```

---

## Trade-offs of Each Option

### Option A: EnvironmentFile (Systemd-native)

```ini
[Service]
EnvironmentFile=/home/ubuntu/tastywork-trading/.env
ExecStart=/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py
```

**Pros:**
- ✅ Systemd reads .env directly (no Python needed)
- ✅ Variables available to all processes
- ✅ Cleaner service file

**Cons:**
- ❌ Systemd doesn't expand variables (e.g., `$HOME` not evaluated)
- ❌ Comments in .env must use `#` at start of line
- ❌ Python application can't verify which vars were loaded
- ❌ EnvironmentFile format limitations (no quotes, no comments after values)

**Format limitations:**
```bash
# .env file for systemd EnvironmentFile=
# Comments OK at start of line
TASTYTRADE_CLIENT_SECRET=XYZ789abc
PYTHON_PATH=/usr/bin/python3

# ❌ These DON'T WORK with systemd:
EXPANDED_VAR=$HOME/path  # $HOME not expanded
MY_VAR=value # inline comment not allowed
```

### Option B: Individual Environment Directives

```ini
[Service]
Environment="TASTYTRADE_CLIENT_SECRET=XYZ789abc"
Environment="TASTYTRADE_CLIENT_ID=ABC123xyz"
ExecStart=/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py
```

**Pros:**
- ✅ No .env file needed
- ✅ Secrets in systemd (can be made secure)
- ✅ Easy to set per environment (dev/prod)

**Cons:**
- ❌ Secrets visible in service file (security risk)
- ❌ Difficult to manage many variables
- ❌ Must update service file for each change
- ❌ No version control for credentials

**When to use:** Testing/development only, not production

### Option C: Python load_dotenv with absolute path (RECOMMENDED)

```python
# In code
load_dotenv('/home/ubuntu/tastywork-trading/.env')

# Service file unchanged
ExecStart=/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py
```

**Pros:**
- ✅ Most reliable (Python controls the loading)
- ✅ Clear error messages if file not found
- ✅ Can verify required variables are set
- ✅ Standard python-dotenv pattern
- ✅ Can log which file was loaded for debugging

**Cons:**
- ⚠️ Secrets in .env file (but encrypted is OK)
- ⚠️ One more dependency (python-dotenv)

**When to use:** **Production - Always use this approach**

### Option D: Combination (Best of All)

```python
# Python code
load_dotenv('/home/ubuntu/tastywork-trading/.env')
# Verify it loaded
if not os.getenv('TASTYTRADE_CLIENT_SECRET'):
    raise Exception("TASTYTRADE_CLIENT_SECRET not loaded!")
```

```ini
# Service file - Add safeguards
[Service]
ExecStartPre=/bin/bash -c 'test -f /home/ubuntu/tastywork-trading/.env || (echo "ERROR: .env file missing"; exit 1)'
ExecStart=/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py
```

---

## Best Practices for Sensitive Credentials

### ❌ DON'T: Hardcode secrets in systemd service file

```ini
# NEVER DO THIS
[Service]
Environment="TASTYTRADE_CLIENT_SECRET=real_secret_here"
```

**Why:**
- Visible to anyone who can read the service file
- Visible in `systemctl cat trademind-api`
- In git history if not careful
- No audit trail of when it changed

### ✅ DO: Store secrets in .env file with proper permissions

```bash
# Create .env with restrictive permissions
sudo touch /home/ubuntu/tastywork-trading/.env
sudo chmod 600 /home/ubuntu/tastywork-trading/.env  # Only ubuntu can read
sudo chown ubuntu:ubuntu /home/ubuntu/tastywork-trading/.env

# Add secrets
echo "TASTYTRADE_CLIENT_SECRET=XYZ789abc" | sudo tee /home/ubuntu/tastywork-trading/.env > /dev/null
```

**Permissions breakdown:**
```
600 = rw------- (owner can read/write, others cannot read)
```

### ✅ PRODUCTION: Use cloud secret managers

**AWS Secrets Manager:**
```python
import boto3

def get_secret(secret_name):
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId=secret_name)
    return response['SecretString']

# At startup
TASTYTRADE_CLIENT_SECRET = get_secret('tastytrade/client-secret')
```

**Azure Key Vault:**
```python
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

def get_secret(secret_name):
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url="https://myvault.vault.azure.net/", credential=credential)
    return client.get_secret(secret_name).value

# At startup
TASTYTRADE_CLIENT_SECRET = get_secret('TastytradeClientSecret')
```

**GCP Secret Manager:**
```python
from google.cloud import secretmanager

def get_secret(secret_id, version_id="latest"):
    client = secretmanager.SecretManagerServiceClient()
    project_id = "my-project"
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# At startup
TASTYTRADE_CLIENT_SECRET = get_secret('tastytrade-client-secret')
```

### ✅ HYBRID: Environment variables + .env file fallback

```python
import os
from dotenv import load_dotenv

# Try environment variables first (from cloud secret manager)
client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')

# Fall back to .env if running locally
if not client_secret:
    load_dotenv('/home/ubuntu/tastywork-trading/.env')
    client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')

# Verify it's set
if not client_secret:
    raise Exception("TASTYTRADE_CLIENT_SECRET not found in environment or .env")

print(f"Loaded client secret from: {'environment' if os.getenv('TASTYTRADE_CLIENT_SECRET') else '.env'}")
```

---

## Debugging Steps

### Step 1: Verify Working Directory

```bash
# Check what directory systemd is using
sudo systemctl show -p WorkingDirectory trademind-api

# Output should show:
# WorkingDirectory=/home/ubuntu/tastywork-trading
```

### Step 2: Verify .env File Location

```bash
# Check file exists and is readable
ls -la /home/ubuntu/tastywork-trading/.env

# Check file contents
cat /home/ubuntu/tastywork-trading/.env

# Test as ubuntu user (the user running the service)
sudo -u ubuntu cat /home/ubuntu/tastywork-trading/.env
```

### Step 3: Add Debugging to Python Code

```python
# Add to top of tasty_api_server.py
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

print("=== ENVIRONMENT LOADING DEBUG ===")
print(f"Current working directory: {os.getcwd()}")
print(f"Script location: {__file__}")
print(f"Script directory: {os.path.dirname(os.path.abspath(__file__))}")

env_path = '/home/ubuntu/tastywork-trading/.env'
print(f"Looking for .env at: {env_path}")
print(f".env exists: {os.path.exists(env_path)}")
print(f".env readable: {os.access(env_path, os.R_OK)}")

# Try to load
result = load_dotenv(env_path)
print(f"load_dotenv() returned: {result}")

# Check if variables are set
client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
print(f"TASTYTRADE_CLIENT_SECRET is set: {client_secret is not None}")
if client_secret:
    print(f"TASTYTRADE_CLIENT_SECRET length: {len(client_secret)}")

print("=== END DEBUG ===\n")

# Now continue with app...
from fastapi import FastAPI
```

### Step 4: Check Systemd Logs

```bash
# View recent logs
sudo journalctl -u trademind-api -n 50

# Follow logs in real-time
sudo journalctl -u trademind-api -f

# View logs with timestamps
sudo journalctl -u trademind-api --no-pager | tail -20

# View logs from specific time
sudo journalctl -u trademind-api --since "2 hours ago"

# View error messages only
sudo journalctl -u trademind-api -p err
```

### Step 5: Manual Service Start for Debugging

```bash
# Stop the service
sudo systemctl stop trademind-api

# Start it manually with explicit commands (helps debug)
cd /home/ubuntu/tastywork-trading
/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py

# This shows real-time output (not journaled)
# You'll see any print() statements we added for debugging
```

---

## Complete Example Systemd Service File

```ini
# /etc/systemd/system/trademind-api.service
# Production-ready configuration with debugging

[Unit]
Description=TradeMind Trading API Server
Documentation=https://github.com/yourusername/trademind
After=network.target
StartLimitInterval=60
StartLimitBurst=3
PartOf=multi-user.target

[Service]
# Identity
Type=simple
User=ubuntu
Group=ubuntu

# Working directory (where .env is located)
WorkingDirectory=/home/ubuntu/tastywork-trading

# Pre-flight checks
ExecStartPre=/bin/bash -c 'test -f /home/ubuntu/tastywork-trading/.env || (echo "FATAL: .env file not found"; exit 1)'
ExecStartPre=/bin/bash -c 'grep -q "TASTYTRADE_CLIENT_SECRET" /home/ubuntu/tastywork-trading/.env || (echo "FATAL: TASTYTRADE_CLIENT_SECRET not in .env"; exit 1)'

# The actual command
ExecStart=/usr/bin/python3 /home/ubuntu/tastywork-trading/tasty_api_server.py

# Restart policy
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=trademind-api

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/ubuntu/tastywork-trading

# Resource limits
LimitNOFILE=65535
LimitNPROC=4096

[Install]
WantedBy=multi-user.target
```

---

## Verification Checklist

Before going to production:

```markdown
- [ ] .env file exists at /home/ubuntu/tastywork-trading/.env
- [ ] .env file has correct permissions (600)
- [ ] .env file is owned by ubuntu:ubuntu
- [ ] TASTYTRADE_CLIENT_SECRET is in .env
- [ ] TASTYTRADE_CLIENT_ID is in .env
- [ ] All required variables are in .env
- [ ] Verified locally: python3 tasty_api_server.py works
- [ ] Updated systemd service file with absolute path to .env
- [ ] Added ExecStartPre checks to service file
- [ ] Added debug prints to Python code
- [ ] Ran: sudo systemctl daemon-reload
- [ ] Ran: sudo systemctl start trademind-api
- [ ] Checked logs: sudo journalctl -u trademind-api
- [ ] Logs show "✅ Environment loaded successfully"
- [ ] No "TASTYTRADE_CLIENT_SECRET is None" errors
- [ ] API responds to requests: curl http://localhost:8000/health
- [ ] Can execute trades without "invalid_credentials" error
- [ ] Tested restart: sudo systemctl restart trademind-api
- [ ] Tested auto-restart: sudo systemctl enable trademind-api
```

---

## Summary

### Your Issue (Root Cause)

The combination of `load_dotenv()` (searching relative to Python file) + systemd (minimal environment) + relative path reference (in .env or code) creates a situation where the .env file isn't found.

### Solution (Quick Version)

1. **Update Python code** to use absolute path:
```python
load_dotenv('/home/ubuntu/tastywork-trading/.env')
```

2. **Update systemd service file:**
```ini
WorkingDirectory=/home/ubuntu/tastywork-trading
ExecStartPre=/bin/bash -c 'test -f /home/ubuntu/tastywork-trading/.env'
```

3. **Verify and restart:**
```bash
sudo systemctl daemon-reload
sudo systemctl restart trademind-api
sudo journalctl -u trademind-api -f
```

### Best Practice (Production)

- ✅ Use absolute paths in `load_dotenv()`
- ✅ Set restrictive permissions (600) on .env file
- ✅ Add pre-flight checks in systemd ExecStartPre
- ✅ Add debug logging to verify environment loaded
- ✅ Use cloud secret manager in production (AWS Secrets Manager, etc.)
- ✅ Store .env in version control only for development

---

## References

- python-dotenv GitHub: https://github.com/theskumar/python-dotenv
- Systemd exec documentation: https://www.freedesktop.org/software/systemd/man/systemd.exec.html
- Stack Overflow: "Environment Variable not loading with load_dotenv() in Linux"
- Merzlabs blog: "Autostart python scripts on boot with systemd"
