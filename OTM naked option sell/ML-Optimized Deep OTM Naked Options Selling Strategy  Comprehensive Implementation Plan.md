# ML-Optimized Deep OTM Naked Options Selling Strategy: Comprehensive Implementation Plan

## Executive Summary

This plan outlines a systematic, machine-learning-enhanced framework for selling deep out-of-the-money (OTM) naked calls and puts by identifying overbought/oversold conditions anchored to 52-week high/low proximity, elevated implied volatility, and mean-reversion signals. The core edge is the well-documented **Volatility Risk Premium (VRP)**: implied volatility persistently overestimates realized volatility, meaning option sellers systematically collect excess premium over time. An ML optimization layer is applied on top to dynamically tune the five core parameters: stock selection, strike price (delta), expiration date (DTE), entry/exit timing, and IV threshold—moving beyond fixed rules like the conventional "16 delta, 45 DTE" heuristic to adapt to changing market regimes.[^1][^2]

A key academic reference: an ML-optimized strangle selling strategy has been demonstrated to **outperform the baseline strangle selling strategy by 22% on annualized return basis**, while improving both Sharpe ratio and monthly returns. Another backtest using IV rank and K-means clustering on SPX put-selling found **100% of 25 tested parameter combinations were profitable** with a CAGR of ~7%.[^3][^4]

> ⚠️ **Risk Warning:** Naked call options carry theoretically unlimited upside risk. Naked puts carry large downside risk in gap-down scenarios. Deep OTM naked strategies have very high win rates but are exposed to rare, catastrophic black-swan losses (e.g., COVID crash in March 2020, flash crashes). This plan includes mandatory risk controls throughout. Position sizing must remain under 1% of account capital per trade, with never more than 2% of account at risk on any single position.[^5]

***

## Section 1: Strategy Architecture Overview

The strategy is composed of four sequential layers:

1. **Stock Screener (Universe Filter)** — identify the eligible universe using fundamental/technical filters
2. **Signal Engine (Entry Logic)** — detect overbought/oversold conditions using 52-week range distance + momentum indicators
3. **Option Parameter Selector (Strike/DTE/Side)** — ML model selects optimal strike delta, DTE, and call vs. put
4. **Risk Management Engine (Position Sizing + Exit Rules)** — monitor Greeks, enforce stop-loss rules, roll or close positions

The pipeline architecture is **modular**: each layer can be improved independently, and the ML model trains on the output of layers 1–2 to optimize layer 3 parameters.

***

## Section 2: Stock Universe Screening

### 2.1 Liquidity Filters (Hard Rules)

These are non-negotiable requirements before any ML model runs:

| Filter | Threshold | Rationale |
|--------|-----------|-----------|
| Market Cap | > $5B (large-cap preferred) | Wide bid/ask spreads in small-caps erode edge |
| Average Daily Volume | > 1M shares/day | Ensure option liquidity |
| Options Open Interest | > 1,000 per contract | Prevent slippage and poor fills |
| Bid/Ask Spread (option) | < $0.10 or < 5% of mid | Actual trade cost control |
| Listing on Major Exchange | NYSE / NASDAQ only | Regulatory and liquidity standards |

### 2.2 Volatility Filters

Selling options is only attractive when premium is elevated relative to historical norms. Key metrics:[^6][^7]

- **IV Rank (IVR) > 50**: Current IV is in the upper half of its 52-week range. IVR > 50 is broadly considered an attractive premium-selling environment. IVR > 70 is considered elevated and highly favorable for sellers.[^8][^6]
- **IV/HV Ratio > 1.2**: Implied volatility exceeds recent realized (historical) volatility — this directly measures the VRP edge.[^7]
- **IV Percentile > 60**: Current IV is higher than it has been on at least 60% of trading days in the past year.[^6]

\[
\text{IV Rank} = \frac{\text{Current IV} - \text{52W Low IV}}{\text{52W High IV} - \text{52W Low IV}} \times 100
\]

### 2.3 Technical / Fundamental Filters

- **No Earnings within 21 days**: Earnings events cause IV crush in an unpredictable direction; avoid entirely.[^9]
- **No FDA/binary events**: Similar binary-event risk.
- **Valuation check**: For put sellers, validate that the P/E, P/B, and P/S are not at extreme lows suggesting structural deterioration.[^10]
- **Sector diversification**: Ensure selected stocks span at least 3–4 distinct sectors to reduce correlated drawdowns.[^11]

### 2.4 Recommended Data Sources

- **Polygon.io (now Massive.com)**: Tick-level options chains with pre-calculated Greeks dating back to 2014, ideal for backtesting.[^12][^13]
- **ThetaData**: Historical options data with pre-computed IV and Greeks — highly regarded by algo traders.[^14]
- **IVolatility**: Key metrics including IV rank, put/call skew, and term structure.[^12]
- **CBOE Historical Options Data**: Free EOD options volume and reference data.[^15]

***

## Section 3: Signal Engine — Entry Logic

The entry signal is a composite of three components: (1) distance from 52-week extremes, (2) momentum oscillators, and (3) IV environment. **All three components must align** for a valid signal.

### 3.1 52-Week High/Low Proximity (Primary Filter)

This is the directional anchor of the strategy. The core hypothesis is **mean reversion**: stocks that have stretched far from their 52-week high (overbought on long-term basis) tend to revert, making naked calls attractive; stocks near their 52-week low (oversold) tend to revert upward, making naked puts attractive.[^16][^17]

**For Naked CALL candidates (overbought):**
- Price is within **5–15% of 52-week high** (stretched and potentially overextended)
- OR price has exceeded 52-week high by > 10% with no fundamental catalyst (momentum exhaustion)

**For Naked PUT candidates (oversold):**
- Price has declined **20–40% from 52-week high** (potential capitulation zone)
- OR price is within **5–10% of 52-week low**

> **Important nuance from backtesting research:** Stocks near 52-week highs often continue in a trend-following direction. The option selling approach sidesteps the directional prediction problem — you don't need to predict the exact reversal; you simply sell far enough OTM that even if the trend continues, the strike is not breached.[^16]

**Distance calculations:**

\[
\text{Pct from 52W High} = \frac{\text{Current Price} - \text{52W High}}{\text{52W High}} \times 100
\]

\[
\text{Pct from 52W Low} = \frac{\text{Current Price} - \text{52W Low}}{\text{52W Low}} \times 100
\]

### 3.2 Momentum Oscillators (Confirmation)

Raw 52-week positioning is insufficient; momentum indicators confirm the overbought/oversold condition at shorter timeframes:[^18][^19]

| Indicator | Overbought Signal | Oversold Signal | Notes |
|-----------|-------------------|-----------------|-------|
| RSI(14) daily | > 70 | < 30 | Classic threshold; RSI(2) < 10 or > 90 is extreme[^18] |
| RSI(2) | > 90 | < 10 | Very short-term, confirms extreme moves[^20] |
| Bollinger Band %B | > 1.0 (above upper band) | < 0.0 (below lower band) | Reversion trigger when used with RSI[^20] |
| Stochastic(14) | > 80 | < 20 | Secondary confirmation |
| Distance from 20-day SMA | > +15% | < -15% | Captures mean-reversion stretch |

**Key finding from backtesting:** Pure RSI mean reversion (buy under 30, sell over 70) has a ~42% win rate alone. It must be combined with additional filters. The approach here uses RSI as a confirmation signal, not a standalone entry trigger.[^21]

### 3.3 Market Regime Filter

Before entering ANY naked options position, assess the broad market regime:[^4]

- **VIX Level**: VIX > 30 signals extreme volatility — tighten position sizing, potentially avoid naked calls entirely (unlimited risk in fast markets).
- **VIX Term Structure**: VIX spot > VIX 3-month futures = backwardation (fear) — step aside or reduce exposure.
- **SPX Trend**: If SPX is below its 200-day SMA, reduce short put exposure to account for bearish macro environment.
- **Put/Call Ratio**: Extremely elevated put/call (>1.5) can signal a capitulation bottom — a contrarian signal favoring short puts.

***

## Section 4: ML Optimization Framework

This is the core innovation layer. Rather than using fixed rules, the ML model is trained to predict the **probability of profitability** and **optimal parameters** for each potential trade setup.

### 4.1 ML Problem Formulation

The ML task is a **supervised classification + regression** problem:

- **Classification target**: Will this trade expire OTM (profitable)? Binary label: 1 = expired OTM (win), 0 = expired ITM or required early close (loss)
- **Regression targets** (secondary models):
  - Expected P&L at expiration (in dollars per spread)
  - Optimal DTE for this specific stock/market condition
  - Optimal delta (strike selection) to maximize Sharpe ratio given current regime

This formulation follows the academic framework established in the SSRN paper on ML-optimized options selling, which demonstrated a 22% improvement over baseline by training on Greeks + technical indicators combined.[^3]

### 4.2 Feature Engineering — Complete Feature Set

The full feature vector for each candidate trade at entry time includes:

**Price/Momentum Features:**
| Feature | Description |
|---------|-------------|
| `pct_from_52w_high` | % below 52-week high |
| `pct_from_52w_low` | % above 52-week low |
| `rsi_14` | 14-day RSI |
| `rsi_2` | 2-day RSI (extreme short-term momentum) |
| `bb_pct_b` | Bollinger Band %B position |
| `atr_14_pct` | ATR(14) as % of price (volatility of underlying) |
| `distance_from_20sma_pct` | % distance from 20-day SMA |
| `distance_from_200sma_pct` | % distance from 200-day SMA (trend filter) |
| `volume_ratio` | Current volume / 20-day average volume |
| `1d_return` | 1-day return |
| `5d_return` | 5-day return |
| `20d_return` | 20-day return |

**Volatility Features:**
| Feature | Description |
|---------|-------------|
| `iv_rank` | Current IV rank (0–100) |
| `iv_percentile` | % of days IV was below current level |
| `iv_hv_ratio` | Current IV / 20-day historical volatility |
| `iv_hv30_ratio` | Current IV / 30-day HV |
| `iv_skew` | Put IV - Call IV at 25-delta (skew measure) |
| `vix_level` | VIX at trade entry |
| `vix_term_structure` | VIX spot / VIX 3M (backwardation indicator) |
| `iv_change_5d` | IV change over past 5 days |

**Options Greeks Features (at candidate strike):**
| Feature | Description |
|---------|-------------|
| `delta` | Absolute delta at chosen strike (target range: 0.05–0.20) |
| `theta` | Daily theta decay ($ per day per contract) |
| `vega` | Vega (IV sensitivity) — want to minimize for sellers |
| `gamma` | Gamma at strike — want low gamma (far OTM) |
| `theta_vega_ratio` | Theta / Vega — higher = better risk-adjusted carry[^3] |
| `bid_ask_spread` | Bid/ask spread in $ |
| `open_interest` | Open interest at selected strike |
| `premium_annualized` | (Premium / Strike) × (365 / DTE) = annualized return |

**Market/Macro Features:**
| Feature | Description |
|---------|-------------|
| `vix_percentile_52w` | VIX percentile over 52 weeks |
| `spx_above_200ma` | Binary: SPX above 200-day MA |
| `sector_etf_rsi` | RSI of sector ETF (e.g., XLK for tech) |
| `earnings_days_away` | Days to next earnings announcement |
| `days_to_expiry` | Candidate DTE |

### 4.3 ML Model Architecture

A **two-stage ML pipeline** is recommended, building on research showing ensemble methods outperform single models for financial prediction:[^22][^3]

**Stage 1: Stock-Selection Classifier (Scikit-Learn / XGBoost)**

- **Model**: XGBoost Classifier[^23][^24]
- **Task**: Binary classification — given all features above, predict P(trade wins)
- **Training data**: Historical options data 2014–2023 (in-sample), 2024 (out-of-sample validation)
- **Why XGBoost**: Handles tabular financial data well, supports feature importance (SHAP), regularization prevents overfitting[^25]
- **Output**: Win probability score; only enter trades with P > 0.65[^26]

```python
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
import shap

model = xgb.XGBClassifier(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=1.5,
    eval_metric='auc',
    early_stopping_rounds=30
)
# Use TimeSeriesSplit to prevent look-ahead bias
tscv = TimeSeriesSplit(n_splits=5)
```

**Stage 2: Parameter Optimizer (Regression Models)**

Three separate regression models predict optimal parameters for trades that pass Stage 1:
- **DTE Regressor**: Predicts optimal days-to-expiration (output: 14–60 days)
- **Delta Regressor**: Predicts optimal strike delta (output: 0.05–0.20)
- **P&L Regressor**: Predicts expected net P&L given the above parameters

All regression models use **LightGBM** for faster training on continuous targets and large datasets.[^23]

**Stage 3: Reinforcement Learning (Advanced / Phase 2)**

For dynamic intra-trade management (rolling, early close decisions), a Reinforcement Learning agent using **Proximal Policy Optimization (PPO)** is the state-of-the-art approach. Academic research on options RL frameworks (OTRL) shows PPO with a "protective closing strategy" consistently outperforms buy-and-hold strategies. The state space includes current Greeks, P&L, days remaining, and VIX; actions include: hold, close for profit, roll to next expiry, or convert to spread.[^27]

### 4.4 Training Methodology — Avoiding Overfitting

Overfitting is the primary enemy of ML trading models. The following protocols are mandatory:[^28][^29][^30]

**Walk-Forward Optimization (WFO)**
- Training window: 24 months rolling
- Test window: 3 months out-of-sample
- Step size: advance 1 month at a time
- Minimum 10 WFO windows required before deployment

The WFO process:
1. Train model on months 1–24
2. Predict on months 25–27 (never seen during training)
3. Advance window: train on months 2–25, predict on 26–28
4. Repeat until all historical data consumed
5. Evaluate performance across ALL out-of-sample windows combined

**Regularization Controls:**
- L1 and L2 regularization in XGBoost (reg_alpha, reg_lambda)
- Feature importance pruning: eliminate features with < 0.5% importance via SHAP values
- Maximum 15 features in final model (avoid feature bloat)
- Cross-validation using `TimeSeriesSplit` (never shuffle time series data)[^29]

**Parameter Space for Bayesian Optimization:**
- DTE range:  days[^31][^19][^32][^33][^18]
- Delta range: [0.05, 0.08, 0.10, 0.12, 0.15, 0.20]
- IVR threshold:[^33][^34][^5][^9]
- Stop-loss multiplier: [1.5x, 2x, 3x, 4x credit received]
- Profit-take threshold: [25%, 50%, 75% of max profit]

Use **Bayesian Optimization** (via `scikit-optimize` or `optuna`) to search this parameter space efficiently with fewer evaluations than grid search.[^35][^36]

```python
import optuna

def objective(trial):
    dte = trial.suggest_categorical('dte', [21, 30, 45])
    delta = trial.suggest_float('delta', 0.05, 0.20)
    ivr_threshold = trial.suggest_int('ivr_threshold', 40, 70)
    stop_loss_mult = trial.suggest_float('stop_loss_mult', 1.5, 4.0)
    take_profit_pct = trial.suggest_float('take_profit_pct', 0.25, 0.75)
    
    # Run backtest with these parameters
    results = run_backtest(dte, delta, ivr_threshold, stop_loss_mult, take_profit_pct)
    return results['sharpe_ratio']  # Maximize Sharpe ratio

study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=200)
```

***

## Section 5: Option Parameter Selection Rules

### 5.1 Strike Selection (Delta-Based)

Deep OTM naked options should target the following delta ranges, calibrated by market regime:

| Market Regime | Naked Call Delta | Naked Put Delta | Rationale |
|---------------|-----------------|-----------------|-----------|
| Low VIX (<15) | 0.08–0.12 | 0.10–0.15 | Low premium; go slightly closer for adequate credit |
| Normal VIX (15–25) | 0.08–0.12 | 0.08–0.12 | Standard range — ~1–1.5 SD OTM |
| High VIX (25–35) | 0.05–0.10 | 0.05–0.10 | More premium available at same delta; can go deeper |
| Extreme VIX (>35) | Avoid / very small size | 0.03–0.06 | Black-swan risk elevated; max protection |

The tastytrade benchmark uses 16-delta (0.16) for both calls and puts at 45 DTE when IVR > 50%. The ML model's value-add is discovering when deviation from this heuristic improves risk-adjusted returns.[^2]

For deep OTM specifically, selling strikes with delta ≤ 0.10 creates scenarios where there is **less than a 10% probability of options expiring in-the-money**. A QuantConnect backtest using strikes > 3 standard deviations below the index price found 93% of contracts expired OTM.[^4][^9]

### 5.2 Expiration Selection (DTE)

**Optimal DTE selection** balances theta decay rate against gamma risk exposure:

- **30–45 DTE is the sweet spot** for premium sellers: theta decay is significant while gamma (near-expiry risk) remains manageable.[^37]
- Managing (closing or rolling) at **21 DTE greatly reduces gamma exposure** and delta expansion, improving cumulative performance.[^37]
- For weekly (0–7 DTE) naked options: acceptable only for index products (SPX, SPY) with very high liquidity; avoid single stocks due to gap-down/gap-up risk.
- **Weekly expirations for high-IVR events** (e.g., post-earnings IV crush): consider 5–14 DTE only when IV rank > 80 following an earnings release.

### 5.3 Which Side to Sell (Call vs. Put)

The ML model should classify call vs. put preference, but the heuristic rules are:

**Sell Naked CALL when:**
- Stock is within 5–15% of 52-week high
- RSI(14) > 70 (overbought)
- Price is > 15% above 20-day SMA
- Overall market trend is neutral-to-bearish (SPX below 50-day MA)
- IV skew is elevated on call side (calls more expensive than puts)

**Sell Naked PUT when:**
- Stock has fallen 20–40% from 52-week high
- RSI(14) < 30 (oversold)
- Price is > 15% below 20-day SMA
- No fundamental deterioration (earnings, guidance cuts) driving the decline
- IV skew is elevated on put side (puts more expensive than calls)
- General: naked puts are structurally safer than naked calls due to capped downside at zero for the underlying stock[^38][^39]

***

## Section 6: Risk Management Framework

### 6.1 Position Sizing Rules

Naked options carry unlimited theoretical risk on calls and substantial risk on puts. Position sizing must be treated with extreme conservatism:[^40][^5]

- **Maximum per-position risk**: 1% of total portfolio capital
- **Maximum naked option exposure**: 5% of portfolio simultaneously across all positions
- **Volatility-adjusted sizing**: In high-IV environments (VIX > 30), reduce position sizes by 50%
- **Kelly Criterion (modified)**: Use half-Kelly based on historical win rate and payoff ratio; never full-Kelly for naked strategies
- **Margin buffer**: Always maintain at least 2× the option's maintenance margin as free capital

```python
def calculate_position_size(account_value, win_rate, avg_win, avg_loss, vix):
    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    half_kelly = kelly / 2  # Use half-Kelly for safety
    
    # Volatility scaling
    vix_scalar = max(0.3, 1.0 - max(0, (vix - 20) / 50))
    
    max_risk_per_trade = account_value * 0.01  # 1% max risk
    position_value = min(account_value * half_kelly * vix_scalar, max_risk_per_trade)
    return position_value
```

### 6.2 Stop-Loss Rules

Stop-loss rules for naked options require careful calibration — hard stops can be triggered by intraday IV spikes even when directionally correct:[^41][^42]

| Stop Type | Trigger | Action |
|-----------|---------|--------|
| Premium-Based Stop | Position loss = 2×–3× credit received | Close position immediately[^11] |
| Delta Breach | Underlying moves to within 1% of strike | Close or convert to spread[^40] |
| Time-Based Exit | Position reaches 21 DTE | Close if < 50% profit; hold if > 50% profit[^37] |
| Profit Take | 50% of max credit received | Close position to lock in profit[^2] |
| Volatility Stop | VIX spikes > 10 points in one day | Reduce all naked positions by 50% |
| Earnings Stop | Earnings announced within 10 days | Close position regardless of P&L |

**The 2× credit rule**: Setting a stop loss where you close if the option premium rises to 2× the original credit received is a commonly validated risk control. For example, if you sold a call for $0.50, close if the premium reaches $1.00. This caps the maximum loss at 2:1 risk/reward, and using frequent exits reduces variance significantly.[^42]

### 6.3 Adjustment and Rolling Rules

When a position moves against you but hasn't triggered a stop:

1. **Roll Down/Up**: If the underlying is approaching the strike with > 21 DTE remaining, roll to a further strike in the same expiry to collect additional credit and increase distance.
2. **Convert to Spread**: Buy a further OTM option to define risk — converts naked to a credit spread. Ideal when IV has spiked (the protective option is cheap relative to the risk reduction).[^31][^41]
3. **Roll to Next Expiry**: If < 21 DTE and position is near break-even, roll to next monthly expiry at a better strike to collect additional credit while extending time.[^43]
4. **Portfolio Hedge**: If multiple positions are simultaneously under pressure, buy SPY bear put spreads as a macro hedge to offset 30–50% of aggregate portfolio delta.[^31]

***

## Section 7: Technical Implementation Plan

### 7.1 Technology Stack

| Component | Recommended Tool | Alternative |
|-----------|-----------------|-------------|
| Data Pipeline | Polygon.io / ThetaData API | IVolatility, Intrinio |
| Backtesting Engine | QuantConnect (LEAN) | Backtrader, custom Python |
| ML Framework | XGBoost + LightGBM + scikit-learn | TensorFlow, PyTorch |
| Hyperparameter Optimization | Optuna (Bayesian) | Scikit-optimize, Ray Tune |
| Feature Store | Pandas + Parquet files | Apache Arrow, DuckDB |
| Signal Generation | Python (FastAPI microservice) | Node.js (TypeScript) |
| Broker Integration | Tastytrade API | E-Trade API, Interactive Brokers TWS |
| Monitoring Dashboard | Streamlit / Next.js | Grafana |
| Scheduling | APScheduler / cron | AWS EventBridge |

This stack aligns with TurboBounce's existing infrastructure (Next.js, Python, Tastytrade API integration).

### 7.2 Data Pipeline Architecture

```
[Market Data Sources]
    Polygon.io (options chains, Greeks, IV) ──┐
    ThetaData (historical IV, Greeks)         │
    yfinance / Alpha Vantage (price OHLCV)   ─┤──► [ETL Pipeline]
    CBOE (VIX term structure)                 │         │
    Tastytrade API (live quotes)             ──┘         ▼
                                                  [Feature Store]
                                                  (Parquet / SQLite)
                                                         │
                                                         ▼
                                                  [ML Training Pipeline]
                                                  (XGBoost + Walk-Forward)
                                                         │
                                                         ▼
                                                  [Signal Generator]
                                                  (Runs daily at market open)
                                                         │
                                                         ▼
                                                  [Risk Manager]
                                                  (Real-time Greeks monitoring)
                                                         │
                                                         ▼
                                                  [Order Execution]
                                                  (Tastytrade API)
```

### 7.3 Development Phases

**Phase 1: Data Infrastructure & Baseline Strategy (Weeks 1–6)**
- Set up Polygon.io/ThetaData API connections
- Build historical data store: 2014–2024 options data with daily IV, Greeks, OHLCV
- Implement 52-week high/low calculator and RSI/BB/Stochastic indicators
- Build baseline vanilla strategy: fixed 45 DTE, 0.10 delta, IVR > 50 rule
- Backtest baseline from 2014–2022 (in-sample), validate on 2023–2024
- Establish benchmark metrics: total return, Sharpe ratio, max drawdown, win rate

**Phase 2: Feature Engineering & ML Training (Weeks 7–12)**
- Engineer all 25+ features from Section 4.2
- Label historical trades (win/loss) based on expiration outcome
- Train XGBoost classifier with 5-fold TimeSeriesSplit cross-validation
- Interpret model with SHAP values — identify top 10 most predictive features
- Train DTE and delta regression models
- Run Bayesian hyperparameter optimization with Optuna
- Conduct walk-forward validation (minimum 10 windows)

**Phase 3: Backtesting with ML Parameters (Weeks 13–18)**
- Replace fixed parameters with ML model predictions in backtest engine
- Compare ML strategy vs. baseline across: Sharpe ratio, annual return, max drawdown, win rate
- Conduct Monte Carlo simulations (1,000+ runs) for drawdown distribution
- Stress test on historical crash periods: 2015 (China crash), 2018 (VIX implosion), 2020 (COVID), 2022 (bear market)
- Adjust position sizing and stop-loss parameters based on stress test results

**Phase 4: Paper Trading & Live Deployment (Weeks 19–26)**
- Deploy signal generator as a microservice (FastAPI on AWS Lambda)
- Paper trade for minimum 60 days across a variety of market conditions
- Compare paper P&L to backtest predictions — reconcile any deviations
- Build real-time monitoring dashboard (position Greeks, P&L, risk metrics)
- Implement automated alerts for stop-loss triggers via email/SMS (Resend API)
- Go live with reduced position sizing (25% of planned size) for first 90 days

**Phase 5: Reinforcement Learning Integration (Months 7–12)**
- Implement PPO-based intra-trade management agent (PyTorch + Stable-Baselines3)
- Define state space, action space, and reward function for options management
- Train RL agent in simulation environment using historical option price paths
- A/B test RL-managed exits vs. fixed rules

***

## Section 8: Performance Metrics & Evaluation Framework

Track the following KPIs continuously:

| Metric | Target | Description |
|--------|--------|-------------|
| Annualized Return | > 15% | Net of commissions and slippage |
| Sharpe Ratio | > 1.5 | Risk-adjusted return target |
| Max Drawdown | < 20% | Peak-to-trough portfolio loss |
| Win Rate | > 80% | % of trades expiring OTM profitably |
| Profit Factor | > 2.0 | Gross profit / gross loss |
| Average P&L per Trade | > 2× commissions | Ensure edge exceeds transaction costs |
| Theta/Day (portfolio) | Positive | Verify theta is working in your favor |
| Average DTE at Entry | 30–45 days | Confirm ML is selecting appropriate range |
| ML Model AUC (OOS) | > 0.65 | Out-of-sample classification accuracy |

### Performance Benchmarks from Literature

- Baseline deep OTM weekly put selling: ~18% annualized (2020, low-rate environment)[^9]
- ML-optimized strangle strategy: 22% improvement over baseline[^3]
- K-means + IV rank put selling (SPX): ~7% CAGR with 93% win rate[^4]
- Tastytrade 16-delta strangle (2005–2016 backtest): the raw formula had known drawdown risks in 2008 and 2011[^2]
- Short OTM strangle average return: ~3% per month before tail events[^34]

***

## Section 9: Known Risks and Mitigation

### 9.1 Black Swan Events

The single biggest risk for naked option sellers is a gap move that bypasses stop-losses entirely. Historical examples: March 2020 (SPX -30% in 30 days), August 2015 (SPX flash crash -11% intraday), February 2018 (VIX explosion, XIV collapse).[^44][^45]

**Mitigation:**
- Maintain a permanent tail-risk hedge: allocate 0.5–2% of portfolio to deep OTM SPX put options as catastrophe insurance.[^46][^45]
- Limit single-stock naked options exposure to < 1% per position; index options are safer due to diversification.
- Never hold naked calls through overnight sessions without a hard broker-level stop order.
- Convert any position to a defined-risk spread (credit spread) if unrealized loss exceeds 1.5× credit received.

### 9.2 Overfitting Risk

Machine learning models trained on historical options data are highly susceptible to overfitting, especially given the non-stationarity of financial markets.[^47][^28]

**Mitigation:**
- Enforce strict walk-forward validation (no in-sample peeking).
- Use SHAP to verify features are economically meaningful, not spurious.
- Minimum 5 years of out-of-sample data validation before live deployment.
- Regularization (L1/L2) + max feature cap at 15.
- Model retraining frequency: monthly rolling update with new data.

### 9.3 Liquidity Risk

Deep OTM options can have very wide bid/ask spreads, especially in less-liquid underlyings. This directly erodes edge.[^5]

**Mitigation:**
- Hard filter: only trade options with open interest > 1,000 and bid/ask spread < $0.15 or < 5% of mid.
- Use limit orders at mid-price (natural); don't chase fills.
- Avoid single-stock options outside S&P 500 universe.
- Size positions such that any single option position represents < 1% of that contract's open interest.

### 9.4 Margin/Assignment Risk

Naked calls can result in assignment if a stock is called away at expiration. Margin requirements can expand dramatically during volatile periods, triggering forced liquidations.[^26][^40]

**Mitigation:**
- Maintain 2× maintenance margin as free capital buffer at all times.
- Monitor broker margin requirements daily.
- Reduce overall exposure (close positions) when free margin falls below 150% of maintenance margin.
- Be aware that many retail brokers (including Tastytrade) require Level 3+ approval for naked options; ensure proper account tier.[^39]

***

## Section 10: Integration with TurboBounce Platform

Given TurboBounce's existing infrastructure and subscriber base, this ML strategy can be layered into the product in stages:

1. **Signal Generation Service**: The daily stock screener output (top 5–10 deep OTM opportunities with ML confidence scores) can be delivered as a new signal tier.
2. **Educational Layer**: Explain to Gen Z retail subscribers why the signal was generated (SHAP-based feature attribution in plain English: "AAPL is 12% below its 52-week high, RSI is 28, IV rank is 72 — this is a classic naked put sell setup").
3. **Risk-Adjusted Premium Tier**: Deep OTM naked options strategies require higher capital and broker approval — this naturally justifies a higher-tier subscription (e.g., $99–$149/month).
4. **Automated Execution Integration**: Connect to Tastytrade API for 1-click execution, or auto-execution for premium subscribers — this is the highest-value feature differentiator.
5. **Backtested Performance Reporting**: Show subscribers the historical signal accuracy and P&L by strategy, similar to how quantitative hedge funds present track records.

***

## Conclusion

The ML-optimized deep OTM naked options selling strategy combines a well-grounded edge (Volatility Risk Premium, mean reversion from 52-week extremes) with a systematic ML optimization layer that dynamically adapts strike selection, DTE, and entry timing to current market conditions. The key innovations over vanilla premium-selling approaches are: (1) composite entry scoring using 52-week positioning + RSI + IV rank, (2) XGBoost classifier for trade selection with SHAP-based explainability, (3) Bayesian optimization for parameter tuning with walk-forward validation to prevent overfitting, and (4) a PPO-based RL agent for intra-trade management in Phase 2.

The primary risk — black-swan tail events — is partially mitigated through portfolio-level SPX put hedges, strict position sizing (1% per trade), and the automatic conversion from naked to defined-risk spreads when adverse moves reach 1.5× credit received. No ML model eliminates this risk entirely, and position sizing remains the single most important variable in the long-term survival of a premium-selling strategy.

---

## References

1. [Selling High IV Rank (In depth study) : r/options - Reddit](https://www.reddit.com/r/options/comments/qcxsmb/ultimate_guide_to_selling_options_profitably_part/) - IV rank tells us what today's implied volatility is for a stock relative to the highest and lowest w...

2. [Does Tastytrade Work - SJ Options Trading](https://www.sjoptions.com/does-tastytrade-work/) - One formula, per their own website, is to sell the 16 delta of the call and put 45 days to expiratio...

3. [[PDF] Options Selling strategy using Machine Learning](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4766370_code6587970.pdf?abstractid=4766370&mirid=1) - The ML optimized strangle selling strategy outperforms the baseline strangle selling strategy on the...

4. [Reducing Option-Writing Risk with IV Rank and Strike Clusters](https://www.quantconnect.com/research/18766/reducing-option-writing-risk-with-iv-rank-and-strike-clusters/) - Implementation of a put options strategy using IV rank and AI with K-means clusters shows high win r...

5. [Risk Management & Position Sizing in Options Trading - TradingView](https://in.tradingview.com/chart/BANKNIFTY/DSgPs1OA-Risk-Management-Position-Sizing-in-Options-Trading/) - Position sizing must assume premium loss of 50–100%. Only invest what you're okay to lose. Rule of t...

6. [Implied Volatility (IV) Rank & Percentile Explained | tastylive](https://www.tastylive.com/concepts-strategies/implied-volatility-rank-percentile) - Implied volatility (IV) rank is a statistic in options trading which reports how the current level o...

7. [How to Use Implied Volatility Rank & Percentile to Find Better ...](https://finance.yahoo.com/news/implied-volatility-rank-percentile-better-133416799.html) - By combining IV Rank, Percentile, and IV/HV ratios, traders can better judge whether conditions favo...

8. [IV Rank Analysis: Options Volatility Near 52-Week Lows - ApexVol](https://apexvol.com/blog/2026-02-19-iv-rank-analysis-options-volatility-near-52-week-lows) - IV Rank measures where current implied volatility stands relative to its 52-week range on a 0-100 sc...

9. [Selling Deep OTM Weekly Cash-Secured Puts to Generate ...](https://www.thebluecollarinvestor.com/selling-deep-otm-weekly-cash-secured-puts-to-generate-substantial-annualized-returns/) - This article will highlight a low-risk put-selling strategy that can be used to generate an 18% annu...

10. [My Stock Screening Process for Selling CSPs - Reddit](https://www.reddit.com/r/Optionswheel/comments/1prf8ig/my_stock_screening_process_for_selling_csps/) - My reasoning is that if valuation is deep enough, you can still structure relatively favorable optio...

11. [8 Tips For Naked Option Writers to Reduce Risk - Bullish Bears](https://bullishbears.com/tips-for-naked-option-writers/) - Tips for naked option writers: 1. Stop loss, 2. Sell spreads, 3. Short-term expirations, 4. Low vola...

12. [Top 7 APIs for Historical Options Data (Live & Archived) - QuantVPS](https://www.quantvps.com/blog/options-data-api) - Compare seven APIs for historical options data, covering granularity, pricing, and integration for b...

13. [Options Market Data API - Massive](https://massive.com/options) - Options data for your big idea. Real-time options prices, historical data, and news on all major opt...

14. [Where Can I Get Historical Options Data? (Preferably 5-10 Years ...](https://www.reddit.com/r/algotrading/comments/1ilxrr9/where_can_i_get_historical_options_data/) - Thetadata and Databento come to mind. Thetada also provides precomputed IV and all the Greeks.

15. [Historical Options Data Download - Cboe Global Markets](https://www.cboe.com/us/options/market_statistics/historical_data/) - Use this form to download historical options volume across the Cboe exchanges by a single symbol, a ...

16. [Backtest 52 Week Highs and Lows Option Strategy | Blog](https://optionsamurai.com/blog/backtest-52-week-highs-and-lows-option-strategy/) - Learn how to use a backtest on new stocks' 52-week highs and lows to trade options. Use our free bac...

17. [Mastering the 52-Week High Momentum Strategy: A Practical Guide ...](https://www.kavout.com/market-lens/mastering-the-52-week-high-momentum-strategy-a-practical-guide-for-investors) - The 52-week high momentum strategy involves selecting stocks whose current prices are near or have r...

18. [RSI Trading Strategy (91% Win Rate): Backtest, Indicator, And Settings](https://www.quantifiedstrategies.com/rsi-trading-strategy/) - The RSI trading strategy identifies overbought and oversold conditions in markets, measuring momentu...

19. [RSI Backtest: Predicting the Stock Movement Using RSI - Part 1. | Blog](https://optionsamurai.com/blog/rsi-backtest-predicting-the-stock-movement-using-rsi-part-1/) - When RSI is below 20, it is considered a bullish signal; when RSI is above 80, it is regarded as a b...

20. [10 Mean Reversion Trading Strategies - Traders Mastermind](https://tradersmastermind.com/10-mean-reversion-trading-strategies/) - VWAP extensions | Low break fake | Ignition candle retrace | Pair trader | Open test reverse | Outsi...

21. [i tested that "rsi oversold" strategy on 5000 trades. it failed hard](https://www.reddit.com/r/Daytrading/comments/1pdj9f1/i_tested_that_rsi_oversold_strategy_on_5000/) - Meaning, when it's overbought then don't buy or take a long position. When its oversold, don't sell ...

22. [Machine Learning in Stock Selection: A Refresher](https://www.xponance.com/machine-learning-in-stock-selection-a-refresher/) - ML enriches stock selection by extending beyond linear models to capture interactions, nonlinearitie...

23. [XGBoost: Key Features, Innovations & When to Use It - MCP Analytics](https://mcpanalytics.ai/articles/xgboost-practical-guide-for-data-driven-decisions) - Gradient boosting performs functional gradient descent in the space of functions rather than paramet...

24. [XGBoost - GeeksforGeeks](https://www.geeksforgeeks.org/machine-learning/xgboost/) - Here we visualize the importance of each feature in the XGBoost model to understand which variables ...

25. [Inferring Trade Directions in Options via Machine Learning](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5127667) - We develop GS-LASSO, a novel machine learning approach integrating XGBoost, SHAP, and LASSO, to clas...

26. [Naked Call Options Strategy: Risks, Benefits, and How It Works](https://www.investopedia.com/terms/n/nakedcall.asp) - A naked call is an options strategy in which an investor writes (sells) call options without owning ...

27. [Reinforcement Learning For Options Trading | PDF - Scribd](https://www.scribd.com/document/675307383/Reinforcement-Learning-for-Options-Trading) - Application of deep reinforcement learning in stock trading strategies and stock forecasting. ... De...

28. [How to Avoid Overfitting When Testing Trading Rules](http://adventuresofgreg.com/blog/2025/12/18/avoid-overfitting-testing-trading-rules/) - Walk-forward optimization is a method traders use to fine-tune strategies while reducing the chances...

29. [What is a Walk-Forward Optimization and How to Run It?](https://algotrading101.com/learn/walk-forward-optimization/) - Walk forward optimisation is a process for testing a trading strategy by finding its optimal trading...

30. [Why we employ walk-forward testing to avoid curve-fitting](https://logical-invest.com/walk-forward-testing-avoid-curve-fitting-backtesting/) - The out-of-sample backtest minimizes the risk of over-fitting, as the data is not previously know to...

31. [Naked Put Gone Wrong? Proven Ways to Defend and Recover](https://www.youtube.com/watch?v=sxkCYmKSkyw) - If you've been selling naked puts long enough, you know the feeling. The stock drops through your st...

32. [Options Greeks: Understanding delta, gamma, theta, vega, rho](https://optionalpha.com/learn/options-greeks) - The options Greeks are used to measure an option price's sensitivity to changes in underlying variab...

33. [I Built a Machine Learning Pipeline to Analyze Fundamental Stock ...](https://betterprogramming.pub/how-to-analyze-fundamental-stock-data-with-machine-learning-pipelines-1128e0fa5b0f) - Learn how I used machine learning pipelines for many classification models in Data Science to analyz...

34. [Option Sellers Could Capture Time Decay with Short-Dated Index ...](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5104300) - Forming a strangle by using paired out-of-the-money call and put options captures time decay and pro...

35. [Optimising Supertrend Parameters using Bayesian ... - arXiv](https://arxiv.org/html/2405.14262v1) - This thesis investigates the potential of Bayesian optimization (BO) to optimize the atr multiplier ...

36. [Optimizing Trading Strategies with Bayesian Optimization](https://onepagecode.substack.com/p/optimizing-trading-strategies-with-6b1) - Optimizing the parameters of a quantitative trading strategy is a critical step in enhancing its per...

37. [45 & 21 Days - Best Practices | tastylive](https://www.tastylive.com/shows/best-practices/episodes/45-21-days-12-12-2018) - Two important numbers to remember when trading are 45 and 21. These numbers help us time trade entry...

38. [Does anyone here sell OTM naked calls of expensive stock taking ...](https://www.reddit.com/r/options/comments/1repkzb/does_anyone_here_sell_otm_naked_calls_of/) - I want to sell naked calls on some stock that I don't own 100 shares, like APP and LLY. Do you guys ...

39. [Selling Naked Calls and Puts... - PowerOptions](https://www.poweropt.com/nakedoptionhelp.asp) - Naked options refers to the strategy of selling a Call or a Put without owning or shorting the stock...

40. [Managing Naked Call Options: Risks and Effective Strategies](https://profitmart.in/blog/managing-naked-call-options-risks-and-effective-strategies/) - You should use stop-loss orders and other risk management strategies to ensure your exposure is fair...

41. [Naked Option Selling: The Stupid Myth of 'Unlimited Losses'](https://optionalpha.com/blog/the-stupid-myth-of-unlimited-losses-in-naked-option-selling) - This “unlimited losses” feature comes only with short call options and the theory is that the stock ...

42. [How to stop loss a naked put? : r/thetagang - Reddit](https://www.reddit.com/r/thetagang/comments/1gu3jak/how_to_stop_loss_a_naked_put/) - Stops would increase the frequency of your losses but would keep them small. No stop would reduce th...

43. [Options Theory: Managing ITM Naked Puts | Tackle Trading](https://tackletrading.com/options-theory-managing-itm-naked-puts/) - There are various techniques for managing a naked put that goes against you. Today I want to discuss...

44. [Selling deep out of money PUT options - Trading Q&A by Zerodha](https://tradingqna.com/t/selling-deep-out-of-money-put-options/127822) - Never ever sell naked puts, never. Instead you can do an iron condor which is selling OTM puts & cal...

45. [Tail Hedging-Black Swan- by buying SPY Puts Deep OTM, Nassim ...](https://www.reddit.com/r/options/comments/g80ijf/tail_hedgingblack_swan_by_buying_spy_puts_deep/) - This portfolio would spend a small percentage of its equity exposure every month buying 2-month put ...

46. [Tail Risk Protection with Deep OTM Puts | Strategic Options Hedging](https://www.youtube.com/watch?v=HC6GKtqNZHc) - Check out the Discord community! https://www.launchpass.com/ditm-20/discord-community Black Swan Hed...

47. [Walk-Forward Analysis vs. Backtesting: Pros, Cons, and Best Practices](https://surmount.ai/blogs/walk-forward-analysis-vs-backtesting-pros-cons-best-practices) - Walk-forward analysis vs. backtesting: Learn which validation method suits your trading strategy, av...

