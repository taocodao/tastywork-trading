# VIX-Adaptive Vertical Put Spread Leg Management on TQQQ: Strategy Analysis & Implementation Plan

## Executive Summary

This report analyzes a proposed strategy of selling vertical put spreads on TQQQ during high-VIX regimes, then "legging out" by closing the short put when VIX drops and price rises, retaining the long put to resell during the next VIX spike. The strategy exploits the strong inverse correlation between TQQQ (a 3x leveraged Nasdaq-100 ETF) and the VIX, which amplifies volatility regime transitions. While the core concept of legging out of verticals is generally discouraged as standard practice, the unique characteristics of TQQQ—3x amplified volatility swings, IV range of 45%–150%, and rapid mean-reverting VIX cycles—create conditions where AI/ML-driven regime detection could make this approach systematically profitable.[^1][^2][^3][^4][^5][^6]

The report provides a complete implementation plan suitable for Antigravity to code, including data pipelines, ML models, execution logic via Interactive Brokers, risk management, and backtesting infrastructure.

***

## 1. Strategy Thesis Validation

### 1.1 The VIX–TQQQ Inverse Relationship

TQQQ delivers 3x the daily return of the Nasdaq-100, which means its implied volatility runs approximately 3x that of QQQ. TQQQ's IV typically ranges from 45% to 150%, with normal conditions between 60%–90%. The VIX and TQQQ exhibit strong inverse correlation: when fear spikes (VIX up), TQQQ drops sharply; when fear subsides (VIX down), TQQQ rallies. This relationship is amplified by the 3x leverage factor, making regime transitions both faster and more extreme than on QQQ or SPY.[^7][^8][^9][^10][^11]

### 1.2 Why Standard Advice Says "Don't Leg Out"

Standard options education advises closing vertical spreads as a package because legging out changes the risk profile fundamentally:[^4][^5][^12]

- Closing the short put and keeping the long put creates a **long put** position that bleeds theta while waiting for the next VIX spike[^13][^14]
- The remaining long put becomes a speculative directional/volatility trade, not the original income trade[^15][^16]
- Without systematic timing, most traders give back profits waiting for a vol spike that may not come before expiration[^14][^17]

### 1.3 Why AI/ML Changes the Calculus

The critical weakness of manual leg management is *timing*. Research demonstrates that machine learning models can predict VIX direction with meaningful accuracy:

- **LSTM neural networks** predict VIX direction with ~61% out-of-sample accuracy[^2]
- **XGBoost models** using VIX moving averages achieve 55.38% directional accuracy, with mean absolute prediction error of 4.77%[^18]
- **Seven ML models** tested on VIX futures term structure show profitable trading strategies with information ratios above 0.6[^19][^1]
- **Hidden Markov Models (HMM)** effectively identify low-volatility vs. high-volatility regimes in real-time[^20][^21][^22]
- **Regime-switching models** with XGBoost classifiers improve volatility forecasting by capturing sudden market shocks[^3]

If an AI system can reliably detect when VIX is transitioning from low→high (time to sell the retained long put at inflated prices) versus high→low (time to close the short leg cheaply), the strategy becomes viable.

### 1.4 TQQQ Options Liquidity Assessment

TQQQ options are among the most liquid ETF options:[^11][^23]

| Metric | Value |
|---|---|
| Daily options volume | 500K+ contracts |
| ATM bid-ask spread | $0.02–$0.05 |
| Open interest | 3M+ contracts |
| IV range | 45%–150% |
| Available expirations | Weekly, Monthly, LEAPS |

However, further OTM strikes and weeklies can have wider spreads. The implementation should prefer **monthly expirations** and strikes within 2–3 strikes of ATM for best execution.[^24]

***

## 2. ML/AI Architecture

### 2.1 Module 1: VIX Regime Detector (Hidden Markov Model)

**Purpose:** Classify the current market into discrete volatility regimes (e.g., Low-Vol, Normal, High-Vol, Crisis) in real-time.

**Model:** Gaussian Hidden Markov Model with 3–4 states[^21][^22][^20]

**Features (input vector):**
- VIX closing price and intraday price
- VIX 5-day, 10-day, 20-day moving averages
- VIX rate of change (1-day, 5-day)
- VIX term structure slope (VIX vs VIX3M ratio)
- TQQQ realized volatility (5-day, 20-day)
- TQQQ–VIX rolling correlation (20-day)
- Put/call ratio on QQQ options
- S&P 500 realized volatility

**Training approach:**
- Use `hmmlearn` library in Python[^20][^21]
- Walk-forward expanding window: train on 2+ years, predict next day, expand window[^1]
- Retrain weekly or when prediction confidence drops below threshold

**Output:** Current regime label (integer 0–3) + transition probability matrix

```python
# Pseudocode for HMM Regime Detector
from hmmlearn.hmm import GaussianHMM
import numpy as np

class VIXRegimeDetector:
    def __init__(self, n_states=3, n_iter=1000):
        self.model = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=n_iter,
            random_state=42
        )
        self.state_map = {}  # Maps HMM states to regime labels

    def train(self, features: np.ndarray):
        """Train on historical feature matrix [n_days x n_features]"""
        self.model.fit(features)
        self._identify_states(features)

    def _identify_states(self, features):
        """Map states to Low/Normal/High vol by mean VIX in each state"""
        states = self.model.predict(features)
        # Sort states by mean VIX level
        ...

    def predict_regime(self, features: np.ndarray) -> dict:
        """Returns current regime + transition probabilities"""
        state = self.model.predict(features)[-1]
        return {
            "regime": self.state_map[state],
            "state_id": state,
            "transition_probs": self.model.transmat_[state],
            "confidence": max(self.model.predict_proba(features)[-1])
        }
```

### 2.2 Module 2: VIX Direction Predictor (XGBoost + LSTM Ensemble)

**Purpose:** Predict short-term VIX direction (next 1–5 days) to time leg management decisions.

**Model A — XGBoost Classifier:**[^25][^26][^18]
- Target: VIX direction next day (Up/Down/Flat with ±1% threshold)
- Features: VIX OHLC, VIX futures term structure, put/call ratios, TQQQ returns, sector breadth, credit spreads
- Walk-forward training with 252-day expanding window
- XGBoost hyperparameters: learning_rate=0.01–0.04, max_depth=3–6, n_estimators=500+, early stopping[^27]

**Model B — LSTM Neural Network:**[^28][^29][^30][^2]
- Target: VIX return magnitude next 1–3 days
- Architecture: 2-layer LSTM (50 units each), dropout 0.2, dense output
- Input: 20-day lookback window of multivariate features
- Features: VIX, SPX options-weighted data, TQQQ price, volume, RSI, MACD

**Ensemble:** Weighted average of XGBoost probability and LSTM directional signal. Use Bayesian model averaging with walk-forward validation to determine weights.

```python
# Pseudocode for Ensemble Predictor
class VIXDirectionPredictor:
    def __init__(self):
        self.xgb_model = XGBClassifier(...)
        self.lstm_model = build_lstm_model(...)
        self.ensemble_weights = [0.5, 0.5]  # Updated via walk-forward

    def predict(self, features) -> dict:
        xgb_prob = self.xgb_model.predict_proba(features)
        lstm_pred = self.lstm_model.predict(features)
        combined = weighted_average(xgb_prob, lstm_pred, self.ensemble_weights)
        return {
            "direction": "UP" if combined > 0.55 else "DOWN" if combined < 0.45 else "FLAT",
            "confidence": abs(combined - 0.5) * 2,
            "xgb_signal": xgb_prob,
            "lstm_signal": lstm_pred
        }
```

### 2.3 Module 3: Optimal Action Selector (Reinforcement Learning)

**Purpose:** Learn the optimal policy for when to enter spreads, when to close the short leg, when to sell the retained long put, and when to close everything.

**Algorithm:** Proximal Policy Optimization (PPO)[^31][^32][^33]

**State space:**
- Current regime (from HMM)
- VIX direction prediction (from ensemble)
- Current VIX level and percentile rank (0–100)
- TQQQ price, RSI, distance from key moving averages
- Position state: {No Position, Full Spread, Long Put Only}
- Days to expiration on open position
- Current P/L on position
- Greeks: position delta, vega, theta

**Action space (discrete):**
- 0: Do nothing
- 1: Open new put credit spread (sell short put, buy long put)
- 2: Close short leg only (buy back short put, keep long put)
- 3: Sell the long put (close retained leg)
- 4: Close entire spread
- 5: Roll the spread

**Reward function:**[^34][^31]

\[ R_t = \text{Realized P/L} - \lambda_1 \cdot \text{Transaction Costs} - \lambda_2 \cdot \text{CVaR}_{95} - \lambda_3 \cdot \text{Max Drawdown Penalty} \]

Where λ values are tunable risk-aversion parameters.

**Training:**
- Environment simulated from historical TQQQ options data
- Walk-forward: train on 2 years, validate on next 6 months, test on next 6 months
- Use Stable-Baselines3 library for PPO implementation

***

## 3. System Architecture

### 3.1 High-Level Design

```
┌──────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR (Python)                      │
│                                                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ Data Pipeline│  │  ML Engine   │  │   Execution Engine       │ │
│  │             │  │              │  │                          │ │
│  │ • VIX Feed  │→│ • HMM Regime │→│ • IB API (ib_insync)     │ │
│  │ • TQQQ Feed │  │ • XGB+LSTM   │  │ • Spread Builder         │ │
│  │ • Options   │  │ • PPO Agent  │  │ • Leg Manager            │ │
│  │ • Greeks    │  │              │  │ • Order Router           │ │
│  └─────────────┘  └──────────────┘  └──────────────────────────┘ │
│                                                                    │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │Risk Manager │  │  Backtester  │  │   Dashboard / Alerts     │ │
│  │             │  │              │  │                          │ │
│  │ • Position  │  │ • Historical │  │ • Real-time P/L          │ │
│  │   Sizing    │  │   Replay     │  │ • Regime Display         │ │
│  │ • Max Loss  │  │ • Walk-fwd   │  │ • Trade Log              │ │
│  │ • Margin    │  │ • Monte Carlo│  │ • Slack/Email Alerts     │ │
│  └─────────────┘  └──────────────┘  └──────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │  Interactive       │
                    │  Brokers TWS/GW    │
                    │  Port 7497 (paper) │
                    │  Port 7496 (live)  │
                    └───────────────────┘
```

### 3.2 Technology Stack

| Component | Technology | Rationale |
|---|---|---|
| Core language | Python 3.11+ | ML ecosystem, ib_insync compatibility |
| IB connection | `ib_insync` | Pythonic IB API wrapper, proven for spreads[^35][^36] |
| ML: HMM | `hmmlearn` | Standard HMM library[^20] |
| ML: XGBoost | `xgboost` | Best VIX direction accuracy[^18] |
| ML: LSTM | `tensorflow/keras` | VIX prediction[^28][^2][^30] |
| ML: RL | `stable-baselines3` | PPO implementation[^32][^33] |
| Data | `yfinance`, FRED API, CBOE CSV | Free VIX/TQQQ data[^37][^38][^39] |
| Options data | IB API + Finnhub (historical) | Real-time + backtest data[^40] |
| Database | PostgreSQL | Position tracking, trade log, model states |
| Scheduling | APScheduler or cron | Intraday signal checks |
| Dashboard | Streamlit or Grafana | Real-time monitoring |
| Deployment | Docker on AWS EC2 | Consistent environment |

***

## 4. Detailed Implementation Plan for Antigravity

### Phase 1: Data Pipeline & Infrastructure (Week 1–2)

**Task 1.1: Data Ingestion Service**

```
File: src/data/data_pipeline.py

Class: DataPipeline
  - fetch_vix_realtime() -> VIX spot from IB or CBOE
  - fetch_vix_historical() -> Daily OHLC from FRED API (VIXCLS series)
  - fetch_vix_futures_term_structure() -> VX1, VX2 from IB
  - fetch_tqqq_realtime() -> TQQQ spot, bid/ask from IB
  - fetch_tqqq_historical() -> Daily OHLC from yfinance
  - fetch_tqqq_options_chain() -> Full chain with Greeks from IB
  - fetch_market_breadth() -> Put/call ratio, advance/decline from IB
  - compute_derived_features() -> RSI, MACD, Bollinger, rolling stats
  
Storage: PostgreSQL tables
  - market_data (timestamp, symbol, open, high, low, close, volume)
  - vix_data (timestamp, vix_spot, vix3m, vx1, vx2, term_slope)
  - options_chain (timestamp, symbol, expiry, strike, type, bid, ask, iv, delta, gamma, theta, vega, oi)
  - features (timestamp, feature_name, value)
```

**Task 1.2: IB Connection Manager**

```
File: src/broker/ib_connection.py

Class: IBConnectionManager
  - connect(host, port, client_id)
  - reconnect_with_backoff()
  - health_check() -> bool
  - get_account_summary() -> dict
  - get_positions() -> list
  
Config: config/config.yaml
  ibkr:
    host: "127.0.0.1"
    paper_port: 7497
    live_port: 7496
    client_id_data: 1
    client_id_trading: 2
    account_code: "YOUR_CODE"
```

Reference implementation: The IBKR-trader project provides a proven Python/Go hybrid architecture for vertical spread automation with IB, and ib_insync combo leg examples show the exact pattern for spread order construction.[^41][^42][^36]

### Phase 2: ML Models (Week 2–4)

**Task 2.1: HMM Regime Detector**

```
File: src/ml/regime_detector.py

Class: VIXRegimeDetector
  - __init__(n_states=3)
  - train(feature_matrix: np.ndarray)
  - predict_regime(current_features: np.ndarray) -> RegimeState
  - get_transition_probabilities() -> np.ndarray
  - save_model(path) / load_model(path)
  - retrain_if_needed(new_data) -> bool

Enum: RegimeState
  LOW_VOL = 0    # VIX < 15, calm market
  NORMAL = 1     # VIX 15-25, typical
  HIGH_VOL = 2   # VIX 25-35, elevated fear
  CRISIS = 3     # VIX > 35, panic (optional 4th state)

Training pipeline:
  1. Pull VIX + features from 2015-present
  2. Compute feature matrix (returns, MA, term structure)
  3. Fit HMM with walk-forward expanding window
  4. Validate: regime labels should correlate with VIX percentiles
  5. Pickle model + state mapping
```

**Task 2.2: XGBoost VIX Direction Predictor**

```
File: src/ml/vix_predictor_xgb.py

Class: VIXXGBoostPredictor
  - __init__(params: dict)
  - train(X_train, y_train, X_val, y_val)
  - predict(features) -> (direction, probability)
  - feature_importance() -> dict
  - walk_forward_validate(data, train_window, test_window)

Features (30+ engineered):
  - VIX: close, MA5, MA10, MA20, ROC1, ROC5, percentile_rank_60d
  - VIX term structure: VIX/VIX3M ratio, VX1-VX2 spread
  - TQQQ: return_1d, return_5d, RSI_14, MACD_signal, BB_position
  - Market: SPX_return, put_call_ratio, HY_spread_change
  - Calendar: day_of_week, days_to_FOMC, days_to_OpEx

Target: VIX direction next day {-1, 0, +1} with ±1.5% threshold

XGBoost params (starting point):
  learning_rate: 0.02
  max_depth: 5
  n_estimators: 800
  subsample: 0.8
  colsample_bytree: 0.8
  early_stopping_rounds: 50
  eval_metric: "mlogloss"
```

**Task 2.3: LSTM VIX Predictor**

```
File: src/ml/vix_predictor_lstm.py

Class: VIXLSTMPredictor
  - __init__(lookback=20, n_features=15)
  - build_model()
  - train(X_train_seq, y_train, epochs=200, batch_size=32)
  - predict(sequence) -> (predicted_return, confidence)

Architecture:
  Input: (batch, 20 timesteps, 15 features)
  → LSTM(50 units, return_sequences=True)
  → Dropout(0.2)
  → LSTM(50 units)
  → Dropout(0.2)
  → Dense(32, relu)
  → Dense(1, linear)  # Predicted VIX return

Preprocessing: MinMaxScaler on features, walk-forward split
```

**Task 2.4: Ensemble Combiner**

```
File: src/ml/ensemble_predictor.py

Class: VIXEnsemblePredictor
  - __init__(xgb_model, lstm_model, weights=[0.6, 0.4])
  - predict(features, sequence) -> SignalOutput
  - calibrate_weights(validation_data)  # Bayesian model averaging

SignalOutput:
  direction: str  # "VIX_RISING", "VIX_FALLING", "NEUTRAL"
  confidence: float  # 0.0 - 1.0
  magnitude: float  # Expected VIX % change
  horizon: int  # Days
```

### Phase 3: Strategy Engine (Week 4–6)

**Task 3.1: Spread Construction Module**

```
File: src/strategy/spread_builder.py

Class: SpreadBuilder
  - select_expiration(min_dte=21, max_dte=45) -> date
  - select_strikes(
      tqqq_price: float,
      target_delta_short: float = -0.30,
      spread_width: int = 5  # $5 wide
    ) -> (short_strike, long_strike)
  - calculate_spread_metrics(chain_data) -> SpreadMetrics
  - build_combo_order(short_strike, long_strike, expiry, quantity) -> Bag

SpreadMetrics:
  credit: float
  max_profit: float
  max_loss: float
  breakeven: float
  probability_of_profit: float
  net_vega: float
  net_theta: float
  net_delta: float

IB Order Construction (using ib_insync):
  shortPut = Option('TQQQ', expiry, short_strike, 'P', 'SMART')
  longPut = Option('TQQQ', expiry, long_strike, 'P', 'SMART')
  ib.qualifyContracts(shortPut, longPut)
  combo_legs = [
      ComboLeg(conId=shortPut.conId, ratio=1, action='SELL', exchange='SMART'),
      ComboLeg(conId=longPut.conId, ratio=1, action='BUY', exchange='SMART')
  ]
  spread = Bag(symbol='TQQQ', comboLegs=combo_legs, exchange='SMART', currency='USD')
```

**Task 3.2: Core Strategy Logic — The VIX-Adaptive Leg Manager**

```
File: src/strategy/vix_adaptive_strategy.py

Class: VIXAdaptiveStrategy
  """
  State Machine with 4 states:
    IDLE → FULL_SPREAD → LONG_PUT_ONLY → IDLE
                       → IDLE (close full spread)
  """

  States:
    IDLE: No position open
    FULL_SPREAD: Short put + Long put (vertical spread active)
    LONG_PUT_ONLY: Short put closed, long put retained
    CLOSING: Actively closing position

  Decision Logic (called every N minutes during market hours):

  def evaluate(self, regime, vix_signal, position_state, greeks, pnl):

    if position_state == IDLE:
      # ENTRY CONDITION: Sell spread when VIX is high
      if regime in [HIGH_VOL, CRISIS] and vix_signal.direction == "VIX_FALLING":
        if vix_signal.confidence > 0.6:
          → ACTION: Open put credit spread
          → Strike selection: short put at ~0.25-0.30 delta
          → Spread width: $3-$5
          → DTE: 30-45 days
          → Quantity: per risk manager sizing

    elif position_state == FULL_SPREAD:
      # EXIT CONDITION 1: Standard profit target (close everything)
      if pnl.percent_of_max_profit >= 0.50:
        → ACTION: Close entire spread

      # EXIT CONDITION 2: Standard loss limit
      elif pnl.current_loss >= 2.0 * credit_received:
        → ACTION: Close entire spread

      # LEG-OUT CONDITION: VIX has dropped, TQQQ rallied
      # This is the KEY DIFFERENTIATOR of this strategy
      elif (regime == LOW_VOL
            and vix_signal.direction == "NEUTRAL"
            and short_put_value <= 0.15 * original_credit
            and days_to_expiry >= 14
            and vix_signal.confidence > 0.65):
        → ACTION: Buy back short put ONLY (it's very cheap now)
        → RETAIN long put
        → Log: "Legged out - holding long put for next VIX spike"

      # TIME-BASED EXIT: Close everything if too close to expiry
      elif days_to_expiry <= 7:
        → ACTION: Close entire spread

    elif position_state == LONG_PUT_ONLY:
      # SELL RETAINED PUT: VIX spiking again, long put gaining value
      if (regime in [HIGH_VOL, CRISIS]
          and vix_signal.direction == "VIX_RISING"
          and long_put_current_value >= 2.0 * long_put_value_at_legout):
        → ACTION: Sell the long put (take profit on vol spike)

      # ABANDON: VIX not spiking and theta eating the long put
      elif (long_put_current_value <= 0.10  # Nearly worthless
            or days_to_expiry <= 5):
        → ACTION: Close long put (accept small loss on this leg)
        → Log: "Long put expired worthless / closed for minimal value"

      # OPTIONAL: Open a NEW short put against the retained long put
      # (Re-establishing a new spread at different strikes)
      elif (regime == HIGH_VOL
            and vix_signal.direction == "VIX_FALLING"
            and days_to_expiry >= 14):
        → ACTION: Sell a new short put against retained long put
        → This recreates a vertical at new, potentially better strikes
```

**Task 3.3: Execution Engine**

```
File: src/execution/order_manager.py

Class: OrderManager
  - place_spread_order(spread: Bag, quantity: int, limit_price: float) -> Trade
  - close_spread_order(spread: Bag, quantity: int) -> Trade
  - close_single_leg(option: Option, action: str, quantity: int) -> Trade
  - monitor_fill(trade: Trade, timeout: int = 60) -> FillStatus
  - adjust_limit_price(trade: Trade, increment: float = 0.05)
  - cancel_order(trade: Trade)

Execution rules:
  - Always use LIMIT orders (never market on spreads)
  - Start at mid-price, walk toward natural side by $0.01 every 15 seconds
  - Max slippage tolerance: $0.10 per contract
  - For leg-out (closing short put only): use individual limit order
  - For selling retained long put: use individual limit order
  - Log all fills with timestamp, price, slippage vs mid
```

### Phase 4: Risk Management (Week 5–6)

**Task 4.1: Risk Manager**

```
File: src/risk/risk_manager.py

Class: RiskManager
  Parameters:
    max_portfolio_risk_pct: 5%     # Max % of account at risk
    max_single_position_risk: 2%   # Per spread max loss as % of account
    max_concurrent_spreads: 3      # Limit overlapping positions
    max_daily_loss: 3%             # Circuit breaker
    max_vega_exposure: -500        # Max negative vega across portfolio
    min_buying_power_reserve: 30%  # Always keep 30% cash available

  Methods:
    - calculate_position_size(account_value, spread_max_loss) -> int
    - check_entry_allowed(current_positions, proposed_trade) -> (bool, reason)
    - check_margin_requirement(proposed_trade) -> float
    - monitor_daily_pnl() -> trigger circuit breaker if needed
    - calculate_portfolio_greeks() -> PortfolioGreeks
    - validate_leg_out_risk(remaining_position) -> (bool, reason)
      """
      Special validation for leg-out:
      - Ensure remaining long put value > $0.30 (worth managing)
      - Ensure DTE > 14 days (enough time for VIX spike)
      - Ensure total long put exposure < 1% of account
      - Log warning: "Position is now directional/long-vol"
      """
```

**Task 4.2: Position Sizing Logic**

```
Position sizing formula:

max_contracts = floor(
    min(
        account_value * max_single_position_risk / spread_max_loss_per_contract,
        account_value * max_portfolio_risk_pct / total_open_risk,
        buying_power_available / margin_per_contract
    )
)

Example:
  Account: $100,000
  Spread: $5 wide, $1.50 credit → max loss = $350 per contract
  Max single position risk: 2% = $2,000
  → max_contracts = floor($2,000 / $350) = 5 contracts
```

### Phase 5: Backtesting Framework (Week 6–8)

**Task 5.1: Historical Options Data**

```
File: src/backtest/data_loader.py

Data sources:
  - VIX daily OHLC: FRED API (free, 1990–present)
  - TQQQ daily OHLC: yfinance (2010–present)
  - TQQQ options: Finnhub API or CBOE DataShop (paid)
  - Simulated TQQQ options: Black-Scholes pricing using historical IV

For backtesting without historical options data:
  - Use Black-Scholes to reconstruct theoretical option prices
  - Input: TQQQ price, historical IV (from VIX × 3 approximation), risk-free rate
  - Approximate bid-ask spread: ATM = $0.05, OTM = $0.10
```

**Task 5.2: Backtest Engine**

```
File: src/backtest/backtest_engine.py

Class: BacktestEngine
  - load_historical_data(start_date, end_date)
  - simulate_options_prices(tqqq_price, iv, dte, strikes) -> chain
  - run_backtest(strategy, data, initial_capital) -> BacktestResult
  - walk_forward_test(strategy, data, train_window, test_window)
  - monte_carlo_simulation(n_paths=10000) -> distribution of outcomes

BacktestResult:
  total_return: float
  annualized_return: float
  sharpe_ratio: float
  max_drawdown: float
  win_rate: float
  avg_win: float
  avg_loss: float
  profit_factor: float
  total_trades: int
  leg_out_success_rate: float  # Key metric: % of leg-outs that profited
  avg_hold_time_full_spread: float
  avg_hold_time_long_put: float
  vix_regime_accuracy: float

Key metrics to track:
  1. Leg-out success rate (what % of retained long puts sold at profit)
  2. Average additional return from leg management vs closing full spread
  3. Theta decay cost of holding retained long puts
  4. Comparison: strategy vs. simple "close at 50% profit" baseline
```

### Phase 6: Dashboard & Monitoring (Week 7–8)

**Task 6.1: Real-Time Dashboard (Streamlit)**

```
File: src/dashboard/app.py

Pages:
  1. Overview: Account value, daily P/L, open positions
  2. Regime Monitor: Current HMM state, VIX chart with regime overlay
  3. ML Signals: XGBoost/LSTM predictions, confidence levels
  4. Position Manager: Open spreads, leg status, Greeks, P/L
  5. Trade History: All trades with entry/exit prices, leg-out events
  6. Backtest Results: Strategy performance charts
  7. Risk Dashboard: Margin usage, portfolio Greeks, risk limits
```

**Task 6.2: Alerting System**

```
File: src/alerts/alert_manager.py

Alerts via Slack/Email/SMS:
  - Regime change detected (e.g., Normal → High Vol)
  - ML signal: high-confidence VIX direction change
  - Trade executed (entry, leg-out, exit)
  - Risk limit approaching (margin, daily loss, vega)
  - System error (IB disconnection, model failure)
  - Daily summary report
```

***

## 5. Configuration & Parameters

```yaml
# config/strategy_config.yaml
strategy:
  symbol: "TQQQ"
  spread_width: 5          # $5 between strikes
  target_dte_min: 21
  target_dte_max: 45
  short_put_delta: -0.30
  entry_vix_percentile: 70  # Enter when VIX > 70th percentile (last 252 days)
  profit_target_full: 0.50  # Close full spread at 50% profit
  profit_target_long_put: 2.0  # Sell retained put at 2x leg-out value
  max_loss_multiplier: 2.0  # Close at 2x credit received loss
  min_dte_for_legout: 14    # Don't leg out with < 14 DTE
  min_long_put_value: 0.30  # Don't retain if long put < $0.30
  signal_check_interval: 5  # Minutes between signal checks

ml:
  hmm_states: 3
  hmm_retrain_frequency: "weekly"
  xgb_retrain_frequency: "weekly"
  lstm_retrain_frequency: "monthly"
  min_confidence_entry: 0.60
  min_confidence_legout: 0.65

risk:
  max_portfolio_risk_pct: 0.05
  max_single_position_risk: 0.02
  max_concurrent_spreads: 3
  max_daily_loss_pct: 0.03
  min_buying_power_reserve: 0.30
  circuit_breaker_drawdown: 0.10

ib:
  host: "127.0.0.1"
  port: 7497
  client_id: 1
  account: "YOUR_ACCOUNT"
```

***

## 6. Development Roadmap

| Phase | Timeline | Deliverable | Dependencies |
|---|---|---|---|
| 1. Data Pipeline | Week 1–2 | VIX/TQQQ data ingestion, PostgreSQL schema, IB connection | IB account, API keys |
| 2. ML Models | Week 2–4 | HMM, XGBoost, LSTM trained and validated | Historical data |
| 3. Strategy Engine | Week 4–6 | Core leg management logic, spread builder, order manager | ML models, IB connection |
| 4. Risk Management | Week 5–6 | Position sizing, margin tracking, circuit breakers | Strategy engine |
| 5. Backtesting | Week 6–8 | Walk-forward backtest, Monte Carlo, performance report | All components |
| 6. Dashboard | Week 7–8 | Streamlit dashboard, Slack alerts | All components |
| 7. Paper Trading | Week 9–12 | Run live on IB paper account, validate | Everything |
| 8. Live (small size) | Week 13+ | Go live with 1–2 contracts | Paper trading validation |

***

## 7. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| VIX spike doesn't come before long put expires | Theta decay eats retained put | Min DTE rule (14 days); abandon at $0.10 value |
| TQQQ bid-ask spread widens during vol spikes | Execution slippage on leg management | Use limit orders with price-walking algo; prefer monthly expirations[^24][^11] |
| ML model overfitting | False signals, bad trades | Walk-forward validation, ensemble averaging, weekly retraining[^1][^3] |
| TQQQ volatility decay on long holds | Basis erosion on underlying | Short DTE only (21–45 days), never hold spreads to expiry[^8][^43][^44] |
| Assignment risk when only one leg open | Unexpected stock assignment | Close or roll before expiration; monitor short put OI; prefer cash-secured sizing[^4][^45] |
| IB API disconnection during critical moment | Missed exit or entry | Auto-reconnect with backoff; manual override dashboard; health checks every 30s[^41][^35] |
| Regime model lag | Enters/exits late | Combine leading indicators (VIX futures term structure) with lagging (HMM state)[^1][^3] |

***

## 8. Expected Performance Benchmarks

Based on the research, reasonable performance targets for this strategy are:

- **VIX direction prediction accuracy:** 55–61%[^2][^18]
- **Regime detection accuracy:** 70–80% (HMM on VIX regimes)[^21][^20]
- **Leg-out success rate target:** 40–50% (retained long puts sold at profit)
- **Strategy win rate target:** 60–70% (including both full-spread closes and leg-outs)
- **Annual return target:** 15–25% on allocated capital (with defined risk)
- **Max drawdown target:** <15% with circuit breakers
- **Sharpe ratio target:** >1.0

The strategy should be benchmarked against a simpler baseline: selling the same put spreads and always closing at 50% profit, without any leg management. The leg management adds value only if the "leg-out success rate" compensates for the theta decay cost of holding retained long puts that expire worthless.

***

## 9. Files to Create for Antigravity

```
project/
├── config/
│   ├── config.yaml              # IB connection, API keys
│   ├── strategy_config.yaml     # Strategy parameters
│   └── ml_config.yaml           # ML hyperparameters
├── src/
│   ├── data/
│   │   ├── data_pipeline.py     # VIX/TQQQ/options data ingestion
│   │   ├── feature_engine.py    # Feature computation
│   │   └── db_manager.py        # PostgreSQL interface
│   ├── ml/
│   │   ├── regime_detector.py   # HMM VIX regime detection
│   │   ├── vix_predictor_xgb.py # XGBoost VIX direction
│   │   ├── vix_predictor_lstm.py# LSTM VIX prediction
│   │   ├── ensemble_predictor.py# Ensemble combiner
│   │   ├── rl_agent.py          # PPO optimal action (Phase 2)
│   │   └── model_trainer.py     # Training pipeline orchestrator
│   ├── strategy/
│   │   ├── vix_adaptive_strategy.py  # Core strategy state machine
│   │   ├── spread_builder.py    # Strike/expiry selection
│   │   └── leg_manager.py       # Leg-out logic
│   ├── execution/
│   │   ├── order_manager.py     # IB order placement
│   │   └── fill_monitor.py      # Fill tracking
│   ├── broker/
│   │   ├── ib_connection.py     # IB connection management
│   │   └── account_monitor.py   # Account/margin tracking
│   ├── risk/
│   │   ├── risk_manager.py      # Position sizing, limits
│   │   └── circuit_breaker.py   # Emergency stop logic
│   ├── backtest/
│   │   ├── data_loader.py       # Historical data prep
│   │   ├── options_simulator.py # BS option price simulation
│   │   ├── backtest_engine.py   # Walk-forward backtester
│   │   └── performance_report.py# Metrics & charts
│   ├── dashboard/
│   │   └── app.py               # Streamlit dashboard
│   ├── alerts/
│   │   └── alert_manager.py     # Slack/email notifications
│   └── main.py                  # Entry point / orchestrator
├── tests/
│   ├── test_regime_detector.py
│   ├── test_strategy.py
│   ├── test_spread_builder.py
│   ├── test_risk_manager.py
│   └── test_backtest.py
├── scripts/
│   ├── train_models.py          # One-off model training
│   ├── run_backtest.py          # Run full backtest
│   └── paper_trade.py           # Start paper trading
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── requirements.txt
└── README.md
```

This implementation plan provides Antigravity with everything needed to build, test, and deploy the system incrementally, starting with data infrastructure and ML models, then layering on the strategy logic, risk management, and live execution.

---

## References

1. [VIX constant maturity futures trading strategy: A walk-forward ...](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0302289) - This study employs seven advanced machine learning approaches to conduct numerical predictions of th...

2. [Neural networks and arbitrage in the VIX: A deep learning approach ...](https://pmc.ncbi.nlm.nih.gov/articles/PMC7659419/) - By just using a small subset of all options for the VIX calculation and knowing their weights, we ca...

3. [Improving S&P 500 Volatility Forecasting through Regime-Switching ...](https://arxiv.org/html/2510.03236v1) - This model is designed to cluster on the daily, weekly, and monthly RV and VIX averages, however, th...

4. [Short Put Vertical Spread Options Strategy Explained](https://tastytrade.com/learn/trading-products/options/short-put-vertical-spread/) - A short put vertical spread is a bullish, defined risk short premium strategy. Learn how it works an...

5. [What are Vertical Spread Options? | tastylive](https://www.tastylive.com/concepts-strategies/vertical-spread) - Typically, vertical spreads are closed prior to expiration to avoid unwanted assignment of shares. Y...

6. [RISK of Legging from Vertical Spreads?](https://www.youtube.com/watch?v=mop5JbNQpaQ) - Ready to start trading? Try Unusual Option Activity Essential. Learn how you can follow the "smart m...

7. [Pros & Cons of Leveraged ETFs When Selling Stock Options](https://www.thebluecollarinvestor.com/pros-cons-of-leveraged-etfs-when-selling-stock-options/) - ... volatility of 17% (lower chart); Note the implied volatility o TQQQ is triple that of QQQ. This ...

8. [TQQQ's Volatility and Nasdaq Corrections: Navigating ...](https://www.ainvest.com/news/tqqq-volatility-nasdaq-corrections-navigating-leveraged-etf-risks-shifting-market-2508/) - TQQQ's Volatility and Nasdaq Corrections: Navigating Leveraged ETF Risks in a Shifting Market

9. [If you follow the VIX, there seems to be an inverse correlation ...](https://www.facebook.com/groups/922304852914465/posts/1302438401567773/) - If you follow the VIX, there seems to be an inverse correlation between the two. Here's a chart on G...

10. [TQQQ: How I Leverage And Why I'm Not Doing It Now](https://seekingalpha.com/article/4764986-tqqq-how-i-leverage-and-why-im-not-doing-it-now) - The overall concept is to leverage more when VIX is high and vice versa as historical data have sugg...

11. [TQQQ Options | ProShares UltraPro QQQ Options Chain, IV & Greeks](https://apexvol.com/options/tqqq) - Real-time options analytics with Greeks, volatility analysis, and strategy builder. Free AAPL demo a...

12. [How to properly close a vertical spread](https://www.reddit.com/r/RealDayTrading/comments/owkj4z/how_to_properly_close_a_vertical_spread/) - How to properly close a vertical spread

13. [Are there situations where closing 1 leg of a vertical spread makes sense?](https://www.reddit.com/r/options/comments/g4qs0h/are_there_situations_where_closing_1_leg_of_a/)

14. [Legging out of verticals](https://www.reddit.com/r/options/comments/1fkxfbr/legging_out_of_verticals/) - Legging out of verticals

15. [What is a Long Put Vertical Spread? - Tastytrade](https://tastytrade.com/learn/trading-products/options/long-put-vertical-spread/) - A defined-risk vertical spread is no longer a defined risk position if one leg of the spread expires...

16. [Trying To Catch A VIX Spike With A Vertical Spread](https://optionstradingiq.com/trying-to-catch-a-vix-spike/) - What does that mean? A few definitions are in order here.

17. [Rolling Strategies](https://tradefundrr.com/vertical-spreads-explained/) - Discover how vertical spreads in options trading can limit risk while maximizing profit potential. L...

18. [[PDF] Enhancing CBOE VIX Forecasting: A Comparative Study of GARCH ...](https://thesis.eur.nl/pub/73749/Thesis_Anna_Grefhorst.pdf)

19. [VIX constant maturity futures trading strategy - PMC - NIH](https://pmc.ncbi.nlm.nih.gov/articles/PMC11029606/) - This study employs seven advanced machine learning approaches to conduct numerical predictions of th...

20. [Market Regime Detection using Hidden Markov Models in QSTrader](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/) - In this article the Hidden Markov Model will be utilised within the QSTrader framework as a risk-man...

21. [Market Regime using Hidden Markov Model - QuantInsti Blog](https://blog.quantinsti.com/regime-adaptive-trading-python/) - This project builds a Python-based adaptive trading strategy that: Detects current market regime usi...

22. [Market Regime Detection using Hidden Markov Models](https://www.pyquantlab.com/articles/Market%20Regime%20Detection%20using%20Hidden%20Markov%20Models.html)

23. [How liquid is TQQQ](https://www.reddit.com/r/TQQQ/comments/1cvsap0/how_liquid_is_tqqq/)

24. [I am getting burned on bid-ask spreads](https://www.reddit.com/r/thetagang/comments/mkznu1/i_am_getting_burned_on_bidask_spreads/)

25. [Forecasting and Hedging the Volatility Index of Financial Markets via ...](https://journals.sagepub.com/doi/full/10.1177/21582440251396044) - In this study, a XGboost (eXtreme Gradient Boosting) model is employed as the principal algorithm fo...

26. [[PDF] to Long-Term Realized Volatility Forecasting using Extreme ... - SSRN](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4267541_code5502887.pdf?abstractid=4267541&mirid=1) - We adopt Extreme Gradient Boosting (XGBoost) to forecast realized volatility. This is motivated by X...

27. [XGBoost in prediction](https://www.reddit.com/r/quant/comments/1kgilnv/xgboost_in_prediction/) - XGBoost in prediction

28. [Forecasting and trading on the VIX futures market: A neural network approach based on open to close returns and coincident indicators](https://www.sciencedirect.com/science/article/abs/pii/S0169207019301372) - Previous work has highlighted the difficulty of obtaining accurate and economically significant pred...

29. [Modeling_the_VIX_with_LSTM - ellenicoleroberts.github.io](https://ellenicoleroberts.github.io/Modeling_the_VIX_with_LSTM/)

30. [GitHub - AzarAnalytics/Multivariate-TimeSeries-Using-LSTM-SP500-Volatility-Index-](https://github.com/AzarAnalytics/Multivariate-TimeSeries-Using-LSTM-SP500-Volatility-Index-) - Contribute to AzarAnalytics/Multivariate-TimeSeries-Using-LSTM-SP500-Volatility-Index- development b...

31. [Chapter 6: Reinforcement Learning and Inverse ... - CFA Institute](https://rpc.cfainstitute.org/research/foundation/2025/chapter-6-reinforcement-learning-inverse-reinforcement-learning) - How reinforcement learning in finance improves trading, risk management, and portfolio optimization ...

32. [Reinforcement Learning for Stock Option Trading](https://arc.cct.ie/cgi/viewcontent.cgi?article=1044&context=ict)

33. ["Reinforcement Learning for Stock Option Trading" by James Garza](https://arc.cct.ie/ict/42/) - Reinforcement learning has recently seen an increase in popularity due to its ability to learn from ...

34. [[PDF] Deep Reinforcement Learning for Trading](https://www.oxford-man.ox.ac.uk/wp-content/uploads/2020/06/Deep-Reinforcement-Learning-for-Trading.pdf) - A Complete Guide to the Futures Market: Technical. Analysis, Trading Systems, Fundamental Analysis, ...

35. [How to use Python and ib_insync to Automate Stock Trades](https://www.blackbullsoftware.com/blog/python-ib-insync-automate-trades) - A comprehensive guide to using ib_insync for automated trading with Interactive Brokers. Learn how t...

36. [IB_INSYNC - getting stuck on PendingSubmit with a vertical spread](https://www.reddit.com/r/interactivebrokers/comments/18r0qi9/ib_insync_getting_stuck_on_pendingsubmit_with_a/) - I can place a spread order in the Live or Paper account with no error, Iron Condors too. The order i...

37. [Historical Data for Cboe VIX® Index and Other Volatility Indices](https://www.cboe.com/tradable_products/vix/vix_historical_data)

38. [CBOE Volatility Index: VIX (VIXCLS) | FRED | St. Louis Fed](https://fred.stlouisfed.org/series/VIXCLS) - Graph and download economic data for CBOE Volatility Index: VIX (VIXCLS) from 1990-01-02 to 2026-02-...

39. [datasets/finance-vix: CBOE Volatility Index (VIX) time- ...](https://github.com/datasets/finance-vix) - CBOE Volatility Index (VIX) time-series dataset including daily open, close, high and low. - dataset...

40. [Top 7 Sources to Download Historical Options Data - QuantVPS](https://www.quantvps.com/blog/download-historical-options-data) - 1. Finnhub. Finnhub stands out as a robust resource for historical options data, designed to support...

41. [GitHub - trustdan/IBKR-trader: An automated trading system ...](https://github.com/trustdan/IBKR-trader) - An automated trading system that implements vertical spread trading strategies using Interactive Bro...

42. [I can't create straddle spread order. · Issue #223 · erdewit/ib_insync](https://github.com/erdewit/ib_insync/issues/223) - spread_contract = Contract() spread_contract.symbol = "TSLA" spread_contract.secType = "BAG" spread_...

43. [TQQQ: Leveraged ETF Decay - July 2024 Update | Seeking Alpha](https://seekingalpha.com/article/4706085-tqqq-leveraged-etf-decay-july-2024-update) - Analyzing hidden costs of investing in leveraged ETFs through mathematical basis. Click here to read...

44. [Leveraged ETFs and Volatility: SPXL and TQQQ](https://menthorq.com/guide/leveraged-etfs-and-volatility-spxl-and-tqqq/) - Leveraged ETFs such as SPXL and TQQQ promise enhanced returns in strong markets. But how are they af...

45. [Risks of Options Assignment | Charles Schwab](https://www.schwab.com/learn/story/risks-options-assignment) - A trader with a call vertical spread where both options are ITM and the ex-dividend date is approach...

