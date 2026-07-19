# MTAS Ladder Bot — live implementation of the validated SNDK strategy

## What this is

This is a live-tradeable port of the exact rule set validated in a separate research
workspace's `real_rule_backtest_5m.py` (walk-forward tested 2026-07-16 through 07-18,
train slice = 2025-02-24→2026-02-27, test slice = 2026-03-02→2026-07-14, held out and
never used for parameter selection).

It is **not** the same strategy as anything else already in this repo:

| | This module (`mtas/`) | `bot_v41.py` / `strangle_manager_v41.py` | `sndk/ladder_manager.py` (older) |
|---|---|---|---|
| Entry target | OTM % of spot (43.4% call / 27.8% put) | Delta (0.12 call / 0.15 put) | Delta, ladder step |
| Position cap | 12 legs per side (ladder) | 3 strangles | 3 rungs |
| Exit mechanic | Moneyness cushion floor (0.40 call / 0.22 put) + 30% profit-take | Premium-multiple stop (3.0x) + 50% profit-take, GTC OCA | own friction/stop model |
| Rolls / ML gating | None (intentionally) | Yes | No |
| DTE | Fixed 45 | IVR-adaptive tiers (30–52) | Fixed 60 |

Do not merge parameters across these — they were tuned independently against different
mechanics and mixing them (e.g. adding a premium-multiple stop to this bot) reintroduces
a mechanic that was explicitly tested and **rejected** in the validated research.

## Validation status (be honest about this)

- **Backtested and walk-forward validated**: yes, extensively, against real chained hourly
  (2025-02-24→2026-04-15) and real IB 5-minute (2026-04-16→2026-07-14) SNDK bars. See
  `config_mtas.yaml` for the headline numbers and the research workspace's
  `logs/walk_forward_*.csv`, `logs/dte_otm_sweep_floor40_walkforward.csv`, and
  `logs/legcap_sweep_floor40_walkforward.csv` for the full sweep data.
- **Live-execution tested**: **no.** This code has not been run against a live or paper
  IB Gateway connection. It compiles and its state-persistence logic has been unit-checked
  in isolation, but order placement, fill handling, margin checks, and reconnection/
  reconciliation behavior are all unverified against a real broker session.
- **Recommended next step before any real capital**: run this against the paper IB Gateway
  (same one bot_v41.py already uses, but use client_id 141 so both can coexist on the
  connection if needed) for at least several weeks, and reconcile every fill against the
  `data_mtas/mtas_trades.jsonl` log by hand before considering `mode: live`.

## What's deliberately NOT implemented

Everything below was either tested and rejected, or never adopted, in the backtest research
this session — do not add any of it without re-validating in `real_rule_backtest_5m.py` first:

- Premium-multiple stop-loss (tested, made results worse for the unbounded-loss call side).
- 20% OTM entry targets (tested, catastrophic — 9,000+ trade explosion in the held-out test slice).
- Symmetric (non-asymmetric) cushion floor (tested, the whole point of the fix is the call/put split).
- Vol-percentile-based dynamic leg-cap throttling (tested both symmetric and call-only; collapsed
  test-slice P&L in the symmetric form, and the call-only form showed no provable edge over the
  static 12-leg cap).
- ML regime classification, LSTM strike selection, rolls — never part of this design; those belong
  to the `bot_v41.py` line of development, which this module does not touch.
- A machine-learning trend predictor or a historical-conditional-probability-driven position sizer —
  explicitly considered and passed on: SNDK's own price history only contains ~14 independent
  historical drawdown episodes over the 17-month dataset, nowhere near enough to estimate a
  reliable conditional probability or train a policy without just fitting noise.

## Files

- `config_mtas.yaml` — all strategy constants, annotated with why each value was chosen.
- `mtas_state.py` — position persistence (separate JSON file from `bot_v41.py`'s state, `data_mtas/`).
- `mtas_ladder_manager.py` — the strategy logic: entries, exits, leg-cap gating. Docstring maps
  every rule back to the exact line/section of `real_rule_backtest_5m.py` it mirrors.
- `mtas_bot.py` — entrypoint (`python -m src.otm_naked.sndk.live.mtas.mtas_bot`).

Also added (additive only, does not change existing behavior): `select_strike_by_otm()` in
`../option_chain_selector.py`, a % OTM-of-spot strike selector alongside the existing delta-based
`select_strike()` used by `bot_v41.py`.
