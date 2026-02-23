# Implementation Plan Review & AI-Optimized Option Selection, Entry/Exit Timing

## 1. Implementation Plan Review: What's Strong

Your plan is well-architected and production-ready. The strengths include:

- **Consistent project structure**: Placing the strategy in `src/tqqq/` following the existing `src/pmcc/`, `src/csp/`, `src/zebra/` pattern ensures plug-and-play extensibility.
- **Clean separation of concerns**: ML models isolated in `src/tqqq/ml/`, execution in `order_manager.py`, risk in `tqqq_risk_manager.py`, and signals in `signal_publisher/tqqq.py`.
- **Shared config**: Appending TQQQ settings to the existing `config.py` rather than creating a separate config file maintains a single source of truth.
- **State machine design**: The 4-state model (IDLE → FULL_SPREAD → LONG_PUT_ONLY → IDLE) clearly captures all possible position transitions.
- **Scheduler timeline**: The 08:00/09:45/12:00/15:45/16:15 check schedule covers the critical trading windows.

***

## 2. Seven Improvements to the Current Plan

### Improvement 1: Add a Bayesian Optimization Auto-Tuner

**Problem:** The plan hardcodes strategy parameters (DTE 21–45, delta -0.30, spread width $5, profit target 50%, etc.) in `config.py`. These values are reasonable starting points but are not optimized for TQQQ's specific behavior across different market regimes.

**Solution:** Add a Bayesian Optimization (BO) module that automatically tunes these parameters using Gaussian Process surrogate models.[^1][^2][^3]

```
[NEW] src/tqqq/ml/param_optimizer.py

Class: StrategyParamOptimizer
  Uses: scikit-optimize (gp_minimize) with Gaussian Process surrogate
  
  Parameters to optimize (search space):
    - target_dte: Integer(14, 60)
    - short_put_delta: Real(-0.40, -0.15)
    - spread_width: Integer(2, 10)
    - profit_target: Real(0.30, 0.80)
    - loss_limit_mult: Real(1.0, 3.0)
    - legout_short_threshold: Real(0.05, 0.30)
    - long_put_profit_target: Real(1.5, 4.0)
    - min_entry_confidence: Real(0.50, 0.80)

  Objective function: Sharpe ratio from walk-forward backtest
  
  Method:
    1. Define search space with trading-logic bounds
    2. Run gp_minimize with n_calls=50-100
    3. Walk-forward cross-validation (train 2 years, test 6 months, roll)
    4. Return optimal parameter set per regime
    5. Store regime-specific configs (LOW_VOL params, HIGH_VOL params, etc.)

  Schedule: Run monthly on weekends with latest data
```

This is significantly better than manual parameter selection because BO efficiently explores high-dimensional spaces that would require millions of combinations via grid search, and it inherently balances exploration of unknown regions with exploitation of promising regions. Research shows BO consistently outperforms grid search and random search for trading strategy parameter optimization, especially when the objective function (backtest Sharpe) is expensive to evaluate.[^2][^3]

**Key insight: Regime-specific parameters.** The optimizer should produce *different* optimal parameters for each VIX regime. For example, in HIGH_VOL regimes, wider spreads and shorter DTE may be optimal, while in NORMAL regimes, tighter spreads with longer DTE might perform better. This means `config.py` should support:

```python
TQQQ_PARAMS_BY_REGIME = {
    "LOW_VOL": {"dte": 35, "delta": -0.25, "width": 3, "profit_target": 0.60},
    "NORMAL":  {"dte": 30, "delta": -0.30, "width": 5, "profit_target": 0.50},
    "HIGH_VOL":{"dte": 21, "delta": -0.35, "width": 5, "profit_target": 0.40},
    "CRISIS":  {"dte": 14, "delta": -0.20, "width": 3, "profit_target": 0.75},
}
```

### Improvement 2: Replace Static Contract Ranker with Contextual Bandit

**Problem:** The current plan uses an XGBoost/Random Forest ranker in `contract_ranker.py` trained on historical P/L labels. This is a supervised approach that doesn't handle the exploration–exploitation tradeoff inherent in contract selection: you need to sometimes try less-popular strikes/expiries to discover if they're actually better.

**Solution:** Replace or augment with a **Contextual Bandit** using Thompson Sampling.[^4][^5][^6]

```
[MODIFY] src/tqqq/ml/contract_ranker.py

Class: ContextualBanditContractSelector
  Algorithm: Thompson Sampling with Bayesian Linear Regression
  
  Context vector (per decision point):
    - VIX regime state (one-hot: LOW/NORMAL/HIGH/CRISIS)
    - VIX level, VIX percentile rank
    - TQQQ price, RSI, distance from 20-day MA
    - Time of day (one-hot: morning/midday/afternoon)
    - Spread metrics: credit/width ratio, net theta, net vega
    - Liquidity score (from existing liquidity filter)
  
  Arms (candidate contracts):
    - Each passing-liquidity strike/expiry combo is an "arm"
    - Typically 5-15 candidates after filtering
  
  Reward signal:
    - Realized P/L per unit of risk after standard exit rules
    - Updated after each trade closes
    - Delayed reward: stored and applied when position resolves
  
  Exploration/Exploitation:
    - Thompson Sampling: sample from posterior distribution of each arm's reward
    - Early phase (first 100 trades): higher exploration (wider posterior)
    - Mature phase: posterior tightens, naturally exploits best arms
    
  Fallback: If bandit has < 20 observations, fall back to XGBoost ranker
```

Research on risk-averse contextual bandits for option hedging shows this approach outperforms Deep Q-Learning in terms of sample efficiency and hedging error. The bandit naturally handles the non-stationary nature of options markets: as the posterior updates with each trade, it adapts to changing market conditions without explicit retraining.[^5]

### Improvement 3: Add Intraday Entry/Exit Timing Engine

**Problem:** The current plan checks signals at fixed times (09:45, 12:00, 15:45) but doesn't optimize *within* those windows for the best execution moment. Research shows significant intraday patterns in options pricing and execution quality.[^7][^8][^9]

**Solution:** Add a dedicated timing module that learns the optimal time-of-day for entries and exits.

```
[NEW] src/tqqq/ml/timing_engine.py

Class: IntradayTimingEngine

  Research-backed baseline rules:
    - AVOID first 30 minutes (9:30-10:00): widest bid-ask spreads,
      highest volatility, worst execution quality
    - PREFER 10:30-11:00 for ENTRIES: post-morning volatility settles,
      spreads tighten, volume still high
    - PREFER 3:00-3:30 for EXITS: stable pricing, sufficient volume,
      before end-of-day market maker inventory pressure
    - AVOID last 15 minutes: afternoon momentum effect can create
      persistent price pressure from market maker inventory management
  
  ML Layer (gradient boosted model):
    Features:
      - Time of day (minute-level)
      - Current bid-ask spread vs 20-day average at this TOD
      - TQQQ volume profile (current vs typical at this TOD)
      - VIX intraday change since open
      - TQQQ intraday return since open
      - Options volume surge indicator
      - Day of week
      - Days to FOMC / OpEx / earnings
    
    Target: Execution quality score = 
      (filled_price - mid_at_signal) / mid_at_signal
      Lower is better for buys, higher for sells
    
    Output: "EXECUTE_NOW" vs "WAIT" vs "SKIP_TODAY"
      with estimated slippage savings in cents

  Integration with scheduler:
    - 09:45 check → if signal triggered, TimingEngine decides
      "execute at 10:35" or "execute now"
    - 12:00 check → midday evaluation, TimingEngine may say
      "wait for 2:30pm" or "execute now"
    - 15:45 check → pre-close, TimingEngine decides if conditions
      are favorable or "skip, too late"
```

Academic research at Notre Dame demonstrates that intraday option returns display persistent seasonality: morning momentum (driven by underreaction to volatility shocks) and afternoon momentum (driven by market maker inventory management). The TimingEngine can exploit these patterns to improve execution by 5–15 basis points per trade.[^8]

### Improvement 4: Add IV Surface Monitor for Dynamic DTE/Strike Selection

**Problem:** The plan selects DTE and strike based on fixed rules (21–45 DTE, ~0.30 delta). But the implied volatility surface changes dynamically: sometimes shorter-dated options offer better risk/reward due to steep term structure, and sometimes the skew makes certain strikes more attractive.[^10][^11]

**Solution:** Add a real-time IV surface monitor.

```
[NEW] src/tqqq/iv_surface_monitor.py

Class: IVSurfaceMonitor
  
  Methods:
    - build_surface(chain_data) -> IVSurface
        Constructs IV surface from current options chain
        Uses SVI parameterization for smooth interpolation
    
    - get_term_structure_slope() -> float
        Slope of IV across expirations at fixed delta
        Steep positive slope → prefer shorter DTE (front-month rich)
        Flat/inverted → prefer longer DTE (back-month relatively cheap)
    
    - get_skew_steepness(expiry) -> float
        OTM put IV - ATM IV for given expiry
        Steep skew → our short OTM puts are expensive → good entry
        Flat skew → less edge in selling OTM puts → wait
    
    - get_iv_percentile(strike, expiry) -> float
        Current IV vs 252-day historical IV for this contract
        High percentile → premium-rich → favorable for selling
    
    - recommend_dte_adjustment() -> int
        Based on term structure: suggest DTE shift from default
        E.g., "Shift from 30 DTE target to 21 DTE because
         front-month IV is 15% above back-month"
    
    - recommend_strike_adjustment() -> float
        Based on skew: suggest delta shift from default
        E.g., "Shift from -0.30 delta to -0.25 delta because
         skew is flat (less edge at -0.30)"
```

This module feeds into both the `spread_builder.py` and the Bayesian Optimizer, providing real-time market structure intelligence that static rules cannot capture.[^11][^10]

### Improvement 5: Enhance PPO Agent with Intraday Timing Action

**Problem:** The current RL agent in the plan has a discrete action space focused on position management (open spread, close short leg, sell long put, etc.) but doesn't include *when* during the day to act.

**Solution:** Expand the PPO action space to include timing decisions, and use a quadratic transaction cost penalty function instead of linear.[^12][^13][^14]

```
[MODIFY] src/tqqq/ml/ — PPO Agent Enhancement

  Expanded Action Space:
    0: Do nothing
    1: Open spread NOW
    2: Open spread DELAYED (wait for TimingEngine optimal window)
    3: Close short leg NOW
    4: Close short leg DELAYED
    5: Sell long put NOW
    6: Sell long put DELAYED
    7: Close entire spread NOW
    8: Close entire spread DELAYED
    9: Roll spread

  Enhanced Reward Function:
    R_t = Realized_PL 
          - λ₁ · (spread_cost)²     ← quadratic penalty
          - λ₂ · CVaR_95
          - λ₃ · max_drawdown_penalty
          + λ₄ · timing_bonus       ← bonus for executing at 
                                       better-than-mid prices

  Retraining Schedule:
    - Weekly retraining on most recent 6 months of data
    - Research shows weekly-retrained DRL agents outperform
      single-trained agents for option management
```

Research at NYU and the University of Toronto demonstrates that PPO outperforms DQN and DDPG for option replication across multiple strikes simultaneously, and that weekly retraining on newly calibrated models significantly improves performance over single-train approaches. The quadratic transaction cost penalty has been shown to produce more realistic and stable agent behavior than linear penalties.[^13][^12]

### Improvement 6: Add Walk-Forward Model Validation Pipeline

**Problem:** The plan mentions backtesting but doesn't detail a structured walk-forward validation framework for the ML models. Without this, overfitting risk is high.

**Solution:**

```
[NEW] src/tqqq/ml/validation_pipeline.py

Class: WalkForwardValidator
  
  Method: validate_all_models()
    
    For each model (HMM, XGBoost, LSTM, Bandit, PPO):
      1. Define walk-forward windows:
         - Train: expanding window, min 504 days (2 years)
         - Validation: 63 days (3 months)
         - Test: 63 days (3 months)
         - Roll forward by 63 days
      
      2. At each fold:
         - Train model on train set
         - Tune hyperparameters on validation set
         - Evaluate on test set (never seen)
         - Record: accuracy, Sharpe, max drawdown, win rate
      
      3. Aggregate results across all folds
      
      4. Statistical tests:
         - Paired t-test vs baseline (close-at-50% strategy)
         - Bootstrap confidence intervals on Sharpe ratio
         - Check for regime-dependent performance variation
      
      5. Output: ValidationReport with go/no-go recommendation
  
  Anti-overfitting checks:
    - Parameter stability: do optimal params change >20% across folds?
    - Out-of-sample degradation: does test Sharpe drop >30% vs validation?
    - Feature importance stability: do top-5 features change across folds?
```

### Improvement 7: Add Fallback Logic to spread_builder.py

**Problem:** The current plan mentions a QQQ fallback when TQQQ liquidity is thin, but doesn't detail the mechanics.

**Solution:**

```
[MODIFY] src/tqqq/spread_builder.py

  Add FallbackManager:
    
    Priority chain:
      1. TQQQ monthly options (preferred)
      2. TQQQ weekly options closest to monthly (if monthly fails filters)
      3. QQQ options (scale strikes by ~3x, adjust contract size)
      4. NO TRADE (if all fail)
    
    QQQ Translation Logic:
      - If TQQQ at $50 → QQQ at ~$500
      - TQQQ $5-wide spread ≈ QQQ ~$15-wide spread (adjusted for 3x)
      - Adjust position size: 1 TQQQ contract ≈ 0.3 QQQ contracts
      - Signal clearly labels: "QQQ SUBSTITUTE — TQQQ liquidity insufficient"
    
    Decision criteria:
      - Switch when < 3 TQQQ contracts pass all liquidity filters
      - Log reason for fallback (which filter failed)
      - Track fallback frequency (if >20% of signals → review filters)
```

***

## 3. New AI Module: Complete Option Selection Pipeline

Combining all the improvements, here is the full AI-optimized option selection flow:

```
┌─────────────────────────────────────────────────────────────┐
│                    OPTION SELECTION PIPELINE                  │
│                                                               │
│  Step 1: REGIME DETECTION (existing HMM)                     │
│    → Current regime: HIGH_VOL                                │
│    → Load regime-specific params from BO auto-tuner          │
│                                                               │
│  Step 2: IV SURFACE ANALYSIS (new)                           │
│    → Term structure slope: steep → prefer shorter DTE        │
│    → Skew steepness: steep → good edge at -0.30 delta       │
│    → IV percentile: 78th → premium-rich, favorable           │
│    → Adjusted targets: DTE=25, delta=-0.28                   │
│                                                               │
│  Step 3: LIQUIDITY FILTER (existing, enhanced)               │
│    → Scan all TQQQ options at adjusted DTE/delta             │
│    → Apply hard filters: vol≥1000, OI≥2000, spread≤$0.05    │
│    → 8 candidates pass                                       │
│                                                               │
│  Step 4: CONTEXTUAL BANDIT (new, replaces XGBoost ranker)    │
│    → Context: regime=HIGH_VOL, VIX=28, TQQQ=$48, TOD=10:30  │
│    → Thompson Sampling across 8 candidate arms               │
│    → Selected: Apr 18 $46/$41 put spread, credit $1.65      │
│                                                               │
│  Step 5: INTRADAY TIMING (new)                               │
│    → Current time: 9:45am                                    │
│    → TimingEngine: "WAIT — execute at 10:35am"               │
│    → Estimated slippage savings: $0.03/contract              │
│                                                               │
│  Step 6: EXECUTION                                           │
│    → At 10:35am: place LIMIT order at mid-price              │
│    → Walk price $0.01 every 15 sec                           │
│    → Filled at $1.63 credit (slippage: $0.02)               │
│                                                               │
│  Step 7: SIGNAL PUBLISH                                      │
│    → Push to users: "🔴 SELL TQQQ $46/$41 Put Spread,       │
│      Apr 18, Credit: $1.63, VIX Regime: HIGH_VOL"           │
└─────────────────────────────────────────────────────────────┘
```

***

## 4. Revised File Summary

Adding the new modules to your existing plan:

| # | File | Type | Component | Status |
|---|---|---|---|---|
| 1 | `src/tqqq/__init__.py` | NEW | Strategy enums | ✅ Keep as-is |
| 2 | `src/tqqq/spread_builder.py` | NEW | Strike/expiry + **fallback logic** | ⚡ Enhanced |
| 3 | `src/tqqq/vix_adaptive_strategy.py` | NEW | Core state machine | ✅ Keep as-is |
| 4 | `src/tqqq/leg_manager.py` | NEW | Leg-out logic | ✅ Keep as-is |
| 5 | `src/tqqq/tqqq_risk_manager.py` | NEW | Risk + leg-out validation | ✅ Keep as-is |
| 6 | `src/tqqq/position_tracker.py` | NEW | State tracking + metrics | ✅ Keep as-is |
| 7 | `src/tqqq/order_manager.py` | NEW | IB execution | ✅ Keep as-is |
| 8 | `src/tqqq/data_pipeline.py` | NEW | VIX/TQQQ data + features | ✅ Keep as-is |
| 9 | `src/tqqq/iv_surface_monitor.py` | **NEW** | **Real-time IV surface analysis** | 🆕 Added |
| 10 | `src/tqqq/ml/__init__.py` | NEW | ML package init | ✅ Keep as-is |
| 11 | `src/tqqq/ml/regime_detector.py` | NEW | HMM VIX regime | ✅ Keep as-is |
| 12 | `src/tqqq/ml/vix_predictor.py` | NEW | XGBoost + LSTM ensemble | ✅ Keep as-is |
| 13 | `src/tqqq/ml/contract_ranker.py` | NEW | **Contextual Bandit selector** | ⚡ Enhanced |
| 14 | `src/tqqq/ml/param_optimizer.py` | **NEW** | **Bayesian Optimization auto-tuner** | 🆕 Added |
| 15 | `src/tqqq/ml/timing_engine.py` | **NEW** | **Intraday entry/exit timing** | 🆕 Added |
| 16 | `src/tqqq/ml/validation_pipeline.py` | **NEW** | **Walk-forward model validation** | 🆕 Added |
| 17 | `signal_publisher/tqqq.py` | NEW | Signal classes | ✅ Keep as-is |
| 18 | `run_tqqq_scheduler.py` | NEW | Launcher | ✅ Keep as-is |
| 19 | `config.py` | MODIFY | Add TQQQ settings + **regime-specific params** | ⚡ Enhanced |
| 20 | `signal_publisher/__init__.py` | MODIFY | Register TQQQ signals | ✅ Keep as-is |

**Total: 17 new files (+3 from original plan), 3 modified files (+1 from original plan)**

***

## 5. Revised Implementation Phases

| Phase | Timeline | New Additions |
|---|---|---|
| Phase 1: Core Strategy | Week 1–2 | Same as original, plus `iv_surface_monitor.py` |
| Phase 2: ML Intelligence | Week 2–4 | Add `param_optimizer.py`, `timing_engine.py`, upgrade `contract_ranker.py` to Contextual Bandit |
| Phase 3: Execution & Risk | Week 4–5 | Add fallback logic to `spread_builder.py` |
| Phase 4: Signals & Config | Week 5–6 | Add regime-specific params to `config.py` |
| Phase 5: Scheduling | Week 6 | Integrate TimingEngine into scheduler decision flow |
| **Phase 5.5: Validation** | **Week 6–7** | **NEW: `validation_pipeline.py`, walk-forward testing for all models** |
| Phase 6: Backtest | Week 7–9 | Enhanced with BO-optimized params, timing simulation |
| Phase 7: Paper Trading | Week 9–13 | Minimum 4 weeks (extended from 2) |
| Phase 8: Live | Week 14+ | Start with 1–2 contracts |

***

## 6. Entry/Exit Timing: Research-Backed Recommendations

### Optimal Entry Timing for Selling Credit Spreads on TQQQ

Research on intraday option returns and execution quality reveals clear patterns that should be built into the TimingEngine:[^9][^7][^8]

**Best entry windows for selling credit spreads:**
- **10:00–11:00 AM ET**: Post-open volatility has settled, bid-ask spreads have tightened from their 9:30 AM peaks, and volume is still high. Research shows the first 30 minutes after open have the widest execution costs independent of volume.[^7]
- **2:30–3:30 PM ET (secondary)**: Afternoon session with stable pricing before end-of-day flows. Good for entries when morning was missed.

**Avoid for entries:**
- **9:30–10:00 AM**: Widest spreads, highest execution slippage, morning volatility overshoot.[^8][^7]
- **3:45–4:00 PM**: Market maker inventory management creates persistent price pressure that can move against you.[^8]

### Optimal Exit Timing

**For closing full spreads (profit target hit):**
- **10:30–11:30 AM**: After morning volatility settles; good fills on limit orders.
- **2:00–3:00 PM**: Stable execution, avoiding end-of-day noise.

**For leg-out (buying back short put):**
- **Mid-day (11:00 AM–2:00 PM)**: When the short put is cheapest (low theta, low gamma mid-day); avoids morning noise and afternoon momentum.[^8]

**For selling retained long put during VIX spike:**
- **9:45–10:15 AM**: If VIX gaps up overnight, the morning session offers the highest premium on long puts due to morning volatility overshoot and underreaction. Research shows morning straddle returns display persistent momentum—morning winners on day t predict winners on day t+1.[^8]

### Integration with the Scheduler

```
Updated Scheduler Timeline:
  08:00: Data refresh, ML retraining check
  09:35: VIX regime check → generate preliminary signal
  09:45: TimingEngine evaluates: "Is now a good entry moment?"
         → If YES: execute
         → If NO: set timer for 10:15-10:45 window
  10:30: Secondary entry window check
  12:00: Midday position review + leg-out evaluation
         (optimal time for buying back cheap short puts)
  14:30: Afternoon check: any pending delayed executions
  15:15: Pre-close review: close any positions hitting time rules
  15:45: Final position check + EOD signals
  16:15: EOD P&L report + model performance logging
```

***

## 7. Summary of All Changes

### New Capabilities Added
1. **Bayesian Optimization** (`param_optimizer.py`): Auto-tunes DTE, delta, spread width, profit targets per regime[^1][^2]
2. **Contextual Bandit** (`contract_ranker.py` upgrade): Thompson Sampling for strike/expiry selection with principled exploration[^4][^5]
3. **Intraday Timing Engine** (`timing_engine.py`): ML-driven optimal time-of-day for entries/exits based on execution quality patterns[^7][^8]
4. **IV Surface Monitor** (`iv_surface_monitor.py`): Real-time volatility surface analysis for dynamic DTE/strike adjustment[^10][^11]
5. **Walk-Forward Validation** (`validation_pipeline.py`): Structured anti-overfitting framework for all ML models
6. **Regime-Specific Parameters**: Different optimal configurations for each VIX regime instead of static config
7. **QQQ Fallback**: Detailed translation logic when TQQQ liquidity is insufficient

### Existing Components Enhanced
- `spread_builder.py`: Added fallback chain (TQQQ monthly → TQQQ weekly → QQQ → no trade)
- `config.py`: Added regime-specific parameter blocks
- PPO Agent: Expanded action space with timing decisions; quadratic cost penalty[^12][^13]
- Scheduler: Integrated with TimingEngine for dynamic execution windows

These additions transform the system from a rule-based strategy with ML signals into a fully adaptive, self-optimizing options trading system that learns the best parameters, contracts, and timing from its own experience.

---

## References

1. [Optimizing Trading Strategies with Bayesian Optimization](https://onepagecode.substack.com/p/optimizing-trading-strategies-with-6b1) - Optimizing the parameters of a quantitative trading strategy is a critical step in enhancing its per...

2. [Bayesian Optimization in Trading - DayTrading.com](https://www.daytrading.com/bayesian-optimization) - We look at the role of Bayesian optimization in trading applications. Step by step process.

3. [Parameter Optimization Methods in Trading Strategies](https://vyftec.com/ai-powered-parameter-optimization-revolutionizing-trading-strategy-performance/) - Discover how Bayesian optimization and AI are transforming trading strategy development by automatin...

4. [Week 6: Multi-Armed Bandits](https://deeprlcourse.github.io/course_notes/bandits/) - This page provides an in-depth exploration of the Multi-Armed Bandit (MAB) problem, a foundational c...

5. [Hedging using reinforcement learning: Contextual k-armed bandit ...](https://www.sciencedirect.com/science/article/pii/S240591882300017X) - In this article, the hedging problem is viewed as an instance of a risk-averse contextual k-armed ba...

6. [Contextual Bandits: Dynamic Pricing and Real-Time Prediction | gganbu marketplace](https://gganbumarketplace.com/machine-learning/contextual-bandits-dynamic-pricing-and-real-time-prediction/) - gganbu marketplace Contextual Bandits: Dynamic Pricing and Real-Time Prediction

7. [The Time of Day Effect: A Breakthrough in Trading Cost Optimization](https://www.bestexresearch.com/insights/the-time-of-day-effect-a-breakthrough-in-trading-cost-optimization) - In this paper, we examine how trading costs vary throughout the day, independent of volume, revealin...

8. [Intraday Option Return: A Tale of Two Momentum](https://academicweb.nd.edu/~zda/IntraOption.pdf)

9. [How to Perfectly Time When to Sell an Options Credit Spread on the ...](https://www.environmentaltradingedge.com/trading-education/how-to-perfectly-time-when-to-sell-an-options-credit-spread-on-the-spx) - Selling an options credit spread on the S&P 500 Index (SPX) can be a profitable strategy for options...

10. [[PDF] INTRADAY VOLATILITY SURFACE CALIBRATION - Diva-Portal.org](http://www.diva-portal.org/smash/get/diva2:1445031/FULLTEXT01.pdf) - (iii) The magnitude of the volatility smile decreases as time to maturity in- creases. Shorter matur...

11. [Volatility Smile: What It Means in Options Trading and How to Use It](https://www.strike.money/options/volatility-smile) - A volatility smile in options trading is a U-shaped curve showing higher implied volatility (IV) for...

12. [[PDF] Deep Reinforcement Learning for Option Replication and Hedging](https://cims.nyu.edu/~ritter/du2020deep.pdf) - The authors propose models for the replication of options over a whole range of strikes subject to d...

13. [Optimizing Deep Reinforcement Learning for American Put Option Hedging](https://www.arxiv.org/abs/2405.08602) - This paper contributes to the existing literature on hedging American options with Deep Reinforcemen...

14. [Deep Reinforcement Learning Algorithms for Option Hedging](https://arxiv.org/abs/2504.05521) - Dynamic hedging is a financial strategy that consists in periodically transacting one or multiple fi...

