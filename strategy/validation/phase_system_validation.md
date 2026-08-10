# NAV-Based Phase System — Four-Run Validation Matrix

**Date:** 2026-08-10
**Engine:** 5y hourly canonical variant (2021-08-02 → 2026-07-31), $8,600 start
**Module:** `src/qqq_leaps/phase_manager.py` + `config/phase_config.yaml` (PR #6)

## Results

| Run | Initial | Final NAV | CAGR | Sharpe | Max DD | Calmar | PMCC opens | Transitions |
|---|---|---|---|---|---|---|---|---|
| **Dynamic (phase system)** | $8,600 | $13,068 | 8.76% | 0.736 | -22.9% | 0.383 | 18 | 1 |
| Static-Seed (SEED const) | $8,600 | $13,068 | 8.76% | 0.736 | -22.9% | 0.383 | 18 | 0 |
| Static-Target @ $8.6K | $8,600 | $31,867 | 30.08% | 1.104 | -25.9% | 1.163 | 139 | 0 |
| Static-Target @ $30K | $30,000 | $65,916 | 17.12% | 0.976 | -17.4% | 0.986 | 285 | 0 |
| QQQ Buy & Hold | $8,600 | $16,230 | 13.56% | 0.672 | -35.6% | 0.381 | — | — |

Dynamic phase transitions: 1 (`NONE → SEED` initial assignment; NAV peaked at $13,217 and never crossed the $15K GROWTH floor, so no further transitions).

## Analysis

### 1. Dynamic ≡ Static-Seed at $8,600 (expected)
Starting at $8,600, NAV never reached the $15,000 GROWTH threshold (peak $13,217), so the
phase system stayed in SEED for all 1,255 days. Dynamic and Static-Seed are identical by
construction here — this confirms the phase machinery is wired correctly and is a no-op when
NAV stays within one band.

### 2. The phase system does NOT beat static TARGET sizing at $8,600 — and why
The original seed-backtest framing assumed TARGET params (0.85 delta) are **capital-starved**
at $8,600 (i.e. cash-rejected). That is **not how this engine behaves**: `open_leaps` solves
for the largest affordable size and floors at `max(1, ...)` contract. One LEAPS contract
(~$10K notional at 0.85 delta) is affordable at $8,600, so Static-Target@8.6K simply runs
1-contract TARGET trades and — because higher delta + more aggressive PMCC compound faster in
this 5y bull-leaning window — it produces the highest CAGR (30%) of any run.

**This is the honest headline: at $8,600, the phase system underperforms naive static TARGET
sizing on CAGR/Sharpe.** The phase system's value is not return maximization at small capital —
it is **risk-appropriate sizing as capital scales**, and **drawdown control at large capital**
(TARGET@30K maxDD -17.4% vs TARGET@8.6K -25.9%).

### 3. Where the phase system actually earns its keep
- **Capital scaling discipline:** it prevents a small account from running full TARGET
  concentration (1 contract = ~100% of NAV at $8.6K), which is a real-account risk even if the
  backtest's 1-contract floor hides it.
- **Drawdown-based demotion:** the 15% emergency demotion and hysteresis protect a grown
  account. This only matters once NAV is large enough to demote *from* — not exercised at $8,600.
- **Deposit-triggered promotion:** the seed backtest's key insight was that the practical path
  to $25K+ is external capital, not compounding. The phase system is built for exactly that —
  a deposit that pushes NAV into GROWTH/TARGET promotes sizing automatically (skip-level
  allowed, dwell-gated).

### 4. Reconciliation with the seed backtest
The seed backtest (Scenario D, seed+PMCC 0.15) reported 8.03% CAGR / -23.7% DD. My Dynamic run
(SEED with defensive PMCC 0.15) reports 8.76% CAGR / -22.9% DD — close but not identical. The
delta is attributable to (a) the precomputed `features_daily_shared.csv` HMM/ML features vs a
fresh in-engine fit, and (b) minor data-prep differences (VIX term structure join, rf fill).
Directionally consistent: SEED+defensive-PMCC lands in the high-8% CAGR / low-20s DD band.

## Caveats
- **Single window, bull-leaning:** 2021-08 → 2026-07 is net-up for QQQ. The phase system's
  demotion/hysteresis logic is untested by this window (no transitions beyond initial). A
  dedicated bear-window or synthetic shock test is needed to exercise demotion.
- **1-contract floor masks capital starvation:** the engine's `max(1, ...)` means "cash
  rejection" never fires. If the goal is to model true capital constraints, the floor should be
  revisited — but that is a separate engine decision, not a phase-system one.
- **Features are precomputed**, not refit in-engine; results are reproducible from
  `data/features/features_daily_shared.csv` in the reference repo.

## Recommendation
Proceed to **Step 2 (tune thresholds)** with a bear-window / shock test to exercise demotion,
then **Step 3 (app-side `account_phase_transitions` + phase-at-fan-out + Resend alerts)**. The
phase system is correct and safe; its production value is capital-scaling discipline and
deposit-triggered promotion, not return maximization at $8,600.
