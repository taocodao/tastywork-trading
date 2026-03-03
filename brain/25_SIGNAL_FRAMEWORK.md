# Signal Publishing Framework — Comprehensive Reference

> Created: 2026-03-02  
> Purpose: Complete documentation of the signal lifecycle across all trading strategies (Theta, TQQQ, TurboBounce) for future alignment and debugging.

---

## Architecture Overview

```mermaid
graph TD
    subgraph "Strategy Schedulers"
        TS[run_theta_scheduler.py]
        TQ[run_tqqq_scheduler.py]
        TB[run_turbobounce_scheduler.py]
    end

    subgraph "signal_publisher/ Module"
        BASE[base.py → BaseSignal]
        SP_T[theta.py]
        SP_Q[tqqq.py]
        WSC[websocket_client.py]
    end

    subgraph "TurboBounce Standalone"
        SP_TB[src/turbobounce/signal_publisher.py → TurboBouncePublisher]
    end

    subgraph "Persistence"
        DB[(PostgreSQL via SignalRepository)]
        JSON_T[tqqq_signals.json]
        JSON_TB[turbobounce_signals.json]
    end

    subgraph "Delivery"
        WS[websocket_server.py :8004]
        API[tasty_api_server.py :8002]
    end

    subgraph "Frontend (trademind-app)"
        FE_SIG[/api/signals → SignalProvider]
        FE_TQ[/api/tqqq/signals → Dashboard]
        FE_TB[/api/turbobounce/signals → Dashboard]
    end

    TS --> SP_T --> DB
    SP_T --> WSC --> WS --> FE_SIG
    DB --> API --> FE_SIG

    TQ --> SP_Q --> TQ
    TQ -- "_persist_signal()" --> JSON_T
    JSON_T --> API --> FE_TQ

    TB --> SP_TB --> JSON_TB
    JSON_TB --> API --> FE_TB
```

---

## Strategy-by-Strategy Comparison

### 1. Theta Strategy ✅ (Gold Standard)

| Step | Implementation | File |
|------|---------------|------|
| **Signal Class** | `ThetaEntrySignal` / `ThetaExitSignal` dataclasses | `signal_publisher/theta.py` |
| **Extends BaseSignal?** | No (standalone dataclass), but uses `to_dict()` pattern | `signal_publisher/theta.py` |
| **Factory Function** | `publish_theta_entry_signal(signal)` | `signal_publisher/theta.py:121` |
| **DB Persistence** | ✅ `SignalRepository.save_signal(data)` | `signal_publisher/theta.py:148-153` |
| **WebSocket Broadcast** | ✅ `broadcast_to_channel('theta_puts', data)` + `('theta_entry', data)` | `signal_publisher/theta.py:174-175` |
| **Auto-Approve** | ✅ `auto_approve_signal(data)` → executes trade if criteria met | `signal_publisher/theta.py:156-171` |
| **Scheduler** | `run_theta_scheduler.py` calls `publish_theta_entry_signal(signal)` | `run_theta_scheduler.py:160` |
| **Frontend Fetch** | `/api/signals` → reads from DB via `SignalRepository.get_all_signals()` | `trademind-app/src/app/api/signals/route.ts` |
| **Real-time Push** | WebSocket server broadcasts on `theta_puts` / `theta_entry` channels | `websocket_server.py` |

**Key Pattern**: The `publish_*` function is the single entry point that handles ALL three steps: DB save → auto-approve → WebSocket broadcast.

---

### 2. TQQQ Strategy ⚠️ (Partial Implementation)

| Step | Implementation | File |
|------|---------------|------|
| **Signal Classes** | 7 typed dataclasses extending `BaseSignal` | `signal_publisher/tqqq.py` |
| **Extends BaseSignal?** | ✅ Yes | `signal_publisher/tqqq.py:128` |
| **Factory Functions** | `publish_tqqq_entry_signal()`, `publish_tqqq_diagonal_entry_signal()`, etc. | `signal_publisher/tqqq.py:29-492` |
| **DB Persistence** | ❌ Not saved to database | - |
| **WebSocket Broadcast** | ❌ Not broadcast | - |
| **Auto-Approve** | ❌ Not implemented | - |
| **Scheduler** | `run_tqqq_scheduler.py` calls `publish_*()` → `_persist_signal(signal_dict)` | `run_tqqq_scheduler.py:345-368` |
| **JSON Persistence** | ✅ `_persist_signal()` writes to `~/tastywork-trading/tqqq_signals.json` | `run_tqqq_scheduler.py:969-1002` |
| **Frontend Fetch** | `/api/tqqq/signals` → reads from `tqqq_signals.json` | `trademind-app/src/app/api/tqqq/signals/route.ts` (proxied) |
| **Real-time Push** | ❌ Polling only (no WebSocket) | - |

**Key Gap**: The `publish_*` functions only construct the signal dataclass; the scheduler's `_persist_signal()` writes to a JSON file. There is no DB or WebSocket integration.

---

### 3. TurboBounce Strategy ❌ (Most Disconnected)

| Step | Implementation | File |
|------|---------------|------|
| **Signal Class** | ❌ No typed class — builds raw `dict` inline | `src/turbobounce/signal_publisher.py:51-74` |
| **Extends BaseSignal?** | ❌ No | - |
| **Part of signal_publisher/?** | ❌ No — standalone class in `src/turbobounce/` | `src/turbobounce/signal_publisher.py` |
| **Factory Function** | `TurboBouncePublisher.publish_scanned_signals()` | `src/turbobounce/signal_publisher.py:30` |
| **DB Persistence** | ❌ Not saved to database | - |
| **WebSocket Broadcast** | ❌ Not broadcast | - |
| **Auto-Approve** | ❌ Not implemented | - |
| **JSON Persistence** | ✅ `_append_to_file()` writes to `~/tastywork-trading/turbobounce_signals.json` | `src/turbobounce/signal_publisher.py:80-105` |
| **Frontend Fetch** | `/api/turbobounce/signals` → reads from `turbobounce_signals.json` | `trademind-app/src/app/api/turbobounce/signals/route.ts` |
| **Real-time Push** | ❌ Polling only (no WebSocket) | - |
| **Status Field** | Uses `"PENDING"` (uppercase) vs Theta's `"pending"` (lowercase) | ⚠️ Case mismatch |

---

## Key Gaps to Fix (TurboBounce → Theta Parity)

### Gap 1: No `signal_publisher/` Integration
TurboBounce has its own standalone `TurboBouncePublisher` class in `src/turbobounce/signal_publisher.py` instead of being part of the unified `signal_publisher/` module.

**Fix**: Create `signal_publisher/turbobounce.py` with typed signal dataclasses extending `BaseSignal`.

### Gap 2: No Database Persistence
Signals are only written to a JSON file and never inserted into the PostgreSQL `signals` table via `SignalRepository`.

**Fix**: Add `SignalRepository.save_signal(data)` call inside the publish function (like Theta does).

### Gap 3: No WebSocket Broadcast
The frontend has no way to receive real-time signal updates. Users must refresh the page to see new signals.

**Fix**: Call `broadcast_to_channel('turbobounce', data)` after saving to DB (like Theta does).

### Gap 4: No Auto-Approve Support
Unlike Theta, TurboBounce cannot automatically execute trades when criteria are met.

**Fix**: Add `auto_approve_signal(data)` call (future enhancement, not needed for MVP).

### Gap 5: Status Case Mismatch
TurboBounce uses `"PENDING"` while the rest of the system uses `"pending"`.

**Fix**: Normalize to lowercase `"pending"` to match the `Signal` DB model.

### Gap 6: No Signal Expiration
TurboBounce signals have no `expires_at` field. The Theta publisher sets `expires_at` to market close (16:00 ET).

**Fix**: Add `expires_at` calculation matching Theta's pattern.

---

## File Reference Map

| File | Role | Strategy |
|------|------|----------|
| `signal_publisher/base.py` | `BaseSignal` dataclass | All |
| `signal_publisher/theta.py` | Theta signal classes + publish (DB+WS+auto) | Theta |
| `signal_publisher/tqqq.py` | TQQQ signal classes + publish (return only) | TQQQ |
| `signal_publisher/websocket_client.py` | `broadcast_to_channel()` helper | All |
| `src/turbobounce/signal_publisher.py` | Standalone JSON writer | TurboBounce |
| `src/earnings_intelligence/database.py` | `SignalRepository` (PostgreSQL CRUD) | Theta |
| `run_theta_scheduler.py` | Theta orchestrator | Theta |
| `run_tqqq_scheduler.py` | TQQQ orchestrator + `_persist_signal()` JSON | TQQQ |
| `run_turbobounce_scheduler.py` | TurboBounce orchestrator | TurboBounce |
| `tasty_api_server.py` | HTTP API serving all signal endpoints | All |
| `websocket_server.py` | WebSocket broadcast server (:8004) | Theta |

---

## Frontend Endpoints

| Next.js Route | Python Backend | Source |
|---------------|---------------|--------|
| `/api/signals` | `GET /api/signals` | PostgreSQL (`SignalRepository`) |
| `/api/tqqq/signals` | `GET /api/tqqq/signals` | `tqqq_signals.json` |
| `/api/turbobounce/signals` | `GET /api/turbobounce/signals` | `turbobounce_signals.json` |

---

## Recommended Target Architecture

All strategies should follow the Theta pattern:

```
Scheduler → publish_*() function
  ├── 1. SignalRepository.save_signal()     → PostgreSQL
  ├── 2. auto_approve_signal() [optional]   → Trade execution
  └── 3. broadcast_to_channel()             → WebSocket → Frontend
```

This ensures:
- **Persistence**: Signals survive server restarts
- **Unified API**: All signals available via `/api/signals`
- **Real-time**: Frontend receives instant updates via WebSocket
- **History**: All signals are queryable for analytics/reporting
