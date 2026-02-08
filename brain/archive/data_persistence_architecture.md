# 🗄️ TradeMind Data Persistence Architecture

## Quick Answer

**Q: Where are signals stored?**  
A: **Backend database (PostgreSQL on EC2)** - NOT in client

**Q: If user closes window/relogins, can they still see signals?**  
A: **YES** - Signals are fetched from backend database on every page load

**Q: After approval → trade → position, where is this persisted?**  
A: **Backend database in 3 tables:** `signals`, `user_signal_executions`, `positions`

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (EC2 Server)                     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         PostgreSQL Database (PERSISTENT)            │   │
│  │                                                     │   │
│  │  ┌──────────────┐  ┌────────────────────────┐     │   │
│  │  │   signals    │  │ user_signal_executions │     │   │
│  │  │──────────────│  │────────────────────────│     │   │
│  │  │ id (PK)      │  │ user_id                │     │   │
│  │  │ symbol       │  │ signal_id (FK)         │     │   │
│  │  │ strategy     │  │ status                 │     │   │
│  │  │ status       │  │ order_id               │     │   │
│  │  │ data (JSON)  │  │ created_at             │     │   │
│  │  │ created_at   │  │ approved_at            │     │   │
│  │  │ expires_at   │  │ executed_at            │     │   │
│  │  └──────────────┘  └────────────────────────┘     │   │
│  │                                                     │   │
│  │  ┌──────────────────────────────────────┐         │   │
│  │  │          positions                   │         │   │
│  │  │──────────────────────────────────────│         │   │
│  │  │ id (order_id from Tastytrade)        │         │   │
│  │  │ user_id                              │         │   │
│  │  │ signal_id (FK)                       │         │   │
│  │  │ symbol, strike, expiration           │         │   │
│  │  │ entry_price, contracts               │         │   │
│  │  │ status (open/closed)                 │         │   │
│  │  │ unrealized_pnl, exit_pnl             │         │   │
│  │  │ created_at, closed_at                │         │   │
│  │  └──────────────────────────────────────┘         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  WebSocket Server (Port 8003)          API Server (8002)   │
│  ├─ Broadcasts new signals             ├─ GET /api/signals │
│  ├─ Loads from database on connect     ├─ POST /approve    │
│  └─ Pushes to clients in real-time     └─ GET /positions   │
└─────────────────────────────────────────────────────────────┘
                           │
                           ↓ WebSocket (ws://)
                           ↓ REST API (https://)
┌─────────────────────────────────────────────────────────────┐
│              FRONTEND (User's Browser - Vercel)             │
│                                                             │
│  React State (EPHEMERAL - Lost on Close/Refresh)           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ SignalProvider (allSignals: Signal[])               │   │
│  │ ├─ WebSocket connection to backend                  │   │
│  │ ├─ Receives signals in real-time                    │   │
│  │ └─ State cleared on window close                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ❌ NO Local Database (No IndexedDB/LocalStorage)          │
│  ❌ NO Persistent Storage                                  │
│  ✅ Re-fetches everything from backend on reload           │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Persistence Locations

### ✅ Backend Database (EC2 PostgreSQL)

**PERSISTENT - Survives Everything**

| Table | What It Stores | Persists |
|-------|---------------|----------|
| `signals` | All generated trading signals | ✅ Forever (or until expired) |
| `user_signal_executions` | Each user's approval/execution status per signal | ✅ Forever |
| `positions` | Active and closed positions | ✅ Forever |

**Location:**
- Production: PostgreSQL on EC2
- Connection: `DATABASE_URL` environment variable
- File: `src/earnings_intelligence/database.py`

### ❌ Frontend (Browser)

**EPHEMERAL - Lost on Close/Refresh**

| Storage | What's Stored | Persists |
|---------|--------------|----------|
| React State | Current signals, WebSocket connection | ❌ Lost on close |
| Memory | UI state, forms, modals | ❌ Lost on close |
| LocalStorage | Privy auth session | ✅ Auth only |

**NO Database:**
- No IndexedDB
- No LocalStorage for signals
- No Service Worker cache
- Everything re-fetched from backend

---

## Complete Signal Lifecycle

### 1️⃣ Signal Generation (Backend)

```
EC2 Scheduler (9:35 AM)
  ↓
ThetaSignalGenerator.generate_entry_signals()
  ↓
For each signal:
  ├─ Create ThetaEntrySignal object
  │
  └─ publish_theta_entry_signal(signal)
      │
      ├─ STEP 1: Save to Database
      │   ↓
      │   SignalRepository.save_signal(data)
      │   ↓
      │   INSERT INTO signals (id, symbol, strategy, status, data, created_at)
      │   VALUES ('uuid', 'SPY', 'theta', 'pending', {...}, NOW())
      │   ✅ PERSISTED in PostgreSQL
      │
      └─ STEP 2: Broadcast to WebSocket
          ↓
          POST http://localhost:8004/
          ↓
          WebSocket server pushes to all connected clients
```

**Database Row Created:**

```sql
-- signals table
id          | abc-123-def
symbol      | SPY
strategy    | theta
status      | pending
data        | {"strike": 575, "delta": -0.32, ...}
created_at  | 2026-02-01 09:35:15
expires_at  | 2026-02-01 16:00:00
```

---

### 2️⃣ User Sees Signal (Frontend)

**Scenario A: User Already Connected**

```
Frontend WebSocket Connection
  ↓
Receives message:
{
  "type": "signal",
  "channel": "theta_puts",
  "data": {
    "id": "abc-123-def",
    "symbol": "SPY",
    "strategy": "theta",
    ...
  }
}
  ↓
SignalProvider.addSignal(data)
  ↓
allSignals state updated
  ↓
SignalsPage re-renders
  ↓
ThetaSignalCard displayed
```

**Scenario B: User Just Logged In / Refreshed Page**

```
1. Page loads
   ↓
2. SignalProvider mounts
   ↓
3. WebSocket connects to ws://EC2:8003
   ↓
4. Server sends welcome + historical signals
   {
     "type": "connected",
     "message": "Connected to TradeMind"
   }
   ↓
5. Server queries database:
   SELECT * FROM signals 
   WHERE status='pending' 
   AND (expires_at IS NULL OR expires_at > NOW())
   ↓
6. Server sends each signal via WebSocket
   ↓
7. Frontend receives and displays
```

**✅ USER CAN SEE SIGNALS AFTER RELOGIN**

The signals are stored in the backend database, not the browser. On every reconnect, the WebSocket server sends historical signals from the database.

---

### 3️⃣ User Approves Signal

```
User clicks "Approve" button
  ↓
Frontend: POST /api/signals/{id}/approve
  {
    "userId": "privy|user123",
    "signalId": "abc-123-def"
  }
  ↓
Backend (tasty_api_server.py)
  │
  ├─ STEP 1: Create user execution record
  │   ↓
  │   UserSignalRepository.create_or_update_execution(
  │       user_id="privy|user123",
  │       signal_id="abc-123-def",
  │       status="approved"
  │   )
  │   ↓
  │   INSERT INTO user_signal_executions
  │   (user_id, signal_id, status, approved_at)
  │   VALUES ('privy|user123', 'abc-123-def', 'approved', NOW())
  │   ✅ PERSISTED
  │
  └─ STEP 2: Execute trade via Tastytrade
      ↓
      Tastytrade API: Place order
      ↓
      Order ID: "12345" returned
      ↓
      Update user execution:
      UPDATE user_signal_executions
      SET status='executed', order_id='12345', executed_at=NOW()
      WHERE user_id='privy|user123' AND signal_id='abc-123-def'
      ✅ PERSISTED
```

**Database After Approval:**

```sql
-- user_signal_executions table
user_id         | privy|user123
signal_id       | abc-123-def
status          | executed
order_id        | 12345
approved_at     | 2026-02-01 10:15:30
executed_at     | 2026-02-01 10:15:32
```

**Note:** The global `signals` table status remains "pending" - other users can still approve the same signal!

---

### 4️⃣ Trade Becomes Position

```
After Tastytrade execution succeeds
  ↓
Backend creates position record
  ↓
PositionRepository.save_position({
    "id": "12345",  # Tastytrade order ID
    "user_id": "privy|user123",
    "signal_id": "abc-123-def",
    "symbol": "SPY",
    "strike": 575.0,
    "expiration": "2026-03-03",
    "contracts": 1,
    "entry_price": 2.85,
    "status": "open"
})
  ↓
INSERT INTO positions (...) VALUES (...)
  ✅ PERSISTED
```

**Database After Position Created:**

```sql
-- positions table
id              | 12345
user_id         | privy|user123
signal_id       | abc-123-def
symbol          | SPY
strike          | 575.0
expiration      | 2026-03-03
contracts       | 1
entry_price     | 2.85
status          | open
unrealized_pnl  | NULL
created_at      | 2026-02-01 10:15:32
```

---

### 5️⃣ User Views Positions (After Relogin)

```
User navigates to /positions page
  ↓
Frontend: GET /api/positions
  ↓
Backend queries database:
  SELECT * FROM positions
  WHERE user_id='privy|user123' AND status='open'
  ↓
Returns JSON:
[
  {
    "id": "12345",
    "symbol": "SPY",
    "strike": 575.0,
    "entryPrice": 2.85,
    "unrealizedPnl": 120.00,
    "status": "open"
  }
]
  ↓
Frontend displays in PositionsPage
```

**✅ POSITIONS PERSIST AFTER RELOGIN**

Positions are stored in the backend database and fetched via REST API on every page load.

---

## Multi-User Signal Execution

### Same Signal, Multiple Users

**Global Signal:**
```sql
-- signals table (SHARED BY ALL USERS)
id          | abc-123-def
symbol      | SPY
status      | pending  ← Stays "pending" for everyone
```

**User A Execution:**
```sql
-- user_signal_executions table
user_id     | privy|userA
signal_id   | abc-123-def
status      | executed
order_id    | 11111
```

**User B Execution:**
```sql
-- user_signal_executions table
user_id     | privy|userB
signal_id   | abc-123-def
status      | executed
order_id    | 22222
```

**User C (Hasn't Acted Yet):**
```sql
-- No row in user_signal_executions
-- User C still sees signal as "pending"
```

---

## What Persists Where

### ✅ Backend Database (PostgreSQL on EC2)

**Always Persisted:**
- ✅ All generated signals
- ✅ User approval/execution status per signal
- ✅ All positions (open and closed)
- ✅ P&L history
- ✅ Order IDs from Tastytrade
- ✅ Timestamps for everything

**Survives:**
- ✅ Server restarts
- ✅ User logout/login
- ✅ Browser close/refresh
- ✅ Network disconnection
- ✅ Forever (until manually deleted)

---

### ❌ Frontend (Browser)

**NOT Persisted:**
- ❌ React state (signals list)
- ❌ WebSocket connection
- ❌ UI state (modals, forms)
- ❌ Temporary data

**Lost On:**
- ❌ Browser close
- ❌ Page refresh (F5)
- ❌ Tab close
- ❌ Logout
- ❌ Network disconnection

**How Data Returns:**
- ✅ WebSocket reconnects automatically
- ✅ Historical signals sent from database
- ✅ Positions fetched via REST API
- ✅ User sees everything again

---

## Example: User Journey

### Day 1 - Morning (9:35 AM)

```
1. Scheduler generates SPY signal
   ├─ Saved to database: signals table
   └─ Broadcast via WebSocket

2. User opens https://trademind.bot/signals
   ├─ WebSocket connects
   ├─ Receives SPY signal from database
   └─ Sees ThetaSignalCard

3. User approves signal
   ├─ Saved to database: user_signal_executions
   ├─ Trade executed via Tastytrade
   └─ Order ID: 12345

4. Position created
   ├─ Saved to database: positions
   └─ Status: "open"

5. User closes browser
   └─ All React state LOST
```

### Day 1 - Afternoon (2:00 PM)

```
6. User opens browser again
   └─ All state is EMPTY

7. User goes to /positions
   ├─ Frontend: GET /api/positions
   ├─ Backend queries: SELECT * FROM positions WHERE user_id='...'
   └─ User sees SPY position with current P&L

✅ POSITION STILL THERE - It was in database!
```

### Day 2 - Morning (9:35 AM)

```
8. New signals generated
   ├─ IWM signal created
   └─ Saved to database

9. User logs in
   ├─ WebSocket connects
   ├─ Server sends ALL pending signals from database
   │   ├─ SPY (if still pending for this user)
   │   └─ IWM (new today)
   └─ User sees both signals

✅ SIGNALS PERSIST ACROSS DAYS
```

---

## API Endpoints Reference

### Signals

```javascript
// Fetch all pending signals
GET /api/signals
Response: [
  {
    id: "abc-123",
    symbol: "SPY",
    strategy: "theta",
    status: "pending",
    ...
  }
]

// Approve a signal
POST /api/signals/{id}/approve
Body: { userId: "privy|user123" }
Response: { success: true, orderId: "12345" }
```

### Positions

```javascript
// Fetch user's positions
GET /api/positions
Response: [
  {
    id: "12345",
    symbol: "SPY",
    status: "open",
    unrealizedPnl: 120.00,
    ...
  }
]
```

---

## Database Schema (Simplified)

```sql
-- Signal lifecycle
signals
├─ id (PK)
├─ symbol
├─ strategy ('theta', 'calendar_spread', etc.)
├─ status ('pending', 'executed', 'expired')
├─ data (JSONB) - full signal details
├─ created_at
└─ expires_at

-- Per-user execution tracking
user_signal_executions
├─ user_id
├─ signal_id (FK → signals.id)
├─ status ('pending', 'approved', 'executed', 'rejected')
├─ order_id (Tastytrade order ID)
├─ approved_at
└─ executed_at

-- Position tracking
positions
├─ id (PK = Tastytrade order ID)
├─ user_id
├─ signal_id (FK → signals.id)
├─ symbol, strike, expiration, contracts
├─ entry_price
├─ current_value, unrealized_pnl
├─ status ('open', 'closed')
├─ created_at, closed_at
└─ exit_pnl
```

---

## Summary

| Question | Answer |
|----------|--------|
| **Where are signals stored?** | Backend PostgreSQL database on EC2 |
| **Does frontend have a database?** | ❌ No - only ephemeral React state |
| **If user closes window, can they see signals again?** | ✅ Yes - re-fetched from backend on reconnect |
| **After approval → trade → position, where is it stored?** | Backend database in 3 tables: `signals`, `user_signal_executions`, `positions` |
| **Do positions persist after relogin?** | ✅ Yes - fetched from backend via REST API |
| **Can multiple users approve the same signal?** | ✅ Yes - tracked separately in `user_signal_executions` |
| **What happens if backend restarts?** | ✅ All data persists - stored in PostgreSQL |
| **What happens if frontend refreshes?** | React state lost, but data re-fetched from backend immediately |

---

## Key Takeaway

```
┌──────────────────────────────────────────────┐
│  BACKEND = SOURCE OF TRUTH (Persistent)     │
│  ✅ PostgreSQL stores everything             │
│  ✅ Signals, executions, positions           │
│  ✅ Survives restarts, relogins, refreshes   │
└──────────────────────────────────────────────┘
                    ↓
                    ↓ WebSocket / REST API
                    ↓
┌──────────────────────────────────────────────┐
│  FRONTEND = DISPLAY LAYER (Ephemeral)       │
│  ❌ No local database                        │
│  ❌ State lost on close                      │
│  ✅ Re-fetches from backend on load          │
└──────────────────────────────────────────────┘
```

**The frontend is a "view" into the backend database - all persistence happens server-side!**
