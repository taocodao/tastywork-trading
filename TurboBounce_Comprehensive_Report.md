# TurboBounce — Comprehensive Strategy Report
*Generated from source code analysis · April 2026 · `d:\Projects\tastywork-trading-1\src\turbobounce\`*

---

## Table of Contents
1. [What Is TurboBounce?](#1-what-is-turbobounce)
2. [Signal Generation — How It Finds Trades](#2-signal-generation--how-it-finds-trades)
3. [Scoring Engine — 4-Factor Ranking](#3-scoring-engine--4-factor-ranking)
4. [Options Strategy Router — IV-Adaptive Structure](#4-options-strategy-router--iv-adaptive-structure)
5. [Spread Builder & Leg Construction](#5-spread-builder--leg-construction)
6. [Risk Manager — Slots, Sizing & Correlation](#6-risk-manager--slots-sizing--correlation)
7. [Exit Engine — 6-Priority Cascade](#7-exit-engine--6-priority-cascade)
8. [Crash Guard — 2-Tier Entry Gate](#8-crash-guard--2-tier-entry-gate)
9. [Backtest Methodology](#9-backtest-methodology)
10. [Backtesting Results — All Capital Sizes](#10-backtesting-results--all-capital-sizes)
11. [Version History & Key Bug Fixes](#11-version-history--key-bug-fixes)
12. [ML Integration — What Exists and What Doesn't](#12-ml-integration--what-exists-and-what-doesnt)
13. [Open Problems & Improvement Roadmap](#13-open-problems--improvement-roadmap)

---

## 1. What Is TurboBounce?

TurboBounce is a **short-term mean-reversion options trading system** — not a trend-following system. Its premise is that stocks and ETFs that experience extreme short-term moves (measured by RSI-2, Bollinger %B, and 3-day returns) reliably snap back toward their means within 5–10 trading days.

The key innovation over a simple RSI contrarian strategy is the **Volatility-Adaptive Engine**: rather than always buying the same type of option, TurboBounce reads the current IV environment and dynamically selects the structurally optimal options structure for that regime:

| IV Environment | Structure Used | Rationale |
|---|---|---|
| Low IV (< 30 IVR) | Deep ITM LEAPS (Naked Long, 180 DTE) | Cheap options — buy leverage with low theta burn |
| High IV (>= 30 IVR) | Bull Put Credit Spread (30-45 DTE) | Expensive options — sell premium, collect IV crush on bounce |
| Leveraged ETFs (TQQQ, LABU) | Forced Credit Spread | Distorted IV profiles make naked longs structurally inferior |
| VIX > 30 (Crisis) | Forced Credit Spread | Crash Guard forbids LEAPS in crisis regimes |
| Extreme IV + VIX above SMA | Put Broken-Wing Butterfly (BWB) | Maximum premium collection in capitulation environments |

### Universe

TurboBounce scans a universe of ~615 tickers: a curated watchlist of 115 liquid names plus the full S&P 500 fetched dynamically from Wikipedia. The base list includes:
- **3x Leveraged ETFs**: TQQQ, LABU, NUGT, AGQ, UVXY
- **Mega-cap tech**: NVDA, AAPL, MSFT, META, GOOG, AMZN, TSLA, AVGO
- **Semiconductors**: AMAT, MU, AMD, ARM, MRVL, CRDO, TSM, ASML, ADI
- **Growth/momentum**: COIN, PLTR, NET, CRWD, SNOW, NOW, DASH, APP, SHOP
- **ETFs**: QQQ, RSP, SPY, ARKK, ARKW, GDX

---

## 2. Signal Generation — How It Finds Trades

**File**: `scanner.py` — Runs at 8:00 AM ET (morning scan)

### Filter Pipeline

```
Universe (~615 tickers)
    |
    v  Filter 1: Liquidity
    |   avg_volume x close_price >= $1,000,000/day
    |
    v  Filter 2: Falling Knife Protection (Regime)
    |   dist_from_200_SMA > -25%  (not in structural downtrend)
    |
    v  Filter 3: Signal Trigger (any ONE must fire)
    |   - RSI-2 < 10         (extreme oversold)
    |   - Bollinger %B < 0   (below lower band)
    |   - 3-day return < -8% (sharp capitulation drop)
    |
    v  Filter 4: CrashGuard scoring (>= 55 points required)
    |
    v  Score & Rank (top 3 per direction, max 6 per day)
```

### Key Metrics Computed Per Ticker

| Metric | Calculation | Purpose |
|---|---|---|
| rsi_2 | 2-period RSI | Primary entry trigger |
| pct_b | Bollinger %B | Band extremity filter |
| ret_3d | 3-day price return | Capitulation catch-all |
| dist_sma_200 | (Close - SMA200) / SMA200 | Falling knife guard |
| realized_vol | 20-day annualized log-return std | Used as IV proxy in backtest |
| iv_rank | Realized vol percentile vs 252-day range | Strategy routing input |
| hurst | Hurst exponent (60-bar rescaled range) | Mean-reversion tendency |
| vol_ratio | Today's volume / 20-day avg | Capitulation volume confirmation |

---

## 3. Scoring Engine — 4-Factor Ranking

**File**: `scoring.py`

Once a ticker passes the hard filters, it receives a 0–100 composite score:

```
Score = 0.35 * RSI_Extremity
      + 0.25 * IV_Rank
      + 0.20 * Options_Liquidity
      + 0.20 * Mean_Reversion_History
```

| Factor | Weight | How Scored |
|---|---|---|
| RSI Extremity | 35% | For oversold: (15 - RSI) x 6.66; score peaks at RSI=0, zero at RSI=15 |
| IV Rank | 25% | Higher IV = higher score (0-100 direct) |
| Options Liquidity | 20% | Bid-ask spread: $0.01 = 100 pts, $0.15 = 0 pts |
| Mean Reversion History | 20% | Historical 5-day bounce rate; hardcoded 85 for 3x leveraged ETFs, 50 for all others |

> NOTE: The mean_reversion_history field is a placeholder — it defaults to 50 for most tickers and 85 for leveraged ETFs. A real ML win-rate estimator per ticker has NOT been implemented (see Section 12).

Candidates with score < 40 are discarded. The top 3 oversold and top 3 overbought are forwarded to the Strategy Router.

---

## 4. Options Strategy Router — IV-Adaptive Structure

**File**: `strategy_router.py`

### Decision Matrix (Bullish / Oversold)

```
Is the ticker a leveraged ETF? (TQQQ, LABU, NUGT, SQQQ, UVXY)
    YES --> CREDIT_SPREAD (30 DTE, 0.20 delta, forced)

Is VIX > VIX 50-day SMA AND IV_Rank >= 70?
    YES --> PUT_BWB (Broken-Wing Butterfly, 30 DTE)

Is VIX > 30? (Crisis regime)
    YES --> CREDIT_SPREAD (Crash Guard override)

Is IV_Rank >= 30?
    YES --> CREDIT_SPREAD (Bull Put, 30 DTE, 0.20 delta)

Otherwise (Low IV environment):
    NAKED_LONG (Deep ITM Call LEAPS, 180 DTE, 0.80 delta)
```

### Options Structures Explained

**CREDIT_SPREAD (Bull Put)**
- Sell a put 3% OTM, buy a put 6% OTM at 30 DTE
- Max profit = credit received; Max loss = spread width minus credit
- Sizing: 3% of account equity per trade
- Best in: high IV environments (IV crush tailwind + price bounce)
- Profit target: close when short put loses 50% of credit value (P0 exit)

**NAKED_LONG (Deep ITM LEAPS)**
- Buy a call 20% ITM at 180 DTE (~0.80 delta)
- Behaves like stock replacement — minimal theta, high delta
- Max loss = premium paid; No cap on upside
- Best in: low IV environments (cheap options)
- Sizing: 5% of account equity per trade (quarter-Kelly)

**DIAGONAL (Poor Man's Covered Call)**
- Buy a deep ITM long-dated anchor call (180 DTE, ~0.85 delta)
- Sell a short-dated OTM call (14 DTE, ~0.30 delta) against it
- Net debit; short call offsets theta on the anchor position

**PUT_BWB (Broken-Wing Butterfly)**
- Buy OTM put (3% OTM), sell 2x body puts (7% OTM), buy far OTM put (15% OTM)
- Structured for guaranteed net credit (ratio rule: lower wing >= 2.0x upper wing)
- Max profit: unlimited to the upside (stock recovers)
- Best in: extreme capitulation with VIX spike

---

## 5. Spread Builder & Leg Construction

**File**: `spread_builder.py`

The StrategyBuilder class constructs real option legs from live chain data (IB Gateway in production, Black-Scholes simulation in backtests).

### Strike Selection Rules

| Structure | Anchor (Long) | Hedge (Short) | Expiry Tolerance |
|---|---|---|---|
| DIAGONAL | ~0.40 delta | ~0.20 delta | +/- 30 days for LEAPS; +/- 5 days for weeklies |
| CREDIT_SPREAD | Closest to target delta | target delta minus spread width | +/- 5 days |
| NAKED_LONG | Closest to target delta (0.80) | N/A | +/- 30 days |

### Liquidity Gate (Per Leg)
- Volume >= 10 contracts
- Open Interest >= 50
- Bid-Ask spread <= $1.00

### Slippage Check
- Entry rejected if ask > 1.20x mid-price (> 20% deviation from fair value)

---

## 6. Risk Manager — Slots, Sizing & Correlation

**File**: `risk_manager.py`

### Allocation Modes

| Mode | TQQQ Slots | Multi-Ticker Slots | Total Max |
|---|---|---|---|
| MODE_A (Dedicated 50/50) | 3 | 3 | 6 |
| MODE_B (Unified 100%) | Up to 6 | Up to 6 | 6 (shared) |

All backtests run in MODE_B (TQQQ competes for slots on equal footing).

### Position Sizing Formula

```python
if strategy_type == 'NAKED_LONG':
    MAX_RISK_PCT = 0.05   # 5% of equity (quarter-Kelly)
else:
    MAX_RISK_PCT = 0.03   # 3% of equity (spreads)

MAX_POSITION_PCT = 0.10   # Hard cap: never > 10% of equity in one position

contracts = floor(equity * MAX_RISK_PCT / max_loss_per_contract)

# CRITICAL RULE: if even 1 contract exceeds risk budget --> SKIP trade (no override)
```

Key fix vs V3: The V3 disaster came from a max(1, contracts) override that forced entry even when 1 contract cost $8,294 on a $15K account (55% of capital in one trade). This override was permanently removed in V4.

### Correlation Guard
- Max 2 positions per sector category (no more than 2 semiconductors open simultaneously)
- Leveraged ETFs and Core ETFs are EXEMPT from the sector limit

---

## 7. Exit Engine — 6-Priority Cascade

**File**: `swing_exit_engine.py` — V4.1, research-validated (Connors, Alvarez, Tastylive)

Exits are evaluated every trading day on every open position:

| Priority | Trigger | Action | Source |
|---|---|---|---|
| P0 | Credit spread: PnL >= 50% of max credit | CLOSE_ALL | Tastylive 50% credit rule |
| P0 | Naked/debit: PnL >= 25% of cost | CLOSE_ALL | 25% of debit structures |
| P1 | Price > 5-day SMA (bulls) after >= 2 days held | CLOSE_ALL | Connors original SMA exit |
| P1 | Price < 5-day SMA (bears) after >= 2 days held | CLOSE_ALL | Connors original SMA exit |
| P2 | RSI-2 >= 65 (bulls) / <= 35 (bears) after >= 2 days | CLOSE_ALL | Alvarez RSI threshold |
| P3 | PnL <= -50% of allocated capital | CLOSE_ALL | Tastylive spread value stop |
| P5 | Days traded >= 8 trading days | CLOSE_ALL | V5: days 8-10 suffer theta cliff |
| P6 | Anchor option DTE <= 7 | CLOSE_ALL | Avoid gamma/assignment risk |

Design note: P1 (5-day SMA cross) fires before RSI (P2). This was changed from V3 where RSI-2 > 50 override was causing premature exits on intraday noise.

---

## 8. Crash Guard — 2-Tier Entry Gate

**File**: `crash_guard.py`

Every entry must pass CrashGuard before a position is opened.

### Tier 1: Hard Gates
- Gate 1: Price is > 25% below 200-day SMA --> REJECTED (falling knife)
- Gate 2: Circuit breaker flag active (live only — Redis state)

### Tier 2: Scoring Engine (0-100 points, minimum 55 required)

| Factor | Max Points | Criteria |
|---|---|---|
| RSI-2 Depth | 25 pts | RSI < 5 = 25 pts; < 10 = 20 pts; < 15 = 15 pts; < 20 = 10 pts |
| Distance from 200 SMA | 20 pts | Above SMA = 20; within 5% below = 15; within 15% below = 10 |
| Hurst Exponent | 15 pts | < 0.35 (strong mean-reversion) = 15; > 0.55 = 0 pts |
| VIX Term Structure | 15 pts | VIX < 50-day SMA = 15; within 10% above = 10 |
| Volume Capitulation | 10 pts | Vol > 2x average = 10; > 1.5x = 7 pts |
| ML Probability | 15 pts | > 75% = 15; > 65% = 10; > 55% = 5 pts |

### CrashGuard Position Size Multiplier

| Score | Multiplier | Interpretation |
|---|---|---|
| 85-100 | 2.0x | Highest confidence — double base position |
| 75-84 | 1.6x | High conviction |
| 65-74 | 1.2x | Above average |
| 55-64 | 1.0x | Standard size — minimum threshold |
| < 55 | 0x | Trade blocked |

---

## 9. Backtest Methodology

**Files**: `options_pricer_backtest.py` (main), `historical_backtest.py` (simplified), `run_multiyear.py` (orchestrator)

### Simulation Approach: Black-Scholes Options Pricer

Unlike simple equity backtests, TurboBounce's primary backtest prices options at entry and exit using Black-Scholes:

``` 
# Entry: price the option with IV premium inflated by IV regime
entry_sigma = realized_vol * IV_multiplier(iv_rank, is_entry=True)
# IVR >= 70 -> 1.50x; IVR >= 50 -> 1.35x; IVR >= 30 -> 1.20x; else 1.05x

# Exit: IV normalizes after bounce — decaying VRP premium
exit_sigma = realized_vol * IV_multiplier(days_held)
# Decays from ~1.30x at day 0 to ~1.05x at day 10+
```

### Key Assumptions & Limitations

| Assumption | Current Value | Reality Gap |
|---|---|---|
| IV proxy | 20-day realized volatility | Conservative — actual implied IV is typically 10-30% higher |
| ML probability | Hardcoded at 0.60 for all | Actual ML model not trained for TurboBounce |
| VIX term structure | 1.05 hardcoded in scanner | Reasonable approximation |
| Risk-free rate | Year lookup table (1.5% 2021, 5.2% 2023) | Approximate |
| Slippage/commissions | NOT modeled | Real execution adds ~$0.65-$1.00/contract |
| Options liquidity | All options assumed available | Not all tickers have liquid options chains |
| Overbought direction | Disabled in options_pricer_backtest | Only BULLISH (oversold) trades are tested |

---

## 10. Backtesting Results — All Capital Sizes

**Period**: 2019-2025 (7 years) compounding capital
**Mode**: MODE B (Unified — TQQQ competes with all tickers)
**Strategies**: NAKED_LONG, CREDIT_SPREAD, DIAGONAL, PUT_BWB

---

### 10.1 — $5,000 Starting Capital (Compounding)

| Year | Start $ | Trades | Win% | Avg Win | Avg Loss | TQQQ PnL | Net PnL | End $ | Return% |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | $5,000 | 167 | 50.9% | $50 | -$58 | +$127 | -$518 | $4,481 | -10.4% |
| 2020 | $4,481 | 147 | 52.4% | $121 | -$106 | -$231 | +$1,956 | $6,438 | +43.7% |
| 2021 | $6,438 | 124 | 50.0% | $149 | -$114 | +$304 | +$2,194 | $8,632 | +34.1% |
| 2022 | $8,632 | 128 | 62.5% | $128 | -$177 | $0 | +$1,727 | $10,359 | +20.0% |
| 2023 | $10,359 | 157 | 43.3% | $139 | -$150 | -$66 | -$3,935 | $6,424 | -38.0% |
| 2024 | $6,424 | 123 | 60.2% | $225 | -$192 | +$161 | +$7,291 | $13,715 | +113.5% |
| 2025 | $13,715 | 139 | 65.5% | $320 | -$509 | -$172 | +$4,711 | $18,426 | +34.4% |

**6-Year Aggregate**: $5K -> $18,426 | +268.5% total | Avg win rate: 55.0% | 985 trades

Notable: 2023 was -38% despite a bullish equity market, because low IV throughout 2023 drove the system into LEAPS entries where bounces were shallow and theta burned quickly.

---

### 10.2 — $20,000 Starting Capital (Compounding)

| Year | Start $ | Trades | Win% | Avg Win | Avg Loss | TQQQ PnL | Net PnL | End $ | Return% |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | $20,000 | 197 | 49.7% | $252 | -$178 | +$3,943 | +$7,055 | $27,055 | +35.3% |
| 2020 | $27,055 | 183 | 48.1% | $363 | -$350 | -$1,008 | -$1,273 | $25,782 | -4.7% |
| 2021 | $25,782 | 195 | 49.7% | $312 | -$267 | +$2,099 | +$4,090 | $29,872 | +15.9% |
| 2022 | $29,872 | 101 | 39.6% | $449 | -$435 | -$3,299 | -$8,595 | $21,277 | -28.8% |
| 2023 | $21,277 | 208 | 45.7% | $402 | -$239 | +$961 | +$11,186 | $32,463 | +52.6% |
| 2024 | $32,463 | 166 | 49.4% | $672 | -$381 | -$52 | +$23,075 | $55,538 | +71.1% |
| 2025 | $55,538 | 157 | 52.2% | $559 | -$627 | -$275 | -$1,190 | $54,348 | -2.1% |

**6-Year Aggregate**: $20K -> $54,348 | +171.7% total | Avg win rate: 47.8% | 1,207 trades

Notable: 2022 was severe (-28.8%). TQQQ lost -$3,299 as leveraged ETF bounces kept failing during structural bear market. The 200 SMA filter was insufficient to block TQQQ entries during the extended 2022 downtrend.

---

### 10.3 — $25,000 Starting Capital (Compounding)

| Year | Start $ | Trades | Win% | Avg Win | Avg Loss | TQQQ PnL | Net PnL | End $ | Return% |
|---|---|---|---|---|---|---|---|---|---|
| 2019 | $25,000 | 50 | 78.0% | $82 | -$52 | -$12 | +$2,645 | $27,645 | +10.6% |
| 2020 | $27,645 | 48 | 68.8% | $80 | -$53 | $0 | +$1,854 | $29,500 | +6.7% |
| 2021 | $29,500 | 48 | 77.1% | $87 | -$66 | +$139 | +$2,481 | $31,980 | +8.4% |
| 2022 | $31,980 | 47 | 80.9% | $87 | -$74 | $0 | +$2,639 | $34,619 | +8.3% |
| 2023 | $34,619 | 48 | 79.2% | $86 | -$54 | $0 | +$2,725 | $37,344 | +7.9% |
| 2024 | $37,344 | 50 | 78.0% | $73 | -$135 | +$142 | +$1,365 | $38,709 | +3.7% |
| 2025 | $38,709 | 48 | 70.8% | $67 | -$120 | +$134 | +$616 | $39,325 | +1.6% |

**6-Year Aggregate**: $25K -> $39,325 | +57.3% total | Avg win rate: 76.1% | 339 trades

Notable paradox: The $25K account has the HIGHEST win rate (76%) but the LOWEST total return (+57%). The 3% rule limits each trade to ~$750 risk max, which at $25K mostly skips large-cap option entries where 1 contract exceeds $750. Result: very few trades (48-50/yr) and tiny dollar wins ($67-$87 avg), producing weak compounding despite a stellar win rate.

---

### 10.4 — $15,000 Starting Capital (2025 Only)

| Year | Start $ | Trades | Win% | Avg Win | Avg Loss | TQQQ PnL | Net PnL | End $ | Return% |
|---|---|---|---|---|---|---|---|---|---|
| 2025 | $15,000 | 87 | 63.2% | $15 | -$9 | -$44 | +$555 | $15,555 | +3.7% |

The very small average win ($15) and loss ($9) values indicate position sizing is extremely conservative at $15K — the 3% rule results in 1-contract micro-trades that generate negligible dollar returns despite decent win rates.

---

### 10.5 — Cross-Account Comparison

| Capital | Total Return | CAGR (est.) | Avg Win Rate | Total Trades | Assessment |
|---|---|---|---|---|---|
| $5K | +268.5% | ~21% | 55.0% | 985 | Best compounding — slingshot effect from small sizing |
| $20K | +171.7% | ~15% | 47.8% | 1,207 | Good growth, high variance in bear years |
| $25K | +57.3% | ~7% | 76.1% | 339 | Over-constrained by 3% rule — too few tradeable signals |
| $15K (1yr) | +3.7% | ~3.7% | 63.2% | 87 | Under-performing — micro-trade sizing problem |

Key Insight: The $5K account outperforms $25K on total return because at $5K, the system can trade 1 contract on almost every signal affordably. At $25K, the 3% rule blocks most signals where 1 contract costs over $750, producing very few trades and tiny dollar wins even with an excellent win rate.

---

## 11. Version History & Key Bug Fixes

### V3 Architecture — Critical Failures
The V4 Fix Research Report documented three root causes of catastrophic loss:

1. Structure Routing Bug: 116/118 trades were routed to NAKED_LONG regardless of IV. The rsi_2 < 8 condition hardcoded NAKED_LONG, bypassing the IV routing gate. High-IV entries were buying expensive options that immediately decayed on IV crush.

2. Position Sizing Override max(1, contracts): When 1 contract cost more than the 3% budget, the system forced entry anyway. This produced the MSTR trade of $8,294 on a $15K account (55% of equity in a single naked call). MSTR went adverse -> -$3,028 loss in one position.

3. Time Stop at 7 Calendar Days: Connors uses 10 *trading* days. At 7 calendar days (~5 trading days), positions were exited before mean-reversion completed, locking in losses prematurely.

### V4 Fixes Applied (Current Code)
- REMOVED rsi_2 < 8 NAKED_LONG override — all routing goes through StrategyRouter
- REMOVED max(1, contracts) override — if 1 contract > budget, SKIP trade
- Time stop changed from 7 calendar -> 8 TRADING days
- Stop loss changed from -40% option value -> -50% of capital_allocated
- Profit target added: 50% credit for spreads, 25% for longs (P0 exit)
- 5-day SMA cross added as P1 exit (Connors original)
- Position sizing now uses current_equity (not fixed initial_capital)

### V5 Changes (Current Code)
- NAKED_LONG DTE extended from 30 -> 180 DTE (LEAPS) to minimize theta drag
- IV multiplier system: entry sigma inflated by IV rank, exit sigma decays with days_held
- Hurst exponent added to metrics and CrashGuard scoring
- Dollar-volume liquidity filter ($1M/day) replacing share-volume filter
- strategy_override = None — router always decides structure

---

## 12. ML Integration — What Exists and What Doesn't

Summary: ML is SCAFFOLDED but NOT TRAINED.

### What Exists (Code Level)

| Component | Status | Detail |
|---|---|---|
| CrashGuard Factor 6 (ML Probability) | Scaffolded | 15 points; affects position size multiplier |
| SwingExitEngine ml_prob parameter | Scaffolded | Passed in but currently unused in exit logic |
| scan_universe() ml_prob | Hardcoded 0.60 | Flat default for all tickers in backtest |
| CrashGuard backtest ml_prob | Hardcoded 0.60 | No actual model applied |

### What Does NOT Exist Yet

- No trained ML model for TurboBounce. The TurboCore ML model (Random Forest classifier on TQQQ/QQQ market regime features) is a completely separate system that does NOT generalize to per-stock bounce prediction.
- No per-ticker win rate history table. The mean_reversion_history field defaults to 50 for all tickers (or 85 for leveraged ETFs) and is never updated from actual backtest outcomes.
- No feature engineering for stock-level ML classification.
- No online learning or signal recalibration from live production trades.

### What ML Could Do (Unimplemented)

1. Per-ticker bounce probability classifier: Train XGBoost/Random Forest on historical features (RSI-2, %B, 3d return, IV rank, Hurst, dist from 200SMA, sector, volume ratio) with binary label "Did price close above 5-day SMA within 8 trading days?" Replace static 0.60 with real quality differentiation per signal.

2. Strategy routing enhancement: High ML confidence input could expand the CrashGuard size multiplier or unlock NAKED_LONG entries for high-probability setups.

3. Dynamic hold length prediction: Regression model estimating expected time to bounce — shorter predicted hold -> shorter DTE options to reduce theta.

4. The TurboCore ML (IV-switching regime model) could potentially be extended to classify market regimes useful to TurboBounce strategy routing (BULL/BEAR/SIDEWAYS affects which structure performs best).

---

## 13. Open Problems & Improvement Roadmap

### Critical / Currently Broken

| Problem | Impact | Proposed Fix |
|---|---|---|
| $25K account paradox: 76% win rate but +57% total | 3% rule blocks too many trades | Implement per-asset-class contract cap: allow up to $1,500/contract for liquid ETF options |
| 2023 underperformance (-38% on $5K) | Low-IV grinding bull markets hurt LEAPS entries | Add regime filter: when VIX 30-day avg < 16 AND market trending (ADX > 25), skip or halve LEAPS positions |
| ML hardcoded at 0.60 | CrashGuard Factor 6 only contributes 5 pts always | Train and deploy per-ticker bounce probability model |
| 2022 TQQQ overexposure (-$3,299 on $20K) | TQQQ kept triggering oversold during structural downtrend | Add TQQQ-specific macro gate: block TQQQ entries when TQQQ is below its 200 SMA AND QQQ 200 SMA slope is negative |

### Medium Priority

| Problem | Fix |
|---|---|
| mean_reversion_history hardcoded | Compute actual 5-day bounce rate per ticker from backtest CSV logs |
| No slippage or commission model | Add $0.65/contract fee + 1.5x bid-ask spread simulation |
| Overbought direction disabled | Re-enable Bear Call Spread for overbought signals, backtest independently |
| Hurst exponent expensive (60-bar daily) | Cache and update weekly instead of daily |

### Enhancement Opportunities

| Feature | Description |
|---|---|
| Earnings exclusion filter | Block entries within 5 trading days of earnings — IV dynamics are driven by the event, not mean reversion |
| Sector momentum overlay | Prefer oversold stocks in sectors with positive 20-day momentum |
| Rolling credit from diagonals | Implement systematic weekly hedge roll to capture ongoing theta income from diagonal positions |
| TurboBounce live execution | The executor.py framework exists but is not connected to the TurboBounce live signal pipeline |

---

## Appendix: File Map

| File | Purpose | Status |
|---|---|---|
| universe.py | 115-ticker base + S&P 500 dynamic fetch | Active |
| scanner.py | Daily scan, filters, candidate selection | Active |
| scoring.py | 4-factor weighted ranking | Active (MRV placeholder) |
| strategy_router.py | IV-adaptive structure selection | Active |
| spread_builder.py | Live option leg construction via IB | Active (IB dep.) |
| risk_manager.py | Slot limits, correlation guards | Active |
| crash_guard.py | 2-tier entry gate with ML scaffolding | Active (ML mocked at 0.60) |
| swing_exit_engine.py | V4.1 6-priority exit cascade | Active |
| executor.py | Tastytrade order submission | Exists, not wired to TurboBounce live |
| data_provider.py | Live market data fetch (yfinance/IB) | Active |
| options_pricer_backtest.py | Full Black-Scholes backtest engine | Primary backtest |
| historical_backtest.py | Simplified allocation-logic backtest | For mode-comparison tests |
| run_multiyear.py | Multi-year compounding orchestrator | Active |
| fast_recalc.py | Quick recalculation utility | Active |
| options_pricer_backtest_backup_2026.py | Pre-V5 backup | Archive only |

---
*Report generated April 2026 | Source: d:\Projects\tastywork-trading-1\src\turbobounce\*
