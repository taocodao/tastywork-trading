# Multi-User Signal Execution & Expiration
**Date:** 2026-01-23
**Status:** Implemented

## Goals
1. Allow multiple users to independently execute the same trade signal
2. Automatically expire signals based on option expiration and staleness

---

## Changes Made

### 1. Database Schema (`src/earnings_intelligence/database.py`)

#### New Fields on Signal Model
- `expires_at` - When signal becomes invalid (DateTime)
- `front_expiry` - Short leg expiration date
- `user_executions` - Relationship to UserSignalExecution

#### New Table: UserSignalExecution
Tracks each user's interaction with a signal independently:
- `user_id` - Privy user ID
- `signal_id` - FK to Signal
- `status` - pending/approved/executed/rejected/failed
- `order_id` - Tastytrade order ID
- `error_message` - Error details if failed
- `created_at`, `approved_at`, `executed_at`

#### New Repository: UserSignalRepository
- `get_user_execution(user_id, signal_id)` - Get user's status for a signal
- `create_or_update_execution(...)` - Track user's execution
- `get_signal_execution_count(signal_id)` - How many users executed

---

### 2. Signal Publisher (`signal_publisher.py`)

Added expiration calculation:
```python
# Expires: earlier of (front_expiry - 1 day) OR (now + 24 hours)
expires_at = min(front_expiry_dt - timedelta(days=1), now + timedelta(hours=24))
```

---

### 3. API Server (`tasty_api_server.py`)

Updated `handle_approve_signal`:
- Accepts `userId` from frontend
- Creates UserSignalExecution record instead of updating Signal status
- Signal's global status stays 'pending' (allows multi-user)
- Checks if signal is expired before allowing execution
- Prevents duplicate executions by same user

---

### 4. WebSocket Server (`websocket_server.py`)

- `get_all_signals()` now automatically filters expired signals
- Only sends non-expired, pending signals to clients

---

### 5. Frontend (`approve/route.ts`)

- Now passes `userId` to Python backend for per-user tracking

---

## How It Works

1. **Signal Created:** Scanner creates signal with `expires_at` set
2. **User A Views:** Gets signal via WebSocket (if not expired)
3. **User A Executes:** 
   - UserSignalExecution(user_id=A, status=executed) created
   - Signal stays status='pending'
4. **User B Views:** Same signal still shows as available
5. **User B Executes:**
   - UserSignalExecution(user_id=B, status=executed) created
   - Both users have independent tracking
6. **Signal Expires:** After expires_at, signal no longer returned

---

## Deployment

### Backend (EC2)
```bash
ssh ubuntu@34.235.119.67
cd ~/tastywork-trading
git pull
pkill -f websocket_server.py && nohup python3 websocket_server.py > websocket.log 2>&1 &
pkill -f tasty_api_server.py && nohup python3 tasty_api_server.py > api.log 2>&1 &

# Run migration (creates new table)
python3 -c "from src.earnings_intelligence.database import init_db; init_db()"
```

### Frontend (Vercel)
```bash
cd trademind-app
git push  # Auto-deploys on Vercel
```
