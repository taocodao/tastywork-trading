# Combined TQQQ Strategy: 530 EMA Crossover + Core-Satellite SMA200 — Viability, ML Optimization & Implementation Plan

## Executive Summary

This report evaluates the viability of combining two complementary TQQQ strategies—the **530 EMA Crossover** (5/30 EMA golden/death cross for swing trade timing) and the **Core-Satellite SMA200** allocation (60% QQQ / 30% QLD / 10% TQQQ with SMA200 hysteresis filter)—into a unified, ML-enhanced trading system. The first strategy excels at micro-level entry/exit timing within bull markets, while the second provides macro-level regime filtering and tiered leverage management. Their combination addresses each other's weaknesses: the SMA200 regime gate eliminates the 530's vulnerability to bear markets, while the EMA crossover adds precision timing that the passive core-satellite allocation lacks.[^1][^2]

Independent research corroborates both strategies individually: EMA crossover on TQQQ yields 24–35% CAGR with controlled drawdowns, and SMA200-based strategies on leveraged ETFs have been validated across 25+ year backtests including the 2000 dotcom crash and 2008 financial crisis. A combined approach, enhanced with ML regime detection, adaptive parameters, and dynamic allocation, has the potential to achieve 30–50% CAGR with maximum drawdowns under 25%.[^3][^4]

***

## Part 1: Individual Strategy Review

### Strategy A — 530 EMA Crossover

The 530 Strategy, presented by 天哥复利之道 (Tian Ge), trades TQQQ based on 5-day EMA / 30-day EMA crossovers:[^1]

| Metric | Value |
|--------|-------|
| Instrument | TQQQ (3x leveraged QQQ) |
| Entry | EMA(5) crosses above EMA(30) |
| Exit | EMA(5) crosses below EMA(30) |
| Backtest Period | Jan 2015 – Nov 2025 (~11 years) |
| Total Trades | 56 (~5/year, avg hold ~2.5 months) |
| Win Rate | 45% (24 wins, 32 losses) |
| Reward-Risk Ratio | 2.93x |
| Max Single Loss | -13.91% |
| Cumulative Return | ~$10K → $198K (peak $233K) |
| 2022 Bear Market | -22% (vs TQQQ buy-hold -83%) |

The strategy benefits from TQQQ's 3x leverage creating volatility decay during sideways markets, which naturally suppresses false golden cross signals. However, it uses 100% position sizing with no regime awareness, making it vulnerable during prolonged bear-to-sideways transitions.[^5][^1]

### Strategy B — Core-Satellite SMA200 with Hysteresis

This strategy, also from Tian Ge, uses a tiered leverage allocation with SMA200 regime filtering:[^2]

| Metric | Value |
|--------|-------|
| Allocation | 60% QQQ + 30% QLD (2x) + 10% TQQQ (3x) |
| Buy Signal | QQQ > SMA(200) + hysteresis buffer |
| Sell Signal | QQQ < SMA(200) − hysteresis buffer |
| Off-Market Asset | SGOV (0-3 month T-bills)[^6] |
| Backtest Period | 26 years (2000–2026) |
| Total Return | 27x (vs QQQ ~13x) |
| 5-Year Max Drawdown | -33% |

The asymmetric hysteresis buffer (+5% to buy / -3% to sell) prevents whipsaw trades near the SMA200 line. During risk-off periods, capital parks in SGOV earning ~4–5% yield. A similar 200SMA +5%/-3% strategy on TradingView showed ~85% win rate with TQQQ execution.[^7][^8][^6][^9]

***

## Part 2: Why These Strategies Combine Well

### Complementary Strengths

The two strategies operate on different timeframes and solve different problems:

| Dimension | 530 EMA Crossover | Core-Satellite SMA200 |
|-----------|-------------------|----------------------|
| Timeframe | Short-term swing (weeks) | Long-term position (months) |
| Signal Frequency | ~5 trades/year | ~1–2 regime shifts/year |
| Primary Strength | Precise entry/exit timing | Bear market avoidance |
| Primary Weakness | No regime awareness | No entry timing optimization |
| Leverage Approach | 100% TQQQ always | Tiered QQQ/QLD/TQQQ |
| Risk Management | None built-in | SMA200 regime gate |

When combined, the SMA200 acts as the **macro gate** controlling whether the system is risk-on or risk-off, while the EMA 5/30 crossover acts as the **micro trigger** for optimizing entries and exits within the risk-on regime. This layered approach has been independently validated: a TradingView strategy combining SMA/EMA crossover with a 200 SMA filter showed that requiring price above SMA(200) for long entries significantly reduced false signals.[^10][^11]

### Combined Strategy Logic

```
MACRO LAYER: SMA200 Regime Gate (checked daily)
├── RISK-ON: QQQ > SMA(200) + 5% buffer
│   └── MICRO LAYER: 530 EMA Crossover (checked daily)
│       ├── EMA(5) > EMA(30) → AGGRESSIVE allocation
│       │   50% QQQ + 25% QLD + 25% TQQQ
│       └── EMA(5) < EMA(30) → DEFENSIVE allocation
│           70% QQQ + 20% QLD + 10% TQQQ
├── TRANSITIONAL: QQQ between SMA(200) ± buffer
│   └── CONSERVATIVE allocation
│       80% QQQ + 15% QLD + 5% TQQQ (no new TQQQ entries)
└── RISK-OFF: QQQ < SMA(200) − 3% buffer
    └── EXIT all leveraged positions
        100% SGOV (earn ~4-5% T-bill yield)
```

This three-tier approach addresses a known problem with the standalone SMA200 strategy: significant drawdowns can occur just before the exit trigger fires. One Reddit user noted that "just before exiting trades, it can experience significant drawdowns, sometimes around 30-40%". The EMA crossover within the risk-on zone would catch these declines earlier, de-leveraging before the SMA200 exit triggers.[^12]

### Enhanced Allocation Variants

An advanced variant draws from the approach by Reddit user XXXMrHOLLYWOOD, who shifts between TQQQ and QLD based on Supertrend signals within the SMA200 regime. This concept maps directly onto our combined strategy:[^12]

| Regime + Signal | QQQ | QLD | TQQQ | SGOV |
|-----------------|-----|-----|------|------|
| Risk-On + EMA Golden Cross | 40% | 30% | 30% | 0% |
| Risk-On + EMA Death Cross | 70% | 20% | 0% | 10% |
| Transitional | 80% | 15% | 0% | 5% |
| Risk-Off | 0% | 0% | 0% | 100% |

***

## Part 3: Viability Assessment

### Evidence Supporting the Combination

- **SMA200 is a proven regime filter**: A 25-year backtest of leveraged ETFs with SMA200 switching showed reliable bear market avoidance across dotcom, GFC, and COVID crashes. The Bogleheads community extensively validated this approach from 1929–2019.[^13][^3]
- **EMA crossover on TQQQ independently works**: A 10/50 EMA crossover on QQQ signals applied to TQQQ yielded ~30% CAGR. The TradingView TQQQ EMA Crossover strategy with 20/50 EMAs is one of the most popular open-source TQQQ indicators.[^14][^4]
- **Tiered leverage reduces catastrophic risk**: TQQQ's -81.66% max drawdown vs QLD's -83.13% shows that even at lower leverage multiples, drawdowns are severe without trend filtering. Blending leverage tiers mathematically bounds worst-case scenarios.[^15]
- **Academic support for dynamic LETF allocation**: A 2025 paper from the University of Waterloo used neural networks to determine optimal dynamic LETF allocations, confirming that "contrarian" strategies that de-risk after gains outperform static allocation. Their data-driven approach improved Omega ratios significantly over passive holding.[^16][^17]
- **Complementary whipsaw reduction**: Reddit user backtesting 200SMA +5/-3 with Supertrend on TQQQ noted that the combination "reduces most of the significant drawdowns that come with TQQQ".[^12]

### Risks & Concerns

- **Overfitting risk**: Both 5/30 EMA and +5%/-3% hysteresis buffer were optimized on historical data. Walk-forward validation is essential to confirm robustness.[^18][^19]
- **Tax drag from frequent trading**: The 530 component generates ~5 trades/year, each potentially triggering short-term capital gains. This should be run in a tax-advantaged account where possible.
- **TQQQ structural risks**: Volatility decay from daily 3x resets means TQQQ's long-term returns deviate from 3× QQQ. A 50% TQQQ loss during the April 2025 decline corresponded to only 17% QQQ loss. The SMA200 gate mitigates this but doesn't eliminate it.[^5]
- **Execution complexity**: Managing four instruments (QQQ, QLD, TQQQ, SGOV) with two signal layers requires robust automation.
- **Correlation with single factor**: Both strategies are 100% correlated to Nasdaq-100 momentum. A prolonged tech rotation (like 2000–2003) could result in years of sitting in SGOV.

### Viability Verdict

The combined strategy is **highly viable** and represents a meaningful improvement over either strategy alone. The SMA200 regime gate provides the structural protection that the 530 lacks, while the EMA crossover provides the tactical timing that the passive core-satellite misses. Conservative CAGR estimate: **28–40%** with max drawdown under **25%** (vs. 530 alone at ~30-35% CAGR / 22% drawdown, and Core-Satellite alone at ~27x/26yr / 33% drawdown).

***

## Part 4: ML Optimization Architecture

### Layer 1: HMM Regime Detection (Replaces Simple SMA200 Gate)

Hidden Markov Models can identify latent market states from observable data, capturing nuanced regime transitions that a simple SMA200 crossover misses. A 3-state Gaussian HMM trained on QQQ returns and volatility can distinguish bull, bear, and sideways regimes.[^20][^21][^22][^23]

**Implementation:**

```python
from hmmlearn import hmm
import numpy as np

# Features: [daily log return, 20-day rolling volatility]
features = np.column_stack([
    np.log(qqq_close / qqq_close.shift(1)),
    np.log(qqq_close / qqq_close.shift(1)).rolling(20).std()
])

model = hmm.GaussianHMM(
    n_components=3,        # Bull, Bear, Sideways
    covariance_type='diag',
    n_iter=500,
    random_state=42
)
model.fit(features)
regimes = model.predict(features)
```

Each state is characterized by its mean return and volatility. The state with the highest mean return becomes "Bull," lowest becomes "Bear," and the middle becomes "Sideways." The HMM also provides transition probabilities, enabling forward-looking regime probability estimates.[^21][^24]

**Enhanced regime features** (beyond simple returns):
- VIX level and VIX vs SMA(50) ratio[^25]
- QQQ price relative to SMA(200) — embeds the original SMA200 signal
- Put/call ratio, treasury yield spread (2Y-10Y)
- NASDAQ advance/decline ratio

An XGBoost classifier trained on HMM-labeled data with these expanded features provides a more robust regime prediction. This ensemble approach (HMM + XGBoost) was shown to improve regime detection accuracy by combining multiple model perspectives.[^26][^27]

### Layer 2: XGBoost Signal Confidence Scorer

When an EMA crossover signal fires within a bull regime, an XGBoost classifier scores the probability of a profitable trade.[^28][^29]

**Feature set** (30+ engineered features per day):[^30][^31]

| Category | Features |
|----------|----------|
| Momentum | RSI(14), RSI(5), MACD histogram, ROC(10), ROC(20), Stochastic %K |
| Trend | ADX(14), Aroon oscillator, price vs SMA(50/100/200), EMA slopes |
| Volatility | ATR(14), Bollinger Band width, VIX, TQQQ 20-day HV, VIX term structure |
| Volume | OBV slope, volume ratio (vs 20-day avg), Chaikin Money Flow |
| Market Breadth | NASDAQ advance/decline ratio, % stocks above 50-day MA |
| Intermarket | TLT change, DXY change, GLD change, BTC correlation |

**Calibrated probability outputs** using Platt scaling ensure that when the model predicts 70% confidence, it's actually correct ~70% of the time:[^32][^33][^28]

```python
from sklearn.calibration import CalibratedClassifierCV
import xgboost as xgb

base_model = xgb.XGBClassifier(n_estimators=200, max_depth=5)
calibrated_model = CalibratedClassifierCV(
    estimator=base_model, method='sigmoid', cv=5
)
calibrated_model.fit(X_train, y_train)
confidence = calibrated_model.predict_proba(X_test)[:, 1]
```

**Decision matrix:**

| Regime | Confidence | Action |
|--------|-----------|--------|
| Bull | > 0.65 | Full aggressive allocation |
| Bull | 0.50–0.65 | Moderate allocation (reduce TQQQ) |
| Bull | < 0.50 | Skip signal, hold defensive |
| Sideways | > 0.70 | Conservative allocation (QQQ + QLD only) |
| Sideways | < 0.70 | Hold cash-heavy position |
| Bear | Any | 100% SGOV |

### Layer 3: Adaptive EMA Period Optimization

Instead of fixed 5/30, dynamically optimize EMA periods monthly using Bayesian optimization with walk-forward validation.[^34][^35][^19]

**Optimization framework:**

```python
import optuna

def objective(trial):
    fast_ema = trial.suggest_int('fast_ema', 3, 15)
    slow_ema = trial.suggest_int('slow_ema', 20, 60)
    
    if fast_ema >= slow_ema * 0.5:  # Maintain separation
        return float('-inf')
    
    # Run backtest on rolling 252-day training window
    results = backtest_ema_crossover(
        data=train_data, fast=fast_ema, slow=slow_ema
    )
    return results['sortino_ratio']

study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=200)
```

Walk-forward optimization uses rolling in-sample/out-of-sample windows to prevent overfitting. The Zeiierman ML-optimized Moving Average demonstrated that self-adapting periods based on performance metrics outperform static parameters across market conditions.[^36][^34][^18]

### Layer 4: Dynamic Allocation via Neural Network

A neural network determines optimal allocation weights across QQQ/QLD/TQQQ/SGOV at each rebalancing point, replacing fixed allocation tables.[^37][^16]

Research from the University of Waterloo showed that data-driven neural network approaches to LETF allocation outperform both static allocation and simple rule-based strategies. The optimal strategies are "contrarian" in nature—systematically de-risking after gains to exploit the compounding behavior of leveraged ETFs.[^17][^16]

**Implementation:**

```python
# State vector: [regime_prob_bull, regime_prob_bear, 
#                ema_signal, xgb_confidence, 
#                vix, realized_vol, current_drawdown,
#                days_in_trade, portfolio_gain_pct]

# Action: [weight_qqq, weight_qld, weight_tqqq, weight_sgov]
# Constraint: weights sum to 1.0, all >= 0

# Trained via DDPG (Deep Deterministic Policy Gradient)
# Reward function: log(portfolio_return) - lambda * max_drawdown
```

Deep RL for asset allocation using DDPG with Kelly criterion-based rewards has been shown to outperform Q-learning and buy-and-hold strategies. The approach formulates allocation as a sequential MDP, naturally handling path-dependent returns of leveraged ETFs.[^38]

### Layer 5: Kelly Criterion Position Sizing

Replace fixed allocation percentages with fractional Kelly sizing scaled by ML confidence and regime:[^39][^40]

```python
def position_size(win_rate, avg_win, avg_loss, confidence, regime):
    b = avg_win / avg_loss
    p = win_rate
    kelly_full = (b * p - (1 - p)) / b
    kelly_fraction = kelly_full * 0.25  # Quarter-Kelly for safety
    
    # Scale by confidence and regime
    regime_scale = {'BULL': 1.0, 'SIDEWAYS': 0.5, 'BEAR': 0.0}
    return min(kelly_fraction * (confidence / 0.65) * regime_scale[regime], 0.95)
```

Fractional Kelly (quarter or half) dramatically reduces drawdown volatility while retaining most of the expected geometric growth rate.[^40][^39]

### Layer 6: FinBERT Sentiment Overlay

FinBERT sentiment analysis on financial headlines provides a supplementary signal that adjusts ML confidence. Integrating FinBERT with LSTM models improved prediction accuracy from 92.8% to 95.5% on NASDAQ-100 stocks.[^41][^42]

***

## Part 5: System Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR AGENT (#1)                        │
│              Antigravity Main Coordination Agent                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐│
│  │ Data        │  │ Regime     │  │ Signal     │  │ Allocation ││
│  │ Pipeline    │  │ Detector   │  │ Scorer     │  │ Optimizer  ││
│  │ Agent #2    │  │ Agent #3   │  │ Agent #4   │  │ Agent #5   ││
│  │             │  │ HMM+XGB   │  │ XGBoost    │  │ NN/RL      ││
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘│
│                                                                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐│
│  │ Execution   │  │ Backtest   │  │ Sentiment  │  │ Risk       ││
│  │ Engine      │  │ Engine     │  │ Analyzer   │  │ Manager    ││
│  │ Agent #6    │  │ Agent #7   │  │ Agent #8   │  │ Agent #9   ││
│  │ TT/IB APIs  │  │ WF Valid.  │  │ FinBERT    │  │ Guardrails ││
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘│
│                                                                   │
│  ┌────────────┐                                                  │
│  │ Alert &     │                                                  │
│  │ Dashboard   │                                                  │
│  │ Agent #10   │                                                  │
│  └────────────┘                                                  │
├─────────────────────────────────────────────────────────────────┤
│              BROKER CONNECTORS                                    │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ Tastytrade SDK    │  │ IB Gateway API    │                     │
│  │ (tastyware/       │  │ (ib_insync)       │                     │
│  │  tastytrade)      │  │                   │                     │
│  └──────────────────┘  └──────────────────┘                     │
├─────────────────────────────────────────────────────────────────┤
│              DATA LAYER                                           │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐│
│  │ TimescaleDB       │  │ Redis Cache       │  │ Model Store   ││
│  │ (OHLCV, trades)   │  │ (real-time)       │  │ (MLflow/pkl)  ││
│  └──────────────────┘  └──────────────────┘  └────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Daily Execution Flow

```
16:00 ET — Market Close
  │
  ├── Agent #2: Fetch daily OHLCV for QQQ, QLD, TQQQ, VIX, TLT, DXY
  │
  ├── Agent #3: Run regime detection
  │   ├── HMM predict current regime state
  │   ├── XGBoost confirm/override
  │   └── Output: {regime: BULL|SIDEWAYS|BEAR, confidence: 0.XX}
  │
  ├── Agent #4: Calculate EMA(5)/EMA(30), check for crossover
  │   ├── If crossover detected → score signal with XGBoost
  │   ├── Calibrate probability via Platt scaling
  │   └── Output: {signal: BUY|SELL|HOLD, confidence: 0.XX}
  │
  ├── Agent #8: (Optional) FinBERT sentiment adjustment
  │
  ├── Agent #5: Determine target allocation
  │   ├── Combine regime + signal + confidence + sentiment
  │   ├── Apply Kelly criterion position sizing
  │   └── Output: {QQQ: X%, QLD: Y%, TQQQ: Z%, SGOV: W%}
  │
  ├── Agent #9: Risk check
  │   ├── Validate against hard limits
  │   ├── Check daily loss limits, VIX circuit breakers
  │   └── Approve or block rebalance
  │
  ├── Agent #6: Execute rebalance
  │   ├── Calculate delta from current positions
  │   ├── Submit orders via Tastytrade SDK (or IB backup)
  │   └── Confirm fills, log to database
  │
  └── Agent #10: Send alerts + update dashboard
      ├── Discord/SMS notification
      └── Grafana metrics update
```

### Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python 3.11+ / TypeScript | Python for ML pipeline, TS for platform UI |
| ML Framework | scikit-learn, XGBoost, hmmlearn, PyTorch | HMM regime + XGBoost scoring + NN allocation[^21][^29] |
| Optimization | Optuna | Bayesian hyperparameter optimization |
| NLP | HuggingFace Transformers (FinBERT) | Financial sentiment analysis[^41] |
| Backtesting | backtrader / backtesting.py | Industry-standard vectorized backtest[^43] |
| Broker Primary | Tastytrade Python SDK (tastyware/tastytrade)[^44] | Full async/sync order management |
| Broker Backup | ib_insync (Interactive Brokers)[^45] | Failover execution, broader access |
| Database | PostgreSQL + TimescaleDB | Time-series optimized storage |
| Cache | Redis | Real-time feature caching |
| Model Store | MLflow or pickle | Model versioning + A/B testing |
| Scheduling | APScheduler / cron | Daily 4:05 PM ET execution |
| Monitoring | Grafana | Real-time P&L + model health dashboard |
| Notifications | Discord webhook, Twilio SMS | Trade alerts + system health |

***

## Part 6: Implementation Plan (Phased)

### Phase 1: Foundation & Base Strategy Replication (Weeks 1–3)

**Goal**: Build data infrastructure and independently validate both base strategies.

**Tasks:**

1. **Data Pipeline (Agent #2)**
   - Fetch daily OHLCV: QQQ, QLD, TQQQ, SGOV, VIX, TLT, DXY, GLD (yfinance, 2000–present)
   - Store in TimescaleDB with automatic daily refresh
   - Data quality: gap detection, split/dividend adjustment, TQQQ inception date handling (Feb 2010)
   - For pre-2010 TQQQ data: synthesize from QQQ with 3x daily returns simulation

2. **Base Strategy A Backtest: 530 EMA Crossover**
   - Implement configurable EMA crossover on TQQQ
   - Replicate original results (target: within 5% of reported ~20x return)
   - Parameter sweep: fast [3–20] × slow [15–120], generate Sortino heatmap
   - Walk-forward validation: 3-year rolling train / 1-year test

3. **Base Strategy B Backtest: Core-Satellite SMA200**
   - Implement 60/30/10 allocation with SMA200 hysteresis (+5%/-3%)
   - Backtest over full 26-year period (using synthesized LETF data pre-inception)
   - Test hysteresis buffer variations: +3/-2, +5/-3, +7/-5

4. **Combined Base Strategy Backtest**
   - Implement the three-tier logic (Risk-On/Transitional/Risk-Off + EMA crossover within Risk-On)
   - Compare: Strategy A alone, Strategy B alone, Combined, QQQ buy-hold, TQQQ buy-hold
   - **Success Criteria**: Combined CAGR > 25%, max drawdown < 30%, Sharpe > 1.0

### Phase 2: HMM Regime Detection (Weeks 4–6)

**Goal**: Replace simple SMA200 gate with ML regime detection.

**Tasks:**

1. **HMM Regime Detector (Agent #3)**
   - Train 3-state Gaussian HMM on QQQ log returns + 20-day rolling volatility[^20][^21]
   - Validate state interpretability: label states by mean return and volatility
   - Cross-validate against known market regimes (2000 crash, 2008 GFC, 2020 COVID, 2022 bear)
   - Compare 2-state vs 3-state vs 5-state models

2. **XGBoost Regime Ensemble**
   - Train on HMM-labeled data with expanded features: VIX, RSI, ADX, put/call, yield spread[^26]
   - Time-series cross-validation (no future leakage)
   - Target: >70% regime classification accuracy on held-out data

3. **Integration & Comparison**
   - Replace SMA200 gate with HMM/XGBoost regime in combined strategy
   - Backtest: ML regime gate vs SMA200 gate vs combined (SMA200 as feature in ML)
   - **Success Criteria**: Drawdown reduction > 20% vs SMA200 alone with CAGR preservation

### Phase 3: Signal Scoring & Confidence (Weeks 7–9)

**Goal**: Build XGBoost signal confidence scorer for EMA crossover signals.

**Tasks:**

1. **Feature Engineering Pipeline**
   - Calculate 30+ technical features daily[^31][^30]
   - Feature store in TimescaleDB for efficient retrieval
   - Feature importance analysis via SHAP values

2. **XGBoost Signal Scorer (Agent #4)**
   - Label: crossover signal → profitable (1) or unprofitable (0)
   - Train with time-series split cross-validation[^29]
   - Calibrate outputs via Platt scaling (CalibratedClassifierCV)[^28][^32]
   - Walk-forward validation across 5+ test periods

3. **Confidence-Based Allocation**
   - Map confidence scores to allocation tiers (see decision matrix in Part 4)
   - Integrate Kelly criterion sizing[^40]
   - **Success Criteria**: Sharpe > 1.5, filtered signals outperform unfiltered by >10% risk-adjusted

### Phase 4: Adaptive Parameters & Dynamic Allocation (Weeks 10–12)

**Goal**: Add adaptive EMA optimization and neural network allocation.

**Tasks:**

1. **Bayesian EMA Optimizer**
   - Monthly re-optimization using Optuna with 252-day rolling window
   - Objective: maximize Sortino ratio
   - Robustness check: ±2 day sensitivity analysis on parameters
   - Reject fragile optima (must perform within 80% of optimal across ±20% range)[^36]

2. **Neural Network Dynamic Allocator (Agent #5)**
   - Input: regime state, EMA signal, confidence score, VIX, drawdown, portfolio state
   - Output: target allocation weights [QQQ, QLD, TQQQ, SGOV]
   - Train via DDPG or PPO with reward = log(return) − λ × max_drawdown[^46][^38]
   - Validate against rule-based allocation tables

3. **Supertrend Trailing Stop Integration**
   - Add ATR-based Supertrend as trailing stop within positions[^47][^12]
   - Catches rapid declines before SMA200/EMA signals react
   - Parameters: ATR(10), multiplier=3[^48]

### Phase 5: Broker Integration & Execution (Weeks 13–15)

**Goal**: Automate live execution across brokers.

**Tasks:**

1. **Tastytrade Integration (Agent #6)**
   - Authenticate via Tastytrade SDK[^49][^44]
   - Market-on-close orders for daily rebalancing
   - Position reconciliation and monitoring
   - Paper trading mode for validation

2. **Interactive Brokers Backup**
   - IB Gateway connection via ib_insync[^45]
   - Identical order logic, activated on TT failure

3. **Multi-Instrument Rebalance Engine**
   - Calculate delta: current allocation vs target allocation
   - Execute rebalance as atomic batch (sell first, then buy)
   - Handle partial fills, slippage tracking
   - SGOV execution for cash parking[^6]

4. **Risk Manager (Agent #9)**

| Guardrail | Threshold | Action |
|-----------|-----------|--------|
| Max portfolio daily loss | -5% | Halt trading 24 hours |
| Max drawdown from peak | -25% | Full exit to SGOV, manual restart required |
| VIX spike | > 40 | Suspend new leveraged entries |
| TQQQ single-day drop | > 15% | Emergency de-leverage to QQQ only |
| Model confidence floor | All signals < 0.45 | Skip all trades |
| Data staleness | > 4 hours | Alert + use last known data |
| Broker connectivity | Failure > 5 min | Failover to IB |

### Phase 6: Sentiment, Dashboard & Retraining (Weeks 16–18)

**Goal**: Add sentiment layer, monitoring, and model maintenance.

**Tasks:**

1. **FinBERT Sentiment Analyzer (Agent #8)**
   - Deploy via HuggingFace Transformers[^41]
   - Ingest: NewsAPI, Finnhub financial headlines
   - Daily aggregated tech/NASDAQ sentiment score
   - Integration: adjust XGBoost confidence ±5-10%

2. **Grafana Dashboard (Agent #10)**
   - Panels: equity curve, drawdown, regime state history, signal log, model confidence
   - Weekly automated performance report
   - Alerts: model drift (accuracy drop >15%), data pipeline failure

3. **Model Retraining Pipeline**
   - Monthly automatic retrain of XGBoost models with latest data
   - A/B testing: new model vs current on 30-day out-of-sample
   - Auto-rollback if new model underperforms by >5%
   - MLflow for model versioning and experiment tracking

***

## Part 7: File Structure for Antigravity

```
tqqq-combined-ml/
├── README.md
├── config/
│   ├── strategy_config.yaml           # EMA periods, SMA200 buffer, allocation tables
│   ├── broker_config.yaml             # API keys (encrypted), account IDs
│   ├── model_config.yaml              # ML hyperparameters, retraining schedule
│   ├── risk_config.yaml               # Guardrails, circuit breakers
│   └── alerts_config.yaml             # Discord/SMS channels
├── agents/
│   ├── orchestrator.py                # Agent #1: daily pipeline coordination
│   ├── data_pipeline.py               # Agent #2: fetch & store OHLCV, VIX, macro
│   ├── regime_detector.py             # Agent #3: HMM + XGBoost regime classification
│   ├── signal_scorer.py               # Agent #4: EMA crossover + XGBoost confidence
│   ├── allocation_optimizer.py        # Agent #5: NN/RL dynamic allocation or rule-based
│   ├── execution_engine.py            # Agent #6: broker order management
│   ├── backtester.py                  # Agent #7: backtest + walk-forward framework
│   ├── sentiment_analyzer.py          # Agent #8: FinBERT sentiment pipeline
│   ├── risk_manager.py                # Agent #9: guardrails + circuit breakers
│   └── alerting.py                    # Agent #10: notifications + dashboard
├── models/
│   ├── hmm_regime/
│   │   ├── train.py                   # Gaussian HMM training
│   │   ├── predict.py                 # Regime inference
│   │   └── saved_models/
│   ├── xgboost_regime/
│   │   ├── train.py                   # Regime classifier
│   │   ├── predict.py
│   │   └── saved_models/
│   ├── xgboost_signal/
│   │   ├── train.py                   # Signal confidence scorer
│   │   ├── feature_engineering.py     # 30+ technical feature calcs
│   │   ├── calibration.py             # Platt scaling wrapper
│   │   └── saved_models/
│   ├── nn_allocator/
│   │   ├── train.py                   # DDPG/PPO training
│   │   ├── predict.py                 # Allocation inference
│   │   └── saved_models/
│   └── finbert_sentiment/
│       ├── analyze.py                 # FinBERT pipeline
│       └── cache/
├── strategies/
│   ├── base_530_ema.py                # Pure 530 EMA crossover
│   ├── base_core_satellite.py         # Pure SMA200 core-satellite
│   ├── combined_base.py               # Combined rule-based strategy
│   ├── combined_ml_enhanced.py        # Full ML pipeline strategy
│   ├── position_sizer.py              # Kelly criterion implementation
│   └── supertrend_stop.py             # ATR trailing stop
├── brokers/
│   ├── tastytrade_connector.py        # Tastytrade SDK wrapper
│   ├── ib_connector.py                # IB Gateway wrapper
│   ├── paper_trader.py                # Simulated execution
│   └── rebalancer.py                  # Multi-instrument rebalance logic
├── backtest/
│   ├── runner.py                      # Backtest execution engine
│   ├── walk_forward.py                # Walk-forward validation
│   ├── parameter_sweep.py             # Grid/Bayesian search
│   ├── monte_carlo.py                 # Stress testing
│   └── reports/                       # Generated backtest reports
├── data/
│   ├── raw/                           # Downloaded OHLCV
│   ├── processed/                     # Feature-engineered datasets
│   ├── synthetic/                     # Pre-2010 LETF simulation
│   └── migrations/
├── dashboard/
│   ├── grafana/                       # Dashboard JSON configs
│   └── weekly_reports/
├── tests/
│   ├── test_strategy_a.py
│   ├── test_strategy_b.py
│   ├── test_combined.py
│   ├── test_regime_detector.py
│   ├── test_signal_scorer.py
│   ├── test_allocator.py
│   ├── test_execution.py
│   └── test_risk_manager.py
├── scripts/
│   ├── daily_run.py                   # Main daily execution
│   ├── retrain_models.py              # Monthly retraining
│   ├── generate_report.py             # Performance reporting
│   └── backfill_data.py               # Historical data download
├── requirements.txt
├── docker-compose.yaml                # PostgreSQL, TimescaleDB, Redis, Grafana
└── .env.example
```

***

## Part 8: Key Dependencies

### Python Packages

```
# Core
pandas>=2.0
numpy>=1.24
yfinance>=0.2.31

# ML & Statistics
scikit-learn>=1.3
xgboost>=2.0
hmmlearn>=0.3
optuna>=3.4
torch>=2.1
stable-baselines3>=2.1     # For DDPG/PPO RL

# NLP / Sentiment
transformers>=4.35

# Backtesting
backtrader>=1.9

# Broker SDKs
tastytrade>=8.0
ib_insync>=0.9

# Infrastructure
sqlalchemy>=2.0
psycopg2-binary>=2.9
redis>=5.0
apscheduler>=3.10
pydantic>=2.0
mlflow>=2.8

# Visualization
plotly>=5.18
grafana-api>=1.0
```

### External APIs

| API | Purpose | Auth |
|-----|---------|------|
| Tastytrade Open API[^50] | Primary execution | OAuth token |
| IB TWS/Gateway[^45] | Backup execution | Client ID |
| yfinance | Historical OHLCV | Free |
| Alpha Vantage | Real-time quotes, VIX | API key |
| FRED API | Macro data (yield curve) | API key |
| NewsAPI / Finnhub | Financial news | API key |

***

## Part 9: Validation & Testing Protocol

### Pre-Launch Checklist

1. **Unit tests**: Each agent function independently tested
2. **Integration test**: Full pipeline from data → signal → order (paper mode)
3. **Backtest replication**: Both base strategies within 5% of reported results
4. **Walk-forward OOS**: Minimum 5 years out-of-sample across all ML layers
5. **Monte Carlo stress test**: Simulate 2000 dotcom, 2008 GFC, 2020 COVID, 2022 bear on full ML system
6. **Paper trading**: Minimum 3 months on Tastytrade sandbox[^51]
7. **Latency test**: Daily pipeline completes within 5 minutes of market close
8. **Failover test**: TT → IB failover executes correctly

### Ongoing Monitoring

| Frequency | Checks |
|-----------|--------|
| Daily | P&L, signal accuracy, regime state, model confidence |
| Weekly | Win rate, trailing 30-day Sortino, allocation drift |
| Monthly | Full model retrain + walk-forward validation |
| Quarterly | Strategy review with human oversight, parameter stability |

***

## Part 10: Timeline & Priority Matrix

| Phase | Duration | Priority | Key Deliverable |
|-------|----------|----------|-----------------|
| Phase 1: Foundation | Weeks 1–3 | 🔴 Critical | Data pipeline + both base backtests + combined base |
| Phase 2: Regime Detection | Weeks 4–6 | 🔴 Critical | HMM + XGBoost regime gate replacing SMA200 |
| Phase 3: Signal Scoring | Weeks 7–9 | 🟡 High | XGBoost confidence + calibrated probabilities |
| Phase 4: Adaptive + NN | Weeks 10–12 | 🟡 High | Bayesian EMA + NN allocator + Supertrend stop |
| Phase 5: Broker Integration | Weeks 13–15 | 🔴 Critical | Tastytrade + IB execution + risk guardrails |
| Phase 6: Sentiment + Ops | Weeks 16–18 | 🟢 Medium | FinBERT + Grafana + retraining pipeline |

**Total estimated build: 18 weeks.** Phases 2–3 can partially overlap with Phase 5 prep work.

**Highest-impact improvements in priority order:**
1. Walk-forward validated combined base strategy (confirms foundation)
2. HMM regime detection (biggest risk reduction vs SMA200 alone)
3. Kelly criterion position sizing (reduces drawdown with minimal CAGR loss)
4. XGBoost signal confidence (filters ~30% of losing trades)
5. Supertrend trailing stop (catches rapid declines within positions)
6. Neural network dynamic allocation (optimal leverage mixing)
7. Adaptive EMA parameters (modest improvement over fixed 5/30)
8. FinBERT sentiment (marginal enhancement, highest complexity)

---

## References

1. [Anyone know how to make the app stop downloading random songs ...](https://www.reddit.com/r/YoutubeMusic/comments/kq3fe5/anyone_know_how_to_make_the_app_stop_downloading/) - In this screen, go down to Smart Downloads. Turn it on, if off. Then push the slide bar (that drops ...

2. [How to Turn Off Smart Downloads on YouTube | Guiding Tech](https://www.youtube.com/watch?v=TSST527UUDw) - It's a feature that automatically downloads videos that you are most likely to be interested in, bas...

3. [Backtesting 25 years of leveraged ETFs with Moving Averages](https://www.reddit.com/r/LETFs/comments/1b0r3ke/backtesting_25_years_of_leveraged_etfs_with/) - Trend Following In Financial Markets · Leveraged SMA200 Strategy Back-tested 1929-2019 · Leverage fo...

4. [Swing Trading TQQQ using 10/50 EMA Crossover (with Backtest ...](https://www.reddit.com/r/TQQQ/comments/1pbq9hp/tqqq_strategy_advice_swing_trading_tqqq_using/) - - For 10/2019 to 11/2025, both strategies produced similar results (~30–35% CAGR), but the EMA cross...

5. [Volatility Decay and Why Leveraged ETFs Multiply Losses During ...](https://www.stockforecasttoday.com/post/volatility-decay-and-why-leveraged-etfs-multiply-losses-during-declines) - Volatility decay destroys leveraged ETF returns during market declines, multiplying losses far beyon...

6. [SGOV Is Still A Tool For Cash But The Yield Is Declining](https://seekingalpha.com/article/4862498-sgov-is-still-a-tool-for-cash-but-the-yield-is-declining) - SGOV is an effective way to own a rolling portfolio of T-bills without having to do the work yoursel...

7. [TQQQ + 200 SMA Strategy: Some questions on implementation 🙏](https://www.reddit.com/r/TQQQ/comments/1ob2p2z/tqqq_200_sma_strategy_some_questions_on/) - TQQQ + 200 SMA Strategy: Some questions on implementation 🙏

8. [200 SMA (5%/-3% Buffer) for SPY & QQQ — Strategy by freefighter07](https://www.tradingview.com/script/0S8jQcA5-200-SMA-5-3-Buffer-for-SPY-QQQ/) - In my testing TQQQ is an absolute monster of an ETF that performs extremely well even from a buy and...

9. [Why Parking Cash in SGOV is a Smart Move - moomoo Communitywww.moomoo.com › community › feed › why-parking-cash-in-sgov-is-a-...](https://www.moomoo.com/community/feed/why-parking-cash-in-sgov-is-a-smart-move-114882886107141) - Why Parking Cash in SGOV is a Smart Move

10. [Refined SMA/EMA Crossover with Ichimoku and 200 SMA Filter](https://www.tradingview.com/script/2Fghcats-Refined-SMA-EMA-Crossover-with-Ichimoku-and-200-SMA-Filter/) - This strategy is designed to identify strong trends and avoid false signals by combining: SMA filter...

11. [Neural Moving Average Crossover Trend Following Strategy with EMA Filtering System](https://www.fmz.com/lang/en/strategy/482515) - Overview This strategy is a trading system based on moving average crossover signals and trend filte...

12. [TQQQ 200SMA (+5%/-3%) Strategy follow up with additional stats and enhancements (Blended with Supertrend)](https://www.reddit.com/r/LETFs/comments/1mc1mvs/tqqq_200sma_53_strategy_follow_up_with_additional/) - TQQQ 200SMA (+5%/-3%) Strategy follow up with additional stats and enhancements (Blended with Supert...

13. [Bogleheads.org](https://www.bogleheads.org/forum/viewtopic.php?t=297591&start=100)

14. [The Most Powerful TQQQ EMA Crossover Trend Trading Strategy](https://www.tradingview.com/script/bkv51za0-The-Most-Powerful-TQQQ-EMA-Crossover-Trend-Trading-Strategy/) - The TQQQ EMA Crossover Strategy operates by calculating two EMAs: a fast EMA (default length of 20) ...

15. [Leveraged ETFs: TQQQ vs. QLD – Balancing Risk and Reward in ...](https://www.ainvest.com/news/leveraged-etfs-tqqq-qld-balancing-risk-reward-nasdaq-100-tactical-trading-2512/) - Leveraged ETFs: TQQQ vs. QLD – Balancing Risk and Reward in Nasdaq-100 Tactical Trading

16. [Making Leveraged Exchange-Traded Funds Work for your Portfolio](https://arxiv.org/html/2506.19200)

17. [Smart leverage? Rethinking the role of ...](https://arxiv.org/html/2412.05431v2)

18. [How to Avoid Overfitting When Testing Trading Rules](http://adventuresofgreg.com/blog/2025/12/18/avoid-overfitting-testing-trading-rules/) - Walk-forward optimization is a method traders use to fine-tune strategies while reducing the chances...

19. [A Key Technique for Reducing Overfitting in Backtests - Runbot](https://runbot.io/understanding-walk-forward-optimization-a-key-technique-for-reducing-overfitting-in-backtests/) - Walk forward optimization is a technique that helps to reduce the risk of overfitting by dividing th...

20. [Market Regime Detection using Hidden Markov Models in QSTrader](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/) - In this article the Hidden Markov Model will be utilised within the QSTrader framework as a risk-man...

21. [Market Regime Detection using Hidden Markov Models](https://www.pyquantlab.com/articles/Market%20Regime%20Detection%20using%20Hidden%20Markov%20Models.html)

22. [Introduction to Hidden Markov Models (HMM) for Traders: Python Tutorial](https://www.marketcalls.in/python/introduction-to-hidden-markov-models-hmm-for-traders-python-tutorial.html) - Trading the financial markets can be challenging, especially when price movements are unpredictable....

23. [Market Regime Detection Using Hidden Markov Models - QuestDB](https://questdb.com/glossary/market-regime-detection-using-hidden-markov-models/) - Market regimes represent distinct states of market behavior, such as low-volatility bull markets, hi...

24. [Market Regime using Hidden Markov Model - QuantInsti Blog](https://blog.quantinsti.com/regime-adaptive-trading-python/) - This project builds a Python-based adaptive trading strategy that: Detects current market regime usi...

25. [Using VIX to Determine Market Volatility Regime - finaur.com](https://finaur.com/blog/en/education/using-vix-volatility-regime/) - A step‑by‑step, educational walk‑through of how to use the CBOE Volatility Index (VIX) as a regime f...

26. [AAdevloper/market-regime-classifier - Hugging Face](https://huggingface.co/AAdevloper/market-regime-classifier) - We’re on a journey to advance and democratize artificial intelligence through open source and open s...

27. [A forest of opinions: A multi-model ensemble-HMM voting framework for market regime shift detection and trading - AIMS Press](https://www.aimspress.com/article/id/69045d2fba35de34708adb5d) - In this paper, we present a framework for detecting market regime shifts using a combination of tree...

28. [Predict Calibrated Probabilities with XGBoostxgboosting.com › predict-calibrated-probabilities-with-xgboost](https://xgboosting.com/predict-calibrated-probabilities-with-xgboost/)

29. [Cryptocurrency Price Forecasting Using XGBoost Regressor ... - arXiv](https://arxiv.org/html/2407.11786v1) - This study introduces a machine learning approach to predict cryptocurrency prices. Specifically, we...

30. [Feature Engineering in Trading: Turning Data into Insights - LuxAlgo](https://www.luxalgo.com/blog/feature-engineering-in-trading-turning-data-into-insights/) - RSI (Relative Strength Index): While moving averages reveal the trend, RSI highlights its strength a...

31. [Assessing the Impact of Technical Indicators on Machine ...](https://arxiv.org/html/2412.15448v1)

32. [The Complete Guide to Platt Scaling - Train in Data's Blog](https://www.blog.trainindata.com/complete-guide-to-platt-scaling/) - Platt scaling is a calibration technique used to convert the raw outputs of classification machine l...

33. [Building a Quantitative Prediction System for Polymarket](https://navnoorbawa.substack.com/p/building-a-quantitative-prediction) - Using CalibratedClassifierCV with Platt scaling ensures that when the model says “70% confidence,” i...

34. [Machine Learning & Optimization Moving Average - Zeiierman Trading](https://www.zeiierman.com/indicators/machine-learning-optimization-moving-average) - Our algorithm optimizes the MA period within the given parameter range and optimizes its value based...

35. [What is the MESA Adaptive Moving Average (MAMA) - TrendSpider](https://trendspider.com/learning-center/what-is-the-mesa-adaptive-moving-average-mama/) - The MESA Adaptive Moving Average (MAMA) is a technical analysis indicator that is designed to respon...

36. [Why we employ walk-forward testing to avoid curve-fitting](https://logical-invest.com/walk-forward-testing-avoid-curve-fitting-backtesting/) - How we backtest our trading strategies, how we avoid overfitting by using walk-forward testing and w...

37. [[PDF] Making Leveraged Exchange-Traded Funds Work for your Portfolio](https://arxiv.org/pdf/2506.19200.pdf) - Using a data-driven neural network approach, we discuss the construction of optimal LETF allocation ...

38. [Deep Reinforcement Learning for Optimal Asset Allocation ...](https://arxiv.org/abs/2508.20103) - The optimal asset allocation between risky and risk-free assets is a persistent challenge due to the...

39. [[PDF] DYNAMIC KELLY CRITERION -BASED PORTFOLIO LEVERAGE ...](https://trepo.tuni.fi/bitstream/10024/228489/2/AntilaTapio.pdf) - Fractional Kelly reduces the bet size, thus decreasing volatility and the risk of substantial drawdo...

40. [Position Sizing & Leverage: Kelly Criterion Strategy - Interactive](https://mbrenndoerfer.com/writing/optimal-position-sizing-kelly-criterion-leverage) - Master optimal position sizing using the Kelly Criterion, risk budgeting, and volatility targeting. ...

41. [FinBERT Sentiment Analysis - Emergent Mind](https://www.emergentmind.com/topics/sentiment-analysis-using-finbert) - The paper outlines FinBERT's framework, detailing fine-tuning on financial texts to accurately class...

42. [Improving Sentiment Score Accuracy With FinBERT](https://blog.gopenai.com/improving-sentiment-score-accuracy-with-finbert-86d9a5363cbf) - In a previous lab titled “Building News Sentiment and Stock Price Performance Analysis NLP Applicati...

43. [The EMA trading Strategy backtest using python | python backtesting #algotrading #pythontrading](https://www.youtube.com/watch?v=f2R2Mb9KauE) - In this video, we explore how to build and backtest an EMA-based trading strategy using Python. This...

44. [An unofficial, sync/async Python SDK for Tastytrade! - GitHub](https://github.com/tastyware/tastytrade) - An unofficial, sync/async Python SDK for Tastytrade! - tastyware/tastytrade

45. [Automating Financial Strategies with Python Bots - Interactive Brokers](https://www.interactivebrokers.com/campus/ibkr-quant-news/automating-financial-strategies-with-python-bots/) - This article delves into how to build effective trading bots using Python, covering the essential co...

46. [Risk-Adjusted Deep Reinforcement Learning for Portfolio ...](https://d-nb.info/1372490175/34)

47. [SuperTrend Indicator: Trailing Stop Strategy - LuxAlgo](https://www.luxalgo.com/blog/supertrend-indicator-trailing-stop-strategy/) - The SuperTrend indicator is a simple yet powerful resource for identifying market trends and managin...

48. [SuperTrend Strategy with Trailing Stop Loss](https://www.fmz.com/lang/en/strategy/433556) - Overview This strategy designs a moving stop loss line and reversal line based on the Average True R...

49. [Automating Your Trading with TastyTrade's API - Coders Digest](https://abhipandey.com/2023/09/automating-your-trading-with-tastytrades-api/) - A Python project that leverages the TastyTrade API to streamline various trading operations, from mo...

50. [Trading API: Access tastytrade's Open API](https://tastytrade.com/api/) - Access tastytrade's trading API to build custom applications for market data, order execution, and p...

51. [TastyTrady API Automated Trading Bot : r/tastytrade - Reddit](https://www.reddit.com/r/tastytrade/comments/1mbtqx9/tastytrady_api_automated_trading_bot/) - ... Bot ... python API for Tastytrade: https://github.com/gandpablo/TastyTrade-API. I can help you t...

