# TQQQ Short Put Diagonal — Complete Implementation Plan for Antigravity

## Overview

This document is a **developer-ready implementation plan** for an automated TQQQ short put diagonal spread trading system using the "Hybrid Swing Trade with Theta Kicker" approach. It is structured as modular components with explicit inputs, outputs, data flows, class structures, configuration parameters, and API integration details for the Tastytrade Python SDK.

**Target Stack:** Python 3.11+, Tastytrade SDK (`tastytrade` PyPI package), `pandas`, `numpy`, `scikit-learn`, `xgboost`, `ta-lib` (or `ta` library), `vix_utils`, `yfinance` (for historical data), SQLite or PostgreSQL for state persistence.

***

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SCHEDULER (cron / APScheduler)               │
│  Runs daily at 3:30 PM EST (market scan) + 3:55 PM EST (execution) │
└────────────┬───────────────────────────────────┬────────────────────┘
             │                                   │
             ▼                                   ▼
┌────────────────────────┐          ┌────────────────────────────────┐
│   DATA PIPELINE        │          │   POSITION MANAGER             │
│   (Module 1)           │          │   (Module 6)                   │
│                        │          │                                │
│  • TQQQ OHLCV          │          │  • Track open spreads          │
│  • VIX spot + futures  │          │  • Monitor hedge expiry        │
│  • Options chain       │          │  • Route orders via Tastytrade │
│  • Greeks streaming    │          │  • Handle fills/partials       │
└────────┬───────────────┘          └──────────┬─────────────────────┘
         │                                     │
         ▼                                     │
┌────────────────────────┐                     │
│   INDICATOR ENGINE     │                     │
│   (Module 2)           │                     │
│                        │                     │
│  • RSI-2               │                     │
│  • Bollinger %B        │                     │
│  • ADX(14)             │                     │
│  • MFI(14)             │                     │
│  • Volume ratio        │                     │
│  • 200-SMA, 20-SMA     │                     │
└────────┬───────────────┘                     │
         │                                     │
         ▼                                     │
┌────────────────────────┐                     │
│   REGIME DETECTOR      │                     │
│   (Module 3)           │                     │
│                        │                     │
│  • Rolling Hurst (100d)│                     │
│  • OU half-life (60d)  │                     │
│  • VIX term structure  │                     │
│  • HMM state (optional)│                     │
└────────┬───────────────┘                     │
         │                                     │
         ▼                                     │
┌────────────────────────┐                     │
│   ML SIGNAL ENGINE     │                     │
│   (Module 4)           │                     │
│                        │                     │
│  • XGBoost classifier  │                     │
│  • Walk-forward retrain│                     │
│  • Probability score   │                     │
└────────┬───────────────┘                     │
         │                                     │
         ▼                                     │
┌────────────────────────┐                     │
│   TRADE DECISION       │◄────────────────────┘
│   ENGINE (Module 5)    │
│                        │
│  • Entry logic         │
│  • Exit logic          │
│  • Hedge roll logic    │
│  • Circuit breaker     │
│  • Position sizing     │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│   LOGGING & MONITORING │
│   (Module 7)           │
│                        │
│  • Trade journal DB    │
│  • P&L tracking        │
│  • Alert system        │
│  • Performance metrics │
└────────────────────────┘
```

***

## Module 1: Data Pipeline

### 1.1 Purpose
Fetch all required market data and maintain a local cache for indicator calculations and ML feature generation.

### 1.2 Data Sources

| Data | Source | Frequency | Method |
|------|--------|-----------|--------|
| TQQQ OHLCV (daily) | `yfinance` or Tastytrade streamer | Daily at 3:30 PM | `yf.download("TQQQ", period="2y")` |
| TQQQ OHLCV (intraday, optional) | Tastytrade DXLink streamer | Real-time | WebSocket subscription |
| VIX spot | `yfinance` ticker `^VIX` | Daily | `yf.download("^VIX")` |
| VIX futures M1, M2 | `vix_utils` PyPI package or CBOE CSV | Daily | Downloads from CBOE historical data[^1][^2] |
| TQQQ options chain | Tastytrade SDK | On-demand | `get_option_chain(session, 'TQQQ')`[^3][^4] |
| TQQQ options Greeks | Tastytrade DXLink streamer | Real-time | Subscribe to `Greeks` event type[^4] |
| QQQ OHLCV | `yfinance` | Daily | For tracking error calculation |

### 1.3 Class Structure

```python
class DataPipeline:
    """
    Attributes:
        tqqq_daily: pd.DataFrame  # columns: Date, Open, High, Low, Close, Volume
        vix_daily: pd.DataFrame   # columns: Date, Close
        vix_futures: pd.DataFrame # columns: Date, M1_Close, M2_Close, M3_Close
        qqq_daily: pd.DataFrame   # columns: Date, Open, High, Low, Close, Volume
        options_chain: dict       # {expiration_date: [Strike objects]}
        
    Methods:
        refresh_daily_data() -> None
            # Pull latest OHLCV for TQQQ, QQQ, VIX
            # Append to local SQLite cache
            # Called at 3:30 PM EST daily
        
        get_options_chain(session: Session, min_dte: int, max_dte: int) -> dict
            # Fetch TQQQ option chain from Tastytrade
            # Filter by DTE range
            # Return {expiration: {strike: {put_symbol, call_symbol, greeks}}}
        
        get_option_greeks(session: Session, symbols: list[str]) -> dict
            # Stream real-time Greeks for specific option symbols
            # Return {symbol: {delta, gamma, theta, vega, iv}}
        
        get_vix_term_structure() -> dict
            # Return {m1: float, m2: float, m3: float, slope: float, is_contango: bool}
        
        get_tqqq_qqq_tracking_error(window: int = 5) -> float
            # Compute rolling tracking error between TQQQ and 3x QQQ daily returns
    """
```

### 1.4 Tastytrade SDK Integration for Options Chain

```python
# Key SDK usage patterns for Antigravity to implement:

from tastytrade import Session, Account
from tastytrade.instruments import get_option_chain, NestedOptionChain, Option
from tastytrade.dxfeed import Greeks
from tastytrade import DXLinkStreamer
from tastytrade.utils import get_tasty_monthly
from datetime import date, timedelta

# Authentication
session = Session("username", "password")  # or certification session for sandbox

# Get nested chain (grouped by expiration and strike)
chain = NestedOptionChain.get(session, 'TQQQ')
# chain.expirations[i].strikes[j].put = 'TQQQ 260321P00055000'
# chain.expirations[i].strikes[j].strike_price = Decimal('55.0')

# Filter expirations by DTE
target_date = date.today() + timedelta(days=45)
# Find closest expiration to target_date

# Stream Greeks for selected options
async with DXLinkStreamer(session) as streamer:
    await streamer.subscribe(Greeks, [put_symbol_1, put_symbol_2])
    greeks = await streamer.get_event(Greeks)
    # greeks.delta, greeks.gamma, greeks.theta, greeks.volatility
```

### 1.5 Configuration

```python
DATA_CONFIG = {
    "tqqq_history_days": 504,       # 2 years of trading days
    "vix_history_days": 504,
    "cache_db": "data_cache.sqlite",
    "refresh_time": "15:30",         # EST
    "yfinance_tickers": ["TQQQ", "QQQ", "^VIX"],
}
```

***

## Module 2: Indicator Engine

### 2.1 Purpose
Compute all technical indicators required by the signal engine, regime detector, and ML model from the daily OHLCV data.

### 2.2 Indicator Specifications

| Indicator | Formula/Library | Parameters | Output Column |
|-----------|----------------|------------|---------------|
| RSI-2 | `ta.momentum.RSIIndicator(close, window=2)` | window=2 | `rsi_2` |
| RSI-2 consecutive days < threshold | Custom rolling count | threshold=10 | `rsi2_consec_below_10` |
| Bollinger %B | `ta.volatility.BollingerBands(close, window=20, window_dev=2)` | window=20, dev=2 | `bb_pct_b` |
| ADX(14) | `ta.trend.ADXIndicator(high, low, close, window=14)` | window=14 | `adx_14` |
| MFI(14) | `ta.volume.MFIIndicator(high, low, close, volume, window=14)` | window=14 | `mfi_14` |
| Volume ratio | `volume / volume.rolling(20).mean()` | window=20 | `vol_ratio_20` |
| SMA-200 | `close.rolling(200).mean()` | window=200 | `sma_200` |
| SMA-20 | `close.rolling(20).mean()` | window=20 | `sma_20` |
| SMA-5 | `close.rolling(5).mean()` | window=5 | `sma_5` |
| ATR(14) / Price | `ta.volatility.AverageTrueRange(high, low, close, 14).atr() / close` | window=14 | `atr_pct` |
| Days since last RSI-2 < 10 | Custom counter | — | `days_since_rsi2_oversold` |

### 2.3 Class Structure

```python
class IndicatorEngine:
    """
    Attributes:
        config: IndicatorConfig
        
    Methods:
        compute_all(df: pd.DataFrame) -> pd.DataFrame
            # Input: OHLCV DataFrame
            # Output: Same DataFrame with all indicator columns appended
            # MUST handle NaN rows at start (200 rows for SMA-200)
        
        get_current_signals(df: pd.DataFrame) -> dict
            # Return latest row's indicator values as dict
            # Example: {"rsi_2": 4.3, "bb_pct_b": -0.12, "adx_14": 18.5, ...}
    """
```

### 2.4 Implementation Notes
- Use the `ta` library (not `ta-lib` C wrapper) for easier installation: `pip install ta`[^5][^6]
- Alternative: `ta-lib` with `ADX = talib.ADX(high, low, close, timeperiod=14)`[^6]
- The RSI-2 consecutive count is custom logic — not available in any library:

```python
def rsi2_consecutive_below(rsi_series: pd.Series, threshold: float = 10) -> pd.Series:
    """Count consecutive days RSI-2 is below threshold."""
    below = (rsi_series < threshold).astype(int)
    groups = below.ne(below.shift()).cumsum()
    result = below.groupby(groups).cumsum()
    return result
```

***

## Module 3: Regime Detector

### 3.1 Purpose
Determine whether the current market environment supports mean-reversion trading. Output a composite regime score and individual filter states.

### 3.2 Component Filters

#### 3.2.1 Rolling Hurst Exponent (100-day window)

**What it measures:** Whether TQQQ returns are mean-reverting (H < 0.5) or trending (H > 0.5).[^7][^8]

**Implementation using Rescaled Range (R/S) analysis:**

```python
def hurst_exponent(price_series: np.ndarray) -> float:
    """
    Compute Hurst exponent using R/S analysis.
    Input: array of prices (at least 100 values)
    Output: float, H < 0.5 = mean-reverting, H > 0.5 = trending
    """
    log_returns = np.diff(np.log(price_series))
    lags = range(2, min(len(log_returns) // 2, 100))
    rs_values = []
    
    for lag in lags:
        subseries = [log_returns[i:i+lag] for i in range(0, len(log_returns) - lag, lag)]
        rs_per_lag = []
        for sub in subseries:
            if len(sub) < 2:
                continue
            mean_sub = np.mean(sub)
            deviate = np.cumsum(sub - mean_sub)
            R = np.max(deviate) - np.min(deviate)
            S = np.std(sub, ddof=1)
            if S > 0:
                rs_per_lag.append(R / S)
        if rs_per_lag:
            rs_values.append((np.log(lag), np.log(np.mean(rs_per_lag))))
    
    if len(rs_values) < 3:
        return 0.5  # indeterminate
    
    x = np.array([v for v in rs_values])
    y = np.array([v[^1] for v in rs_values])
    slope, _ = np.polyfit(x, y, 1)
    return slope

def rolling_hurst(close_prices: pd.Series, window: int = 100) -> pd.Series:
    """Compute rolling Hurst exponent over specified window."""
    return close_prices.rolling(window).apply(
        lambda x: hurst_exponent(x.values), raw=False
    )
```

**Thresholds:**
- H < 0.40: Strong mean-reversion → full confidence
- 0.40 ≤ H < 0.50: Mild mean-reversion → normal confidence
- 0.50 ≤ H < 0.55: Ambiguous → reduced position size (50%)
- H ≥ 0.55: Trending → no trades[^8][^9]

#### 3.2.2 Ornstein-Uhlenbeck Half-Life (60-day window)

**What it measures:** Expected time (in days) for price to revert halfway to its mean. If half-life > 14 days, the expected reversion is too slow for a 3–7 day swing trade.[^10][^11]

**Implementation:**

```python
def ou_half_life(price_series: np.ndarray) -> float:
    """
    Estimate OU process half-life via AR(1) regression.
    Input: array of log prices (at least 60 values)
    Output: half-life in days. Returns np.inf if non-mean-reverting.
    """
    log_prices = np.log(price_series)
    y = np.diff(log_prices)             # y(t) - y(t-1)
    x = log_prices[:-1]                 # y(t-1)
    x = np.column_stack([x, np.ones(len(x))])
    
    # OLS regression: delta_y = lambda * y(t-1) + mu + epsilon
    result = np.linalg.lstsq(x, y, rcond=None)
    lam = result
    
    if lam >= 0:
        return np.inf  # not mean-reverting
    
    half_life = -np.log(2) / lam
    return half_life

def rolling_ou_half_life(close_prices: pd.Series, window: int = 60) -> pd.Series:
    """Compute rolling OU half-life over specified window."""
    return close_prices.rolling(window).apply(
        lambda x: ou_half_life(x.values), raw=False
    )
```

**Thresholds:**
- Half-life < 7 days: Fast reversion → ideal for strategy
- 7 ≤ half-life < 14: Normal → acceptable
- Half-life ≥ 14: Slow/non-reverting → no trades[^11][^10]

#### 3.2.3 VIX Term Structure

**What it measures:** Whether VIX futures are in contango (normal, M2 > M1) or backwardation (stress, M1 > M2).[^12][^13]

**Implementation:**

```python
def vix_term_structure(m1_price: float, m2_price: float) -> dict:
    """
    Compute VIX term structure metrics.
    Input: front-month (M1) and second-month (M2) VIX futures prices
    Output: dict with slope, is_contango, contango_pct
    """
    slope = m2_price - m1_price
    contango_pct = (m2_price - m1_price) / m1_price * 100
    return {
        "slope": slope,
        "is_contango": slope > 0,
        "contango_pct": contango_pct,
        "m1": m1_price,
        "m2": m2_price
    }
```

**Data source:** Use `vix_utils` package to download CBOE VIX futures data, or subscribe to VX1!/VX2! via a data provider. For real-time, TradingView's VX1!/VX2! symbols provide M1/M2 futures prices.[^14][^1][^2]

**Thresholds:**
- Contango (slope > 0): Normal → green light
- Flat (-0.5 < slope < 0.5): Caution → half position size
- Backwardation (slope < -0.5): Stress → no new trades[^13][^15]

#### 3.2.4 Composite Regime Score

```python
class RegimeDetector:
    """
    Methods:
        compute_regime(df: pd.DataFrame, vix_data: dict) -> RegimeState
        
    RegimeState (dataclass):
        trend_gate: bool           # TQQQ > 200 SMA
        hurst_value: float         # rolling Hurst
        hurst_ok: bool             # H < 0.50
        ou_half_life: float        # rolling OU half-life
        ou_ok: bool                # half-life < 14
        vix_contango: bool         # M2 > M1
        adx_ok: bool               # ADX < 25
        composite_score: float     # 0.0 to 1.0
        regime: str                # "GREEN", "YELLOW", "RED"
        position_size_multiplier: float  # 0.0, 0.25, 0.50, 1.0
    """
```

**Composite Scoring Logic:**

```python
def compute_composite(self, trend_gate, hurst, ou_hl, contango, adx) -> tuple:
    # Hard stops — any of these = RED, no trades
    if not trend_gate:
        return 0.0, "RED", 0.0
    if hurst >= 0.60:
        return 0.0, "RED", 0.0
    if ou_hl >= 21:  # 3x target holding period
        return 0.0, "RED", 0.0
    
    # Scoring (each filter contributes 0-25 points)
    score = 0.0
    
    # Trend: binary 25 or 0
    score += 25.0 if trend_gate else 0.0
    
    # Hurst: scaled 0-25
    if hurst < 0.35:
        score += 25.0
    elif hurst < 0.45:
        score += 20.0
    elif hurst < 0.50:
        score += 15.0
    elif hurst < 0.55:
        score += 5.0
    
    # OU half-life: scaled 0-25
    if ou_hl < 5:
        score += 25.0
    elif ou_hl < 7:
        score += 20.0
    elif ou_hl < 10:
        score += 15.0
    elif ou_hl < 14:
        score += 10.0
    
    # VIX + ADX: scaled 0-25
    if contango and adx < 20:
        score += 25.0
    elif contango and adx < 25:
        score += 20.0
    elif contango:
        score += 15.0
    elif adx < 25:
        score += 10.0
    
    # Regime classification
    if score >= 75:
        return score / 100, "GREEN", 1.0
    elif score >= 50:
        return score / 100, "YELLOW", 0.50
    else:
        return score / 100, "RED", 0.0
```

***

## Module 4: ML Signal Engine

### 4.1 Purpose
Provide a probability score for each potential trade signal, filtering out low-quality RSI-2 signals that are likely to fail.

### 4.2 Feature Vector

For each day where RSI-2 < 10 AND trend gate is true, construct the following feature vector:

| Feature Index | Name | Computation | Type |
|---------------|------|-------------|------|
| 0 | `rsi_2` | Current RSI-2 value | float |
| 1 | `rsi2_consec` | Consecutive days RSI-2 < 10 | int |
| 2 | `bb_pct_b` | Bollinger %B value | float |
| 3 | `vix_sma_ratio` | VIX / VIX 50-day SMA | float |
| 4 | `vix_term_slope` | (M2 - M1) / M1 in percent | float |
| 5 | `vol_ratio` | Volume / 20-day avg volume | float |
| 6 | `mfi_14` | Money Flow Index value | float |
| 7 | `atr_pct` | ATR(14) / Close price | float |
| 8 | `hurst_100` | Rolling Hurst exponent (100d) | float |
| 9 | `ou_half_life` | Rolling OU half-life (60d) | float |
| 10 | `adx_14` | ADX(14) value | float |
| 11 | `tqqq_qqq_tracking_error` | 5-day rolling tracking error | float |
| 12 | `days_since_oversold` | Days since last RSI-2 < 10 | int |
| 13 | `drawdown_from_high` | TQQQ % below 52-week high | float |
| 14 | `sma20_slope` | 5-day slope of 20-day SMA | float |

### 4.3 Target Variable

```python
# Binary classification: will TQQQ be higher in 5 days?
target = (df['close'].shift(-5) > df['close']).astype(int)
# 1 = bounce (profitable trade), 0 = continued decline
```

### 4.4 Model Architecture

```python
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit

class MLSignalEngine:
    """
    Attributes:
        model: xgb.XGBClassifier
        feature_names: list[str]
        last_train_date: date
        performance_log: list[dict]  # track predictions vs actuals
        
    Methods:
        train(df: pd.DataFrame) -> None
            # Walk-forward training on historical data
            # Filter to only rows where RSI-2 < 10 AND price > 200 SMA
            # Train XGBoost classifier
        
        predict(features: dict) -> float
            # Return probability of bounce (0.0 to 1.0)
            # Only called when RSI-2 < 10 signal fires
        
        retrain_monthly(df: pd.DataFrame) -> None
            # Re-train on all available data through end of prior month
            # Log old vs new model accuracy
        
        get_feature_importance() -> dict
            # Return SHAP or gain-based feature importance
    """
```

### 4.5 XGBoost Configuration

```python
ML_CONFIG = {
    "model_params": {
        "n_estimators": 200,
        "max_depth": 4,           # shallow trees to prevent overfitting
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,    # requires 5+ samples per leaf
        "scale_pos_weight": 1.0,  # adjust if class imbalance
        "objective": "binary:logistic",
        "eval_metric": "auc",
        "random_state": 42
    },
    "walk_forward": {
        "train_window_days": 504,  # 2 years
        "test_window_days": 63,    # 3 months
        "step_days": 21,           # slide forward 1 month
        "min_train_samples": 30    # minimum RSI-2 < 10 events to train
    },
    "prediction_threshold": 0.60,  # only trade if P(bounce) > 60%
    "retrain_schedule": "monthly"  # first trading day of each month
}
```

### 4.6 Walk-Forward Training Loop

```python
def walk_forward_train(self, df: pd.DataFrame):
    """
    Walk-forward validation and final model training.
    
    Steps:
    1. Filter df to rows where rsi_2 < 10 AND close > sma_200
    2. Create feature matrix X and target y
    3. For each fold:
       a. Train on [i : i + train_window]
       b. Predict on [i + train_window : i + train_window + test_window]
       c. Record AUC, accuracy, precision, recall
    4. Train final model on ALL available data
    5. Save model to disk with timestamp
    """
    # TimeSeriesSplit ensures no lookahead bias
    tscv = TimeSeriesSplit(n_splits=5)
    fold_results = []
    
    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        
        model = xgb.XGBClassifier(**self.config["model_params"])
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False
        )
        
        y_pred_proba = model.predict_proba(X_val)[:, 1]
        # Record metrics for this fold
    
    # Final model trained on all data
    self.model = xgb.XGBClassifier(**self.config["model_params"])
    self.model.fit(X, y)
```

***

## Module 5: Trade Decision Engine

### 5.1 Purpose
The central orchestrator that combines signals from all other modules and makes entry, exit, hedge roll, and position sizing decisions.

### 5.2 State Machine

The system operates in one of these states at any time:

```
IDLE → SIGNAL_DETECTED → ENTRY_CONFIRMED → POSITION_OPEN → 
    ├── BOUNCE_EXIT (success)
    ├── HEDGE_ROLL (theta kicker)
    ├── TIME_STOP_EXIT (12-day max)
    ├── EMERGENCY_EXIT (10%+ adverse)
    └── REGIME_EXIT (filter turned red mid-trade)

CIRCUIT_BREAKER_HALT → OBSERVE → PROBE → SCALE → NORMAL
```

### 5.3 Entry Logic (Detailed Decision Tree)

```python
def evaluate_entry(self) -> EntryDecision:
    """
    Called daily at 3:30 PM EST.
    Returns EntryDecision with action, strike selection, sizing.
    """
    
    # Step 1: Circuit breaker check
    if self.circuit_breaker.is_active():
        if self.circuit_breaker.phase == "HALT":
            return EntryDecision(action="NO_TRADE", reason="Circuit breaker HALT")
        elif self.circuit_breaker.phase == "OBSERVE":
            return EntryDecision(action="NO_TRADE", reason="Circuit breaker OBSERVE")
        # PROBE and SCALE phases allow reduced-size trades (handled in sizing)
    
    # Step 2: Regime check (hard gates)
    regime = self.regime_detector.compute_regime(self.data, self.vix_data)
    if regime.regime == "RED":
        return EntryDecision(action="NO_TRADE", reason=f"Regime RED: {regime}")
    
    # Step 3: Signal check
    signals = self.indicator_engine.get_current_signals(self.data)
    if signals["rsi_2"] >= 10:
        return EntryDecision(action="NO_TRADE", reason="RSI-2 not oversold")
    
    # Step 4: ML probability check
    features = self.build_feature_vector(signals, regime)
    ml_prob = self.ml_engine.predict(features)
    if ml_prob < ML_CONFIG["prediction_threshold"]:
        return EntryDecision(
            action="NO_TRADE", 
            reason=f"ML probability too low: {ml_prob:.2f}"
        )
    
    # Step 5: Concurrent position check
    if self.position_manager.total_risk_pct() >= MAX_CONCURRENT_RISK:
        return EntryDecision(action="NO_TRADE", reason="Max concurrent risk reached")
    
    # Step 6: Select strikes and construct spread
    spread = self.select_spread(signals, regime, ml_prob)
    size = self.compute_position_size(regime, ml_prob)
    
    return EntryDecision(
        action="ENTER",
        spread=spread,
        contracts=size,
        ml_probability=ml_prob,
        regime_score=regime.composite_score,
        entry_signals=signals
    )
```

### 5.4 Strike Selection Algorithm

```python
def select_spread(self, signals: dict, regime: RegimeState, ml_prob: float) -> SpreadSpec:
    """
    Select optimal put strikes for the diagonal spread.
    
    ANCHOR LEG (short put):
        - Target: -0.25 delta
        - DTE: 30-45 days (prefer 45 for more premium)
        - Select expiration closest to 45 DTE
        - Select strike with delta closest to -0.25
        - Constraints: strike must have open interest > 100
                       bid-ask spread < $0.10 or < 5% of mid price
    
    HEDGE LEG (long put):
        - Target: -0.06 to -0.10 delta
        - DTE: 7-12 days (prefer 10)
        - Select expiration closest to 10 DTE
        - Select strike with delta closest to -0.08 (midpoint of range)
        - Must be BELOW anchor strike (further OTM)
        - Constraints: same liquidity requirements
    """
    
    chain = self.data_pipeline.get_options_chain(
        self.session, min_dte=7, max_dte=61
    )
    
    # --- Anchor Leg ---
    anchor_candidates = []
    for exp_date, strikes in chain.items():
        dte = (exp_date - date.today()).days
        if 30 <= dte <= 50:
            for strike in strikes:
                greeks = strike.put_greeks
                if greeks and -0.35 <= greeks.delta <= -0.15:
                    if strike.put_open_interest > 100:
                        anchor_candidates.append({
                            "exp": exp_date,
                            "strike": strike.strike_price,
                            "delta": greeks.delta,
                            "symbol": strike.put_symbol,
                            "dte": dte,
                            "bid": strike.put_bid,
                            "ask": strike.put_ask,
                            "delta_diff": abs(greeks.delta - (-0.25))
                        })
    
    # Sort by closest to target delta, then prefer 45 DTE
    anchor_candidates.sort(key=lambda x: (x["delta_diff"], abs(x["dte"] - 45)))
    anchor = anchor_candidates
    
    # --- Hedge Leg ---
    hedge_candidates = []
    for exp_date, strikes in chain.items():
        dte = (exp_date - date.today()).days
        if 7 <= dte <= 14:
            for strike in strikes:
                greeks = strike.put_greeks
                if greeks and -0.15 <= greeks.delta <= -0.03:
                    if strike.strike_price < anchor["strike"]:
                        hedge_candidates.append({
                            "exp": exp_date,
                            "strike": strike.strike_price,
                            "delta": greeks.delta,
                            "symbol": strike.put_symbol,
                            "dte": dte,
                            "bid": strike.put_bid,
                            "ask": strike.put_ask,
                            "delta_diff": abs(greeks.delta - (-0.08))
                        })
    
    hedge_candidates.sort(key=lambda x: (x["delta_diff"], abs(x["dte"] - 10)))
    hedge = hedge_candidates
    
    return SpreadSpec(
        anchor_symbol=anchor["symbol"],
        anchor_strike=anchor["strike"],
        anchor_exp=anchor["exp"],
        anchor_delta=anchor["delta"],
        anchor_dte=anchor["dte"],
        hedge_symbol=hedge["symbol"],
        hedge_strike=hedge["strike"],
        hedge_exp=hedge["exp"],
        hedge_delta=hedge["delta"],
        hedge_dte=hedge["dte"],
        net_credit_or_debit=anchor["bid"] - hedge["ask"],  # positive = credit
    )
```

### 5.5 Hybrid Exit Logic (Swing Trade with Theta Kicker)

This is the core innovation — the system adapts its behavior based on whether the bounce happens quickly or slowly.

```python
def evaluate_exit(self, position: OpenPosition) -> ExitDecision:
    """
    Called daily at 3:30 PM EST for each open position.
    
    EXIT PRIORITY (checked in order):
    1. Emergency exit: TQQQ dropped 10%+ from entry price
    2. Regime exit: Any regime filter turned RED mid-trade
    3. Bounce exit: Price crossed above 5-day SMA OR RSI-2 > 70
    4. Hedge roll (theta kicker): Hedge DTE <= 1 AND regime still GREEN
    5. Time stop: Position held > 12 trading days
    """
    
    days_held = (date.today() - position.entry_date).days
    current_price = self.data_pipeline.tqqq_daily["close"].iloc[-1]
    signals = self.indicator_engine.get_current_signals(self.data)
    regime = self.regime_detector.compute_regime(self.data, self.vix_data)
    
    # --- EXIT 1: Emergency Stop ---
    pct_change = (current_price - position.entry_price) / position.entry_price
    if pct_change <= -0.10:  # TQQQ down 10%+ from entry
        return ExitDecision(
            action="CLOSE_ALL",
            reason=f"Emergency stop: TQQQ down {pct_change:.1%} from entry",
            urgency="IMMEDIATE"
        )
    
    # --- EXIT 2: Regime Deterioration ---
    if regime.regime == "RED":
        return ExitDecision(
            action="CLOSE_ALL",
            reason=f"Regime turned RED mid-trade: {regime}",
            urgency="END_OF_DAY"
        )
    
    # --- EXIT 3: Bounce Achieved (Primary Profit Target) ---
    bounce_achieved = (
        current_price > signals["sma_5"]  # price above 5-day SMA
        or signals["rsi_2"] > 70          # RSI-2 overbought
    )
    if bounce_achieved:
        return ExitDecision(
            action="CLOSE_ALL",
            reason=f"Bounce exit: price={current_price}, sma5={signals['sma_5']:.2f}, rsi2={signals['rsi_2']:.1f}",
            urgency="END_OF_DAY",
            target_profit_pct=self._calc_spread_pnl(position)
        )
    
    # --- EXIT 4: Hedge Roll (Theta Kicker) ---
    hedge_dte = (position.hedge_exp - date.today()).days
    if hedge_dte <= 1 and regime.regime != "RED":
        # The hedge is expiring. Decision: roll or close?
        
        anchor_dte = (position.anchor_exp - date.today()).days
        anchor_pnl = self._calc_anchor_pnl(position)
        
        # Roll the hedge if:
        # - Regime is still GREEN/YELLOW
        # - Anchor short put has already decayed meaningfully (>15% profit)
        # - Total days held < 12 (still within time window)
        # - ML model still gives >50% probability of bounce
        
        current_features = self.build_feature_vector(signals, regime)
        current_ml_prob = self.ml_engine.predict(current_features)
        
        should_roll = (
            regime.regime in ["GREEN", "YELLOW"]
            and days_held < 10  # leave 2 days buffer before time stop
            and anchor_dte > 15  # anchor still has meaningful time value
            and current_ml_prob > 0.50  # relaxed threshold for roll
        )
        
        if should_roll:
            new_hedge = self._select_new_hedge(position)
            return ExitDecision(
                action="ROLL_HEDGE",
                reason=f"Theta kicker: rolling hedge. Days held={days_held}, ML prob={current_ml_prob:.2f}",
                new_hedge=new_hedge,
                max_rolls_remaining=MAX_HEDGE_ROLLS - position.hedge_roll_count
            )
        else:
            return ExitDecision(
                action="CLOSE_ALL",
                reason=f"Hedge expiring, conditions not met for roll. ML={current_ml_prob:.2f}",
                urgency="IMMEDIATE"
            )
    
    # --- EXIT 5: Time Stop ---
    if days_held >= 12:
        return ExitDecision(
            action="CLOSE_ALL",
            reason=f"Time stop: {days_held} trading days held (max 12)",
            urgency="END_OF_DAY"
        )
    
    # --- No exit condition met ---
    return ExitDecision(action="HOLD", reason="No exit trigger")
```

### 5.6 Hedge Roll Mechanics (Theta Kicker Detail)

```python
def _select_new_hedge(self, position: OpenPosition) -> HedgeSpec:
    """
    Select a new hedge put when rolling the expiring one.
    
    Rules:
    - Same delta target as original (-0.06 to -0.10)
    - New DTE: 7-12 days
    - Strike must be below anchor strike
    - Must be a NET CREDIT or small debit to roll
      (sell expiring hedge for residual value, buy new hedge)
    - Maximum 2 rolls per position (3 total hedge cycles)
    """
    
    # Close expiring hedge (buy to close if short, sell to close if long)
    expiring_value = self._get_current_bid(position.hedge_symbol)
    
    # Select new hedge
    chain = self.data_pipeline.get_options_chain(self.session, min_dte=7, max_dte=14)
    # ... same selection logic as initial hedge in select_spread()
    
    new_hedge = best_candidate
    roll_cost = new_hedge["ask"] - expiring_value  # positive = debit
    
    return HedgeSpec(
        close_symbol=position.hedge_symbol,
        close_price=expiring_value,
        open_symbol=new_hedge["symbol"],
        open_strike=new_hedge["strike"],
        open_exp=new_hedge["exp"],
        open_delta=new_hedge["delta"],
        roll_cost=roll_cost,
        roll_number=position.hedge_roll_count + 1
    )
```

### 5.7 Position Sizing

```python
def compute_position_size(self, regime: RegimeState, ml_prob: float) -> int:
    """
    Determine number of contracts based on regime, ML confidence, 
    and circuit breaker phase.
    
    Base risk: 2-3% of portfolio per trade
    Max risk per spread = (anchor_strike - hedge_strike) * 100
    """
    
    portfolio_value = self.account.get_balance().net_liquidating_value
    base_risk_pct = 0.025  # 2.5% base
    
    # Regime adjustment
    size_multiplier = regime.position_size_multiplier  # 0.0, 0.50, or 1.0
    
    # ML confidence adjustment
    if ml_prob > 0.75:
        ml_multiplier = 1.2  # slight increase for high conviction
    elif ml_prob > 0.60:
        ml_multiplier = 1.0
    else:
        ml_multiplier = 0.0  # shouldn't reach here due to threshold
    
    # Circuit breaker phase adjustment
    cb_multiplier = {
        "NORMAL": 1.0,
        "SCALE": 0.50,
        "PROBE": 0.25,
        "OBSERVE": 0.0,
        "HALT": 0.0
    }[self.circuit_breaker.phase]
    
    risk_budget = portfolio_value * base_risk_pct * size_multiplier * ml_multiplier * cb_multiplier
    
    # Max loss per contract = width of spread * 100
    spread_width = self.current_spread.anchor_strike - self.current_spread.hedge_strike
    max_loss_per_contract = float(spread_width) * 100
    
    contracts = max(1, int(risk_budget / max_loss_per_contract))
    
    # Cap at max concurrent risk
    current_risk = self.position_manager.total_risk_dollars()
    max_total_risk = portfolio_value * MAX_CONCURRENT_RISK_PCT
    remaining_budget = max_total_risk - current_risk
    contracts = min(contracts, int(remaining_budget / max_loss_per_contract))
    
    return max(0, contracts)

# Configuration
SIZING_CONFIG = {
    "base_risk_pct": 0.025,           # 2.5% per trade
    "max_concurrent_risk_pct": 0.10,  # 10% total across all positions
    "max_contracts_per_trade": 10,     # hard cap
    "max_concurrent_positions": 3,     # max 3 open spreads at once
}
```

***

## Module 6: Position Manager & Order Execution

### 6.1 Purpose
Track all open positions, execute orders through Tastytrade, handle fills, and manage the position lifecycle.

### 6.2 Order Construction for Tastytrade SDK

```python
from decimal import Decimal
from tastytrade import Account, Session
from tastytrade.instruments import Option, get_option_chain
from tastytrade.order import (
    NewOrder, OrderAction, OrderTimeInForce, OrderType, Leg, InstrumentType
)

class PositionManager:
    """
    Attributes:
        session: Session
        account: Account
        open_positions: list[OpenPosition]
        trade_journal: list[TradeRecord]  # persisted to DB
        
    Methods:
        open_spread(spread: SpreadSpec, contracts: int) -> OrderResult
        close_spread(position: OpenPosition) -> OrderResult
        roll_hedge(position: OpenPosition, new_hedge: HedgeSpec) -> OrderResult
        get_positions() -> list[OpenPosition]
        total_risk_pct() -> float
        total_risk_dollars() -> float
    """

    def open_spread(self, spread: SpreadSpec, contracts: int) -> OrderResult:
        """
        Place a 2-leg order: sell anchor put + buy hedge put.
        Uses Tastytrade SDK multi-leg order.
        """
        # Build anchor leg (SELL TO OPEN)
        anchor_option = Option.get_option(self.session, spread.anchor_symbol)
        anchor_leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=spread.anchor_symbol,
            action=OrderAction.SELL_TO_OPEN,
            quantity=Decimal(str(contracts))
        )
        
        # Build hedge leg (BUY TO OPEN)
        hedge_leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=spread.hedge_symbol,
            action=OrderAction.BUY_TO_OPEN,
            quantity=Decimal(str(contracts))
        )
        
        # Calculate limit price (net credit expected)
        # Positive price = credit received
        net_credit = spread.net_credit_or_debit
        
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[anchor_leg, hedge_leg],
            price=Decimal(str(round(net_credit, 2)))
        )
        
        # Dry run first for validation
        dry_response = self.account.place_order(self.session, order, dry_run=True)
        
        if dry_response.errors:
            return OrderResult(success=False, errors=dry_response.errors)
        
        # Place live order
        response = self.account.place_order(self.session, order, dry_run=False)
        
        # Record in journal
        self._record_trade(spread, contracts, response)
        
        return OrderResult(
            success=True,
            order_id=response.order.id,
            fill_price=None  # filled async
        )
    
    def close_spread(self, position: OpenPosition) -> OrderResult:
        """
        Close both legs: buy to close anchor + sell to close hedge.
        """
        anchor_leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=position.anchor_symbol,
            action=OrderAction.BUY_TO_CLOSE,
            quantity=Decimal(str(position.contracts))
        )
        
        hedge_leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=position.hedge_symbol,
            action=OrderAction.SELL_TO_CLOSE,
            quantity=Decimal(str(position.contracts))
        )
        
        # Use market order for urgency, limit for normal exits
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[anchor_leg, hedge_leg],
            price=self._calculate_close_price(position)  # mid-price of spread
        )
        
        response = self.account.place_order(self.session, order, dry_run=False)
        return OrderResult(success=True, order_id=response.order.id)
    
    def roll_hedge(self, position: OpenPosition, new_hedge: HedgeSpec) -> OrderResult:
        """
        Roll the hedge: close expiring hedge + open new hedge.
        This is a 2-order sequence (Tastytrade doesn't support 
        rolling across expirations in a single order for diagonals).
        """
        # Order 1: Close expiring hedge
        close_leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=new_hedge.close_symbol,
            action=OrderAction.SELL_TO_CLOSE,
            quantity=Decimal(str(position.contracts))
        )
        close_order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[close_leg],
            price=Decimal(str(round(new_hedge.close_price, 2)))
        )
        close_response = self.account.place_order(self.session, close_order, dry_run=False)
        
        # Order 2: Open new hedge
        open_leg = Leg(
            instrument_type=InstrumentType.EQUITY_OPTION,
            symbol=new_hedge.open_symbol,
            action=OrderAction.BUY_TO_OPEN,
            quantity=Decimal(str(position.contracts))
        )
        open_order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[open_leg],
            price=Decimal(str(-round(new_hedge.roll_cost, 2)))  # negative = debit
        )
        open_response = self.account.place_order(self.session, open_order, dry_run=False)
        
        # Update position record
        position.hedge_symbol = new_hedge.open_symbol
        position.hedge_strike = new_hedge.open_strike
        position.hedge_exp = new_hedge.open_exp
        position.hedge_delta = new_hedge.open_delta
        position.hedge_roll_count += 1
        
        return OrderResult(success=True)
```

### 6.3 Important Tastytrade SDK Notes for Antigravity

- **Authentication:** `Session("username", "password")` for live; `Session("username", "password", is_test=True)` for sandbox[^16][^17]
- **Option symbology:** OCC format — `TQQQ  260320P00055000` = TQQQ, March 20 2026 expiry, Put, $55 strike[^17][^18]
- **Price convention:** Negative = debit, positive = credit in the SDK (opposite of the platform UI)[^19]
- **Multi-leg limitation:** Diagonal spreads span expirations, so they must be built manually as multi-leg orders, not using built-in spread types[^20]
- **Dry run:** Always call `dry_run=True` first to validate buying power and fees before live execution[^19]
- **Greeks streaming:** Use `DXLinkStreamer` with `Greeks` subscription for real-time delta/gamma[^4]

***

## Module 7: Circuit Breaker System

### 7.1 Purpose
Protect the portfolio from catastrophic losses and manage the recovery process with a tiered re-entry protocol.

### 7.2 State Machine

```python
from enum import Enum
from dataclasses import dataclass

class CBPhase(Enum):
    NORMAL = "NORMAL"
    HALT = "HALT"
    OBSERVE = "OBSERVE"
    PROBE = "PROBE"
    SCALE = "SCALE"

@dataclass
class CircuitBreakerState:
    phase: CBPhase
    triggered_date: date | None
    trigger_drawdown: float | None      # drawdown % that triggered
    peak_equity: float                   # high-water mark
    current_equity: float
    probe_trade_count: int               # trades completed in PROBE
    probe_profitable_count: int          # profitable trades in PROBE
    days_in_current_phase: int
    
class CircuitBreaker:
    """
    Configuration:
        TRIGGER_DRAWDOWN_PCT: -0.10       # 10% drawdown triggers HALT
        MIN_HALT_DAYS: 5                   # minimum days in HALT
        MIN_OBSERVE_DAYS: 5                # minimum days in OBSERVE
        PROBE_WIN_REQUIREMENT: 3           # consecutive profitable trades to advance
        SCALE_RECOVERY_PCT: -0.05          # advance to NORMAL when drawdown < 5%
        
    Phase Transitions:
        NORMAL → HALT:    drawdown from peak >= 10%
        HALT → OBSERVE:   5 trading days elapsed
        OBSERVE → PROBE:  All re-entry signals met (see below)
        PROBE → SCALE:    3 consecutive profitable probe trades
        SCALE → NORMAL:   drawdown from peak recovers to < 5%
        ANY → HALT:       drawdown from CURRENT phase peak >= 10%
    """
    
    def check_trigger(self, current_equity: float) -> bool:
        drawdown = (current_equity - self.state.peak_equity) / self.state.peak_equity
        if drawdown <= -TRIGGER_DRAWDOWN_PCT:
            self.transition_to(CBPhase.HALT)
            return True
        return False
    
    def check_phase_transition(self, regime: RegimeState, signals: dict) -> CBPhase:
        if self.state.phase == CBPhase.HALT:
            if self.state.days_in_current_phase >= MIN_HALT_DAYS:
                self.transition_to(CBPhase.OBSERVE)
        
        elif self.state.phase == CBPhase.OBSERVE:
            if self.state.days_in_current_phase >= MIN_OBSERVE_DAYS:
                if self._reentry_conditions_met(regime, signals):
                    self.transition_to(CBPhase.PROBE)
        
        elif self.state.phase == CBPhase.PROBE:
            if self.state.probe_profitable_count >= PROBE_WIN_REQUIREMENT:
                self.transition_to(CBPhase.SCALE)
        
        elif self.state.phase == CBPhase.SCALE:
            drawdown = (self.state.current_equity - self.state.peak_equity) / self.state.peak_equity
            if drawdown > -SCALE_RECOVERY_PCT:
                self.transition_to(CBPhase.NORMAL)
                self.state.peak_equity = self.state.current_equity  # reset HWM
        
        return self.state.phase
    
    def _reentry_conditions_met(self, regime: RegimeState, signals: dict) -> bool:
        """
        ALL conditions must be true to move from OBSERVE to PROBE:
        1. VIX < VIX 50-day SMA for 3 consecutive days
        2. TQQQ > 20-day SMA AND 20-SMA slope positive for 5 days
        3. At least one regime filter is GREEN (Hurst < 0.50 OR VIX contango)
        4. RSI-2 has generated at least 1 qualifying signal in past 10 days
           that WOULD have been profitable (paper trade validation)
        """
        vix_normalized = signals.get("vix_below_sma_consecutive", 0) >= 3
        tqqq_recovering = (
            signals["close"] > signals["sma_20"]
            and signals.get("sma20_slope_positive_days", 0) >= 5
        )
        regime_ok = regime.hurst_ok or regime.vix_contango
        paper_validated = self._check_paper_trades()
        
        return all([vix_normalized, tqqq_recovering, regime_ok, paper_validated])
```

***

## Module 8: Logging, Monitoring & Alerts

### 8.1 Database Schema (SQLite)

```sql
-- Trade journal
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date DATE NOT NULL,
    exit_date DATE,
    anchor_symbol TEXT NOT NULL,
    anchor_strike REAL NOT NULL,
    anchor_exp DATE NOT NULL,
    anchor_delta REAL,
    hedge_symbol TEXT NOT NULL,
    hedge_strike REAL NOT NULL,
    hedge_exp DATE NOT NULL,
    hedge_delta REAL,
    contracts INTEGER NOT NULL,
    entry_price REAL,          -- net credit/debit at entry
    exit_price REAL,           -- net credit/debit at exit
    realized_pnl REAL,
    exit_reason TEXT,          -- BOUNCE, TIME_STOP, EMERGENCY, REGIME, ROLL
    hedge_rolls INTEGER DEFAULT 0,
    ml_probability REAL,
    regime_score REAL,
    entry_rsi2 REAL,
    entry_vix REAL,
    entry_hurst REAL,
    entry_ou_halflife REAL,
    status TEXT DEFAULT 'OPEN'  -- OPEN, CLOSED, ROLLED
);

-- Daily state snapshot
CREATE TABLE daily_state (
    date DATE PRIMARY KEY,
    portfolio_value REAL,
    drawdown_from_peak REAL,
    circuit_breaker_phase TEXT,
    regime_state TEXT,
    regime_score REAL,
    hurst_value REAL,
    ou_halflife REAL,
    vix_close REAL,
    vix_term_slope REAL,
    rsi2 REAL,
    tqqq_close REAL,
    positions_open INTEGER,
    total_risk_pct REAL
);

-- ML model performance tracking
CREATE TABLE ml_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_date DATE,
    ml_probability REAL,
    predicted_class INTEGER,    -- 1=bounce, 0=continue
    actual_5d_return REAL,
    actual_class INTEGER,
    model_version TEXT
);

-- Circuit breaker events
CREATE TABLE circuit_breaker_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date DATE,
    from_phase TEXT,
    to_phase TEXT,
    trigger_reason TEXT,
    portfolio_value REAL,
    drawdown_pct REAL
);
```

### 8.2 Alert System

```python
ALERT_CONFIG = {
    "channels": ["email", "sms"],   # or webhook/Discord/Telegram
    "alerts": {
        "trade_entry": True,         # notify on every entry
        "trade_exit": True,          # notify on every exit
        "hedge_roll": True,          # notify on hedge roll
        "circuit_breaker_trigger": True,  # CRITICAL
        "circuit_breaker_phase_change": True,
        "regime_change": True,       # RED/GREEN transitions
        "daily_pnl_threshold": -0.03,  # alert if daily P&L < -3%
        "ml_retrain_complete": True,
    }
}
```

***

## Module 9: Scheduler & Main Loop

### 9.1 Daily Execution Schedule

| Time (EST) | Action | Module |
|-------------|--------|--------|
| 9:31 AM | Refresh daily data (previous close) | Module 1 |
| 9:35 AM | Compute indicators | Module 2 |
| 9:40 AM | Compute regime state | Module 3 |
| 3:30 PM | **Main scan:** evaluate all entry/exit conditions | Module 5 |
| 3:35 PM | Execute any entry/exit/roll orders | Module 6 |
| 3:55 PM | Verify fills, update positions | Module 6 |
| 4:05 PM | End-of-day state snapshot to DB | Module 8 |
| 4:10 PM | Send daily summary alert | Module 8 |
| 1st of month, 9:00 AM | ML model retrain | Module 4 |

### 9.2 Main Loop

```python
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

class TradingSystem:
    def __init__(self, config: dict):
        self.data = DataPipeline(config)
        self.indicators = IndicatorEngine(config)
        self.regime = RegimeDetector(config)
        self.ml = MLSignalEngine(config)
        self.decisions = TradeDecisionEngine(config)
        self.positions = PositionManager(config)
        self.circuit_breaker = CircuitBreaker(config)
        self.logger = TradingLogger(config)
        self.scheduler = BlockingScheduler()
    
    def run(self):
        # Morning data refresh
        self.scheduler.add_job(
            self.morning_refresh,
            CronTrigger(hour=9, minute=31, timezone="US/Eastern"),
            day_of_week="mon-fri"
        )
        
        # Main trading scan
        self.scheduler.add_job(
            self.afternoon_scan,
            CronTrigger(hour=15, minute=30, timezone="US/Eastern"),
            day_of_week="mon-fri"
        )
        
        # Order execution
        self.scheduler.add_job(
            self.execute_orders,
            CronTrigger(hour=15, minute=35, timezone="US/Eastern"),
            day_of_week="mon-fri"
        )
        
        # End-of-day wrap
        self.scheduler.add_job(
            self.end_of_day,
            CronTrigger(hour=16, minute=5, timezone="US/Eastern"),
            day_of_week="mon-fri"
        )
        
        # Monthly ML retrain
        self.scheduler.add_job(
            self.monthly_retrain,
            CronTrigger(day=1, hour=9, minute=0, timezone="US/Eastern")
        )
        
        self.scheduler.start()
    
    def afternoon_scan(self):
        """Main decision loop — called at 3:30 PM EST."""
        try:
            # Refresh latest intraday data
            self.data.refresh_daily_data()
            df = self.data.tqqq_daily
            
            # Compute all indicators
            df = self.indicators.compute_all(df)
            
            # Compute regime
            vix_data = self.data.get_vix_term_structure()
            regime = self.regime.compute_regime(df, vix_data)
            
            # Check circuit breaker
            equity = self.positions.get_account_equity()
            self.circuit_breaker.check_trigger(equity)
            self.circuit_breaker.check_phase_transition(regime, self.indicators.get_current_signals(df))
            
            # Evaluate exits for all open positions
            for position in self.positions.get_open_positions():
                exit_decision = self.decisions.evaluate_exit(position)
                if exit_decision.action != "HOLD":
                    self.pending_orders.append(("EXIT", position, exit_decision))
            
            # Evaluate new entry
            entry_decision = self.decisions.evaluate_entry()
            if entry_decision.action == "ENTER":
                self.pending_orders.append(("ENTRY", None, entry_decision))
            
            # Log state
            self.logger.log_daily_state(df, regime, equity)
            
        except Exception as e:
            self.logger.log_error(e)
            self.alert("SYSTEM_ERROR", str(e))
```

***

## Configuration Summary

```python
MASTER_CONFIG = {
    # --- Strategy Parameters ---
    "anchor_target_delta": -0.25,
    "anchor_min_dte": 30,
    "anchor_max_dte": 50,
    "anchor_preferred_dte": 45,
    "hedge_target_delta": -0.08,
    "hedge_min_dte": 7,
    "hedge_max_dte": 14,
    "hedge_preferred_dte": 10,
    "max_hedge_rolls": 2,           # 3 total hedge cycles max
    
    # --- Signal Thresholds ---
    "rsi2_entry_threshold": 10,
    "rsi2_exit_threshold": 70,
    "sma_bounce_period": 5,
    "ml_entry_threshold": 0.60,
    "ml_roll_threshold": 0.50,
    
    # --- Regime Filters ---
    "hurst_window": 100,
    "hurst_max_for_trade": 0.50,
    "hurst_red_threshold": 0.55,
    "ou_window": 60,
    "ou_max_halflife": 14,
    "adx_max_for_trade": 25,
    "sma_trend_period": 200,
    
    # --- Position Sizing ---
    "base_risk_pct": 0.025,
    "max_concurrent_risk_pct": 0.10,
    "max_contracts_per_trade": 10,
    "max_concurrent_positions": 3,
    
    # --- Exit Rules ---
    "emergency_stop_pct": -0.10,
    "time_stop_days": 12,
    
    # --- Circuit Breaker ---
    "cb_trigger_drawdown": -0.10,
    "cb_halt_days": 5,
    "cb_observe_days": 5,
    "cb_probe_wins_required": 3,
    "cb_scale_recovery_pct": -0.05,
    
    # --- Execution ---
    "min_open_interest": 100,
    "max_bid_ask_spread_pct": 0.05,
    "use_sandbox": True,            # True for testing, False for live
    
    # --- Data ---
    "history_days": 504,
    "vix_futures_source": "vix_utils",
    "cache_db": "trading_system.sqlite",
}
```

***

## Testing & Deployment Checklist

### Phase 1: Backtesting (Week 1–2)
- [ ] Build historical feature dataset (TQQQ OHLCV + VIX + indicators, 2020–2025)
- [ ] Validate Hurst exponent calculation against known values
- [ ] Validate OU half-life calculation against `arbitragelab` library[^10]
- [ ] Run walk-forward XGBoost training, verify AUC > 0.55 on out-of-sample
- [ ] Backtest entry/exit logic on historical data with simulated fills
- [ ] Verify circuit breaker would have prevented 2022 catastrophic losses
- [ ] Calculate backtest Sharpe, max drawdown, win rate, avg trade duration

### Phase 2: Paper Trading (Week 3–4)
- [ ] Deploy on Tastytrade sandbox (`is_test=True`)
- [ ] Run full system for 2 weeks with live market data, no real orders
- [ ] Verify order construction produces valid OCC symbols
- [ ] Test hedge roll mechanics end-to-end
- [ ] Verify Greeks streaming provides real-time delta for strike selection
- [ ] Confirm all alerts fire correctly

### Phase 3: Small Live (Week 5+)
- [ ] Switch to live Tastytrade session
- [ ] Set `max_contracts_per_trade: 1` initially
- [ ] Monitor fills, slippage, and actual vs. expected execution
- [ ] Run for 1 month before increasing size
- [ ] Review ML model performance vs. backtest expectations

### Phase 4: Full Deployment
- [ ] Scale to configured position sizes
- [ ] Set up monitoring dashboard (Grafana or custom)
- [ ] Implement automatic daily backup of SQLite database
- [ ] Set up fail-safe: if system doesn't run by 3:45 PM, alert immediately

***

## Dependencies

```
# requirements.txt
tastytrade>=12.0         # Tastytrade SDK
pandas>=2.0
numpy>=1.24
scikit-learn>=1.3
xgboost>=2.0
ta>=0.11                 # Technical analysis indicators
yfinance>=0.2.30
vix-utils>=0.0.5         # VIX term structure data
apscheduler>=3.10        # Job scheduling
sqlalchemy>=2.0          # Database ORM (optional, can use raw sqlite3)
requests>=2.31
python-dotenv>=1.0       # Credentials management
```

---

## References

1. [vix-utils - PyPI](https://pypi.org/project/vix-utils/) - Provide VIX Cash and Futures Term Structure as Pandas dataframes

2. [dougransom/vix_utils - GitHub](https://github.com/dougransom/vix_utils) - vix_utils provides command line tools and a a Python API for preparing data for analysing the VIX Fu...

3. [Instruments - tastytrade 12.0.2 documentation](https://tastyworks-api.readthedocs.io/en/latest/instruments.html) - Options chains​​ Alternatively, NestedOptionChain and NestedFutureOptionChain provide a structured w...

4. [tastytrade - PyPI](https://pypi.org/project/tastytrade/) - An unofficial, sync/async SDK for Tastytrade!

5. [Mathematical Intuition of the ADX Indicator: A Python Approach](https://blog.quantinsti.com/adx-indicator-python/) - The ADX indicator is calculated as the smoothed average of the difference between the +DI indicator ...

6. [Momentum Indicators](https://ta-lib.github.io/ta-lib-python/func_groups/momentum_indicators.html) - TA-Lib : Python wrapper for TA-Lib (https://ta-lib.org/).

7. [Exploring the Hurst Exponent - Samara Alpha Management](https://www.samara-am.com/insights/hurst-exponent) - We can use the Hurst exponent as a regime filter to segment trending versus non-trending market and ...

8. [The Hurst Exponent: Trend vs Range Detection | FractalCycles Guides](https://fractalcycles.com/guides/hurst-exponent-explained) - In a mean-reverting regime, the trough may represent a more complete reversal. This combination of t...

9. [Rolling Hurst Exponent: Detecting Regime Shifts in Real-Time](https://fractalcycles.com/guides/rolling-hurst-exponent) - Track how market character evolves over time. A rolling Hurst calculation reveals regime transitions...

10. [Trading Under the Ornstein-Uhlenbeck Model](https://hudson-and-thames-arbitragelab.readthedocs-hosted.com/en/latest/optimal_mean_reversion/ou_model.html)

11. [Half life of Mean Reversion – Ornstein-Uhlenbeck Formula for Mean ...](https://flare9xblog.wordpress.com/2017/09/27/half-life-of-mean-reversion-ornstein-uhlenbeck-formula-for-mean-reverting-process/) - Ernie chan proposes a method to calculate the speed of mean reversion. He proposes to adjust the ADF...

12. [Exploiting Term Structure of VIX Futures - Quantpedia](https://quantpedia.com/strategies/exploiting-term-structure-of-vix-futures) - When the VIX futures curve is upward sloped (in contango), the VIX is expected to rise because it is...

13. [Inside Volatility Trading: Is VIX Backwardation Necessarily ...](https://www.cboe.com/insights/posts/inside-volatility-trading-is-vix-backwardation-necessarily-a-sign-of-a-future-down-market/) - Cboe Global Markets, a leading provider of market infrastructure and tradable products, delivers cut...

14. [VIX Term Structure Tracker [VX1!/VX2!] — Indicator by chinodc1](https://www.tradingview.com/script/rNSLWu2s-VIX-Term-Structure-Tracker-VX1-VX2/) - 1. Data Preparation The script starts by fetching four key data series on a daily ("D") timeframe: V...

15. [Bear Market and VIX Pattern: How to Read Volatility Signals for ...](https://intellectia.ai/blog/bear-market-vix-pattern) - Learn how VIX volatility patterns signal bear market bottoms and tops. Discover key VIX thresholds, ...

16. [An unofficial, sync/async Python SDK for Tastytrade! - GitHub](https://github.com/tastyware/tastytrade) - An unofficial, sync/async Python SDK for Tastytrade! - tastyware/tastytrade

17. [tastytrade API Overview](https://developer.tastytrade.com/api-overview/)

18. [API Overview - Login Sandbox Account - Tastytrade](https://developer.tastytrade.com/api-overview) - For a full list of future option products that we support, hit the List Future Option Products endpo...

19. [Orders¶](https://tastyworks-api.readthedocs.io/en/latest/orders.html)

20. [How Do I Set Up A Calendar Or Diagonal Spread Order - tastytrade](https://support.tastytrade.com/support/s/solutions/articles/43000532578) - Since a calendar or diagonal spans different expirations, you'll need to build the trade manually wh...

