# Decisions Log

Architecture decisions and important changes, in reverse chronological order.

---

## 2026-03-04: Principal-Based Position Sizing (6-Slot Allocation)

**Decision**: Implement user-level position management using a fixed 6-slot capital allocation model, mirroring the `options_pricer_backtest.py` logic.

**Context**: Users needed a way to manage position sizes based on their configured `investmentPrincipal`. The backtest uses `initial_capital / MAX_SLOTS` (where MAX_SLOTS = 6). This provides a conservative but effective equal-weight allocation.

**Resolution**:
- Exposed `investmentPrincipal` from `SettingsProvider` on the Dashboard.
- Displayed "Slot Size" (`Principal / 6`) in the Balance Card.
- Modified `handleTurboApprove` in `dashboard/page.tsx` to send positioning metadata (`investmentPrincipal`, `maxSlots`, `slotCapital`, `riskLevel`) with the approval request.
- This allows the backend execution engine to calculate exact contract quantities based on the user's current settings.

**Affected**: `src/app/dashboard/page.tsx`, `src/components/providers/SettingsProvider.tsx`

---

## 2026-03-03: TurboBounce Signal Pipeline — Full Alignment Complete

**Decision**: Complete all 4 phases of TurboBounce signal pipeline alignment to match Theta gold standard (DB + WebSocket + typed signal classes).

**Context**: TurboBounce was writing signals only to a standalone JSON file and had no DB persistence, no WebSocket broadcast, no typed signal class, and no frontend card. Signals were not appearing on the dashboard, and approval was incorrectly routed through the Calendar Spread executor causing `400 Bad Request` crashes.

**Resolution**:
- Created `signal_publisher/turbobounce.py` with `TurboBounceEntrySignal` (extends `BaseSignal`)
- Updated `signal_publisher/__init__.py` to export new class and factory
- Refactored `run_turbobounce_scheduler.py` to call `publish_turbobounce_entry_signal()`
- Deleted legacy `src/turbobounce/signal_publisher.py`
- Rerouted `tasty_api_server.py` `/api/turbobounce/signals` to query `SignalRepository` (PostgreSQL)
- Added strategy-aware approval routing: TurboBounce → `_execute_turbobounce_for_user()` (raises `NotImplementedError` as explicit placeholder for Option Constructor)
- Fixed `UnicodeEncodeError` in `websocket_client.py` (emoji + Windows cp1252 encoding)
- Built `TurboBounceSignalCard.tsx` React component; linked into `src/app/signals/page.tsx`
- **Deep-Dive Pipeline Fixes**:
    - Fixed `websocket_server.py` history replay logic to correctly map 'turbobounce' strategy to 'turbobounce' channel (previously leaking into `calendar_spread`).
    - Fixed `SignalProvider.tsx` subscription to include `'turbobounce'` in the `CHANNELS` array.
    - Fixed `run_turbobounce_scheduler.py` missing `load_dotenv()` which caused RDS connection failures on EC2.
    - Removed `localhost` WebSocket override in `useSignalSocket.ts` to ensure production connectivity (`wss://ws.trademind.bot`).
    - Added comprehensive normalization in `useSignalSocket.ts` to preserve ML-specific fields (`rsi_2`, `iv_rank`, `total_score`).
- **Verified**: Signals now appearing in real-time on dashboard and signals page with correct ML stats.

**Affected**: `signal_publisher/turbobounce.py` (new), `signal_publisher/__init__.py`, `run_turbobounce_scheduler.py`, `src/turbobounce/signal_publisher.py` (deleted), `tasty_api_server.py`, `websocket_client.py`, `TurboBounceSignalCard.tsx`, `src/app/signals/page.tsx`

---

## 2026-03-02: TurboBounce Signal Pipeline Gap Analysis


**Decision**: Align TurboBounce signal publishing with the Theta strategy's pattern (DB + WebSocket + auto-approve).

**Context**: TurboBounce signals were not appearing on the frontend despite being generated successfully. Investigation revealed TurboBounce's `signal_publisher.py` writes only to a standalone JSON file (`turbobounce_signals.json`) and is completely disconnected from the unified `signal_publisher/` module, `SignalRepository` (PostgreSQL), and WebSocket broadcast infrastructure.

**Resolution**:
- Documented all 6 gaps in `brain/25_SIGNAL_FRAMEWORK.md`
- Target architecture: create `signal_publisher/turbobounce.py` with typed `BaseSignal` dataclasses, add `SignalRepository.save_signal()`, and call `broadcast_to_channel('turbobounce', data)` — matching the Theta gold standard.
- TQQQ has the same gaps (JSON-only persistence, no DB, no WebSocket) but uses proper typed signal classes.

**Affected**: `src/turbobounce/signal_publisher.py`, `signal_publisher/turbobounce.py` (new), `run_turbobounce_scheduler.py`, `tasty_api_server.py`

---

## 2026-03-01: TurboBounce PWA Interactive Simulator & Next.js SSG Refactor

**Decision**: Replaced conventional static web pages with interactive Recharts simulators powered by a global `NarrationContext`, allowing dynamically scalable backtest visualizations (using real ML data) locked to ElevenLabs HTML5 Audio output. 

**Context**: TurboBounce requires a premium, dynamic landing page to convert users by showing them the mathematical reality of compounded trades over time. During construction, the Next.js `npm run build` process failed via SSG timeout loop because `i18next-http-backend` was attempting to fire HTTP network requests while the node build server wasn't live.

**Resolution**:
- Developed interactive `InteractiveTimeline`, `SynchronizedTradeFeed`, and `CompoundingCalculator` React components driven by an `initialInvestment` state multiplier.
- Migrated out of `i18next-http-backend` in favor of statically importing the localized `translation.json` files directly into `src/lib/i18n.ts`, resolving all Production Build compile bugs.
- Deployed Node.js scripts handling automated CSV-to-JSON timeline conversion (`process_turbobounce_trades.js`) and ElevenLabs SDK multi-language generation (`generateNarration.ts`).

**Affected**: `src/app/page.tsx`, `src/components/marketing/*`, `src/lib/i18n.ts`, `scripts/*`

---

## 2026-02-24: EC2 Deployment via Git Push (Not SCP)

**Decision**: Use `git push` + `git pull` on EC2 for all source code deployment. Avoid SCP.

**Context**: Was using `scp` to copy files directly to EC2, which creates uncommitted local changes that conflict with subsequent `git pull`. Also no audit trail.

**Resolution**:
- Local: `git add <files>; git commit -m "..."; git push origin main` (PowerShell: semicolons not `&&`)
- EC2: `cd ~/tastywork-trading && git pull origin main && sudo systemctl restart trademind-api`
- If SCP conflict: `git stash && git pull origin main && git stash drop`
- EC2 project dir is `~/tastywork-trading` (NO `-1` suffix)

**Affected**: `brain/40_EC2_OPERATIONS.md` (updated with workflow)

---

## 2026-02-24: TQQQ DE-Optimized Parameters Deployed

**Decision**: Replace manual TQQQ strategy parameters with DE-optimized values from 29,046-eval overnight Differential Evolution run.

**Context**: Previous params were hand-tuned. After implementing fair 3-scenario comparison (all optimized equally), Scenario A (Put Credit Only) confirmed as optimal.

**Results** (2019–2025, $25K starting capital):
- Scenario A (Put Credit): **+75.1% return, Sharpe 14.58, MaxDD -1.9%** ✅ Winner
- Scenario B (Put + Bear Call): +70.9%, Sharpe 12.20, MaxDD -2.3%
- Scenario C (Full): +53.4%, Sharpe 13.89, MaxDD -1.0%

**Resolution** — Parameters updated in `config.py`:
| Regime | Old Delta | New Delta | Old PT | New PT | Old LM | New LM |
|---|---|---|---|---|---|---|
| LOW_VOL | -0.25 | **-0.16** | 60% | **50%** | 2.0x | **3.8x** |
| NORMAL | -0.30 | **-0.18** | 50% | **56%** | 2.0x | **3.2x** |
| HIGH_VOL | -0.35 | **-0.24** | 40% | **82%** | 2.0x | **2.3x** |
| CRISIS | -0.20 | **-0.14** | 75% | **78%** | 3.0x | **4.3x** |

Also added: `TQQQ_COOLDOWN_DAYS=6`, `TQQQ_VIX_5D_MAX=4.0`, `TQQQ_IV_MULTIPLIER=2.10`, `TQQQ_MAX_RISK_PCT=8.4%`

Also deployed:
- `run_tqqq_scheduler.py`: Cooldown gate + VIX 5-day entry filter
- `spread_builder.py`: `_adjust_delta_by_vix_prediction()` — spike-zone targeting
- `tqqq_backtest_simulation.py`: Breakeven width bonus in optimizer score

**Affected**: `config.py`, `run_tqqq_scheduler.py`, `src/tqqq/spread_builder.py`, `tqqq_backtest_simulation.py`

---


## 2026-02-05: Workspace-Scoped Brain Structure

**Decision**: Create file-based brain directory under each project for persistent memory across sessions.

**Context**: Chat-based memory is ephemeral and doesn't persist across different logins or machines.

**Resolution**: 
- Created `brain/` directory under each workspace
- Structured documentation (00_INDEX, 01_VISION, 02_ARCHITECTURE, etc.)
- Session snapshots for work tracking

**Affected**: All future sessions

---

## 2026-02-05: IB Docker Container Causing Wrong Trades

**Decision**: Stop IB-program-trading Docker containers to prevent individual stock trades.

**Context**: 
- IB paper account showed trades for NFLX, MSTR, KTOS (individual stocks)
- Theta scheduler only trades ETFs (THETA_UNIVERSE)
- Investigation revealed Docker container running separate VCP trading system

**Resolution**:
- Stopped `ib-program-trading-trading-system-1` container
- Stopped related containers (dashboard, api-server, signal-service)
- Left IB Gateway container running for theta scheduler

**Affected**: Docker configuration on EC2

---

## 2026-02-05: IB Connection CancelledError

**Decision**: Change IB_HOST from public IP to localhost on EC2.

**Context**:
- Scheduler connects then immediately disconnects
- Config had `IB_HOST = "34.235.119.67"` (public IP)
- On EC2, should connect via localhost since IB Gateway is local

**Resolution**:
- Changed to `IB_HOST = "127.0.0.1"` on EC2
- IB Gateway runs in Docker, mapped to port 4004

**Affected**: `config.py` on EC2

---

## 2026-02-04: IB Paper Trading Successfully Tested

**Decision**: Confirmed dual-execution model works.

**Context**:
- Manual test via `force_test_trades.py`
- Placed 3 SPY theta puts + 3 calendar spreads

**Resolution**: Code validated, ready for production use.

---

## 2026-02-02: Cron vs Continuous Monitor

**Decision**: Use 24/7 continuous monitor instead of cron.

**Context**:
- Cron approach had issues with wrong directory
- Continuous monitor provides better control and logging

**Resolution**: `theta_monitor_continuous.py` runs 24/7, calls scheduler at scheduled times.

**Affected**: `theta_monitor_continuous.py`
