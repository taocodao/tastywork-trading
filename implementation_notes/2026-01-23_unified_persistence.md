# Unified Persistence Architecture
**Date:** 2026-01-23
**Status:** Implemented

## Problem: "Split Brain" Signals
The system previously had a race condition/disconnect between signal generation and execution:
1. **Signal Publisher** (Scanner) wrote new signals to the Database (`SignalRepository`).
2. **WebSocket Server** (Frontend Feed) read from a stale/legacy `signals.json` file on disk.
3. **API Server** (Trade Approval) also read from `signals.json`.

This resulted in:
- Frontend showing stale or no signals (or failing with 401/426 when trying to fetch HTTP).
- Approvals failing because the API server couldn't find the signal ID in its local JSON file, even if the user somehow clicked approve.

## Solution: Single Source of Truth
We have unified all components to use the `src.earnings_intelligence.database` module.

### Components Updated
1. **WebSocket Server (`websocket_server.py`)**
   - **Old:** `load_signals_from_disk()` reading `signals.json`.
   - **New:** `load_signals_from_db()` calling `SignalRepository.get_all_signals()`.
   - **Result:** Pushes correct, real-time DB signals to frontend upon connection.

2. **API Server (`tasty_api_server.py`)**
   - **Old:** `handle_approve_signal` looked in `_signals` list loaded from JSON.
   - **New:** `handle_approve_signal` calls `SignalRepository.get_signal(id)` and `save_signal()`.
   - **Result:** Approvals update the actual DB record, which is visible to the Publisher and WebSocket server.

3. **Frontend (`SignalProvider.tsx`)**
   - **Old:** Fetched HTTP `GET /api/signals` (causing 426 errors on WS port).
   - **New:** Relies 100% on WebSocket `connected` and `signal` messages to populate state.

## Deployment Instructions (EC2)
When deploying this fix to EC2:

1. **Pull Code:**
   ```bash
   git pull
   ```

2. **Restart Services:**
   Both python processes must be restarted to load the new database logic.
   ```bash
   pkill -f websocket_server.py
   pkill -f tasty_api_server.py
   
   nohup python3 websocket_server.py > websocket.log 2>&1 &
   nohup python3 tasty_api_server.py > api.log 2>&1 &
   ```
