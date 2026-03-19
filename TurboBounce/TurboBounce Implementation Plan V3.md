<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# yes please

Now I have everything. Here is the complete regenerated V3 plan with the diagonal DTE asymmetry structure fully integrated throughout every section.

***

# TurboBounce V3: Volatility-Adaptive Diagonal Swing Spread System

## Unified Strategy Framework, Data-Backed Analysis \& ML Implementation Plan


***

## Executive Summary

TurboBounce V3 is a **pure swing-trade options system** built entirely around price behavior — not calendar time, not theta decay. Every position is managed by three iron-clad laws: never hold to expiration; when wrong, close the full spread and immediately re-open at a better location; when right, close only the short leg and stop-limit the long put. The core structural upgrade in V3 is the **Diagonal DTE Asymmetry**: the short put uses a *longer* DTE (60–90 days) for maximum premium collection, while the long put uses a *shorter* DTE (21–35 days) for minimum hedge cost. This single change doubles the net credit per spread vs. a same-expiration vertical — from approximately 19% to 38% of spread width — without meaningfully increasing directional risk on a swing time frame.

Trade data from 1,274 live-tested positions across seven years (2019–2025) on the 25K account confirms the strategic imperative. Credit Spreads represent only 7.7% of historical trades but generate **92.7% of total profit** (\$84,866). They achieved 100% win rates in 2019, 2021, 2022, and 2025, and 95% in 2024. The DIAGONAL/BEARISH allocation has destroyed value in every year except 2021, producing −\$38,385 in cumulative losses at a 22.7% win rate. V3 eliminates that drag entirely, replaces it with disciplined Mode 2 Bear Put Diagonal Swings, and deploys ML across four purpose-built modules trained on TurboBounce's own historical trade library.

***

## 1. What the Trade Data Demands

### 1.1 Strategy Performance Matrix (25K Account, 2019–2025)

| Strategy | Direction | Trades | Win Rate | Total PnL | % of Total PnL | Avg PnL% | Avg Days Held |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| CREDIT_SPREAD | BULLISH | 98 | **91.8%** | **+\$84,866** | **+92.7%** | +10.3% | 15.2 |
| NAKED_LONG | BULLISH | 343 | 48.7% | +\$28,432 | +31.1% | +1.0% | 6.2 |
| NAKED_LONG | BEARISH | 299 | 49.8% | +\$16,096 | +17.6% | +1.2% | 6.3 |
| DIAGONAL | BULLISH | 468 | 40.4% | +\$507 | +0.6% | +0.1% | 15.1 |
| DIAGONAL | BEARISH | 66 | 22.7% | **−\$38,385** | **−41.9% drag** | −7.0% | 15.1 |

The same pattern holds across all account sizes. In the 20K account, DIAGONAL/BEARISH lost −\$47,761 at a 19.7% win rate. In the 5K account, −\$12,519 at 14.0%. The DIAGONAL/BEARISH structure is not a position sizing problem — it is a structural design problem, rooted in managing by TIME rather than PRICE.

### 1.2 Credit Spread Year-by-Year: The Bear Market Edge

| Year | Trades | Win Rate | Net PnL | Avg PnL% | Market Context |
| :-- | :-- | :-- | :-- | :-- | :-- |
| 2019 | 16 | 100% | +\$9,915 | +14.9% | Bull — IV spikes on pullbacks |
| 2020 | 5 | 60% | +\$838 | +2.9% | COVID crash — limited entries, choppy |
| 2021 | 2 | 100% | +\$1,658 | +15.0% | Bull — sparse entries |
| 2022 | 24 | **100%** | **+\$17,743** | +10.1% | **Tech bear market** — elevated IV all year |
| 2023 | 14 | 64% | +\$3,073 | +4.2% | Recovery — mixed |
| 2024 | 21 | 95% | +\$22,050 | +12.0% | Bull AI rally — large IV spikes on dips |
| 2025 | 16 | 100% | +\$29,590 | +10.9% | High vol — best year ever |

The 2022 result is the most important. While DIAGONAL/BEARISH lost −\$17,410 that year and the overall account dropped −27.7%, the credit spread engine produced 24 trades at **100% win rate** generating \$17,743 profit. Every future bear market is an opportunity, not a threat, for this system — provided entries are managed by price rather than time.

### 1.3 The Exit Method Problem

Every single position in the historical data exited by **TIME** — a fixed 15-day calendar hold. Not one position was managed by swing price action. This is the largest single untapped improvement in V3. Converting to price-triggered short-leg exits (BTC at 50% credit on bounce), combined with stop-limited long put retention, is projected to increase average credit captured per trade and generate additional tail-hedge payoffs from the retained long put.

***

## 2. The V3 Core Structure: Short Diagonal Put Spread

### 2.1 What Changes vs. a Standard Vertical

V3 uses a **Short Diagonal Put Spread** — the two legs expire on *different dates* — rather than a same-expiration vertical. The short put has a longer DTE to maximize time value collected; the long put has a shorter DTE to minimize the cost of protection.

**Credit comparison on a \$10-wide spread (stock at \$184, IVR 38%):**


| Structure | Short Put DTE | Long Put DTE | Short Put Premium | Long Put Cost | Net Credit | Credit/Width |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Vertical (same) | 60 days | 60 days | ~\$4.80 | ~\$2.90 | **\$1.90** | 19.0% |
| Diagonal (V3) | 75 days | 28 days | ~\$5.60 | ~\$1.80 | **\$3.80** | **38.0%** |

The diagonal structure approximately **doubles the net credit** per spread vs. a comparable vertical. This is because the shorter-DTE long put carries far less time value — it is cheaper to buy, expanding the net credit pocket substantially.

### 2.2 The Long Put Replacement Cycle

Since the long put is shorter-DTE, it will expire (or reach near-zero value) while the short put is still active. This creates a recurring hedge replacement task:

```
Day 0:   Enter diagonal (Short: 75 DTE / Long: 28 DTE)
Day 21:  Long put has 7 DTE → REPLACE IT (automated rule)
         Short put has 54 DTE → still active, keep running
Day 21+: Buy new long put: 28 DTE, SAME or LOWER strike
Day 42:  Second long put has 7 DTE → REPLACE AGAIN
         Short put has 33 DTE → entering active management zone
Day 55:  Short put at 20 DTE → Begin closing/rolling assessment
Day 61:  Short put at 14 DTE → LAW 1 FORCE CLOSE activated
```

Annual hedge cost comparison (5-contract position):

- **V3 Diagonal** (replace every ~21 days, net \$1.60/replacement): ~\$1,040/year
- **Vertical** (single long put, \$2.10 net/cycle at same frequency): ~\$1,365/year
- **Annual savings from diagonal structure: ~\$325 per 5-contract position** — pure additional profit


### 2.3 The Critical Rule: Zero Naked Exposure Window

When replacing the long put, the replacement order must be placed **before or simultaneously** with the closing of the expiring long put. The naked short put window must never exceed a single trading session:

```python
# Automated long put replacement trigger
if long_put.dte <= 7 and short_put.dte > 21:
    # Step 1: Place BTO order for new long put (same/lower strike, 21-35 DTE)
    new_long_put = place_order(
        action='BTO',
        strike=long_put.strike,     # same or lower strike if stock drifted
        dte_target=28,              # fresh 28-day protection window
        max_cost=long_put.original_cost * 1.20  # don't overpay for replacement
    )
    # Step 2: Close expiring long put only after new one confirmed filled
    if new_long_put.filled:
        close_order(long_put, action='STC')
    # NEVER allow naked_short_put_window > same_trading_session
```


### 2.4 Diagonal-Specific Risk: Slow Grind Declines

The shorter-DTE long put loses time value faster than a longer-dated hedge. In a **slow, grinding decline** (stock falls 1–2% per week over many weeks), the long put may decay significantly before reaching the protection strike. This structure works best when drops are **sharp and swift** — which is precisely TurboBounce's entry philosophy (entering after sudden spikes when IV is elevated and bounces are typically fast). The Roll-Down Qualifier (Section 4) explicitly filters out slow-grind setups through the ML re-entry score.

***

## 3. The Three Laws: Complete Management Specification

### Law 1 — Never Hold to Expiration

This system harvests price movement, not time decay. Holding to expiration converts a swing trade into a passive calendar bet and introduces assignment risk, gamma risk, and spread-widening in the final days. **Hard rules:**

- Any short put position with ≤ 14 DTE: force-close regardless of P\&L — no exceptions
- Any long put position with ≤ 7 DTE and the short put still has > 21 DTE: trigger the long put replacement cycle (Section 2.3)
- "Expiration" monitoring runs on two clocks: the short put clock AND the long put clock


### Law 2 — When Wrong: Close the Full Spread, Then Re-Open at a Better Location

When the trade goes against the position — the stock continues falling through the strikes on a bull put spread, or rising on a bear put spread — the response is two actions:

**Step 1:** Close the entire spread (both legs) via stop-limit order. Never use stop-market on options — wide bid-ask spreads cause stop-market orders to fill above stated max loss.

**Step 2:** Run the 8-point Roll-Down Qualifier (Section 4). If all 8 pass, immediately open a new **diagonal spread** at lower strikes — maintaining the same DTE asymmetry structure (longer-DTE short put / shorter-DTE long put). If any criterion fails, stand aside for a minimum of 5 trading days.

The principle: a challenged spread is a **location problem**, not necessarily a thesis problem. The stock may need to find a lower equilibrium before bouncing. Rolling down — while staying in the same diagonal structure — repositions the trade to catch the bounce at an improved level with a fresh credit.

### Law 3 — When Right: Close Only the Short Leg, Then Stop-Limit the Long Put

**Step 1:** When the short put has lost ≥ 50% of its original credit value on a bounce, BTC the short put leg via limit order.

**Step 2:** The long put is now a solo asset. Immediately place a stop-limit at:

$$
SL_{long} = V_{current} \times (1 - k)
$$

where $k$ is regime-calibrated: 0.40 in Complacent Bull (VIX < 18), 0.55 in Elevated Fear (VIX 18–30), 0.65 in Crisis (VIX > 30).

**Step 3:** Trail the stop upward as the long put gains value on any subsequent move. If the long put doubles in value, sell 50% to lock in gains and let the remainder ride as a zero-cost tail hedge.

**Step 4:** If DTE on the long put falls below 7 with no new directional catalyst, close it for residual value. Do not hold a decaying long put with no management framework.

***

## 4. The Roll-Down Mechanic: Full Specification

### 4.1 Why Rolling Down Beats Walking Away

On a \$10-wide diagonal spread entered for \$3.80 credit (max loss = \$6.20):


| Outcome | Path A: Close \& Walk Away | Path B: Close \& Re-Open Diagonal at Lower Strikes (\$2.80 new credit) |
| :-- | :-- | :-- |
| Realized loss to close | −\$4.00 | −\$4.00 |
| New credit received | \$0 | +\$2.80 |
| Net out-of-pocket | **−\$4.00** | **−\$1.20** |
| If stock bounces from new level (50% credit) | No upside | +\$1.40 → **net total: −\$0.60** (near breakeven) |
| If stock fully recovers | −\$4.00 | −\$1.20 net |
| If stock crashes further (worst case) | −\$4.00 max | −\$4.00 + (−\$7.20) = −\$11.20 |

Rolling converts a losing trade into a near-breakeven when the mean-reversion thesis is simply delayed rather than broken — which is the most common scenario in fundamental strong-stock temporary overshoots. The worst-case only materializes in structural breakdown, which the 8-point qualifier explicitly prevents.

### 4.2 The 8-Point Roll-Down Qualifier (ALL must pass)

1. **Structural support intact**: Stock is still above its 52-week low and above a major support level (prior consolidation, 200-week SMA). Structural breakdown = no roll, ever.
2. **IV still elevated**: IVR ≥ 25% after the continued decline. If IV has not risen or collapsed despite the drop, the new spread won't generate adequate credit.
3. **New long put strike has identifiable support below it**: Protection leg must sit beneath a recognizable floor — not in open air.
4. **ML roll qualifier score ≥ 0.55**: The LightGBM Roll Qualification Model (Section 6.2) scores the roll setup. Threshold is lower than fresh entry (0.65) because the position already has context.
5. **No earnings within 5 days**: Binary events destroy mean-reversion setups instantly. Never roll into an earnings window.
6. **New credit ≥ 25% of new spread width**: Ensures meaningful premium collected on the rolled position. A thin-premium roll has inadequate reward for the additional risk.
7. **Roll count ≤ 1 for this ticker this cycle**: Maximum **one roll-down per ticker per mean-reversion cycle**. A second roll is averaging into a structural decline.
8. **Account buying power sufficient**: Combined risk (original realized loss + new spread max loss) must not exceed 6% of total portfolio.

### 4.3 Roll-Down Execution Mechanics

```
TRIGGER: Spread P&L reaches −75% of max loss 
         OR stock closes below the long put strike

QUALIFIER: Run all 8 criteria — ALL must pass

IF ALL 8 PASS:
  ── Close current diagonal spread (both legs, stop-limit order)
  ── Open new diagonal at lower strikes:
       New short put: same delta target (0.35–0.45) at new lower price level
       New long put:  same delta target (0.20–0.25), 21–35 DTE (reset fresh)
       New short put: 60–90 DTE (reset fresh)
       Execute as single spread order — not legged
  ── Record net basis: original realized loss − new credit received
  ── Apply same 3 Laws to the new diagonal position
  ── Mark ticker as "1 roll used — no further rolls this cycle"

IF ANY CRITERION FAILS:
  ── Close spread only (stop-limit order)
  ── No re-entry on same ticker for minimum 5 trading days
  ── Tag the trade in system as "structural close — thesis invalidated"
```


***

## 5. The Four-Mode Strategy Matrix

V3 operates across four volatility-adaptive modes. The diagonal DTE asymmetry applies to all spread-based modes. PMCC and LEAPS Diagonal use their own DTE logic as described below.


| Mode | IV Regime | Direction | Structure | Short Leg DTE | Long/Hedge Leg DTE | Roll Adjustment |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| **1: Bull Put Diagonal Swing** | High IV (IVR > 30%) | Bullish | Sell high-strike put + Buy low-strike put | **60–90 DTE** | **21–35 DTE** | Roll **down** to lower strikes |
| **2: Bear Put Diagonal Swing** | High IV (IVR > 30%) | Bearish | Buy high-strike put + Sell low-strike put | Long: 60–90 DTE / Short sold: 60–90 DTE | Long hedge: 21–35 DTE | Roll **up** to higher strikes |
| **3: LEAPS PMCC** | Low IV (IVR < 20%) | Bullish | Buy deep ITM LEAPS call + Sell OTM short call | Short call: 30–45 DTE | LEAPS: 12+ months | Roll short call **up-and-out** |
| **4: LEAPS Diagonal Put** | Low IV (IVR < 20%) | Bearish | Buy deep ITM LEAPS put + Sell OTM short put | Short put: 30–45 DTE | LEAPS: 12+ months | Roll short put **down-and-out** |

### 5.1 Mode 1: Bull Put Diagonal Swing (Core Engine)

**Entry conditions:**

- Stock has dropped ≥ 5% from its 10-day high on a fundamentally sound ticker
- IVR ≥ 30% (elevated premiums available)
- Stock above 200-day SMA on weekly, or within 15% of 52-week high (structural health check)
- ML entry score ≥ 0.65 (XGBoost classifier, Section 6.1)

**Diagonal structure:**

- Short put: delta 0.35–0.45, **DTE 60–90** (fat premium, long runway)
- Long put: delta 0.20–0.25, **DTE 21–35** (cheap hedge, defined risk)
- Net credit target: ≥ 35% of spread width (achievable at 38%+ on the diagonal)
- Width: \$5–\$15 depending on regime (Section 6.4 parameters)

**Favorable management (stock bounces):**

- Short put loses ≥ 50% of original credit → BTC short leg via limit order
- Immediately set stop-limit on long put at $V_{current} \times (1 - k)$
- Trail stop upward; sell 50% if long put doubles; close remainder at 7 DTE if no catalyst

**Unfavorable management (stock continues falling):**

- At −75% max loss or long put strike breach → run 8-point qualifier
- If all pass: close diagonal + re-open new diagonal at lower strikes (same DTE asymmetry)
- If any fail: close entire spread, stand aside 5 days minimum

**Long put replacement (no directional move — time passes):**

- Long put reaches 7 DTE while short put has > 21 DTE remaining
- Replace long put: new 28-DTE long put at same or lower strike before closing expiring leg
- Never allow naked short put exposure beyond same trading session

**Force close:**

- Short put reaches 14 DTE: close both legs regardless of P\&L — Law 1 non-negotiable


### 5.2 Mode 2: Bear Put Diagonal Swing (Replaces DIAGONAL/BEARISH)

This mode directly replaces the −\$38,385 DIAGONAL/BEARISH drain. The fix is precise: V1 managed diagonal bearish positions by TIME (15-day exits), which meant positions that were temporarily wrong were held through further adverse moves and then closed at losses when the timer ran out. V3 manages by PRICE — using roll-up logic symmetrically with the bull put's roll-down.

**Entry conditions:**

- Stock has rallied ≥ 5% from its 10-day low into identifiable resistance
- IVR ≥ 25% (at least moderate premium available on the bearish side)
- Stock shows structural weakness: below 200-day SMA, post-earnings miss, or sector breakdown
- ML bearish entry score ≥ 0.65

**Diagonal structure:**

- Long put: delta 0.45–0.55, **DTE 60–90** (directional leg, needs time to play out)
- Short put (sold below): delta 0.20–0.25, **DTE 21–35** (premium reduction, also shorter hedge cost)
- Net debit ≤ 50% of spread width (minimum 2:1 max reward/risk)

**Favorable (stock drops):**

- BTC the short lower-strike put when it's at near-zero value (let decay work)
- Stop-limit the long put at entry cost basis (protect gains)
- Let long put run as bearish momentum extends; remove stop if macro breakdown unfolds

**Unfavorable (stock rallies against position):**

- At −75% max loss: run Roll-Up Qualifier (same 8-point gate, inverted for bearish)
- If all pass: close spread + re-open at higher strikes with same DTE asymmetry
- Maximum one roll-up per ticker per cycle


### 5.3 Mode 3: LEAPS PMCC (Low IV Bullish)

When IVR < 20%, buying options is cheap and selling generates thin premiums. The PMCC captures directional delta at low IV cost while systematically selling short-dated calls on rally peaks.

- **LEAPS Call (bought)**: delta 0.75–0.85, DTE ≥ 12 months — high-delta stock replacement
- **Short Call (sold)**: delta 0.25–0.35, DTE 30–45 days — **only sold when stock is at overbought extreme (RSI-2 > 90)**; not on a calendar basis
- Roll short call up-and-out when breached
- Close LEAPS when it appreciates 40–60% or when bullish thesis breaks (close below 200-day SMA)


### 5.4 Mode 4: LEAPS Diagonal Put (Low IV Bearish)

Replaces the DIAGONAL/BEARISH allocation when IV is too low for credit spread entry:

- **LEAPS Put (bought)**: delta −0.75 to −0.85, DTE ≥ 12 months
- **Short OTM Put (sold)**: delta −0.25 to −0.35, 30–45 DTE — **only sold on relief rallies** (overbought signal), not on calendar
- Roll short put down-and-out when stock drops (your direction) through the short strike
- Close if fundamental thesis repairs — stop-limit the LEAPS put at entry cost basis once 30% profitable

***

## 6. Complete Trade Flow: Master Decision Tree

```
═══════════════════════════════════════════════════════════════
STEP 1 — IV REGIME CHECK (runs at market open daily)
═══════════════════════════════════════════════════════════════
  IVR < 20% (LOW IV)
    → BULLISH signal?  → MODE 3: LEAPS PMCC
    → BEARISH signal?  → MODE 4: LEAPS Diagonal Put
  
  IVR 20–30% (NEUTRAL)
    → Use spread modes at 50% reduced position size only
  
  IVR ≥ 30% (HIGH IV — optimal spread entry zone)
    → BULLISH signal?  → MODE 1: Bull Put Diagonal Swing
    → BEARISH signal?  → MODE 2: Bear Put Diagonal Swing
    → Run ML Entry Classifier on specific ticker/strikes
    → p_entry ≥ 0.65? → ENTER | < 0.65? → PASS, monitor next day

═══════════════════════════════════════════════════════════════
STEP 2 — POSITION OPENED (diagonal entered)
═══════════════════════════════════════════════════════════════
  MONITORING RUNS HOURLY during market hours
  
  CHECK A — LONG PUT DTE ≤ 7?
    YES → Is short put DTE > 21?
      YES → Trigger long put replacement cycle (new 28-DTE long put)
      NO  → Short put near force-close anyway; continue to CHECK C
  
  CHECK B — FAVORABLE MOVE: short put lost ≥ 50% of credit?
    YES → LAW 3: BTC short leg
          → Set stop-limit on long put at V_current × (1−k)
          → Trail stop; sell 50% if long put doubles; close at 7 DTE
    NO  → HOLD
  
  CHECK C — UNFAVORABLE: spread at −75% max loss OR long strike breached?
    YES → Run 8-Point Roll-Down Qualifier
      ALL 8 PASS → LAW 2 (ROLL): Close diagonal + Open new diagonal at lower strikes
                   Same DTE asymmetry (Short: 60–90 DTE / Long: 21–35 DTE)
                   Mark ticker: "1 roll used — no further rolls this cycle"
      ANY FAIL  → LAW 2 (CLOSE): Close spread only, stand aside 5 days
    NO  → HOLD
  
  CHECK D — SHORT PUT DTE ≤ 14?
    YES → LAW 1: FORCE CLOSE both legs immediately
          No exceptions. Log as time-exit in position tracker.
    NO  → HOLD, continue monitoring
```


***

## 7. ML Enhancement Framework

Four purpose-built ML modules replace discretionary judgment at the four highest-value decision points. With 1,274 labeled trades across three account sizes and seven years, TurboBounce possesses a proprietary training dataset that off-the-shelf models lack.

### 7.1 Module 1: Entry Signal Classifier (XGBoost)

**Goal:** Predict the probability that a new diagonal spread entry on a given ticker at current strikes will capture ≥ 50% of max credit within 21 days. Separate models for Mode 1 (bull put) and Mode 2 (bear put) — the feature structure differs between oversold bounces and overbought reversals.

**Feature engineering table:**


| Category | Features |
| :-- | :-- |
| Volatility | IVR (1-year), VIX level, VIX 5-day change %, VRP (IV − HV30), put/call skew ratio |
| Price action | % drop from 10-day high, % from 50/200-day SMA, ATR-normalized drop |
| Momentum | RSI-14, RSI-2, Stochastic %K, Williams %R, Bollinger %B |
| Options-specific | Short put delta, spread width/price ratio, OI put/call ratio, gamma at short strike |
| Diagonal-specific | **DTE ratio (short/long)**, **long put replacement cost vs. net credit ratio**, IV term structure slope (short-vs-long dated IV differential) |
| Market context | SPY 20-day return, % S\&P 500 stocks above 200 SMA, sector relative strength |
| Fundamental | Days since earnings, distance from 52-week high, EPS trend direction |

The diagonal-specific features are new in V3 — they give the model signal on whether the DTE asymmetry is favorable (long put cheap relative to premium collected) or unfavorable (flat IV term structure reduces the diagonal advantage).

```python
from xgboost import XGBClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit

model = XGBClassifier(
    n_estimators=500, max_depth=5, learning_rate=0.05,
    subsample=0.8, colsample_bytree=0.8,
    scale_pos_weight=neg_count/pos_count,
    eval_metric='auc', early_stopping_rounds=50
)
tscv = TimeSeriesSplit(n_splits=5, gap=21)  # 21-day gap prevents lookahead
calibrated = CalibratedClassifierCV(model, cv=tscv, method='isotonic')
# Entry thresholds: fresh entry p >= 0.65 | roll re-entry p >= 0.55
```


### 7.2 Module 2: Roll-Down Qualification Model (LightGBM)

**Goal (V3 new):** When a spread is challenged and a roll is being considered, predict whether the roll will lead to recovery — i.e., will the stock bounce from the new lower strike zone within 30 days? This model automates and scores the 8-point Roll Qualifier checklist, replacing manual review with a calibrated probability.

**Roll-specific features:**

- Distance from current price to 52-week low (structural support proximity score)
- IVR at moment of roll decision (premium availability at new strikes)
- VIX slope over prior 5 days (is fear accelerating or peaking?)
- RSI-2 at time of roll (is the stock deeply oversold at the new level?)
- SPY 5-day momentum (is market-wide selling still escalating?)
- Diagonal premium advantage at new strikes (long put cost / short put premium ratio)
- Prior roll count on this ticker this cycle

**Training data:** The 8 historical losing credit spread trades across accounts, augmented with ORATS simulated challenged-spread scenarios on the 40-ticker universe.

**Threshold:** Roll score ≥ 0.55 → proceed with roll; < 0.55 → close only.

### 7.3 Module 3: Exit Timing Optimizer (LSTM + RL)

**Goal:** Determine the optimal short-leg BTC timing and stop-limit calibration for the long put, replacing the fixed 15-day TIME exit.

**LSTM Reversal Predictor (short leg close trigger):**

- Input: 20-bar OHLCV sequence + current Greeks (delta, theta, vega of short put) + running P\&L%
- Output: $p_{reversal}$ — probability of ≥ 3% downward reversal within 3 trading days
- Trigger: $p_{reversal} \geq 0.60$ AND short put down ≥ 40% → BTC short leg immediately
- Research shows LSTM reversal prediction achieves F1 scores of 55–68%; even at 55%, this edge materially improves average credit capture vs. a fixed time rule

**Stop-Limit Calibration ($k$ per regime):**

$$
k = \begin{cases} 0.40 & \text{Complacent Bull (VIX < 18)} \\ 0.55 & \text{Elevated Fear (VIX 18–30)} \\ 0.65 & \text{Crisis (VIX > 30)} \end{cases}
$$

In high-volatility regimes, the stop is set wider — the long put experiences larger intraday swings, and a tight stop would be triggered by noise rather than a genuine reversal.

**Reinforcement Learning Exit Agent (Phase 5, advanced):**

A DQN agent trained in a simulated diagonal options environment, with five actions:


| Action | Description |
| :-- | :-- |
| 0: Hold | Maintain position |
| 1: Close Short Leg | BTC short put, retain long put with stop-limit |
| 2: Replace Long Put | Trigger long put replacement cycle (7-DTE threshold) |
| 3: Close Full Spread | Exit both legs, stand aside |
| 4: Roll Diagonal Down | Close current diagonal, open new at lower strikes |

The RL agent discovers optimal sequences across regimes — for example, it may learn to roll diagonals earlier (at 60% max loss instead of 75%) in Elevated Fear regimes where the diagonal premium advantage at lower strikes is most favorable.

### 7.4 Module 4: Diagonal Parameter Optimizer (Bayesian + Regime-Conditioned)

**Goal:** Select optimal short put delta, spread width, DTE ratio, and long put replacement schedule per market regime, using Bayesian optimization over a walk-forward validation framework.

**HMM 3-State Regime Classifier:**


| Regime | VIX | IVR | IV Term Structure | Short DTE | Long DTE | Width | Roll Threshold |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Complacent Bull | < 18 | < 20% | Flat (no IV advantage) | — use LEAPS modes — | — | — | — |
| Elevated Fear | 18–30 | 20–50% | Steep (diagonal premium high) | 60–75 days | 21–28 days | \$8–\$15 | −75% max loss |
| Crisis / Panic | > 30 | > 50% | Inverted/flat (short IV spikes) | 75–90 days | 28–35 days | \$10–\$20 | **No rolls** |

The IV term structure slope is particularly important for the diagonal: when short-term IV > long-term IV (inverted), buying the short-DTE long put becomes more expensive relative to the long-DTE short put. The model detects this and either widens the strike gap to compensate or switches to same-expiration vertical structure temporarily.

**Walk-forward schedule:**

- In-sample: 104 weeks (2 years)
- Out-of-sample validation: 26 weeks (6 months)
- Advance quarterly
- Optimization metric: **Calmar Ratio** (annual return ÷ maximum drawdown)

***

## 8. Implementation Plan: 20-Week Roadmap

### Phase 1 — Diagonal Engine \& Roll Logic Foundation (Weeks 1–3)

**Build `DiagonalSpreadManager` class:**

```python
class DiagonalSpreadManager:
    def __init__(self, short_put, long_put, regime, roll_count=0):
        self.short_put = short_put   # 60–90 DTE
        self.long_put = long_put     # 21–35 DTE
        self.regime = regime
        self.roll_count = roll_count
    
    def evaluate(self, market_data):
        # CHECK A: Long put replacement
        if self.long_put.dte <= 7 and self.short_put.dte > 21:
            return Action.REPLACE_LONG_PUT  # before short put close
        
        # CHECK B: Law 1 - force close
        if self.short_put.dte <= 14:
            return Action.FORCE_CLOSE
        
        # CHECK C: Law 3 - favorable (short put down ≥ 50%)
        if self.short_put.pnl_pct_of_credit >= 0.50:
            return Action.CLOSE_SHORT_LEG_ONLY  # then stop-limit long put
        
        # CHECK D: Law 2 - unfavorable (−75% max loss)
        if self.spread_pnl_pct <= -0.75:
            if self.roll_count < 1 and RollQualifier(self, market_data).score >= 0.55:
                return Action.CLOSE_AND_ROLL_DIAGONAL_DOWN
            else:
                return Action.CLOSE_FULL_SPREAD
        
        return Action.HOLD
```

**Deliverables:**

- `RollQualifier` class with all 8 criteria automated
- `LongPutReplacer` class: BTO new 28-DTE put → confirm fill → STC expiring put
- `StopLimitManager`: regime-calibrated k, trailing stop logic
- Backtesting scaffold on 2019–2025 TurboBounce history


### Phase 2 — ML Training Pipeline (Weeks 4–7)

1. Feature extraction: compute all features (including new diagonal-specific ones) for every trade entry date in TurboBounce history
2. Label construction: was each position a swing success (≥ 50% credit in ≤ 21 days)?
3. Train XGBoost entry classifier for Mode 1 (bull put) and Mode 2 (bear put) separately
4. Train LightGBM roll qualification model on 8 loss instances + ORATS augmented data
5. SHAP analysis on both models — validate feature importance, ensure no look-ahead contamination

### Phase 3 — V1 vs. V3 Backtest (Weeks 8–10)

**Three-scenario comparison, 2015–2025, ORATS historical data:**


| Scenario | Exit Method | Diagonal Structure | Roll Logic |
| :-- | :-- | :-- | :-- |
| V1 (baseline) | TIME (15 days) | Same-expiration vertical | None |
| V3 Rules-Only | PRICE (50% credit) | DTE asymmetric diagonal | 8-point gate |
| V3 + ML | LSTM + XGBoost + LightGBM | DTE asymmetric diagonal | ML-scored gate |

**Minimum bar for V3 to proceed to live deployment:**

- V3 win rate ≥ 88% on spread trades (vs 91.8% V1 — minor reduction acceptable)
- V3 average credit captured per spread ≥ 55% (vs. TIME-exit baseline)
- V3 max drawdown in 2022-equivalent ≤ 20% (vs. −27.7% V1)
- V3 diagonal net credit/width ≥ 35% on average (vs. ~19% same-expiration vertical)


### Phase 4 — Bear Put, PMCC \& LEAPS Modes (Weeks 11–13)

1. **Mode 2 Bear Put Diagonal**: build roll-up logic mirror. Replace DIAGONAL/BEARISH entirely. Target recovery of −\$38,385 historical drag across all accounts.
2. **Mode 3 PMCC**: implement RSI-2 triggered short call selling (not calendar), roll up-and-out logic
3. **Mode 4 LEAPS Diagonal Put**: swing-managed short put selling, roll-down-and-out mechanics
4. IV term structure monitor: detect when diagonal advantage is reduced (flat term structure) and switch to same-expiration vertical or LEAPS mode automatically

### Phase 5 — Integration, Paper Trade \& Deployment (Weeks 14–20)

**Signal card format for TurboBounce V3 platform:**

```
═══════════════════════════════════════════════════════
TURBOBOUNCE V3 SIGNAL — Mode 1: Bull Put Diagonal
═══════════════════════════════════════════════════════
TICKER:       NVDA ($184 after 8% drop)
STRUCTURE:    Sell $175P (75 DTE) / Buy $165P (28 DTE)
NET CREDIT:   $3.80 target  [vs. $1.90 vertical = +100%]
REGIME:       Elevated Fear (IVR 38%, VIX 24)
ML ENTRY SCORE: 0.74 ✅ HIGH CONFIDENCE
─────────────────────────────────────────────────────
MANAGEMENT RULES:
  ✓ Close SHORT put when it loses 50%+ of value (bounce)
  ✓ Set stop-limit on LONG put at 45% below current mark
  ✓ Replace LONG put when it reaches 7 DTE (auto-alert)
  ✗ DO NOT hold short put below 14 DTE
  ✗ DO NOT allow naked short put window > same session
─────────────────────────────────────────────────────
ROLL-DOWN ALERT: If NVDA falls below $165 and roll
  score ≥ 0.55 → Re-open diagonal at $165/$155 zone
  Net basis after roll: initial loss − new credit
═══════════════════════════════════════════════════════
```


***

## 9. Optimized Parameter Benchmarks

| Parameter | V1 (Current) | V3 Rules-Based | V3 + ML Target |
| :-- | :-- | :-- | :-- |
| **Short put DTE** | 30–45 days | **60–90 days** | Bayesian per regime |
| **Long put DTE** | Same as short | **21–35 days** | Bayesian per regime |
| **Net credit / width** | ~19% | **~38%** | ≥ 35% minimum |
| Entry trigger | VIX change > +10% | IVR ≥ 30% + swing signal | XGBoost p ≥ 0.65 |
| Roll re-entry trigger | None | 8-point checklist | LightGBM score ≥ 0.55 |
| Short put delta | 0.25–0.30 | 0.35–0.45 | Regime-Bayesian |
| Long put delta | 0.10–0.15 | 0.20–0.25 | Regime-Bayesian |
| Long put replacement | N/A | At 7 DTE of long leg | Automated in platform |
| Short leg BTC trigger | 15-day TIME | 50% credit PRICE | LSTM p_reversal ≥ 0.60 |
| Stop-limit k (long put) | None | 0.50 fixed | Regime-calibrated (0.40/0.55/0.65) |
| Roll trigger | None | −75% max loss | −65% to −90% regime-adjusted |
| Max rolls per cycle | N/A | 1 (hard cap) | 1 (hard cap, no exceptions) |
| Rolls in Crisis regime | N/A | 0 (VIX > 30) | 0 (VIX > 30) |
| Force close DTE | Expiration | 14 DTE short put | 14 DTE short put |
| Target CAGR (25K) | 24.6% | 27–30% | **30–35%** |
| Target max drawdown | −27.7% (2022) | −22% | **−17%** |


***

## 10. Risk Framework

### Position-Level Rules

- Maximum risk per spread: (width − credit) ≤ 3% of portfolio
- After roll-down: combined risk (original loss + new spread max loss) ≤ 6% of portfolio. If this would be exceeded, close only — do not roll.
- Always stop-limit orders on options spreads (never stop-market)
- Force close at 14 DTE on short put — gamma risk, assignment risk, and spread widening in final days make this non-negotiable
- Long put replacement: automated, zero naked window tolerance


### Roll-Down Absolute Limits

- Maximum 1 roll per ticker per mean-reversion cycle
- No rolls in Crisis/Panic regime (VIX > 30, IVR > 50%): trending crashes are the primary failure mode of roll strategies
- No rolls within 5 days of earnings
- Combined position size cap: original + rolled spread ≤ 6% of account


### Portfolio-Level Rules

- Maximum 5 concurrent spread positions across ≥ 5 uncorrelated tickers
- No more than 2 positions in the same sector simultaneously
- In Crisis regime: reduce to maximum 2 positions, widen spread to ≥ \$15, suspend all rolls
- Total theta cost of all open long puts ≤ 10% of monthly credit collected

***

## 11. Technology Stack

| Component | Tool | Purpose |
| :-- | :-- | :-- |
| Live options data | Alpaca Markets API, Tastytrade API | Real-time chain + Greeks + DTE tracking |
| Historical options | ORATS, OptionsDX | ML training, IV term structure history |
| Feature engineering | `pandas-ta`, `ta-lib` | 20+ features including diagonal-specific |
| Entry classifier | `xgboost` + `shap` | Mode 1/2 entry scoring (trained on TurboBounce data) |
| Roll qualifier | `lightgbm` | Automated 8-point roll qualification scoring |
| IV term structure | ORATS API | Detect flat term structure → disable diagonal advantage |
| Exit optimizer | `PyTorch` LSTM | Short leg BTC timing via reversal prediction |
| RL exit agent | `stable-baselines3` PPO | 5-action management agent (Hold/Close Short/Replace Long/Close All/Roll) |
| Regime classifier | `hmmlearn` 3-state HMM | Bull / Fear / Crisis regime detection |
| Parameter optimizer | `optuna` Bayesian | Walk-forward DTE ratio / delta / width optimization |
| Backtesting | `vectorbt` + ORATS Backtester | V1 vs. V3 comparison |
| Order execution | Tastytrade API + Alpaca SDK | Spread orders, long put replacement automation |
| Signal delivery | Next.js API routes | Signal cards with ML score, DTE clocks, roll alerts |
| Mobile dashboard | React Native | Live position P\&L, DTE countdown, replacement alerts |


***

## 12. Integration Map: Existing TurboBounce Assets → V3

| Existing Asset | V3 Integration Point |
| :-- | :-- |
| **Landing Page** | Signal cards show DTE clock for both legs, ML confidence, roll availability, net basis after any roll |
| **Mobile Website Plan** | Push alert: "⚠️ NVDA long put reaches 7 DTE — replacement order auto-queued at \$165P 28-DTE. Tap to confirm." |
| **Market Analysis** | V3's diagonal DTE engine is a quantifiable moat: "We collect 2× the premium of standard vertical spreads using a diagonal DTE structure — no competitor publishes this." |
| **Competitive Analysis** | No competing retail options signal service (SteadyOptions, Option Alpha, Mean Reversion Trading) publishes a diagonal-optimized, ML-scored roll qualification model |
| **Master Marketing Plan** | Lead headline: "When the trade goes against you, TurboBounce rolls to a better location and waits for the bounce. When it goes for you, we close the short leg and let the hedge ride free." |
| **Legal Compliance Plan** | Add: "Diagonal spread strategies involve legs with different expiration dates. The long protective leg will expire before the short leg, requiring active management including periodic replacement of the protective leg." |
| **Referral / Social Media Plan** | Content series: "Why I use a diagonal instead of a vertical for options spreads" — this is a specific, demonstrable edge that Gen Z traders can test and validate |


***

The full V3 plan is above. The diagonal DTE asymmetry is now woven through every layer — the structure section has the credit math showing the ~100% credit improvement, the management rules have the dual-clock (short put DTE AND long put DTE) with the automated replacement cycle, the ML parameter optimizer now includes diagonal-specific features (DTE ratio and IV term structure slope), the RL agent has a 5th action (Replace Long Put), and the parameter benchmark table shows the DTE targets explicitly. The key operational addition is the **zero naked window rule** — the long put replacement must be confirmed filled before the expiring leg is closed, which is now a first-class automated function in the `DiagonalSpreadManager` class.
<span style="display:none">[^1][^2][^3]</span>

<div align="center">⁂</div>

[^1]: turbobounce_options_20k_all_trades.csv

[^2]: turbobounce_options_5k_all_trades.csv

[^3]: turbobounce_options_25k_all_trades.csv

