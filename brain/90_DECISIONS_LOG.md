# Decisions Log

Architecture decisions and important changes, in reverse chronological order.

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
