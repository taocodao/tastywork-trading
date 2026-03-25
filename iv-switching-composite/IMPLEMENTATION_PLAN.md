# IV-Switching Composite Options Strategy
## Comprehensive Implementation Plan — Gemini Coding Handoff

**Project directory:** `d:\Projects\tastywork-trading-1\iv-switching-composite\`
**Target:** Backtested prototype → paper trading → live on Tastytrade API
**Expected CAGR:** 14–22% | **Max Drawdown Target:** -12% to -20%
**Capital:** $25,000 starting

---

## 1. Strategy Architecture Overview

This is a **five-mode regime-switching composite** that allocates capital based on the current volatility environment, as determined by the VIX term structure and a multi-model ML regime classifier.

### The Five Modes

| Mode | Name | Active When | Primary Instrument |
|------|------|-------------|-------------------|
| **A** | CSP Premium Capture | QQQ > SMA200, Contango, IVP > 30 | TQQQ weekly 10-delta cash-secured puts |
| **B** | LEAPS Directional | QQQ > SMA100, Contango, IVP < 30 | QQQ 60–70 delta call LEAPS, 365 DTE |
| **D1** | Pre-Crash VIX Hedge | Concurrent with Mode A or B, VIX 15–30 | VIX 30-delta calls, 30–45 DTE |
| **D2** | Active Bear Tactical | Backwardation confirmed + QQQ < SMA200 + HMM crisis > 0.70 | SQQQ ETF (5–7% NAV) or QQQ put spreads |
| **D3** | Crash Recovery Re-entry | VIX declining 20%+ from peak + contango returning | QQQ LEAPS double-size (2 contracts) |

### Mode Switching Signal (Primary Gate)
```
VIX/VIX3M ratio:
  < 1.0  = Contango  → Modes A or B eligible
  >= 1.05 = Backwardation → Mode C (cash) or D2 if all conditions met

IVP (252-day rolling percentile of VIX):
  > 50   → Mode A strongly favored (premiums rich)
  30–50  → Overlap zone: both A and B at reduced sizing
  < 30   → Mode B favored (LEAPS cheap, directional leverage efficient)
```

### Core API: Use IVP, not IVR
- **IVP** = `# days in past 252 where VIX < today's VIX` / 252 × 100
- **NOT** IVR = (current - 52w low) / (52w high - 52w low)
- IVR is distorted by single spikes (e.g., after March 2020 VIX=80, IVR reads 20 even at VIX=30); IVP does not have this flaw

---

## 2. Directory & File Structure

```
iv-switching-composite/
├── IMPLEMENTATION_PLAN.md          ← this file
├── backtest_composite.py           ← Phase 1: full backtest engine
├── regime_engine.py                ← Mode detection logic (deterministic + ML)
├── position_sizer.py               ← Kelly + vol-targeted sizing
├── pricing.py                      ← Black-Scholes LEAPS & CSP pricing
├── portfolio.py                    ← Portfolio/NAV tracking
├── ml/
│   ├── regime_classifier.py        ← LightGBM 4-class regime (Phase 2)
│   ├── entry_scorer.py             ← XGBoost entry signal scorer (Phase 2)
│   ├── crash_hmm.py                ← 2-state HMM for Mode D2 (Phase 2)
│   └── pmcc_manager.py             ← PMCC short-call timing/exit (Phase 3)
├── data/
│   └── features.py                 ← Feature engineering pipeline
├── results/
│   └── (CSV outputs, equity curves)
└── tests/
    └── test_regime_signals.py      ← Unit tests for key logic
```

---

## 3. Phase 1: Rule-Based Backtest Engine

### 3.1 Data Pipeline (`data/features.py`)

Download and compute the following for 2015-01-01 → 2026-03-20:

**Required yfinance tickers:**
- `QQQ` — close, open (for gap detection)
- `TQQQ` — close
- `^VIX` — close (VIX spot)
- `^VIX3M` — close (3-month VIX futures proxy)
- `^VIX9D` — close (9-day VIX)
- `^VVIX` — close (vol-of-vol, for D1 VVIX early-warning)
- `^IRX` — close / 100 = risk-free rate
- `SQQQ` — close (for D2 NAV tracking)

**Computed features:**

```python
# VIX Term Structure (PRIMARY MODE GATE)
df['vix_vix3m_ratio']  = df['vix'] / df['vix3m']
df['is_backwardation'] = df['vix_vix3m_ratio'] >= 1.0   # bool
df['vix9d_vix_ratio']  = df['vix9d'] / df['vix']

# IVP: 252-day rolling percentile of VIX (USE THIS, not IVR)
df['ivp_252'] = df['vix'].rolling(252).apply(
    lambda x: (x[:-1] < x[-1]).sum() / 251 * 100, raw=True
)

# QQQ SMAs
df['sma_50']  = df['qqq_close'].rolling(50).mean()
df['sma_100'] = df['qqq_close'].rolling(100).mean()
df['sma_200'] = df['qqq_close'].rolling(200).mean()
df['above_sma100'] = df['qqq_close'] > df['sma_100']
df['above_sma200'] = df['qqq_close'] > df['sma_200']

# Gap-down signals (for Mode B LEAPS entries)
df['qqq_gap_pct']         = (df['qqq_open'] - df['qqq_close'].shift(1)) / df['qqq_close'].shift(1)
df['gap_down_1pct']       = df['qqq_gap_pct'] <= -0.01   # Standard entry
df['gap_down_2pct']       = df['qqq_gap_pct'] <= -0.02   # Aggressive entry (2 contracts)

# TQQQ volatility (for CSP IV calibration)
tqqq_log_ret = np.log(df['tqqq_close'] / df['tqqq_close'].shift(1))
df['tqqq_hv20'] = tqqq_log_ret.rolling(20).std() * np.sqrt(252)

# Perplexity-calibrated IV for TQQQ CSP puts
df['tqqq_iv_atm']   = df[['tqqq_hv20', 'vix']].apply(
    lambda r: max(r['tqqq_hv20'] * 1.20, r['vix'] / 100 * 3.0), axis=1
)
df['tqqq_iv_10d']   = df['tqqq_iv_atm'] * 1.30   # OTM 10-delta skew

# QQQ LEAPS IV
df['qqq_iv_leaps']  = df['vix'] / 100 * 1.10     # 1y term structure premium; no ITM discount

# VVIX features (for D1 early warning)
df['vvix_10d_chg']  = df['vvix'].pct_change(10)

# Momentum
df['qqq_ret_1d']  = df['qqq_close'].pct_change(1)
df['qqq_ret_5d']  = df['qqq_close'].pct_change(5)
df['qqq_ret_10d'] = df['qqq_close'].pct_change(10)
df['qqq_ret_21d'] = df['qqq_close'].pct_change(21)

# RSI(14)
delta = df['qqq_close'].diff()
gain  = delta.clip(lower=0).rolling(14).mean()
loss  = (-delta.clip(upper=0)).rolling(14).mean()
df['rsi_14'] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
```

---

### 3.2 Regime Engine (`regime_engine.py`)

The deterministic rule-based mode classifier. No ML needed for Phase 1.

```python
def classify_mode(row, peak_vix=None, d2_active=False, d2_entry_date=None, current_date=None):
    """
    Returns one of: 'A', 'B', 'C', 'D1_trigger', 'D2', 'D3'
    D1 is not a mode — it is a concurrent allocation returned as a flag.
    """
    vix          = row['vix']
    vix_vix3m    = row['vix_vix3m_ratio']
    above_sma200 = row['above_sma200']
    above_sma100 = row['above_sma100']
    ivp          = row['ivp_252']

    # ── D3: Crash recovery check (takes priority if D2 was recently active) ──
    if d2_active and peak_vix:
        vix_off_peak    = vix < peak_vix * 0.80        # VIX down 20%+ from peak
        contango_back   = vix_vix3m < 1.0              # Term structure normalizing
        qqq_recovering  = row['qqq_ret_10d'] > 0       # QQQ green over 10 days
        if vix_off_peak and contango_back and qqq_recovering:
            return 'D3'

    # ── D2: Active bear (all 3 conditions required simultaneously) ──
    # NOTE: HMM crisis probability is added in Phase 2; for Phase 1, use False
    d2_hmm_signal   = False                            # Phase 2: hmm_crisis_prob > 0.70
    d2_ts_signal    = vix_vix3m >= 1.05               # Backwardation by >5% margin
    d2_sma_signal   = not above_sma200                # QQQ below SMA200
    d2_vvix_signal  = row.get('vvix', 25) > 30        # VVIX elevated
    if d2_ts_signal and d2_sma_signal and d2_vvix_signal:
        return 'D2'

    # ── Mode C: Cash/defense (backwardation or QQQ deeply below SMA200) ──
    if vix_vix3m >= 1.0 or not above_sma100:
        return 'C'

    # ── Mode A: CSP — sell premium ──
    if above_sma200 and vix_vix3m < 1.0 and ivp >= 30:
        if vix > 35:
            return 'C'            # VIX too extreme even in contango
        return 'A'

    # ── Mode B: LEAPS — buy directional exposure ──
    if above_sma100 and vix_vix3m < 1.0 and ivp < 30:
        return 'B'

    # ── Default: Neutral/Cash ──
    return 'C'

def should_open_d1(vix, vvix_10d_chg, regime_label, regime_duration_days):
    """
    Returns (bool, allocation_pct) for Mode D1 VIX call purchase.
    D1 runs concurrently with A and B.
    """
    if vix <= 15:
        base_pct = 0.0
    elif vix <= 30:
        base_pct = 0.015     # 1.5% NAV
    elif vix <= 50:
        base_pct = 0.005     # 0.5% NAV (vol already expensive)
    else:
        base_pct = 0.0       # Too late — transition to D2

    # ML enhancement 1: Complacency bump after 90+ days of BULL_STRONG
    if regime_label == 'A' and regime_duration_days > 90:
        base_pct = min(base_pct * 1.25, 0.025)

    # ML enhancement 2: VVIX early warning
    if vvix_10d_chg > 0.25 and vix < 25:
        base_pct = min(base_pct * 1.50, 0.025)

    return base_pct > 0, base_pct
```

---

### 3.3 Position Sizer (`position_sizer.py`)

Kelly + volatility-targeted sizing. Deterministic — no ML.

```python
def size_csp_trade(nav, vix, strike, premium_per_share):
    """
    Returns number of CSP contracts for Mode A.
    Minimum of Kelly-fraction method and income-target method.
    """
    # Kelly fraction by VIX regime
    if vix < 17.8:
        kelly_frac = 0.15
    elif vix < 23.1:
        kelly_frac = 0.12
    elif vix < 30.0:
        kelly_frac = 0.08
    elif vix < 35.0:
        kelly_frac = 0.05
    else:
        return 0                        # No new CSPs above VIX 35

    # Method 1: Kelly-fraction collateral limit
    max_collateral   = nav * kelly_frac
    kelly_contracts  = int(max_collateral / (strike * 100))

    # Method 2: Income-target normalization
    # Target: 0.75% of NAV per week / 52 weeks → weekly premium income target
    weekly_target    = nav * 0.0075 / 52
    income_contracts = int(weekly_target / max(premium_per_share * 100, 0.01))

    contracts = min(kelly_contracts, income_contracts)
    return max(contracts, 0)


def size_leaps_trade(nav, leaps_cost_per_contract, mode='B', n_open_positions=0):
    """
    Returns number of LEAPS contracts for Mode B or D3.
    """
    max_positions = 3
    if n_open_positions >= max_positions:
        return 0

    pct_per_slot = 0.10           # 10% NAV per LEAPS position (Mode B)
    if mode == 'D3':
        pct_per_slot = 0.20       # D3 recovery: aggressive 20% per slot

    max_outlay   = nav * pct_per_slot
    contracts    = int(max_outlay / leaps_cost_per_contract)
    return min(contracts, 1) if mode == 'B' else min(contracts, 2)   # D3: up to 2


def size_d2_sqqq(nav, vix):
    """Returns dollar amount for Mode D2 SQQQ position."""
    if vix < 30:
        return nav * 0.07      # 7% NAV
    else:
        return nav * 0.05      # Reduce to 5% when vol already high


def size_d1_vix_calls(nav, vix, vvix_10d_chg, regime_duration_days):
    """Returns dollar amount for Mode D1 VIX call purchase."""
    _, alloc_pct = should_open_d1(vix, vvix_10d_chg, 'A', regime_duration_days)
    return nav * alloc_pct
```

---

### 3.4 Pricing (`pricing.py`)

Black-Scholes with Perplexity-calibrated IV multipliers. Same structure as prior backtests but centralized.

```python
import math
from scipy.stats import norm

def bs_call_price(S, K, T, r, sigma):
    """European call via Black-Scholes."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)

def bs_put_price(S, K, T, r, sigma):
    """European put via Black-Scholes."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def bs_call_delta(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1)

def bs_put_delta(S, K, T, r, sigma):
    return bs_call_delta(S, K, T, r, sigma) - 1.0

def find_strike_for_delta(S, T, r, sigma, target_delta, option_type='call'):
    """Binary search for strike at target delta."""
    lo, hi = S * 0.30, S * 1.40
    for _ in range(80):
        mid = (lo + hi) / 2
        if option_type == 'call':
            d = bs_call_delta(S, mid, T, r, sigma)
            if abs(d - target_delta) < 1e-4:
                return mid
            lo, hi = (mid, hi) if d > target_delta else (lo, mid)
        else:
            d = abs(bs_put_delta(S, mid, T, r, sigma))
            if abs(d - target_delta) < 1e-4:
                return mid
            lo, hi = (lo, mid) if d > target_delta else (mid, hi)
    return mid

# IV calibration constants (Perplexity-validated 2026-03-22)
TQQQ_ATM_HV_MULT    = 1.20    # ATM IV = max(HV20 * 1.2, VIX * 3)
TQQQ_LEVERAGE_FLOOR = 3.00    # TQQQ: leverage factor on VIX
TQQQ_OTM_SKEW       = 1.30    # 10-delta OTM put skew premium
QQQ_LEAPS_IV_SCALE  = 1.10    # 1y QQQ IV = VIX * 1.10 (term premium; no ITM discount)
QQQ_PMCC_IV_SCALE   = 1.08    # OTM short call: VIX * 1.08

def tqqq_put_iv(hv20, vix):
    atm  = max(hv20 * TQQQ_ATM_HV_MULT, vix / 100 * TQQQ_LEVERAGE_FLOOR)
    return min(atm * TQQQ_OTM_SKEW, 3.0)

def qqq_leaps_call_iv(vix):
    return vix / 100 * QQQ_LEAPS_IV_SCALE

def qqq_short_call_iv(vix):
    return vix / 100 * QQQ_PMCC_IV_SCALE

# Slippage
SLIPPAGE_PER_SIDE = 1.50   # $/contract per leg
COMMISSION        = 1.00   # $/contract
```

---

### 3.5 Main Backtest Engine (`backtest_composite.py`)

**Architecture:** Single-file orchestrator that imports `regime_engine`, `position_sizer`, `pricing`, and `portfolio`. Iterates daily, applies mode logic, tracks NAV, logs all trades.

**Key simulation rules (implement exactly as specified):**

#### Mode A — CSP (TQQQ Weekly Cash-Secured Puts)
- Open every **Monday** when Mode A is active
- Strike: 10-delta put (use `find_strike_for_delta(..., target_delta=0.10, option_type='put')`)
- Expiry: next Friday from entry (7 DTE)
- IV: `tqqq_put_iv(hv20, vix)`
- Premium = `bs_put_price(tqqq_px, strike, 7/365, rf, iv)`
- Profit target: **75% of premium collected** (close when current put < 25% of entry)
- Stop-loss: close if current put > 3× entry premium
- Kill-switch: immediately close all CSPs if `vix_vix3m_ratio >= 1.0` (backwardation trigger)
- Max simultaneous: `size_csp_trade()` contracts per week; only 1 expiry open at a time

#### Mode B — QQQ LEAPS Dip-Buy
- Open on **gap-down days** ONLY (QQQ opens ≥ 1% below prior close)
- Contract: 65-delta call, 365 DTE
- Strike: `find_strike_for_delta(qqq_px, 365/365, rf, qqq_leaps_call_iv(vix), 0.65, 'call')`
- Entry price: `bs_call_price(...)` + slippage
- Profit target: **150% of entry value** (50% gain on option)
- Roll at 90 DTE: close and reopen at fresh 365 DTE at current market
- PMCC overlay: sell 30-delta covered call (35 DTE) once per month per LEAPS position
  - PMCC close: 50% premium collected, or if QQQ moves 3%+ toward short strike
  - PMCC short call strike must always be ABOVE LEAPS long call strike (diagonal rule)
- Max 3 simultaneous LEAPS positions

#### Mode D1 — VIX Call Hedge (Concurrent)
- Buy VIX 30-delta calls, 35 DTE, on the first of each month when `should_open_d1()` returns True
- VIX call option: priced via `bs_call_price(vix_spot, vix_call_strike, 35/365, rf, vvix/100)`
  - (VVIX approximates implied vol of VIX options)
- Close at: 50% profit, OR if VIX has declined >20% from entry
- Annual budget: ~1.5–2% NAV (this is an expense; it pays off in crash years)

#### Mode D2 — Active Bear (SQQQ)
- **Trigger:** ALL of: `vix_vix3m >= 1.05` AND `not above_sma200` (3+ days) AND `vvix > 30`
- Phase 1: use `vvix > 30` as HMM proxy; Phase 2: replace with actual HMM crisis probability > 0.70
- Buy SQQQ at `size_d2_sqqq(nav, vix)` dollars
- Hard exits: (a) 21 calendar days max hold; (b) QQQ gaps up >3% in single session; (c) `vix_vix3m < 1.0`
- Profit target: 30% gain on SQQQ position
- Do NOT open Mode A or B while D2 is active

#### Mode D3 — Crash Recovery Re-Entry
- Trigger: (a) VIX < `peak_vix * 0.80`; (b) `vix_vix3m < 1.0`; (c) `qqq_ret_10d > 0`
- Close all D2 positions first
- Buy QQQ LEAPS: 2 contracts per gap-down signal (double Mode B sizing)
- Simultaneously reinstate Mode A at 5% NAV (half-size) as VIX normalizes
- After 10 trading days: D3 transitions into normal A/B cycle

#### Mode C — Cash/Defense
- Hold cash in T-bills (rf rate from IRX)
- Do not open new A or B positions
- Let existing LEAPS **ride** (do NOT force-close on Mode C entry — LEAPS survive bear markets)
- Close all open CSPs immediately on C entry

---

### 3.6 Portfolio Tracker (`portfolio.py`)

Track daily:
- `cash` (float)
- `open_csps` (list of dicts: `{strike, expiry, entry_price, contracts, entry_date}`)
- `open_leaps` (list of LeapsPosition objects with attached short_call)
- `d2_position` (dict: `{entry_date, sqqq_shares, entry_sqqq_price, max_hold_date}`)
- `d1_positions` (list of monthly VIX calls)
- `nav` = cash + mark-to-market value of all positions

Daily NAV calculation:
```python
nav = cash
nav += sum(leaps.current_value(spot, date, iv, rf) * 100 * contracts for leaps in open_leaps)
nav -= sum(sc_value(date) * 100 * contracts for sc in open_short_calls)   # PMCC liability
nav += sum(bs_put_price(tqqq, csp.strike, dte, rf, iv) * 100 * contracts for csp in open_csps_to_close)
# Actually for CSPs: collateral is locked up; NAV uses cash + unrealized P&L
nav += d2_sqqq_market_value   # SQQQ position mark-to-market
nav += d1_vix_call_value       # VIX call position mark-to-market
```

---

## 4. Phase 2: ML Model Development

After Phase 1 backtest validates the rule-based system (target: CAGR > 12%, DD < -30%), add ML:

### 4.1 Model 1 — Regime Classifier (`ml/regime_classifier.py`)

- **Algorithm:** LightGBM Classifier
- **Output:** 4-class probability: `{BULL_STRONG, BULL_MODERATE, NEUTRAL, BEAR}`
- **Training data:** 2015–2021 (hold out 2022–2025 for validation)
- **Key validation:** Did model output BEAR for Feb–Sept 2022? For March 2020?
- **Features for training:**

```python
features = [
    'vix_level', 'vix3m_level', 'vix9d_level',
    'vix_vix3m_ratio',          # Primary: term structure slope
    'vix9d_vix_ratio',          # Short-term panic signal
    'ivp_252',                  # IV percentile
    'vvix',                     # Vol-of-vol
    'qqq_vs_sma50',             # % deviation from SMA50
    'qqq_vs_sma100',
    'qqq_vs_sma200',
    'qqq_ret_5d',
    'qqq_ret_10d',
    'qqq_ret_21d',
    'rsi_14',
    'tqqq_hv20',
]
```

- **Training target:** Forward 21-day regime label derived from: if QQQ > SMA200 and VIX/VIX3M < 1.0 → BULL; else BEAR
- **Walk-forward:** 252-day rolling training window, 21-day hold-out; retrain monthly
- **VIX thresholds (RegimeFolio calibration):** Low < 17.8; Medium 17.8–23.1; High > 23.1

### 4.2 Model 2 — Entry Signal Scorer (`ml/entry_scorer.py`)

Two separate XGBoost classifiers, one for each mode:

**Mode A (CSP) scorer features:**
- `days_since_vix_spike_above30` (days since last VIX > 30 event)
- `ivp_252` (current vs. 4-week average IVP)
- `tqqq_hv20` vs `tqqq_iv_atm` (VRP magnitude)
- `vix_5d_chg` (is IV rising or falling?)
- `vix_vix3m_ratio` (term structure reading at entry)

**Mode B (LEAPS) scorer features:**
- `qqq_gap_pct` (gap-down magnitude)
- `rsi_14` (oversold = higher recovery probability)
- `vix_5d_chg` (VIX falling into gap = good; rising = bad)
- `qqq_vs_sma100` (distance from support)
- `ivp_252` (IV cheapness)

- **Threshold:** Only trade Mode A entries with score > 0.60; Mode B entries with score > 0.65
- **Training target (Mode B):** Binary — did the trade hit 50% profit within 90 days?
- **Training target (Mode A):** Binary — did the put expire OTM or close at ≥75% profit without triggering stop?

### 4.3 Model 3 — Crash HMM (`ml/crash_hmm.py`)

2-state Gaussian HMM for Mode D2 confirmations:

```python
from hmmlearn.hmm import GaussianHMM

# Observations: (qqq_daily_return, vix_daily_change, vix_vix3m_daily_change)
# States: 0=Normal, 1=Crisis
# Training: 2000-01-01 to 2019-12-31 (Baum-Welch EM)
# Validation: 2020 and 2022 out-of-sample
# Real-time: score last 21 days of observations → P(crisis state)
```

- State 1 (Crisis) identified as: state with negative mean QQQ return + high volatility emission
- Real-time threshold: `crisis_probability > 0.70` → D2 eligible
- Replace Phase 1's VVIX proxy with this in Phase 2

### 4.4 Model 4 — PMCC Manager (`ml/pmcc_manager.py`)

Two sub-models (lightweight):

- **Entry timing:** Wait until QQQ's 5-day momentum turns negative before selling short call
  - Avoids selling calls at the bottom of a dip into a fast rally
  - Simple rule-based for Phase 1; XGBoost binary classifier in Phase 2
- **Management:** Close short call at: (a) 50% profit, (b) QQQ moves 2%+ toward strike in 2 sessions
  - No ML required; deterministic rules

---

## 5. Data Validation Checkpoints

After building Phase 1, verify these empirical results before Phase 2:

| Test | Expected Result | Pass Criterion |
|------|----------------|----------------|
| Mode classification 2020 Q1 | C or D2 from Feb 24 onward | Backwardation triggered before SMA200 break |
| Mode classification 2022 | C or D2 for majority of Feb–Oct | <2 weeks of Mode A during sustained bear |
| Mode classification 2019 | Mostly B (LEAPS), some A | IVP typically 20–40 in low-VIX 2019 |
| Mode classification 2020 Q2 | A (CSP) — Goldilocks: VIX 25-35, contango | Premium-rich environment |
| TQQQ CSP premium check | ~$0.50–0.80/share at VIX=20 | Verify vs. prior $0.20 (wrong) |
| QQQ LEAPS price check | ~$82–85 for $430 strike, QQQ=$500, 365 DTE | Intrinsic $70 + ~$12–15 time value |
| D1 VIX call cost | ~$0.80–1.20 for 30-delta, 45 DTE, VIX=15 | Annual budget ~$3,500–4,500 on $25K |
| 2022 bear recovery | D3 fires around Oct–Nov 2022 | VIX declining + 10d QQQ positive |

---

## 6. Output Metrics to Report

The backtest must output all of these:

```
COMPOSITE STRATEGY BACKTEST RESULTS
=====================================
Period: YYYY-MM-DD to YYYY-MM-DD (N years)
Initial Capital: $25,000

PORTFOLIO PERFORMANCE:
  Final NAV          : $XX,XXX
  Total Return        : XX.X%
  CAGR (portfolio)    : XX.X%
  Max Drawdown        : -XX.X%
  Sharpe Ratio        : X.XX
  Calmar Ratio        : X.XX (CAGR / |Max DD|)
  Best Year           : XXXX (+XX.X%)
  Worst Year          : XXXX (-XX.X%)

BENCHMARK (QQQ Buy-and-Hold):
  QQQ CAGR            : XX.X%
  Alpha               : +/- X.X pp

MODE ATTRIBUTION:
  Mode A (CSP) active days    : XXX  (XX% of calendar)
  Mode B (LEAPS) active days  : XXX  (XX%)
  Mode C (Cash) active days   : XXX  (XX%)
  Mode D2 (Bear) active days  : XXX  (XX%)

MODE A (CSP) STATS:
  Total CSPs opened   : XXX
  Win rate            : XX.X%
  Avg winner ($)      : $XXX
  Avg loser ($)       : -$XXX
  Weeks skipped (kill-switch): XX

MODE B (LEAPS) STATS:
  Total entries       : XX
  Win rate            : XX.X%
  Avg winner ($)      : $X,XXX
  Avg loser ($)       : -$XXX
  Rolls at 90 DTE     : XX
  PMCC cycles         : XXX
  PMCC income total   : $X,XXX

MODE D1 (VIX Hedge) STATS:
  Total premium spent : $X,XXX
  Payoff events       : XX
  Net D1 contribution : $X,XXX (positive in crash years)

MODE D2 (SQQQ) STATS:
  Total entries       : X
  Win rate            : XX.X%
  Net contribution    : $X,XXX

ROC ON DEPLOYED CAPITAL (separate from portfolio CAGR):
  Mode A ROC           : XX.X% annualized
  Mode B ROC           : XX.X% annualized
  (These will be higher than portfolio CAGR — capital not 100% deployed at all times)
```

---

## 7. Known Limitations & Caveats

1. **B-S IV proxies:** Without real historical option chain data, IV is estimated from VIX. Actual fills may differ. Databento or Polygon.io historical chains are the recommended upgrade path for Phase 3.
2. **SQQQ daily reset erosion:** Mode D2's SQQQ position is tracked at end-of-day prices. The 21-day hard exit prevents most of the daily-rebalancing volatility decay problem but not all.
3. **VIX call pricing:** VIX options are European-style and cash-settled against the VIX futures (not spot VIX). Using `VIX_spot` as the underlying in B-S is a simplification — the correct underlying is VIX futures for the specific expiry.
4. **PMCC diagonal rule:** The backtest must enforce that the short call strike is always above the LEAPS long call strike. If not enforced, the strategy can accidentally become a debit spread with capped upside.
5. **Term structure lag:** Backwardation signal takes 1–3 days to confirm a new bear regime. Expect ~2–5% transition drawdown at the start of any bear market before kill-switches trigger.
6. **No margin:** The backtest assumes a cash account. Tastytrade supports portfolio margin which would meaningfully change the capital efficiency of both CSPs and LEAPS, but that is Phase 4+ complexity.

---

## 8. Tech Stack & Dependencies

```python
# requirements.txt
yfinance>=0.2.40
pandas>=2.0
numpy>=1.24
scipy>=1.10
lightgbm>=4.0       # Phase 2 regime classifier
xgboost>=2.0        # Phase 2 entry scorer
hmmlearn>=0.3       # Phase 2 crash HMM
scikit-learn>=1.3   # Preprocessing, calibration, cross-val
ta-lib>=0.4         # Technical indicators (RSI, SMA)
joblib>=1.3         # Model save/load
matplotlib>=3.7     # Equity curve plots
pandas-datareader   # FRED macro data (optional Phase 2)
```

Run the backtest:
```powershell
cd d:\Projects\tastywork-trading-1
python iv-switching-composite\backtest_composite.py
```

---

## 9. Phase Roadmap

| Phase | Timeline | Milestone | Success Criteria |
|-------|----------|-----------|-----------------|
| **1** | Week 1–2 | Rule-based composite backtest | CAGR > 12%, DD < -30% |
| **2** | Week 3–6 | LightGBM + XGBoost + HMM integration | Win rate improvement vs. Phase 1 |
| **3** | Week 7–10 | PMCC ML manager + VVIX early-warning | D1 net contribution positive |
| **4** | Week 11–16 | Paper trading on Tastytrade | Live regime matches backtest classification |
| **5** | Month 5+ | Live capital (20% of target, 1–2 contracts) | 2 consecutive profitable months |
| **6** | Month 7+ | Scale to 100% target capital | 1 profitable quarter |
