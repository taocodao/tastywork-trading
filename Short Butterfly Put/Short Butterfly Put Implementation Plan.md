# Short Butterfly Put Strategy: Deep Research & AI-Powered Implementation Plan

***

## Part 1: Strategy Deep Dive

### 1.1 What Is the Short Put Butterfly?

The Short Put Butterfly is an options strategy that profits when the underlying asset's price remains near a target strike price at expiration. It involves three strike prices with the same expiration date:[^1][^2]

- **Buy 1 put** at a lower strike price (OTM wing)
- **Sell 2 puts** at a middle strike price (ATM body)
- **Buy 1 put** at a higher strike price (ITM wing)

The wings must be equidistant from the body. This creates a net credit upon entry — the premium collected from selling 2 middle puts exceeds the cost of buying the 2 wing puts.[^3][^2]

> **Important distinction:** Despite the name "short," this is actually a *credit* spread that profits from price stability and time decay — not from a directional move.

### 1.2 Payoff Structure & Mathematics

| Parameter | Formula | Example ($45/$50/$55 strikes, $2 credit) |
|---|---|---|
| **Max Profit** | Net credit received | $2.00 per share ($200/contract) |
| **Max Loss** | Wing width − credit | $5 − $2 = $3.00 ($300/contract) |
| **Lower Breakeven** | Middle strike − credit | $50 − $2 = $48.00 |
| **Upper Breakeven** | Middle strike + credit | $50 + $2 = $52.00 |
| **Profit Zone** | Between breakevens | $48 to $52 |
| **Risk/Reward Ratio** | Max loss ÷ Max profit | 3:2 (1.5:1) |

The maximum profit occurs **only** when the underlying closes exactly at the middle strike ($50) at expiration, causing all puts to expire worthless and the trader keeps the full credit.[^2][^3]

The maximum loss occurs if the price finishes **below the lower wing** ($45) or **above the upper wing** ($55) at expiration. In this scenario, the short puts are exercised while the long puts expire worthless.[^3]

### 1.3 Greeks Profile

| Greek | Behavior | Trading Implication |
|---|---|---|
| **Delta** | Near zero at entry (ATM body) | Directionally neutral — no bias needed[^4] |
| **Gamma** | Negative near body | Hurts if price oscillates around middle strike; low gamma preferred[^4] |
| **Theta** | Positive | Time decay benefits the position — premiums erode into expiration[^4] |
| **Vega** | Low/negative preferred | Low IV environment ideal; IV expansion can hurt[^4] |
| **Rho** | Minimal impact | Interest rate changes have negligible effect[^4] |

**Key insight:** The strategy is fundamentally a **theta play** — it profits from the passage of time when the underlying stays range-bound. Unlike many short premium strategies, it has **defined risk** on both sides.[^2]

### 1.4 Ideal Market Conditions

- **IV Rank/Percentile below 30-40%** — options are relatively expensive to sell[^5][^2]
- **Range-bound price action** — stock oscillating between clear support/resistance[^2]
- **No upcoming catalysts** — or entering just before earnings to capture IV crush post-announcement[^2]
- **30-60 DTE** — enough time for theta decay without excessive assignment risk[^2]

***

## Part 2: Comprehensive Pros & Cons Analysis

### 2.1 Advantages

1. **Defined Risk** — Maximum loss is strictly capped at wing width minus credit. Unlike naked short puts, you always know your worst case.[^3][^2]
2. **Net Credit Entry** — The trade generates income upfront, lowering breakeven points and providing a profit buffer.[^2]
3. **Positive Theta** — Time decay works in your favor. As expiration approaches, option premiums erode, benefiting the short positions.[^4]
4. **Low Margin Requirements** — Typically ~20% of max loss vs. full cash-secured requirements for naked shorts. Frees capital for other positions.[^2]
5. **Delta Neutral** — No directional bias needed at entry. Profits from price consolidation rather than predicting direction.[^4]
6. **High Probability of Profit** — When targeting partial profit (e.g., 50% of max), probability of profit can reach ~80%.[^2]
7. **Flexible Adjustments** — Can leg out to convert to iron condor, roll strikes, or close one side if the underlying trends.[^2]
8. **Works in Quiet Markets** — Ideal for periods when markets are range-bound and other strategies underperform.[^3]

### 2.2 Disadvantages

1. **Capped Profit** — Maximum gain is limited to the net credit. Requires precise pinning at middle strike for max profit, which is statistically rare.[^3][^2]
2. **Multi-Leg Complexity** — 3 legs = higher commissions, wider bid-ask spreads, and execution slippage. Each leg adds friction.[^3]
3. **Assignment Risk** — Short puts can be assigned early if deep ITM, tying up capital and incurring fees.[^2]
4. **Vulnerable to Large Moves** — Any strong directional move beyond the wings triggers max loss. Black swan events are particularly dangerous.[^3]
5. **IV Spike Risk** — Sudden volatility expansion increases the value of all puts, hurting the net position despite defined risk.[^3]
6. **Liquidity Dependent** — Requires liquid options with tight spreads. Illiquid underlyings cause poor fills and unpredictable execution.[^3]
7. **Expiration Management** — Requires active monitoring as expiration approaches; pin risk near wings can cause unexpected outcomes.[^2]
8. **Opportunity Cost** — Capital tied in margin could be deployed in higher-return strategies during trending markets.

### 2.3 Viability Assessment

**Verdict: VIABLE with AI enhancement.** The Short Put Butterfly is a legitimate income strategy for range-bound, low-volatility environments. Its defined risk profile makes it suitable for systematic/algorithmic deployment. However, it requires:

- Precise market regime identification (when to deploy vs. avoid)
- Optimal strike/DTE selection under varying IV conditions
- Automated entry/exit/adjustment logic
- Position sizing calibrated to account risk tolerance

These requirements are **ideal use cases for AI/ML augmentation**.

***

## Part 3: AI/ML Leverage Opportunities

### 3.1 AI Enhancement Architecture

```
┌──────────────────────────────────────────────────┐
│              AI SHORT BUTTERFLY ENGINE            │
├──────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Market    │  │ Strategy │  │  Execution   │  │
│  │ Analysis  │→ │ Selection│→ │  Engine      │  │
│  │ Layer     │  │ Layer    │  │              │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│       │              │              │            │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ IV Rank  │  │ Strike   │  │  Order Mgmt  │  │
│  │ Scanner  │  │ Optimizer│  │  & Fills     │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│       │              │              │            │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Regime   │  │ DTE/Wing │  │  Position    │  │
│  │ Detector │  │ Selector │  │  Monitor     │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│       │              │              │            │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Vol Fore-│  │ Risk     │  │  Adjustment  │  │
│  │ caster   │  │ Sizer    │  │  Engine      │  │
│  └──────────┘  └──────────┘  └──────────────┘  │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │        Reinforcement Learning Agent       │   │
│  │    (Entry Timing / Exit Optimization)     │   │
│  └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

### 3.2 Module-by-Module AI Integration

#### Module A: IV Rank/Percentile Scanner

**Purpose:** Identify underlyings where IV is "cheap" (low percentile) — ideal entry conditions for short butterfly puts.[^6][^5]

**AI Method:** Statistical screening + ML anomaly detection

```python
# Core IV Rank/Percentile Logic
def compute_iv_rank(current_iv: float, iv_history_52w: list) -> float:
    """IV Rank: where current IV sits between 52-week high/low"""
    iv_min = min(iv_history_52w)
    iv_max = max(iv_history_52w)
    if iv_max == iv_min:
        return 50.0
    return ((current_iv - iv_min) / (iv_max - iv_min)) * 100

def compute_iv_percentile(current_iv: float, iv_history_52w: list) -> float:
    """IV Percentile: % of historical observations below current IV"""
    below_count = sum(1 for iv in iv_history_52w if iv < current_iv)
    return (below_count / len(iv_history_52w)) * 100
```

**Entry Signal:** IV Rank < 30 AND IV Percentile < 40[^5][^2]

#### Module B: Volatility Regime Detection

**Purpose:** Classify current market as Low-Vol / Normal / High-Vol / Transition to determine if short butterfly is appropriate.[^7][^8]

**AI Method:** Hidden Markov Model (HMM) + rolling volatility features

```python
# Regime Detection Features
features = {
    'realized_vol_10d': rolling_std(returns, 10) * sqrt(252),
    'realized_vol_30d': rolling_std(returns, 30) * sqrt(252),
    'vix_level': current_vix,
    'vix_term_structure': vix_front_month - vix_second_month,  # contango/backwardation
    'iv_rv_spread': current_iv - realized_vol_30d,  # variance risk premium
    'put_call_ratio': put_volume / call_volume,
    'skew_index': skew_25d_put - skew_25d_call,
}

# HMM States
REGIMES = {
    0: 'LOW_VOL',       # DEPLOY short butterfly
    1: 'NORMAL',        # DEPLOY with tighter wings
    2: 'HIGH_VOL',      # AVOID - too much movement risk
    3: 'TRANSITION',    # WAIT - regime shifting
}
```

**Deploy short butterfly ONLY in LOW_VOL and NORMAL regimes.**

#### Module C: GARCH-SVR Volatility Forecaster

**Purpose:** Predict implied volatility 7-30 days forward to time entries when IV is likely to compress further.[^7]

**AI Method:** Two-stage GARCH(1,1) → Support Vector Regression

The GARCH-SVR hybrid model has shown maximum arbitrage returns of 0.1858 in empirical tests with CSI 300 ETF options, outperforming standalone GARCH, SVR, LSTM, and MLP models.[^7]

```python
# Stage 1: GARCH(1,1) for conditional variance
from arch import arch_model
garch = arch_model(returns, vol='Garch', p=1, q=1)
garch_result = garch.fit(disp='off')
garch_forecast = garch_result.forecast(horizon=30)

# Stage 2: SVR refinement
from sklearn.svm import SVR
features = [garch_residuals, historical_iv, realized_vol, vix_level, skew]
svr = SVR(kernel='rbf', C=100, gamma=0.1, epsilon=0.01)
svr.fit(X_train, y_train_iv)
iv_forecast_30d = svr.predict(X_current)
```

#### Module D: Reinforcement Learning Entry/Exit Timing

**Purpose:** Learn optimal entry timing, profit-taking thresholds, and adjustment triggers from historical performance.[^9][^10]

**AI Method:** Proximal Policy Optimization (PPO)

```python
# RL State Space
state = {
    'iv_rank': float,           # 0-100
    'regime': int,              # 0-3
    'days_to_expiry': int,      # DTE remaining
    'underlying_distance_from_body': float,  # % from middle strike
    'current_pnl_pct': float,   # current P&L as % of max profit
    'theta_remaining': float,   # theta decay left to capture
    'vix_level': float,
    'delta_position': float,    # net portfolio delta
}

# RL Action Space
actions = [
    'ENTER_BUTTERFLY',      # Open new position
    'HOLD',                 # Maintain current position
    'TAKE_PROFIT',          # Close at current profit
    'STOP_LOSS',            # Close to limit loss
    'ADJUST_TO_CONDOR',     # Leg out to iron condor
    'ROLL_STRIKES',         # Roll body to new ATM
    'SKIP',                 # No action this period
]

# Reward Function
def reward(action, pnl_change, risk_adjusted_return, transaction_cost):
    return pnl_change - (transaction_cost * 0.5) + (risk_adjusted_return * 0.3)
```

#### Module E: ML-Optimized Strike/DTE Selection

**Purpose:** Select optimal wing width, body strike, and DTE for current market conditions.

**AI Method:** Gradient Boosted Trees (XGBoost) trained on historical butterfly outcomes

```python
# Feature Engineering for Strike Selection
strike_features = {
    'underlying_price': current_price,
    'atm_iv': at_the_money_iv,
    'iv_skew': put_25d_iv - call_25d_iv,
    'term_structure_slope': iv_60d - iv_30d,
    'support_distance': current_price - nearest_support,
    'resistance_distance': nearest_resistance - current_price,
    'atr_14': average_true_range_14d,
    'expected_move': atm_straddle_price,
    'regime': current_regime,
    'earnings_days_away': days_until_earnings,
}

# Output: Optimal configuration
optimal_config = {
    'wing_width': 5,            # $5 between body and each wing
    'body_strike': round_to_strike(current_price),
    'dte': 45,                  # days to expiration
    'target_credit': 1.50,      # minimum acceptable credit
    'profit_target_pct': 50,    # take profit at 50% of max
    'stop_loss_pct': 200,       # stop at 2x credit received
}
```

***

## Part 4: Comprehensive Implementation Plan for Antigravity

### 4.1 Technology Stack

| Component | Technology | Rationale |
|---|---|---|
| **Backend** | Python 3.11+ / TypeScript (Node.js) | Matches existing TradeMind.bot stack |
| **Broker API** | `ib_insync` (IB) + Tastytrade API | Dual broker support[^11] |
| **ML Framework** | scikit-learn, XGBoost, PyTorch | Full ML pipeline |
| **RL Framework** | Stable-Baselines3 (PPO) | Proven RL for finance |
| **Database** | PostgreSQL (RDS) | Existing infrastructure |
| **Queue** | Redis / AWS SQS | Async job processing |
| **Deployment** | AWS EC2 + Docker | Existing infrastructure |
| **Monitoring** | Grafana + CloudWatch | Real-time dashboards |
| **Frontend** | React/Next.js (Vercel) | TradeMind.bot integration |

### 4.2 Database Schema

```sql
-- Core Tables

CREATE TABLE butterfly_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    broker VARCHAR(20) NOT NULL,  -- 'IB' or 'TASTYTRADE'
    underlying VARCHAR(10) NOT NULL,
    strategy_type VARCHAR(30) DEFAULT 'SHORT_PUT_BUTTERFLY',
    
    -- Strike Configuration
    lower_wing_strike DECIMAL(10,2) NOT NULL,
    body_strike DECIMAL(10,2) NOT NULL,
    upper_wing_strike DECIMAL(10,2) NOT NULL,
    wing_width DECIMAL(10,2) NOT NULL,
    expiration_date DATE NOT NULL,
    dte_at_entry INT NOT NULL,
    
    -- Premium & P/L
    net_credit DECIMAL(10,4) NOT NULL,
    max_profit DECIMAL(10,4) NOT NULL,
    max_loss DECIMAL(10,4) NOT NULL,
    lower_breakeven DECIMAL(10,2) NOT NULL,
    upper_breakeven DECIMAL(10,2) NOT NULL,
    current_pnl DECIMAL(10,4) DEFAULT 0,
    realized_pnl DECIMAL(10,4),
    
    -- Greeks at Entry
    delta_at_entry DECIMAL(8,4),
    theta_at_entry DECIMAL(8,4),
    vega_at_entry DECIMAL(8,4),
    gamma_at_entry DECIMAL(8,4),
    iv_rank_at_entry DECIMAL(5,2),
    iv_percentile_at_entry DECIMAL(5,2),
    regime_at_entry VARCHAR(20),
    
    -- Leg Order IDs (for broker tracking)
    lower_wing_order_id VARCHAR(50),
    body_order_id VARCHAR(50),
    upper_wing_order_id VARCHAR(50),
    combo_order_id VARCHAR(50),
    
    -- Management
    quantity INT NOT NULL DEFAULT 1,
    profit_target_pct DECIMAL(5,2) DEFAULT 50.00,
    stop_loss_pct DECIMAL(5,2) DEFAULT 200.00,
    status VARCHAR(20) DEFAULT 'OPEN',  -- OPEN, CLOSED, ADJUSTED, EXPIRED
    adjustment_type VARCHAR(30),  -- NONE, ROLLED, CONDOR_CONVERSION
    close_reason VARCHAR(50),
    
    -- ML Metadata
    ml_entry_score DECIMAL(5,4),
    ml_strike_score DECIMAL(5,4),
    rl_action_taken VARCHAR(30),
    
    -- Timestamps
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    last_monitored_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE butterfly_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    underlying VARCHAR(10) NOT NULL,
    scan_timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    -- Screening Scores
    iv_rank DECIMAL(5,2),
    iv_percentile DECIMAL(5,2),
    regime VARCHAR(20),
    regime_confidence DECIMAL(5,4),
    vol_forecast_30d DECIMAL(8,4),
    vol_forecast_direction VARCHAR(10),  -- DECLINING, STABLE, RISING
    
    -- Recommended Config
    recommended_body_strike DECIMAL(10,2),
    recommended_wing_width DECIMAL(10,2),
    recommended_dte INT,
    estimated_credit DECIMAL(10,4),
    estimated_probability_profit DECIMAL(5,2),
    ml_composite_score DECIMAL(5,4),
    
    -- Technical Context
    support_level DECIMAL(10,2),
    resistance_level DECIMAL(10,2),
    atr_14 DECIMAL(10,4),
    expected_move DECIMAL(10,4),
    
    approved BOOLEAN DEFAULT FALSE,
    approved_at TIMESTAMPTZ
);

CREATE TABLE butterfly_greeks_history (
    id SERIAL PRIMARY KEY,
    position_id UUID REFERENCES butterfly_positions(id),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    underlying_price DECIMAL(10,2),
    delta DECIMAL(8,4),
    gamma DECIMAL(8,4),
    theta DECIMAL(8,4),
    vega DECIMAL(8,4),
    iv_current DECIMAL(8,4),
    pnl_unrealized DECIMAL(10,4),
    dte_remaining INT
);

CREATE TABLE ml_model_performance (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(50),
    model_version VARCHAR(20),
    metric_name VARCHAR(50),
    metric_value DECIMAL(10,6),
    evaluation_date DATE,
    sample_size INT,
    notes TEXT
);

CREATE TABLE rl_training_episodes (
    id SERIAL PRIMARY KEY,
    episode_number INT,
    total_reward DECIMAL(10,4),
    avg_pnl DECIMAL(10,4),
    win_rate DECIMAL(5,4),
    sharpe_ratio DECIMAL(8,4),
    max_drawdown DECIMAL(8,4),
    training_timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_positions_status ON butterfly_positions(status);
CREATE INDEX idx_positions_user ON butterfly_positions(user_id);
CREATE INDEX idx_positions_expiry ON butterfly_positions(expiration_date);
CREATE INDEX idx_candidates_score ON butterfly_candidates(ml_composite_score DESC);
CREATE INDEX idx_greeks_position ON butterfly_greeks_history(position_id, timestamp);
```

### 4.3 Module Specifications

***

#### MODULE 1: Universe Scanner & IV Screener
**File:** `modules/scanner/iv_screener.py`

**Purpose:** Scan a universe of optionable stocks/ETFs and rank by short butterfly suitability.

**Inputs:**
- Watchlist of tickers (default: SPY, QQQ, IWM, AAPL, MSFT, AMZN, GOOGL, META, NVDA, TSLA + configurable)
- Market data feed from broker API

**Processing Logic:**
1. Fetch option chains for each ticker (30-60 DTE range)
2. Calculate IV Rank and IV Percentile using 252-day lookback[^5]
3. Compute Variance Risk Premium (VRP) = IV - Realized Vol[^12]
4. Score each ticker: `composite_score = (0.4 * iv_rank_score) + (0.3 * vrp_score) + (0.2 * liquidity_score) + (0.1 * regime_score)`
5. Filter: IV Rank < 30, IV Percentile < 40, average daily volume > 1M shares, option bid-ask spread < 5% of mid

**Output:** Ranked list of `butterfly_candidates` records saved to database

**Cron Schedule:** Every 30 minutes during market hours (9:30-16:00 ET)

***

#### MODULE 2: Volatility Regime Detector
**File:** `modules/ml/regime_detector.py`

**Purpose:** Classify current market regime to gate butterfly deployment.

**Model:** Hidden Markov Model (HMM) with 4 states
- State 0: LOW_VOL → **DEPLOY** (full position size)
- State 1: NORMAL → **DEPLOY** (75% position size)
- State 2: HIGH_VOL → **AVOID** (no new positions)
- State 3: TRANSITION → **WAIT** (no new positions, monitor existing)

**Features (per ticker + market-wide):**
- 10-day and 30-day realized volatility
- VIX level and VIX term structure (contango/backwardation)
- Put/call ratio
- IV skew (25-delta)
- Correlation with SPX

**Training:**
- Historical data: 5+ years of daily data
- Retrain monthly
- Validation: out-of-sample regime prediction accuracy > 70%

***

#### MODULE 3: GARCH-SVR Volatility Forecaster
**File:** `modules/ml/vol_forecaster.py`

**Purpose:** Forecast 30-day forward IV to predict IV compression (favorable for short butterfly).[^7]

**Architecture:**
1. GARCH(1,1) → conditional variance estimate
2. Feature extraction: GARCH residuals, historical IV, RV, VIX, skew, term structure
3. SVR (RBF kernel) → refined IV forecast
4. Output: predicted IV in 30 days + confidence interval

**Entry signal:** Forecasted IV < Current IV (IV compression expected)

***

#### MODULE 4: Strike & DTE Optimizer
**File:** `modules/ml/strike_optimizer.py`

**Purpose:** Select optimal wing width, body strike, and DTE for each candidate.

**Model:** XGBoost regressor trained on historical butterfly outcomes

**Features:**
- Current price, ATM IV, IV skew, term structure slope
- Distance to support/resistance levels
- ATR(14), expected move (straddle price)
- Regime classification, earnings proximity
- Sector and market-wide correlation

**Target Variable:** Risk-adjusted P&L (Sharpe) of the butterfly at various configurations

**Output per candidate:**
```json
{
    "body_strike": 450,
    "wing_width": 5,
    "dte": 45,
    "min_acceptable_credit": 1.50,
    "profit_target_pct": 50,
    "stop_loss_multiplier": 2.0,
    "expected_probability_profit": 0.78,
    "expected_sharpe": 1.2,
    "confidence": 0.85
}
```

***

#### MODULE 5: RL Entry/Exit Agent
**File:** `modules/rl/butterfly_agent.py`

**Purpose:** Optimize entry timing, profit-taking, and adjustment decisions.

**Algorithm:** PPO (Proximal Policy Optimization) via Stable-Baselines3

**State Space (12 dimensions):**
```python
state = [
    iv_rank,                    # 0-100
    iv_percentile,              # 0-100
    regime,                     # 0-3
    vol_forecast_direction,     # -1, 0, 1
    dte_remaining,              # days
    price_distance_from_body,   # % deviation
    current_pnl_pct,            # % of max profit
    theta_remaining,            # $ theta left
    vega_exposure,              # position vega
    delta_exposure,             # position delta
    vix_level,                  # absolute VIX
    hour_of_day,                # 0-6.5 (market hours)
]
```

**Action Space (7 discrete actions):**
```python
actions = {
    0: 'ENTER',         # Open new butterfly
    1: 'HOLD',          # Maintain position
    2: 'TAKE_PROFIT',   # Close for profit
    3: 'STOP_LOSS',     # Close to limit loss
    4: 'ADJUST_CONDOR', # Convert to iron condor
    5: 'ROLL',          # Roll to new expiration
    6: 'SKIP',          # Do nothing
}
```

**Reward Function:**
```python
def calculate_reward(action, state, next_state):
    pnl_change = next_state.pnl - state.pnl
    transaction_cost = get_commission_cost(action) * -1
    time_penalty = -0.01 if action == 'HOLD' and dte < 7 else 0
    risk_bonus = 0.1 if action == 'TAKE_PROFIT' and pnl_pct > 0.4 else 0
    drawdown_penalty = -0.5 if max_drawdown > 0.5 else 0
    
    return pnl_change + transaction_cost + time_penalty + risk_bonus + drawdown_penalty
```

**Training:**
- Environment: Custom Gym environment with historical options data
- Episodes: 100,000+ with 10-fold cross-validation
- Evaluation: Paper trade for 30 days before live deployment

***

#### MODULE 6: Execution Engine
**File:** `modules/execution/butterfly_executor.py`

**Purpose:** Place, monitor, and manage butterfly orders on IB and Tastytrade.

**IB Execution (ib_insync):**
```python
from ib_insync import IB, Option, ComboLeg, Contract, LimitOrder, TagValue

class ButterflyExecutor:
    def __init__(self, ib: IB):
        self.ib = ib
    
    def create_butterfly_contract(
        self, symbol: str, expiry: str, 
        lower_strike: float, body_strike: float, upper_strike: float
    ) -> Contract:
        """Build a BAG contract for short put butterfly"""
        
        # Get conIds for each leg
        lower_put = Option(symbol, expiry, lower_strike, 'P', 'SMART')
        body_put = Option(symbol, expiry, body_strike, 'P', 'SMART')
        upper_put = Option(symbol, expiry, upper_strike, 'P', 'SMART')
        
        self.ib.qualifyContracts(lower_put, body_put, upper_put)
        
        # Build combo contract
        combo = Contract()
        combo.symbol = symbol
        combo.secType = 'BAG'
        combo.exchange = 'SMART'
        combo.currency = 'USD'
        
        # Leg 1: Buy 1 lower wing put
        leg1 = ComboLeg()
        leg1.conId = lower_put.conId
        leg1.ratio = 1
        leg1.action = 'BUY'
        leg1.exchange = 'SMART'
        
        # Leg 2: Sell 2 body puts
        leg2 = ComboLeg()
        leg2.conId = body_put.conId
        leg2.ratio = 2
        leg2.action = 'SELL'
        leg2.exchange = 'SMART'
        
        # Leg 3: Buy 1 upper wing put
        leg3 = ComboLeg()
        leg3.conId = upper_put.conId
        leg3.ratio = 1
        leg3.action = 'BUY'
        leg3.exchange = 'SMART'
        
        combo.comboLegs = [leg1, leg2, leg3]
        return combo
    
    def place_butterfly(
        self, combo: Contract, quantity: int,
        limit_price: float
    ) -> dict:
        """Place the short put butterfly as a combo limit order"""
        
        order = LimitOrder(
            action='SELL',  # Selling the butterfly = short butterfly
            totalQuantity=quantity,
            lmtPrice=limit_price,
            tif='GTC',
        )
        order.smartComboRoutingParams = [
            TagValue('NonGuaranteed', '1')
        ]
        
        trade = self.ib.placeOrder(combo, order)
        self.ib.sleep(1)
        
        return {
            'order_id': trade.order.orderId,
            'status': trade.orderStatus.status,
            'trade': trade
        }
    
    def close_butterfly(self, combo: Contract, quantity: int, limit_price: float):
        """Close position by buying back the butterfly"""
        order = LimitOrder(
            action='BUY',
            totalQuantity=quantity,
            lmtPrice=limit_price,
            tif='GTC',
        )
        order.smartComboRoutingParams = [
            TagValue('NonGuaranteed', '1')
        ]
        return self.ib.placeOrder(combo, order)
```

**Tastytrade Execution:**
```python
class TastytradeExecutor:
    """Adapter for Tastytrade API butterfly execution"""
    
    async def place_butterfly(self, config: dict) -> dict:
        # Use Tastytrade's native multi-leg order API
        legs = [
            {'type': 'PUT', 'strike': config['lower_strike'], 
             'action': 'BUY_TO_OPEN', 'quantity': config['quantity']},
            {'type': 'PUT', 'strike': config['body_strike'],
             'action': 'SELL_TO_OPEN', 'quantity': config['quantity'] * 2},
            {'type': 'PUT', 'strike': config['upper_strike'],
             'action': 'BUY_TO_OPEN', 'quantity': config['quantity']},
        ]
        return await self.tastytrade_client.place_complex_order(
            symbol=config['symbol'],
            legs=legs,
            expiration=config['expiration'],
            price_type='CREDIT',
            price=config['limit_credit'],
            time_in_force='GTC'
        )
```

***

#### MODULE 7: Position Monitor & Risk Manager
**File:** `modules/risk/position_monitor.py`

**Purpose:** Real-time monitoring, Greeks tracking, and automated risk management.

**Monitoring Loop (every 60 seconds during market hours):**

```python
class PositionMonitor:
    # Risk thresholds (configurable per user)
    MAX_PORTFOLIO_BUTTERFLY_ALLOCATION = 0.20  # 20% of portfolio
    MAX_SINGLE_POSITION_RISK = 0.02            # 2% of portfolio per position
    MAX_DELTA_EXPOSURE = 0.15                   # net delta < 15%
    MAX_CONCURRENT_POSITIONS = 5
    
    async def monitor_loop(self):
        while market_is_open():
            for position in get_open_positions():
                # 1. Update Greeks
                greeks = await self.fetch_current_greeks(position)
                self.save_greeks_snapshot(position, greeks)
                
                # 2. Calculate current P&L
                current_pnl = self.calculate_pnl(position, greeks)
                pnl_pct = current_pnl / position.max_profit
                
                # 3. Check exit conditions
                if pnl_pct >= position.profit_target_pct / 100:
                    await self.close_position(position, 'PROFIT_TARGET')
                
                elif abs(current_pnl) >= position.max_loss * (position.stop_loss_pct / 100):
                    await self.close_position(position, 'STOP_LOSS')
                
                elif position.dte_remaining <= 3:
                    await self.close_position(position, 'EXPIRATION_APPROACHING')
                
                # 4. Check adjustment triggers
                elif self.needs_adjustment(position, greeks):
                    action = self.rl_agent.predict(self.build_state(position, greeks))
                    await self.execute_adjustment(position, action)
                
                # 5. Portfolio-level risk check
                await self.check_portfolio_risk()
            
            await asyncio.sleep(60)  # 1-minute intervals
    
    def needs_adjustment(self, position, greeks):
        """Determine if position needs adjustment"""
        price = greeks['underlying_price']
        lower_warning = position.lower_breakeven * 1.02  # 2% buffer
        upper_warning = position.upper_breakeven * 0.98
        
        if price <= lower_warning or price >= upper_warning:
            return True
        if abs(greeks['delta']) > 0.20:  # Delta getting too directional
            return True
        if greeks['iv_current'] > greeks['iv_at_entry'] * 1.30:  # 30% IV spike
            return True
        return False
```

**Adjustment Strategies:**
1. **Convert to Iron Condor:** Close one wing, add call spread opposite side
2. **Roll Strikes:** Move body to new ATM if underlying trends
3. **Widen Wings:** Add width for more breathing room (increases risk)
4. **Close Early:** Take partial profit/loss before full damage

***

#### MODULE 8: Backtesting Engine
**File:** `modules/backtest/butterfly_backtester.py`

**Purpose:** Validate strategy parameters before live deployment.

**Data Requirements:**
- 5+ years of daily options data (CBOE, IB historical)
- Underlying price history (OHLCV)
- VIX history
- IV surface data (by strike/expiry)

**Backtest Metrics:**
```python
@dataclass
class BacktestResults:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_profit_per_trade: float
    avg_loss_per_trade: float
    profit_factor: float          # gross profit / gross loss
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int    # days
    calmar_ratio: float           # annual return / max drawdown
    avg_days_in_trade: float
    avg_credit_received: float
    avg_pnl_pct_of_credit: float
    total_return: float
    annualized_return: float
    total_commissions: float
```

**Benchmark comparison:** Buy-and-hold SPY, Sell 30-delta CSPs, Iron condors[^13]

***

### 4.4 Sprint Plan

| Sprint | Duration | Deliverables | Dependencies |
|---|---|---|---|
| **Sprint 1: Foundation** | Week 1-2 | Database schema, broker connections (IB + Tastytrade), basic option chain data fetching | Broker API credentials |
| **Sprint 2: Scanner** | Week 3-4 | IV Rank/Percentile screener, universe scanner, candidate ranking pipeline | Sprint 1 |
| **Sprint 3: Execution** | Week 5-6 | Butterfly combo order placement (IB + Tastytrade), order tracking, position database | Sprint 1 |
| **Sprint 4: Monitoring** | Week 7-8 | Real-time Greeks monitoring, P&L tracking, profit target / stop loss automation | Sprint 3 |
| **Sprint 5: ML Models** | Week 9-12 | Regime detector (HMM), Vol forecaster (GARCH-SVR), Strike optimizer (XGBoost) | Sprint 2 data pipeline |
| **Sprint 6: RL Agent** | Week 13-16 | PPO entry/exit agent, Gym environment, training pipeline, paper trade validation | Sprint 5 |
| **Sprint 7: Backtest** | Week 17-18 | Full backtesting engine, performance analytics, strategy comparison dashboard | Sprint 5 + 6 |
| **Sprint 8: Integration** | Week 19-20 | TradeMind.bot UI integration, alert system, user configuration panel, go-live checklist | All sprints |

### 4.5 Configuration & Risk Parameters (Defaults)

```yaml
# config/butterfly_defaults.yaml

strategy:
  type: SHORT_PUT_BUTTERFLY
  enabled: true

screening:
  universe: ['SPY', 'QQQ', 'IWM', 'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'NVDA', 'TSLA']
  scan_interval_minutes: 30
  iv_rank_max: 30
  iv_percentile_max: 40
  min_option_volume: 500
  max_bid_ask_spread_pct: 5.0
  min_underlying_volume: 1000000

entry:
  min_dte: 30
  max_dte: 60
  preferred_dte: 45
  min_wing_width: 3
  max_wing_width: 10
  min_credit_received: 0.50
  body_strike_offset: 0  # 0 = ATM
  allowed_regimes: ['LOW_VOL', 'NORMAL']
  ml_score_threshold: 0.70
  rl_confidence_threshold: 0.65

exit:
  profit_target_pct: 50           # Close at 50% of max profit
  stop_loss_multiplier: 2.0       # Close if loss = 2x credit
  max_dte_hold: 3                 # Close if <= 3 DTE remaining
  delta_breach_threshold: 0.25    # Adjust if |delta| > 0.25
  iv_spike_threshold: 1.30        # Adjust if IV rises 30%+
  breakeven_buffer_pct: 2.0       # Warning at 2% from breakeven

risk_management:
  max_portfolio_allocation_pct: 20
  max_single_position_risk_pct: 2
  max_concurrent_positions: 5
  max_single_underlying_positions: 1
  min_account_balance: 10000      # Minimum to trade
  kelly_fraction: 0.25            # Quarter-Kelly for position sizing
  max_daily_loss_pct: 3           # Stop all trading if daily loss > 3%

broker:
  primary: 'TASTYTRADE'           # or 'IB'
  fallback: 'IB'
  paper_trade_first: true
  paper_trade_days: 30

ml:
  regime_retrain_frequency: 'monthly'
  vol_model_retrain_frequency: 'weekly'
  strike_model_retrain_frequency: 'monthly'
  rl_retrain_frequency: 'quarterly'
  min_training_samples: 1000
  validation_split: 0.2
```

### 4.6 API Endpoints (for TradeMind.bot Integration)

```
POST   /api/butterfly/scan              # Trigger manual scan
GET    /api/butterfly/candidates         # Get ranked candidates
POST   /api/butterfly/approve/{id}       # Approve candidate for execution
POST   /api/butterfly/execute            # Execute butterfly trade
GET    /api/butterfly/positions          # Get all open positions
GET    /api/butterfly/positions/{id}     # Get specific position details
PUT    /api/butterfly/positions/{id}     # Update position parameters
DELETE /api/butterfly/positions/{id}     # Close position
GET    /api/butterfly/history            # Historical trades
GET    /api/butterfly/analytics          # Performance analytics
GET    /api/butterfly/greeks/{id}        # Greeks history for position
GET    /api/butterfly/backtest           # Run backtest with parameters
POST   /api/butterfly/config             # Update strategy configuration
GET    /api/butterfly/ml/status          # ML model health & accuracy
POST   /api/butterfly/ml/retrain         # Trigger model retraining
GET    /api/butterfly/alerts             # Active alerts
```

### 4.7 Alert System

```python
ALERT_TYPES = {
    'CANDIDATE_FOUND':    'High-score butterfly candidate: {symbol} | Score: {score} | Credit: ${credit}',
    'POSITION_OPENED':    'Butterfly opened: {symbol} {strikes} | Credit: ${credit} | Max Loss: ${max_loss}',
    'PROFIT_TARGET_HIT':  'Profit target reached: {symbol} | P&L: ${pnl} ({pnl_pct}% of max)',
    'STOP_LOSS_HIT':      'Stop loss triggered: {symbol} | Loss: ${loss}',
    'ADJUSTMENT_NEEDED':  'Position needs adjustment: {symbol} | Reason: {reason}',
    'ADJUSTMENT_EXECUTED':'Position adjusted: {symbol} | Action: {action}',
    'POSITION_CLOSED':    'Position closed: {symbol} | P&L: ${pnl} | Reason: {reason}',
    'EXPIRATION_WARNING': 'Position expiring soon: {symbol} | DTE: {dte}',
    'REGIME_CHANGE':      'Market regime changed: {old_regime} → {new_regime}',
    'RISK_BREACH':        'Portfolio risk threshold breached: {metric} = {value}',
    'ML_MODEL_DEGRADED':  'ML model accuracy below threshold: {model} = {accuracy}',
}

# Delivery channels: Push notification, Email, SMS, Discord/Slack webhook
```

### 4.8 Testing Requirements

| Test Type | Coverage Target | Tools |
|---|---|---|
| Unit Tests | 90%+ for all modules | pytest |
| Integration Tests | Broker API round-trips (paper) | pytest + mock broker |
| Backtest Validation | 5-year historical data | Custom backtester |
| Paper Trading | 30-day minimum before live | IB Paper / Tastytrade Sandbox |
| Stress Testing | Max concurrent positions, API failures | Locust / custom scripts |
| ML Model Validation | Walk-forward cross-validation | scikit-learn pipelines |
| RL Agent Validation | 10,000+ episodes, converged reward | Stable-Baselines3 evaluation |

### 4.9 Go-Live Checklist

- [ ] All unit tests passing (90%+ coverage)
- [ ] Integration tests passing with both brokers
- [ ] Backtest shows positive Sharpe > 1.0 over 5 years
- [ ] Paper trade results: 30 days, > 60% win rate, profit factor > 1.5
- [ ] ML models trained and validated (accuracy above thresholds)
- [ ] RL agent converged and validated in paper environment
- [ ] Alert system tested across all channels
- [ ] Risk management guardrails tested (max position, daily loss limits)
- [ ] Database backup and recovery tested
- [ ] Monitoring dashboards operational (Grafana)
- [ ] Rollback procedure documented and tested
- [ ] User configuration UI deployed on TradeMind.bot
- [ ] Legal/compliance review (if applicable)
- [ ] Start with 25% of target position size for first 2 weeks

***

## Part 5: Key Implementation Notes for Antigravity

1. **Combo Orders Are Critical:** The butterfly MUST be placed as a single combo/BAG order (not 3 separate legs). This ensures atomic execution and avoids leg risk. Use `secType='BAG'` with `ComboLeg` objects for IB.[^14][^15]

2. **Paper Trade First — Always:** Set `paper_trade_first: true` in config. Minimum 30 days of paper results before any live capital. This is non-negotiable.

3. **Tastytrade as Primary Broker:** Given the existing TradeMind.bot integration with Tastytrade, use Tastytrade as the primary execution venue. IB serves as fallback and for advanced Greeks/data.

4. **Position Sizing via Quarter-Kelly:** Use Kelly Criterion at 25% fraction to avoid over-sizing. The formula: `f = (p * (b + 1) - 1) / b` where p = win rate, b = win/loss ratio. Quarter it for safety.

5. **Graceful Degradation:** If ML models degrade or API connections drop, the system should halt new entries but continue monitoring existing positions. Never open positions without all systems green.

6. **Human-in-the-Loop:** Default mode should require approval for each trade (approve candidates in UI). Add "full-auto" mode only after successful paper trading validation.[^10]

7. **Commission Awareness:** Multi-leg trades have higher commissions. Factor $0.65/contract (IB) or $1.00/contract (Tastytrade, capped) into all P&L calculations and minimum credit thresholds.

8. **Assignment Handling:** If short puts are assigned early, the system must detect this via position reconciliation and auto-close the assigned stock position + remaining option legs to maintain defined risk.[^2]

---

## References

1. [Short Put Butterfly Options Strategy - Lightspeed](https://lightspeed.com/trader-education/options-academy/options-strategies/neutral-outlook/short-put-butterfly/) - Buying two puts at a middle strike, and selling one put each at a lower and upper strike results in ...

2. [Short Put Butterfly: Definition, How it Works, Trading Guide & Example](https://www.strike.money/options/short-put-butterfly) - The short put butterfly is an options trading strategy that involves selling a put option at a middl...

3. [Short Put Butterfly Spread: A Profitable Neutral Options Strategy](https://algomojo.com/blog/short-put-butterfly-spread-a-profitable-neutral-options-strategy/) - Payoff Structure of a Short Put Butterfly Spread

 Maximum Loss: Occurs if the underlying price rema...

4. [Short Put Butterfly Options Strategy | Visualize + Live Data](https://www.insiderfinance.io/options-profit-calculator/strategy/short-put-butterfly) - Understanding the Greeks is vital in managing the Short Put Butterfly strategy effectively. Key metr...

5. [Implied Volatility (IV) Rank & Percentile Explained | tastylive](https://www.tastylive.com/concepts-strategies/implied-volatility-rank-percentile) - Options and volatility traders use IV rank to assess whether current levels of implied volatility ar...

6. [IV Percentile and What is Implied Volatility Rank? - Option Samurai](https://optionsamurai.com/blog/implied-volatility-percentile-iv-percentile/) - IV percentile is a ranking function that ranks the current IV of the asset with the asset's IV over ...

7. [Financial Option Volatility Prediction Based on Machine Learning ...](https://unige.org/volume-74-issue-4-2024/financial-option-volatility-prediction-based-on-machine-learning-algorithm/) - Implied volatility is obtained by inverting the Black-Scholes option pricing formula. Implied volati...

8. [A Hybrid AI-Driven Trading System Integrating Technical Analysis ...](https://arxiv.org/html/2601.19504v1) - This paper proposes a hybrid AI-based trading strategy that combines (1) trend-following and directi...

9. [AI Trading Agent Concept: Self-Training for Optimal ... - FRANKI T](https://www.francescatabor.com/articles/2025/2/15/ai-trading-agent-concept-self-training-for-optimal-trading-methodologies) - The AI Trading Agent's core strength lies in its reinforcement learning (RL) algorithm. Over time, t...

10. [AI Agents in Options Trading: Powerful and Proven | Digiqt Blog](https://digiqt.com/blog/ai-agents-for-options-trading/) - At a glance, an AI agent can scan option chains, calculate Greeks, evaluate volatility shifts, simul...

11. [Maximizing Automated Options Trading with Interactive Brokers ...](https://www.quantlabsnet.com/post/maximizing-automated-options-trading-with-interactive-brokers-trader-workstation) - The provided Python script, designed to automate a Butterfly Option Strategy on the SPX index, highl...

12. [Uhkneerudh/stockoptionscanner: Option Scanner - GitHub](https://github.com/Uhkneerudh/stockoptionscanner) - A high implied volatility means the market believes the stock will vary wildly in price. This makes ...

13. [Backtesting Short Butterfly Strategy - Quantra by QuantInsti](https://quantra.quantinsti.com/glossary/How-do-you-test-the-performance-of-an-options-trading-strategy-You-Backtest-it) - Backtesting Short Butterfly Strategy · In this post, we will see how to do options backtesting, i.e....

14. [comboLeg contract order placement #91 - erdewit/ib_insync - GitHub](https://github.com/erdewit/ib_insync/issues/91) - These are my logs trying to place an options order that consists of several legs. My order object is...

15. [TWS Python API Placing Complex Orders | Trading Lesson](https://www.interactivebrokers.com/campus/trading-lessons/python-complex-orders/) - In this lesson, we will walk through placing complex orders, such as a Bracket and Combo orders, usi...

