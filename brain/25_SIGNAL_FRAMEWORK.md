# Signal Publishing Framework — Comprehensive Reference

> Created: 2026-03-02 | Updated: 2026-03-03
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
        SP_TB[turbobounce.py ✅ NEW]
        WSC[websocket_client.py]
    end

    subgraph "Persistence"
        DB[(PostgreSQL via SignalRepository)]
        JSON_T[tqqq_signals.json]
        JSON_TB[turbobounce_signals.json — legacy backup]
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

    TB --> SP_TB --> DB
    SP_TB --> WSC --> WS --> FE_SIG
    SP_TB -- "legacy backup" --> JSON_TB
    DB --> API --> FE_TB
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

### 3. TurboBounce Strategy ✅ (Aligned — Mar 2026)

| Step | Implementation | File |
|------|---------------|------|
| **Signal Class** | ✅ `TurboBounceEntrySignal` typed dataclass extending `BaseSignal` | `signal_publisher/turbobounce.py` |
| **Extends BaseSignal?** | ✅ Yes | `signal_publisher/turbobounce.py` |
| **Part of signal_publisher/?** | ✅ Yes — fully integrated | `signal_publisher/turbobounce.py` |
| **Metadata Support** | ✅ `confidence`, `cost`, `capital_required` explicitly handled | `signal_publisher/turbobounce.py` |
| **Factory Function** | `publish_turbobounce_entry_signal()` | `signal_publisher/turbobounce.py` |
| **DB Persistence** | ✅ `SignalRepository.save_signal(data)` | `signal_publisher/turbobounce.py` |
| **WebSocket Broadcast** | ✅ `broadcast_to_channel('turbobounce', data)` | `signal_publisher/turbobounce.py` |
| **Auto-Approve** | ✅ `auto_approve_signal(data)` via `executor.py` | `auto_approve.py` |
| **Legacy JSON Backup** | ✅ Still writes to `turbobounce_signals.json` as backward compat | `signal_publisher/turbobounce.py` |
| **Frontend Fetch** | ✅ `/api/signals` (REST Polling) | `SignalProvider.tsx` |
| **Status Field** | ✅ Normalized to lowercase `"pending"` | `SignalRepository.save_signal` |
| **Approval Routing** | ✅ Unified `execute_turbobounce_trade` via `executor.py` | `src/turbobounce/executor.py` |
| **Frontend Card** | ✅ `TurboBounceSignalCard.tsx` renders ML stats correctly | `trademind-app/src/components/` |

---

## ✅ TurboBounce Alignment — COMPLETED (Mar 3, 2026)

All 6 gaps were fixed. See `90_DECISIONS_LOG.md` for details and `sessions/2026-03-03-session-01.md` for full implementation log.

| Gap | Status | Fix Applied |
|-----|--------|-------------|
| No `signal_publisher/` integration | ✅ Fixed | Created `signal_publisher/turbobounce.py` |
| No DB persistence | ✅ Fixed | `SignalRepository.save_signal()` in publish function |
| No WebSocket broadcast | ✅ Fixed | `broadcast_to_channel('turbobounce', data)` |
| Timestamp parsing bug | ✅ Fixed | Stripped microseconds from ISO string in frontend (JS NaN fix) |
| Status case mismatch | ✅ Fixed | Normalized to lowercase `"pending"` |
| No signal expiration | ✅ Fixed | `expires_at` added matching Theta's pattern |
| Missing metadata sync | ✅ Fixed | Updated `SignalResponse` Pydantic model for `confidence` & `cost` |

## Remaining Gap: TQQQ → Theta Parity

TQQQ still uses JSON-only persistence. Same alignment work needed:
- Add `SignalRepository.save_signal()` to `publish_tqqq_*()` functions
- Add `broadcast_to_channel('tqqq', data)` WebSocket broadcast
- Reroute `tasty_api_server.py` `/api/tqqq/signals` to query PostgreSQL

---

## File Reference Map

| File | Role | Strategy |
|------|------|----------|
| `signal_publisher/base.py` | `BaseSignal` dataclass | All |
| `signal_publisher/theta.py` | Theta signal classes + publish (DB+WS+auto) | Theta |
| `signal_publisher/tqqq.py` | TQQQ signal classes + publish (return only) | TQQQ |
| `signal_publisher/turbobounce.py` | ✅ TurboBounce signal classes + publish (DB+WS) | TurboBounce |
| `signal_publisher/websocket_client.py` | `broadcast_to_channel()` helper | All |
| ~~`src/turbobounce/signal_publisher.py`~~ | ~~Standalone JSON writer~~ — **DELETED** | - |
| `src/earnings_intelligence/database.py` | `SignalRepository` (PostgreSQL CRUD) | Theta + TurboBounce |
| `run_theta_scheduler.py` | Theta orchestrator | Theta |
| `run_tqqq_scheduler.py` | TQQQ orchestrator + `_persist_signal()` JSON | TQQQ |
| `run_turbobounce_scheduler.py` | TurboBounce orchestrator (refactored) | TurboBounce |
| `tasty_api_server.py` | HTTP API serving all signal endpoints | All |
| `websocket_server.py` | WebSocket broadcast server (:8004) | Theta + TurboBounce |
| `trademind-app/.../TurboBounceSignalCard.tsx` | ✅ React component for TB signal display | TurboBounce |

---

## Frontend Endpoints

| Next.js Route | Python Backend | Source |
|---------------|---------------|--------|
| `/api/signals` | `GET /api/signals` | PostgreSQL (`SignalRepository`) |
| `/api/tqqq/signals` | `GET /api/tqqq/signals` | `tqqq_signals.json` ⚠️ JSON only |
| `/api/turbobounce/signals` | `GET /api/turbobounce/signals` | ✅ PostgreSQL (strategy=turbobounce, status=pending) |

---

## Recommended Target Architecture

All strategies should follow the Theta pattern:

```
Scheduler → publish_*() function
  ├── 1. SignalRepository.save_signal()     → PostgreSQL
  ├── 2. auto_approve_signal()              → Unified Executor (`executor.py`)
  └── 3. broadcast_to_channel()             → WebSocket → Frontend
```

This ensures:
- **Persistence**: Signals survive server restarts
- **Unified API**: All signals available via `/api/signals`
- **Real-time**: Frontend receives instant updates via WebSocket
- **History**: All signals are queryable for analytics/reporting

---

## Client-Side Portfolio Sizing (Two-Tier Model) - Mar 2026

To handle scaling across multiple users with different capital levels, start dates, and brokerage types, the system adopts a decoupled sizing architecture.

### 1. Tier 1: General Signals (Backend)
The backend ML engine calculates the **theoretical optimal state** of the portfolio and broadcasts a universal "Target Percentage" payload.
*   **Source**: `signal_publisher/turbocore.py`
*   **Payload Example**: `{"TQQQ": 0.80, "SGOV": 0.20}`
*   **Benefit**: Infinite backend scalability.

### 2. Tier 2: Personalized Execution (Client/Adapter)
The execution engine (linked to the user's specific account) interprets the general signal and calculates the absolute delta required to synchronize.

#### Mode A: Direct Broker Sync (Live)
For users with linked Tastytrade accounts, the engine:
1.  Queries real-time `Net_Liq` via API.
2.  Calculates `Target_Value = Net_Liq * Target_%`.
3.  Determines `Delta_Shares = (Target_Value - Current_Value) / Market_Price`.
4.  Submits limit orders directly to the broker.

#### Mode B: Virtual Shadow Ledger (Manual)
For users without linked accounts, the engine:
1.  Tracks a virtual balance (updated manually by the user).
2.  Calculates the same Delta math.
3.  Triggers an SMS/App Notification with the specific "Buy/Sell" instructions for the user's external brokerage.

### Summary of Benefits
*   **Start-Time Agnostic**: A user starting on Day 100 simply buys into the correct Day 100 percentages immediately.
*   **Self-Correcting**: If a user's balance changes due to external factors (deposits/fees), the next signal rebalance naturally accounts for the new total capital.
