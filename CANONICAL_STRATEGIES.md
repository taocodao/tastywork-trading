# Canonical Strategy Lineup

As of this consolidation, the repository runs exactly **two** strategies.
Everything else is kept in-tree for reference but is disabled — not
scheduled, not published, and not selectable by the signal orchestrator.

## 1. QQQ LEAPS (`QQQ_LEAPS`)

Automated QQQ options strategy: buys deep-in-the-money long-dated calls
after gated pullbacks, with an optional PMCC (poor-man's covered call)
overlay selling shorter-dated calls.

- **Canonical engine:** `src/qqq_leaps/canonical/qqq_leaps_enhanced_2y_hourly.py`
  - Causal (forward-only) HMM regime filtering — no lookahead
  - Walk-forward gradient-boosted confidence model (`ml_confidence_model.py`),
    40-day forward-return target, purged expanding folds, 0.80 persistence
    threshold for bonus sizing
  - Live NAV sizing: 33% of broker-reported NAV with regime multipliers,
    max 5 contracts per entry
  - PMCC gate: `pmcc_skip_adx_min=16`, VRP 0.9
- **Live executor:** `src/qqq_leaps/canonical/qqq_live_trader.py`
  (hourly during market hours, IBKR paper, marketable-limit orders)
- **Signal service:** `src/qqq_leaps/canonical/qqq_live_signal.py`
- **Source of truth:** github.com/taocodao/qqq-leaps-strategy (PR #1 branch)

## 2. TurboCore Pro (`TURBOCORE_PRO`)

ETF-only tactical allocator across QQQ / QLD / TQQQ / SGOV. Version 3.3
prioritizes drawdown control and execution efficiency.

- **Canonical package:** `src/turbocore_pro/`
  - Two-stage confidence pipeline: 9-feature primary XGBoost → 26-feature
    meta model
  - 0.05 confidence-tier hysteresis band; skips opening/closing hourly bars
  - 15% bull-regime SGOV floor; graduated SMA200 defense; QLD is the
    default leverage satellite, TQQQ reserved for the strongest bull state
- **Live executor:** `src/turbocore_pro/live/paper_trader.py`
  (hourly, IBKR paper, 20% NAV kill switch, $50k order cap, SQLite audit)
- **Frozen models:** `src/turbocore_pro/models/` (fold-10 walk-forward
  artifacts — set up periodic retraining separately)
- **Source of truth:** github.com/taocodao/turbocore-pro

## Disabled strategies

The following remain in the tree but are no longer wired into signal
generation, scheduling, or publishing:

`src/tqqq`, `src/tqqq_turbocore`, `src/turbobounce`, `src/zebra`,
`src/theta_spreads`, `src/calendar_spreads`, `src/diagonal_spreads`,
`src/vertical_spreads`, `src/otm_naked` (incl. SNDK/MTAS), `src/csp`,
`src/dual_core`, `src/ema_cci_macd`, `src/dvo`, `src/pmcc` (standalone),
`src/earnings_intelligence`, plus their `signal_publisher/*` modules and
`run_*_scheduler.py` entry points.

To re-enable one, revert this commit's changes to
`src/combined_signal_generator.py` and `install_signal_crons.sh` and
re-add the corresponding scheduler.
