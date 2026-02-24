# Decisions Log

Architecture decisions and important changes, in reverse chronological order.

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
