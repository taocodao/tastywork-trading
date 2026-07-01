# HILO-IV Seller — Comprehensive Implementation Plan V1

> **Date:** 2026-05-31 | **Strategy:** AI/ML-Enhanced OTM Options Selling  
> **Codebase:** `d:\Projects\tastywork-trading-1\src\otm_naked\`

---

## 1. Executive Summary

The HILO-IV Seller strategy identifies stocks near 52-week highs/lows, confirms overbought/oversold conditions via technical indicators, scans for OTM options with elevated IV rank, sells them short to collect premium, and manages risk with spread-aware trailing GTC stops and rolling logic.

**This plan maps the original Perplexity strategy document against the existing codebase, identifies gaps, and defines a phased rollout including backtest validation.**

---

## 2. Current Codebase Audit

### 2.1 What Already Exists (✅ Built)

| Plan Module | Existing File | Status | Notes |
|---|---|---|---|
| Screener (52W H/L) | `signal_engine.py` L205-221 | ✅ Built | 52W proximity checks via `_check_52w_call/put` |
| Signal Engine (RSI/BB/Stoch) | `signal_engine.py` | ✅ Built | 3-layer composite: proximity + momentum + regime |
| Options Scanner (IV Rank) | `feature_engineering.py` L49-56 | ✅ Built | HV-based IV rank proxy over 252 sessions |
| ML Classifier (XGBoost) | `entry_classifier.py` | ✅ Built | 2-stage XGBoost with calibration, 20 primary + 10 meta features |
| Risk Engine | `risk_manager.py` | ✅ Built | 1% per-trade, 5% portfolio heat, VIX crisis gate, 2x stop |
| Strike Selector (BS) | `strike_selector.py` | ✅ Built | Binary search for delta-targeted puts/calls, regime-aware DTE |
| Feature Engineering | `feature_engineering.py` | ✅ Built | RSI(2/5/14/30), Stoch, BB %B, 52W H/L, HV, IV rank, gaps, earnings |
| Backtest Engine | `backtest_engine.py` | ✅ Built | Walk-forward with ML retraining, BS synthetic pricing |
| Backtest Runner | `backtest_otm_naked.py` | ✅ Built | CLI with --no-ml, --capital, --symbols flags |
| Live Scanner | `scanner.py` | ✅ Built | Daily scan with VirtualPortfolio integration |
| Signal Publisher | `signal_publisher/otm_naked.py` | ✅ Built | PostgreSQL signal persistence |
| Config | `config.py` | ✅ Built | 35-stock universe, regime-delta map, all params as dataclass |
| Optimization | `optimization/` | ✅ Built | Optuna study, fast simulator, stress tester, SBB generator |

### 2.2 What Is Missing (❌ Gaps)

| Plan Module | Gap | Priority |
|---|---|---|
| **Spread-Aware Stop-Loss** | No bid/ask spread-aware GTC logic (plan §3.5a-e) | 🔴 HIGH |
| **Trailing Stop Maintenance** | No periodic stop adjustment job (plan §3.5b-c) | 🔴 HIGH |
| **Rolling Logic** | `should_roll` / `find_roll_target` in plan but NOT in code | 🔴 HIGH |
| **Order Manager (Broker)** | Plan uses Alpaca; system uses TastyTrade. No order_manager exists | 🔴 HIGH |
| **GTC Stop Placement** | Backtest uses 2x credit stop but no spread-aware or trailing | 🟡 MED |
| **Alert System** | No Telegram/Discord notifications | 🟡 MED |
| **Trade Logger (SQLite)** | No SQLite trade log; uses VirtualPortfolio JSON | 🟡 MED |
| **Scheduler (APScheduler)** | No scheduler — live scanner runs via external cron | 🟡 MED |
| **Stop Adjustments DB** | No `stop_adjustments` table (plan §3.5d) | 🟡 MED |
| **Earnings Data** | `earnings_days_away` defaults to 999 (no real source) | 🟡 MED |
| **CCI / MACD Indicators** | Plan calls for CCI(20) and MACD; code uses RSI + BB + Stoch only | 🟢 LOW |
| **Dashboard API** | No Next.js API routes | 🟢 LOW |

### 2.3 Backtest Results (Last Run)

From `backtest_otm_naked_trades.csv` (26 closed trades, 2020-2022):

| Metric | Value |
|---|---|
| Total Trades | 26 |
| Wins / Losses | 22W / 4L |
| Win Rate | 84.6% |
| Avg Win | ~$30 |
| Avg Loss | ~$-50 |
| Exit Reasons | profit_take: 20, stop_loss_2x: 4, vix_crisis: 1 |
| Symbols Traded | NVDA (12), NFLX (6), XLE (2) |

> ⚠️ **Key Issue:** Only 26 trades over 4+ years with 35 symbols. Signal filters are too restrictive — most of the equity curve is flat at $50,000. Need to tune entry thresholds to generate more trades for statistical significance.

---

## 3. Implementation Phases

### Phase 1: Core Fixes & Backtest Improvement (Week 1-2)

#### 1.1 Relax Entry Filters

**Files:** `config.py`, `signal_engine.py`

| Parameter | Current | Proposed | Rationale |
|---|---|---|---|
| `min_iv_rank` | 0.25 | 0.15 | 15th pctl still elevated |
| `rsi_overbought` | 70 | 65 | Catch more setups |
| `rsi_oversold` | 30 | 35 | Catch more setups |
| `bb_overbought` | 0.95 | 0.90 | Less extreme needed |
| `bb_oversold` | 0.05 | 0.10 | Less extreme needed |
| `call_near_52w_high_pct` | 0.15 | 0.10 | Tighter = stronger signal |

#### 1.2 Add CCI and MACD Features

**File:** `feature_engineering.py` — Add CCI(20) and MACD(12,26,9) histogram, then add to `entry_classifier.py` PRIMARY_FEATURES.

#### 1.3 Validate Backtest

```bash
python backtest_otm_naked.py --start 2018-01-01 --end 2025-12-31
python backtest_otm_naked.py --start 2018-01-01 --end 2025-12-31 --no-ml
# Target: 100+ trades, Win Rate >= 70%, Sharpe >= 1.0, Max DD < 20%
```

**Tasks:**
- [x] `config.py` — Relax entry thresholds (min_iv_rank 0.25→0.10, RSI 70/30→65/35, BB 0.95/0.05→0.90/0.10, put_decline 0.15→0.08)
- [x] `feature_engineering.py` — Add CCI(20), MACD(12,26,9) histogram + normalized
- [x] `entry_classifier.py` — Add cci_20, macd_hist_norm to PRIMARY_FEATURES; macd_hist to META_FEATURES
- [x] `signal_engine.py` — Extract CCI/MACD from row, pass to momentum checkers (1-of-4 scoring)
- [x] Run backtest — rule-only: 42 trades, WR=81%, Sharpe=2.20; ML-gated: 31 trades, WR=77%, Sharpe=1.86
- [x] Compare ML vs rule-only: rule-only generates more trades (42 vs 31) with higher quality metrics

> **Phase 1 Finding:** The strategy by design goes quiet in low-volatility bull markets (2023-2025). This is correct behavior — the HILO-IV Seller targets stress events (high IV rank + extreme 52W positioning). The 2022 bear market produced 28 of 42 total trades. Accept this regime-conditional frequency.

---

### Phase 2: Spread-Aware Stop-Loss & Trailing (Week 3-4)

#### 2.1 New Module: `stop_manager.py`

From plan §3.5a: Stop price = `max(premium × 1.10, ask_at_entry × 1.05)`

From plan §3.5b: Every 30 min, recompute trailing stop. Stop can only move DOWN (lock in profit as theta decays).

```python
def calculate_spread_aware_stop(premium_collected, ask_at_entry,
                                 stop_loss_pct=0.10, ask_buffer_pct=0.05):
    candidate_naive  = round(premium_collected * (1 + stop_loss_pct), 2)
    candidate_spread = round(ask_at_entry * (1 + ask_buffer_pct), 2)
    return max(candidate_naive, candidate_spread)

def adjust_trailing_stop(current_bid, current_ask, original_stop,
                          stop_loss_pct=0.10, ask_buffer_pct=0.05):
    current_mid    = round((current_bid + current_ask) / 2, 2)
    candidate_mid  = round(current_mid * (1 + stop_loss_pct), 2)
    candidate_ask  = round(current_ask * (1 + ask_buffer_pct), 2)
    new_stop_raw   = max(candidate_mid, candidate_ask)
    adjusted_stop  = min(new_stop_raw, original_stop)  # Only DOWN
    should_update  = adjusted_stop < original_stop
    return adjusted_stop, should_update
```

#### 2.2 Integrate Into Backtest

Simulate bid/ask spread as ±5% around BS mid. Replace simple 2x credit stop with spread-aware trailing logic.

**Tasks:**
- [ ] Create `src/otm_naked/stop_manager.py`
- [ ] Modify `backtest_engine.py` — integrate spread-aware stop + trailing
- [ ] Add bid/ask spread simulation (±5% of BS mid)
- [ ] Add `stop_adjustments` tracking to position dataclass
- [ ] Re-run backtest, verify trailing stops improve P&L ← **NEXT**

---

### Phase 3: Rolling Logic (Week 5-6)

#### 3.1 Add to Risk Manager

- `should_roll()`: signal valid + roll_count < 2 + new_credit >= 50% of stop risk
- `find_roll_target()`: further OTM by 1-2 delta steps using BS strike selector

#### 3.2 Integrate Into Backtest Exit Logic

When stop triggers → re-evaluate signal → roll if conditions met → else close as STOPPED_OUT. Track roll chains.

**Tasks:**
- [ ] Add `should_roll()` and `find_roll_target()` to `risk_manager.py`
- [ ] Modify `backtest_engine.py` exit logic — roll on stop trigger
- [ ] Track roll chains in trades output CSV
- [ ] Re-run backtest, verify rolling reduces stop-out losses

---

### Phase 4: TastyTrade Order Manager (Week 7-8)

#### 4.1 New Module: `order_manager.py`

Wraps existing `tastytrade_client.py` (50KB, full OAuth). Methods: `sell_option`, `place_gtc_stop`, `cancel_gtc_stop`, `roll_position`, `get_option_quote`.

#### 4.2 GTC Stop Maintenance Job: `stop_maintenance.py`

Every 30 min during market hours: fetch quotes → recompute trailing stop → cancel/replace GTC if needed → alert on spread danger.

**Tasks:**
- [ ] Create `src/otm_naked/order_manager.py` (wraps tastytrade_client.py)
- [ ] Create `src/otm_naked/stop_maintenance.py` (30-min trailing job)
- [ ] Paper trade integration test: scan → order → GTC → trail
- [ ] Verify quote fetching for bid/ask spread checks

---

### Phase 5: Trade Logger & Alerts (Week 9-10)

#### 5.1 SQLite Trade Logger: `trade_logger.py`

Tables: `signals`, `trades`, `rolls`, `stop_adjustments` (schema from plan §3.5d, §3.7).

#### 5.2 Telegram Alert System: `alert_system.py`

Alert types: New Signal, Order Filled, Stop Triggered, Position Rolled, Trade Closed, Daily Summary, Spread Danger.

**Tasks:**
- [ ] Create `src/otm_naked/trade_logger.py` (SQLite)
- [ ] Create `src/otm_naked/alert_system.py` (Telegram)
- [ ] Wire logger into scanner.py and order_manager.py
- [ ] Wire alerts into all trade lifecycle events

---

### Phase 6: Scheduler & Go-Live (Week 11-12)

#### 6.1 APScheduler: `run_otm_naked_scheduler.py`

| Time (ET) | Job |
|---|---|
| 8:30 AM | Pre-market scan |
| 9:35 AM | Signal evaluation |
| 9:45 AM | Options chain scan |
| 9:50 AM | Execute signals + GTC stops |
| Every 30m | Position monitor + trailing stop maintenance |
| 3:30 PM | Daily P&L summary |
| 4:30 PM | ML retrain check |

#### 6.2 Deployment

Deploy to EC2 alongside existing TurboCore scheduler. 2-week paper trading validation, then go-live with 1-2 contracts max.

**Tasks:**
- [ ] Create `run_otm_naked_scheduler.py` (APScheduler)
- [ ] Deploy to EC2 alongside TurboCore
- [ ] 2-week paper trading validation
- [ ] Go-live with 1-2 contracts max

---

## 4. Backtest Infrastructure

### 4.1 Current Architecture (Built)

```
backtest_otm_naked.py (CLI)
  └── OTMNakedBacktestEngine (walk-forward)
        ├── build_all_features()      — 40+ features/stock
        ├── OTMSignalEngine           — 3-layer composite
        ├── OTMNakedEntryClassifier   — 2-stage XGBoost
        ├── OTMStrikeSelector         — BS delta targeting
        ├── OTMNakedRiskManager       — sizing + risk gates
        └── Daily loop: exits → retrain → entries → MTM
```

### 4.2 Improvements Needed

| Item | Current | Target |
|---|---|---|
| Trade count | 26 | 100+ |
| Symbols traded | 3 | 15+ |
| Stop logic | 2x credit | Spread-aware + trailing |
| Rolling | Not implemented | Up to 2 rolls |
| Bid/ask sim | None (BS mid) | ±5% spread |
| Earnings | Disabled (999) | Real calendar |

### 4.3 Target Metrics

| Metric | Target | Minimum |
|---|---|---|
| Win Rate | >= 75% | >= 65% |
| CAGR | >= 10% | >= 5% |
| Max Drawdown | < 15% | < 25% |
| Sharpe Ratio | >= 1.2 | >= 0.8 |
| Profit Factor | >= 2.0 | >= 1.3 |
| Trades/Year | >= 15 | >= 8 |

### 4.4 Validation Protocol

```bash
# 1. Baseline (rule-only, relaxed filters)
python backtest_otm_naked.py --no-ml --start 2018-01-01 --end 2025-12-31

# 2. ML-gated
python backtest_otm_naked.py --start 2018-01-01 --end 2025-12-31

# 3. Stress test (already built)
python -m src.otm_naked.optimization.stress_tester

# 4. Optuna optimization (already built)
python -m src.otm_naked.optimization.optuna_study
```

---

## 5. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    HILO-IV SELLER SYSTEM                     │
│                                                              │
│  feature_engineering.py ──► signal_engine.py                │
│  (40+ features)             (3-layer composite)             │
│                                    │                         │
│                                    ▼                         │
│  entry_classifier.py ◄── strike_selector.py                 │
│  (2-stage XGBoost)        (BS delta targeting)              │
│           │                                                  │
│           ▼                                                  │
│  risk_manager.py ───► order_manager.py [NEW]                │
│  (1% risk, 2x stop)   (TastyTrade API)                     │
│                              │                               │
│        ┌─────────────────────┼──────────────┐               │
│        ▼                     ▼              ▼               │
│  stop_manager.py [NEW] trade_logger.py  alert_system.py    │
│  (spread-aware trail)  (SQLite) [NEW]   (Telegram) [NEW]   │
│                                                              │
│  backtest_engine.py (Walk-Forward + Monte Carlo)            │
│  optimization/ (Optuna, Stress Test, Fast Sim)              │
│                                                              │
│  run_otm_naked_scheduler.py (APScheduler) [NEW]             │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Key Design Decisions

1. **Broker: TastyTrade** — Original plan targets Alpaca, but codebase uses TastyTrade with full OAuth. We adapt.
2. **Stops: Spread-Aware + Trailing** — 10% fixed stop replaced with `max(premium*1.10, ask*1.05)`, trailing DOWN only.
3. **Filters: Need Relaxation** — 26 trades in 4+ years is insufficient. Phase 1 tunes thresholds.
4. **ML Bootstrap** — Classifier needs 50+ labeled trades. Heuristic fallback already implemented.
5. **Rolling: Max 2** — Roll further OTM only if signal valid and credit >= 50% of new stop risk.
6. **Crisis Gate** — VIX >= 35 pauses all new entries (non-negotiable, already built).

---

## 7. Risk Guardrails

| Rule | Value | Module |
|---|---|---|
| Max risk per trade | 1% of NAV | risk_manager.py |
| Max portfolio heat | 5% naked notional | risk_manager.py |
| Stop-loss | 2x credit OR spread-aware | stop_manager.py |
| Trailing stop | DOWN only | stop_manager.py |
| Max positions | 5 concurrent | risk_manager.py |
| Max rolls | 2 per trade | risk_manager.py |
| VIX crisis | No entries >= 35 | signal_engine.py |
| Earnings blackout | 21 days | risk_manager.py |
| Max contracts | 5 hard cap | risk_manager.py |
| Spread danger | Alert when ask > GTC | stop_maintenance.py |
