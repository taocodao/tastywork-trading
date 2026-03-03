# Last Session — Quick Reference

> **Updated**: 2026-03-01

## Current State

### Active Systems on EC2
- **TQQQ Scheduler** — running `run_tqqq_scheduler.py` with DE-optimized parameters
  - Put Credit strategy (Scenario A), principal-based concurrent position gating
  - Cooldown 6 days, VIX 5-day entry filter, IV multiplier 2.10
- **Theta Scheduler** — `theta_monitor_continuous.py` (24/7 continuous monitor)
- **TradeMind API** — backend serving frontend at trademind.bot

### Recent Work (Mar 2026)
- **Mar 01**: Built the TurboBounce PWA Landing Page Interactive Simulator (EquityCurveChart, TradeFeed, CompoundingCalculator) with scalable multiplier math. Fixed Next.js build timeouts by statically importing translation dictionaries. Constructed ElevenLabs localized voice integration.

### Recent Work (Feb 2026)
- **Feb 27**: Investigated TurboBounce `options_pricer_backtest.py`. Discovered the file is untracked in Git. The +12.31% Mode B result came from `historical_backtest.py`, not the options pricer. The options pricer currently has logic issues with `NAKED_LONG` handling (14 DTE held for 15 days = guaranteed loss).
- **Feb 27**: Set up permanent brain directories across all workspaces (LAST_SESSION.md, brain-bootstrap.md)
- **Feb 26**: Backtested TurboBounce strategy with StrategyRouter (IV-driven routing)
- **Feb 26**: Implemented unified 3-layer TQQQ strategy (order manager, signal publisher, position tracker, risk manager, data pipeline)
- **Feb 25**: Deep analysis of `src/tqqq` — ML components (vix_predictor, contract_ranker)
- **Feb 24**: Deployed DE-optimized TQQQ parameters to EC2
- **Feb 24**: Established Git push deploy workflow (no more SCP)
- **Feb 23**: TQQQ signal execution and monitoring finalized
- **Feb 20**: SFX strategy exit logic improvements (tiered profit targets)
- **Feb 18**: Fixed SFX strategy exits

### Key Config
- **EC2 project dir**: `~/tastywork-trading` (NO `-1` suffix)
- **Deploy**: `git push` → EC2 `git pull` → `systemctl restart trademind-api`
- **IB Gateway**: Docker container, port 4004, IB_HOST=127.0.0.1 on EC2

## Pending / Next Steps
- Rebuild `options_pricer_backtest.py` logic (currently on disk in `src/turbobounce/`) to properly handle `NAKED_LONG` options with realistic DTEs, stop-losses, and profit targets.
- The original +12.31% result came from `src/turbobounce/historical_backtest.py`. Ensure option-pricing backtest aligns with those stock-price-based returns.
- Verify unified TQQQ strategy integration with scheduler (Step 7)
- Continue improving ML signal discovery

---

> ⚠️ **This file should be updated at the end of every session.** Run `/end-session` or manually update before switching accounts.
