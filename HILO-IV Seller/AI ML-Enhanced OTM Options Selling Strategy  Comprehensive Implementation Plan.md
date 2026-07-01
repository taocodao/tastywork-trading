# AI/ML-Enhanced OTM Options Selling Strategy: Comprehensive Implementation Plan

***

## Executive Summary

This document presents a full implementation blueprint for an automated, AI/ML-enhanced options premium-selling system. The strategy identifies stocks near historical highs or lows, confirms overbought/oversold conditions using technical oscillators, scans for OTM options with elevated implied volatility (IV rank ≥ 80%), sells those options short to collect premium, places a GTC stop-loss at 10% of max loss, and — if triggered — rolls to a further OTM strike and repeats. The plan is structured for handoff to a developer using Google Antigravity or any agentic coding environment.

**Strategy Nickname:** *HILO-IV Seller* (Historical High/Low + IV-Rank Options Seller)

***

## Section 1: Strategy Foundations & Academic Context

### 1.1 The 52-Week Anchoring Effect

Academic research establishes that traders systematically use the 52-week high or low as a psychological anchor when evaluating news and fair value. When stock prices approach a 52-week high, investors anchor to that reference point and under-react — delaying momentum-confirming trades and briefly creating a mispricing window. The "52-week high effect" was formally documented by George & Hwang (2004) and extended to industry-level strategies; stocks near their 52-week highs have been shown to produce positive subsequent excess returns vs. stocks far from their highs.[^1][^2]

For options sellers, this anchoring creates opportunity from both sides:
- **Near 52-week high + overbought indicators** → sell OTM call (premium seller bets price won't break significantly higher)
- **Near 52-week low + oversold indicators** → sell OTM put (premium seller bets price won't break significantly lower)

A backtested credit-spread study on 52-week high/low events found that MMM's price varied only -2% to +2% four days after hitting a new 52-week high in 58.11% of cases, and LVS continued lower only 36.71% of the time in the 25 days following a new 52-week low — supporting the thesis that these extremes represent bounded-movement environments favorable to OTM option sellers.[^3]

### 1.2 IV Rank as a Premium-Selling Trigger

Implied volatility rank (IVR) compares current IV to the 52-week range: `IVR = (Current IV − 52w Low IV) / (52w High IV − 52w Low IV) × 100`. An IVR above 50 signals that options are relatively expensive; above 80 signals extreme richness. Research confirms a strong mean-reversion tendency: when IV rank is high, future IV decreases in nearly all time periods tested — validating premium-selling when IVR ≥ 80%.[^4][^5][^6][^7]

Tastylive research on options selling recommends selling premium when IVR > 50 and IV Percentile > 75%. When IVR exceeds 80%, the risk/reward skews strongly toward sellers because options are priced well above their statistical fair value and the market has over-estimated future volatility.[^8][^5][^9][^4]

### 1.3 Overbought/Oversold Confirmation

RSI (Relative Strength Index) above 70 is the standard overbought signal; below 30 is oversold. For more extreme confirmation, 80/20 thresholds reduce false signals in trending markets. CCI (Commodity Channel Index) above +100 or below −100 similarly flags extremes. A 2024 SSRN paper specifically developed an ML-optimized options selling strategy combining technical indicators (including oscillators), options Greeks, and a machine learning model; the ML-enhanced strangle strategy outperformed the vanilla baseline in both Sharpe ratio and monthly returns.[^10][^11][^12][^13][^14]

Overbought/oversold signals are most reliable when combined with the broader context:
- RSI > 70–80 near 52-week high → confirms overextension, sell OTM call
- RSI < 30–20 near 52-week low → confirms oversold washout, sell OTM put
- Divergence between price action and RSI is an additional confirmation layer[^15][^16]

### 1.4 Rolling and Stop-Loss Mechanics

When a short OTM option is threatened, the standard response is "rolling" — closing the current position and opening a new one further OTM and/or further in time. Rolling down (on calls) or rolling up (on puts) increases distance from the current price, collecting additional credit to offset partial losses. A 10% max-loss GTC stop ensures bounded risk per trade cycle; upon trigger, the system re-evaluates market conditions and re-enters at a further OTM strike rather than accepting assignment.[^17][^18][^19][^20][^21]

The GTC (Good Til Canceled) order type is placed immediately at trade entry, with a buy-to-close trigger at `entry_premium × (1 + stop_loss_pct)`, i.e., if the option was sold for $1.00, the GTC stop fires at $1.10 (10% above premium collected).[^18]

***

## Section 2: System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    HILO-IV SELLER SYSTEM                        │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │  Screener    │───▶│  Signal      │───▶│  Options Chain   │   │
│  │  Module      │    │  Engine      │    │  Scanner         │   │
│  │(52w H/L scan)│    │(RSI/CCI/EMA) │    │(IV Rank, Greeks) │   │
│  └──────────────┘    └──────────────┘    └──────────────────┘   │
│         │                  │                      │              │
│         ▼                  ▼                      ▼              │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │               ML SIGNAL CLASSIFIER                      │    │
│  │      (RandomForest / XGBoost feature scoring)           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                             │                                    │
│                             ▼                                    │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │  Order       │◀───│  Risk Engine │◀───│  Position        │   │
│  │  Manager     │    │  (Stop Loss) │    │  Monitor         │   │
│  │  (Alpaca API)│    │  (GTC, Roll) │    │  (WebSocket)     │   │
│  └──────────────┘    └──────────────┘    └──────────────────┘   │
│         │                                       │                │
│         ▼                                       ▼                │
│  ┌──────────────┐                      ┌──────────────────┐     │
│  │  SQLite DB   │                      │  Alert System    │     │
│  │  Trade Log   │                      │  (Telegram/       │     │
│  │              │                      │   Discord)       │     │
│  └──────────────┘                      └──────────────────┘     │
│                                                                  │
│         APScheduler (Market Hours Cron Jobs)                    │
│         Next.js API Route (Optional Frontend Dashboard)         │
└─────────────────────────────────────────────────────────────────┘
```

### Module Breakdown

| Module | Responsibility | Libraries |
|--------|----------------|-----------|
| `screener.py` | Scan universe for stocks near 52w H/L | `yfinance`, `pandas`, `yfscreen` |
| `signal_engine.py` | Compute RSI, CCI, EMA, MACD; generate directional signal | `pandas_ta`, `numpy` |
| `options_scanner.py` | Fetch option chains, compute IV rank, filter by Greeks | `yfinance`, `mibian`, `py_vollib` |
| `ml_model.py` | Score setups using ML classifier; gate on confidence threshold | `scikit-learn`, `xgboost`, `joblib` |
| `risk_engine.py` | Calculate stop price, manage rolling logic, position sizing | `pandas`, `scipy` |
| `order_manager.py` | Submit/cancel/replace orders, manage GTC stops | `alpaca-py` |
| `position_monitor.py` | Monitor open positions, detect stop triggers | `alpaca-py` WebSocket |
| `trade_logger.py` | Log all signals, orders, fills, P&L to SQLite | `sqlite3` |
| `alert_system.py` | Send Telegram/Discord notifications | `python-telegram-bot`, `discord.py` |
| `scheduler.py` | Orchestrate all jobs during market hours | `APScheduler` |
| `config/` | Per-ticker YAML configs (EMA periods, thresholds) | `PyYAML` |
| `api/` | Next.js API endpoints (optional dashboard integration) | `Next.js`, REST |

***

## Section 3: Detailed Module Specifications

### 3.1 Screener Module (`screener.py`)

**Purpose:** Daily pre-market scan to identify candidate stocks near 52-week high or low.

**Logic:**
1. Load universe from `config/universe.yaml` (e.g., S&P 500 constituents or custom watchlist)
2. Fetch daily OHLCV for each ticker using `yfinance` (1-year history)[^22][^23]
3. Compute `52w_high = max(close[-252:])` and `52w_low = min(close[-252:])`
4. Apply proximity thresholds (configurable per ticker or global):
   - Near High: `current_price >= 0.95 × 52w_high` (within 5%)
   - Near Low: `current_price <= 1.05 × 52w_low` (within 5%)
5. Tag each qualifying stock with `position_bias = "SELL_CALL"` (near high) or `"SELL_PUT"` (near low)
6. Output filtered DataFrame to `signals/screener_output.csv`

**YAML Config Example (`config/universe.yaml`):**
```yaml
universe:
  - ticker: AAPL
    near_high_pct: 0.05
    near_low_pct: 0.05
    ema_short: 20
    ema_long: 50
  - ticker: TSLA
    near_high_pct: 0.08
    near_low_pct: 0.08
    ema_short: 10
    ema_long: 30
global_defaults:
  near_high_pct: 0.05
  near_low_pct: 0.05
  min_volume: 500000
  min_market_cap: 1_000_000_000
```

**Code Skeleton:**
```python
import yfinance as yf
import pandas as pd
import yaml

def load_config(path="config/universe.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)

def screen_universe(config: dict) -> pd.DataFrame:
    results = []
    for item in config["universe"]:
        ticker = item["ticker"]
        cfg = {**config["global_defaults"], **item}
        data = yf.download(ticker, period="1y", progress=False)
        if data.empty:
            continue
        current = data["Close"].iloc[-1]
        high_52w = data["High"].max()
        low_52w = data["Low"].min()
        near_high = current >= (1 - cfg["near_high_pct"]) * high_52w
        near_low = current <= (1 + cfg["near_low_pct"]) * low_52w
        if near_high or near_low:
            results.append({
                "ticker": ticker,
                "current_price": current,
                "52w_high": high_52w,
                "52w_low": low_52w,
                "near_high": near_high,
                "near_low": near_low,
                "bias": "SELL_CALL" if near_high else "SELL_PUT"
            })
    return pd.DataFrame(results)
```

***

### 3.2 Signal Engine (`signal_engine.py`)

**Purpose:** Compute technical indicators and generate a directional signal with confirmation score.

**Indicators:**
- RSI (14): overbought > 70, oversold < 30[^24][^10]
- CCI (20): overbought > +100, oversold < −100
- EMA crossover (short/long per config): trend alignment
- MACD histogram: momentum confirmation
- Stochastic %K/%D: secondary overbought/oversold (>80 / <20)[^14]

**Signal Logic:**

| Bias | RSI | CCI | EMA | Stoch | Signal Strength |
|------|-----|-----|-----|-------|-----------------|
| SELL_CALL | >70 | >100 | Price < Short EMA | >80 | STRONG |
| SELL_CALL | >65 | >80 | Neutral | >70 | MODERATE |
| SELL_PUT | <30 | <-100 | Price > Short EMA | <20 | STRONG |
| SELL_PUT | <35 | <-80 | Neutral | <30 | MODERATE |

**Code Skeleton:**
```python
import pandas_ta as ta
import pandas as pd

def compute_signals(df: pd.DataFrame, cfg: dict) -> dict:
    df = df.copy()
    df.ta.rsi(length=14, append=True)
    df.ta.cci(length=20, append=True)
    df.ta.ema(length=cfg.get("ema_short", 20), append=True)
    df.ta.ema(length=cfg.get("ema_long", 50), append=True)
    df.ta.macd(append=True)
    df.ta.stoch(append=True)

    last = df.iloc[-1]
    signals = {
        "rsi": last.get(f"RSI_14"),
        "cci": last.get("CCI_20_0.015"),
        "stoch_k": last.get("STOCHk_14_3_3"),
        "ema_short": last.get(f"EMA_{cfg.get('ema_short', 20)}"),
        "ema_long": last.get(f"EMA_{cfg.get('ema_long', 50)}"),
        "macd_hist": last.get("MACDh_12_26_9"),
    }
    return signals

def evaluate_signal(signals: dict, bias: str) -> str:
    rsi, cci, stoch_k = signals["rsi"], signals["cci"], signals["stoch_k"]
    if bias == "SELL_CALL":
        if rsi > 70 and cci > 100 and stoch_k > 80:
            return "STRONG_SELL_CALL"
        elif rsi > 65 and cci > 80:
            return "MODERATE_SELL_CALL"
    elif bias == "SELL_PUT":
        if rsi < 30 and cci < -100 and stoch_k < 20:
            return "STRONG_SELL_PUT"
        elif rsi < 35 and cci < -80:
            return "MODERATE_SELL_PUT"
    return "NO_SIGNAL"
```

***

### 3.3 Options Chain Scanner (`options_scanner.py`)

**Purpose:** For each signaled stock, fetch the option chain, calculate IV rank, identify the target OTM option to sell.

**Selection Criteria:**
- **Expiration:** 21–45 days to expiration (DTE) — the sweet spot for theta decay[^25]
- **IV Rank:** ≥ 80% (confirms premium is rich)[^5][^9][^4]
- **Delta:** −0.15 to −0.30 for calls (SELL_CALL); +0.15 to +0.30 for puts (SELL_PUT) — OTM but not too far[^26][^25]
- **Bid > $0.20:** Ensures sufficient premium to justify trade costs
- **Open Interest ≥ 100:** Liquidity filter
- **Bid/Ask Spread ≤ 10% of Midpoint:** Execution quality filter

**IV Rank Calculation:**

```
IVR = (Current_IV - Min_IV_52w) / (Max_IV_52w - Min_IV_52w) × 100
```

IV history must be computed from historical option chain data or sourced from a data provider (ORATS, Market Chameleon, Polygon.io, or Alpaca Options Historical Data API).[^6][^27]

**Code Skeleton:**
```python
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def get_iv_rank(ticker: str, current_iv: float) -> float:
    """Approximate IV rank from 1-year historical IV via HV proxy."""
    hist = yf.download(ticker, period="1y", progress=False)
    returns = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
    rolling_hv = returns.rolling(30).std() * np.sqrt(252) * 100
    iv_min = rolling_hv.min()
    iv_max = rolling_hv.max()
    return (current_iv - iv_min) / (iv_max - iv_min) * 100

def scan_options_chain(ticker: str, bias: str, iv_rank_threshold: float = 80.0) -> pd.DataFrame:
    tk = yf.Ticker(ticker)
    expirations = tk.options
    target_date_min = datetime.today() + timedelta(days=21)
    target_date_max = datetime.today() + timedelta(days=45)

    candidates = []
    for exp in expirations:
        exp_dt = datetime.strptime(exp, "%Y-%m-%d")
        if not (target_date_min <= exp_dt <= target_date_max):
            continue
        chain = tk.option_chain(exp)
        options = chain.calls if bias == "SELL_CALL" else chain.puts

        for _, row in options.iterrows():
            iv = row["impliedVolatility"] * 100
            iv_rank = get_iv_rank(ticker, iv)
            delta = row.get("delta", None)
            bid = row["bid"]
            ask = row["ask"]
            spread_pct = (ask - bid) / ((ask + bid) / 2) if (ask + bid) > 0 else 999
            oi = row["openInterest"]

            if (
                iv_rank >= iv_rank_threshold
                and bid >= 0.20
                and oi >= 100
                and spread_pct <= 0.10
            ):
                candidates.append({
                    "ticker": ticker,
                    "bias": bias,
                    "expiration": exp,
                    "strike": row["strike"],
                    "iv": iv,
                    "iv_rank": iv_rank,
                    "delta": delta,
                    "bid": bid,
                    "ask": ask,
                    "mid": (bid + ask) / 2,
                    "open_interest": oi,
                    "dte": (exp_dt - datetime.today()).days
                })

    df = pd.DataFrame(candidates)
    if df.empty:
        return df
    # Prefer: closest to 0.20 delta, highest IV rank, 30-45 DTE
    df["score"] = df["iv_rank"] * 0.5 + df["dte"] * 0.3 + df["mid"] * 0.2
    return df.sort_values("score", ascending=False)
```

***

### 3.4 ML Signal Classifier (`ml_model.py`)

**Purpose:** Gate trade entries using a trained ML model that scores the probability of a favorable outcome (option expires OTM). This adds a probabilistic filter on top of the rules-based signal, consistent with the SSRN paper's approach of using ML to optimize vanilla options selling.[^12]

**Feature Engineering:**

| Feature | Description |
|---------|-------------|
| `rsi_14` | RSI reading at signal time |
| `cci_20` | CCI reading at signal time |
| `iv_rank` | IV rank of the selected option |
| `dte` | Days to expiration |
| `delta_abs` | Absolute delta of the option |
| `pct_from_52w_extreme` | % from 52w high or low |
| `stoch_k` | Stochastic %K value |
| `ema_spread_pct` | (EMA_short − EMA_long) / EMA_long |
| `macd_hist_norm` | MACD histogram normalized by ATR |
| `vol_ratio` | Current volume / 20-day avg volume |
| `hv_iv_ratio` | Historical volatility / Implied volatility (IV overpricing) |
| `vix_level` | Current VIX (macro fear gauge) |
| `days_since_earnings` | Recency of last earnings (avoid IV crush risk) |

**Target Variable:** Binary — `1` if the option expired OTM (profitable), `0` if it moved ITM (loss).

**Model:** `XGBoostClassifier` or `RandomForestClassifier`. Train on 2–4 years of historical options data with the features above. Use walk-forward cross-validation to prevent data leakage.[^28][^29]

**Code Skeleton:**
```python
import joblib
import pandas as pd
from xgboost import XGBClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score

FEATURES = [
    "rsi_14", "cci_20", "iv_rank", "dte", "delta_abs",
    "pct_from_52w_extreme", "stoch_k", "ema_spread_pct",
    "macd_hist_norm", "vol_ratio", "hv_iv_ratio", "vix_level"
]

def train_model(df: pd.DataFrame, model_path: str = "models/ml_classifier.pkl"):
    X = df[FEATURES]
    y = df["target"]
    tscv = TimeSeriesSplit(n_splits=5)
    model = XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.05,
                          use_label_encoder=False, eval_metric="logloss")
    scores = []
    for train_idx, val_idx in tscv.split(X):
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        prob = model.predict_proba(X.iloc[val_idx])[:, 1]
        scores.append(roc_auc_score(y.iloc[val_idx], prob))
    print(f"Mean AUC: {sum(scores)/len(scores):.4f}")
    model.fit(X, y)  # Final fit on full data
    joblib.dump(model, model_path)
    return model

def score_trade(features: dict, model_path: str = "models/ml_classifier.pkl",
                min_confidence: float = 0.60) -> tuple[bool, float]:
    model = joblib.load(model_path)
    df = pd.DataFrame([features])[FEATURES]
    prob = model.predict_proba(df)[^1]
    return prob >= min_confidence, prob
```

***

### 3.5 Risk Engine (`risk_engine.py`)

**Purpose:** Calculate position size, stop price, monitor P&L, and execute rolling logic.

**Position Sizing:**
- Max risk per trade: configurable (e.g., 2% of portfolio)
- Max contracts: `floor(max_risk_dollars / (premium_per_contract × 100))`
- High-IV names use half the standard position size[^30]

**Stop-Loss Calculation:**
```
stop_price = premium_collected × (1 + stop_loss_pct)
# Default stop_loss_pct = 0.10 (10% above premium)
# GTC BTC order placed immediately at fill
```

**Rolling Logic — Triggered when GTC stop is filled:**
1. Confirm current signal still valid (re-run screener + signal engine)
2. If signal valid: roll to next OTM strike (further from money by 1–2 strikes)
3. If signal flipped or no signal: do NOT re-enter, log exit
4. Max roll attempts: configurable (default = 2 before closing position)
5. Credit check: new option must collect credit ≥ 50% of new stop risk

**Code Skeleton:**
```python
def calculate_stop_price(premium: float, stop_pct: float = 0.10) -> float:
    return round(premium * (1 + stop_pct), 2)

def calculate_position_size(portfolio_value: float, max_risk_pct: float,
                             premium: float) -> int:
    max_risk = portfolio_value * max_risk_pct
    risk_per_contract = premium * 100
    return max(1, int(max_risk // risk_per_contract))

def should_roll(signal: str, roll_count: int, max_rolls: int,
                new_credit: float, stop_risk: float) -> bool:
    if roll_count >= max_rolls:
        return False
    if signal == "NO_SIGNAL":
        return False
    return new_credit >= 0.5 * stop_risk

def find_roll_target(chain_df: pd.DataFrame, current_strike: float,
                     bias: str, strikes_out: int = 2) -> dict:
    """Roll further OTM by strikes_out from current."""
    if bias == "SELL_CALL":
        candidates = chain_df[chain_df["strike"] > current_strike].sort_values("strike")
    else:
        candidates = chain_df[chain_df["strike"] < current_strike].sort_values("strike", ascending=False)
    if len(candidates) <= strikes_out:
        return {}
    return candidates.iloc[strikes_out].to_dict()
```

***

### 3.6 Order Manager (`order_manager.py`)

**Purpose:** Interface with Alpaca Markets API to submit, modify, and cancel orders.[^31][^32][^33]

**Order Types Used:**
- `sell_to_open` (STO): Initial short option entry
- `buy_to_close` (BTC) GTC: Stop-loss order at `stop_price`
- `buy_to_close` (BTC) market: Roll out — close existing position
- `sell_to_open` (STO): Roll in — open new further OTM position

**Code Skeleton:**
```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    OptionLegRequest, MarketOrderRequest, LimitOrderRequest
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType

class OrderManager:
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.client = TradingClient(api_key, secret_key, paper=paper)

    def sell_option(self, symbol: str, qty: int, limit_price: float):
        order = LimitOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.SELL,
            type=OrderType.LIMIT, time_in_force=TimeInForce.DAY,
            limit_price=limit_price
        )
        return self.client.submit_order(order)

    def place_gtc_stop(self, symbol: str, qty: int, stop_price: float):
        """BTC GTC stop to close short position if premium spikes."""
        order = LimitOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.BUY,
            type=OrderType.LIMIT, time_in_force=TimeInForce.GTC,
            limit_price=stop_price
        )
        return self.client.submit_order(order)

    def roll_position(self, close_symbol: str, open_symbol: str,
                      qty: int, new_limit: float):
        btc = self.close_position(close_symbol, qty)
        sto = self.sell_option(open_symbol, qty, new_limit)
        return btc, sto

    def close_position(self, symbol: str, qty: int):
        order = MarketOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )
        return self.client.submit_order(order)
```

***

### 3.7 Trade Logger (`trade_logger.py`)

**Purpose:** Persist all signals, orders, fills, and P&L to SQLite for audit trail, ML retraining, and performance analysis.[^34][^35]

**Database Schema:**
```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    ticker TEXT NOT NULL,
    bias TEXT,
    rsi REAL,
    cci REAL,
    iv_rank REAL,
    ml_confidence REAL,
    signal_type TEXT
);

CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER REFERENCES signals(id),
    ticker TEXT NOT NULL,
    option_symbol TEXT NOT NULL,
    direction TEXT, -- SELL_CALL or SELL_PUT
    strike REAL,
    expiration TEXT,
    dte INTEGER,
    premium_collected REAL,
    qty INTEGER,
    entry_time TEXT,
    stop_price REAL,
    status TEXT, -- OPEN, STOPPED_OUT, ROLLED, EXPIRED_PROFIT, CLOSED
    exit_premium REAL,
    pnl REAL,
    roll_count INTEGER DEFAULT 0
);

CREATE TABLE rolls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_trade_id INTEGER REFERENCES trades(id),
    roll_number INTEGER,
    closed_strike REAL,
    new_strike REAL,
    new_expiration TEXT,
    credit_received REAL,
    timestamp TEXT
);
```

***

### 3.8 Alert System (`alert_system.py`)

**Purpose:** Send real-time trade alerts and status updates to Telegram or Discord.[^36][^37][^38]

**Alert Types:**
- 🎯 **New Signal Found:** Ticker, bias, RSI, IV rank, ML confidence
- ✅ **Order Filled:** Option symbol, strike, premium, stop price
- 🛑 **Stop Triggered:** Ticker, loss amount, roll status
- 🔄 **Position Rolled:** Old strike → New strike, net credit
- 💰 **Trade Closed:** Final P&L, win/loss, option expired worthless
- 📊 **Daily Summary:** Total open positions, P&L, IV environment

**Code Skeleton:**
```python
import asyncio
from telegram import Bot

class AlertSystem:
    def __init__(self, telegram_token: str, chat_id: str):
        self.bot = Bot(token=telegram_token)
        self.chat_id = chat_id

    async def send(self, message: str):
        await self.bot.send_message(chat_id=self.chat_id, text=message,
                                    parse_mode="Markdown")

    def new_signal(self, ticker, bias, rsi, iv_rank, confidence):
        msg = (f"🎯 *New Signal: {ticker}*\n"
               f"Bias: {bias}\n"
               f"RSI: {rsi:.1f} | IV Rank: {iv_rank:.0f}%\n"
               f"ML Confidence: {confidence:.1%}")
        asyncio.run(self.send(msg))

    def stop_triggered(self, ticker, loss, roll_count, action):
        msg = (f"🛑 *Stop Triggered: {ticker}*\n"
               f"Loss: ${loss:.2f}\n"
               f"Action: {action} | Roll #{roll_count}")
        asyncio.run(self.send(msg))
```

***

### 3.9 Scheduler (`scheduler.py`)

**Purpose:** Orchestrate all jobs during NYSE market hours using APScheduler.[^39][^40]

**Job Schedule (NYSE Hours: 9:30 AM – 4:00 PM ET):**

| Time (ET) | Job | Description |
|-----------|-----|-------------|
| 8:30 AM | `pre_market_scan` | Run screener on all universe tickers |
| 9:35 AM | `signal_evaluation` | Compute indicators + ML scores for screener output |
| 9:45 AM | `options_scan` | Scan option chains for IV rank + candidates |
| 9:50 AM | `execute_signals` | Submit STO orders + place GTC stops |
| Every 30 min | `position_monitor` | Check fills, monitor stop triggers, manage rolls |
| 3:30 PM | `daily_summary` | Log P&L, send daily summary alert |
| 4:30 PM | `ml_retrain_check` | Check if new training data meets threshold; retrain if so |

**Code Skeleton:**
```python
from apscheduler.schedulers.blocking import BlockingScheduler
import pytz

scheduler = BlockingScheduler(timezone=pytz.timezone("America/New_York"))

scheduler.add_job(pre_market_scan, "cron", day_of_week="mon-fri", hour=8, minute=30)
scheduler.add_job(signal_evaluation, "cron", day_of_week="mon-fri", hour=9, minute=35)
scheduler.add_job(options_scan, "cron", day_of_week="mon-fri", hour=9, minute=45)
scheduler.add_job(execute_signals, "cron", day_of_week="mon-fri", hour=9, minute=50)
scheduler.add_job(position_monitor, "interval", minutes=30,
                  start_date="2026-01-01 09:30:00", end_date="2026-12-31 16:00:00")
scheduler.add_job(daily_summary, "cron", day_of_week="mon-fri", hour=15, minute=30)
scheduler.add_job(ml_retrain_check, "cron", day_of_week="mon-fri", hour=16, minute=30)

scheduler.start()
```

***

## Section 4: ML Model Training Pipeline

### 4.1 Data Collection for Training

Historical training data requires:
1. **Option price histories:** Polygon.io Historical Options API, ORATS, or OptionsDX (paid) for accurate IV history
2. **Stock price history:** `yfinance` for OHLCV going back 4+ years
3. **VIX data:** `yfinance` ticker `^VIX`
4. **Earnings dates:** Yahoo Finance earnings calendar or Alpaca corporate actions

**Training Dataset Construction:**
- For each historical signal (stock near 52w H/L, RSI extreme, IV rank > 80%), record entry features
- Label = 1 if option expired OTM or was closed at ≥ 50% profit; label = 0 if stopped out
- Minimum 2,000 labeled examples recommended before first deployment
- Retrain monthly as new trades are logged[^12][^28]

### 4.2 Feature Importance (Expected)

Based on the SSRN ML options selling paper and community research, the most predictive features are expected to be:[^41][^12]

1. `iv_rank` — High IVR strongly predicts mean reversion (premium collapses)[^7]
2. `hv_iv_ratio` — When IV >> HV, options are systematically overpriced[^41]
3. `rsi_14` — Extreme readings confirm momentum exhaustion[^10]
4. `pct_from_52w_extreme` — Proximity to anchor level[^1]
5. `dte` — Controls theta decay rate
6. `vix_level` — Macro fear environment affects IV persistence

### 4.3 Model Validation

Use walk-forward (time-series) cross-validation only — never k-fold with shuffling on financial data as it causes data leakage. Target metrics:[^29]
- AUC-ROC ≥ 0.62 (better than random)[^29]
- Profit Factor ≥ 1.5 (gross profit / gross loss)
- Max drawdown < 20%
- Sharpe ratio ≥ 1.0[^29]

***

## Section 5: Configuration & Environment

### 5.1 Project Structure
```
hilo_iv_seller/
├── config/
│   ├── universe.yaml          # Ticker list + per-ticker params
│   ├── strategy.yaml          # Global strategy params
│   └── credentials.yaml       # API keys (gitignored)
├── modules/
│   ├── screener.py
│   ├── signal_engine.py
│   ├── options_scanner.py
│   ├── ml_model.py
│   ├── risk_engine.py
│   ├── order_manager.py
│   ├── position_monitor.py
│   ├── trade_logger.py
│   └── alert_system.py
├── models/
│   └── ml_classifier.pkl      # Trained model artifact
├── data/
│   ├── training_dataset.csv   # Historical labeled trades
│   └── screener_output.csv    # Daily screener results
├── db/
│   └── trades.db              # SQLite database
├── api/                       # Next.js API routes (optional)
│   └── routes/
│       └── signals.js
├── scheduler.py               # Main entry point
├── requirements.txt
└── README.md
```

### 5.2 Global Strategy Config (`config/strategy.yaml`)
```yaml
screening:
  near_high_pct: 0.05
  near_low_pct: 0.05

signals:
  rsi_overbought: 70
  rsi_oversold: 30
  cci_overbought: 100
  cci_oversold: -100
  stoch_overbought: 80
  stoch_oversold: 20
  min_signal_strength: MODERATE

options:
  min_dte: 21
  max_dte: 45
  iv_rank_min: 80
  min_bid: 0.20
  min_oi: 100
  max_spread_pct: 0.10
  target_delta_range: [0.15, 0.30]

risk:
  stop_loss_pct: 0.10
  max_risk_per_trade_pct: 0.02
  max_portfolio_concentration: 0.10
  max_roll_attempts: 2
  roll_min_credit_ratio: 0.50

ml:
  min_confidence: 0.60
  model_path: "models/ml_classifier.pkl"
  retrain_threshold_new_trades: 50

alerts:
  telegram_enabled: true
  discord_enabled: false
```

### 5.3 Requirements (`requirements.txt`)
```
yfinance>=0.2.40
pandas>=2.0.0
pandas-ta>=0.3.14b
numpy>=1.24.0
scikit-learn>=1.3.0
xgboost>=2.0.0
joblib>=1.3.0
alpaca-py>=0.13.0
python-telegram-bot>=21.0.0
APScheduler>=3.10.0
PyYAML>=6.0
scipy>=1.11.0
mibian>=0.1.3
py_vollib>=1.0.2
sqlite3  # built-in
pytz>=2024.1
requests>=2.31.0
```

***

## Section 6: Next.js API Integration (Optional Dashboard)

For teams wanting a web dashboard or integration with an existing Next.js frontend, expose the system's SQLite data via REST API routes.

**Endpoint Specifications:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/signals/active` | Current open signals and positions |
| GET | `/api/trades/history` | Full trade log with P&L |
| GET | `/api/performance/summary` | Win rate, P&L, Sharpe, drawdown |
| POST | `/api/signals/force-scan` | Manually trigger a scan cycle |
| GET | `/api/positions/{ticker}` | Detail view for a specific position |
| PUT | `/api/positions/{ticker}/roll` | Manually trigger a roll |
| GET | `/api/config` | Current strategy configuration |
| PUT | `/api/config` | Update strategy configuration |

**Example Next.js Route (`api/routes/signals.js`):**
```javascript
import sqlite3 from 'sqlite3';
import { open } from 'sqlite';

export default async function handler(req, res) {
  const db = await open({ filename: '../db/trades.db', driver: sqlite3.Database });
  if (req.method === 'GET') {
    const trades = await db.all(
      "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY entry_time DESC"
    );
    res.status(200).json({ trades });
  }
}
```

***

## Section 7: Phased Rollout Timeline

### Phase 1 — Foundation (Weeks 1–3)
- [ ] Set up project structure and `requirements.txt`
- [ ] Implement `screener.py` with YAML config loading and yfinance integration
- [ ] Implement `signal_engine.py` with pandas_ta indicators
- [ ] Unit tests for screener and signal modules
- [ ] Implement `trade_logger.py` and initialize SQLite schema
- [ ] Paper trading account setup on Alpaca

### Phase 2 — Options Layer (Weeks 4–6)
- [ ] Implement `options_scanner.py` with IV rank computation
- [ ] Implement `order_manager.py` with Alpaca paper trading
- [ ] Implement `risk_engine.py` with position sizing and stop-loss logic
- [ ] End-to-end test: screener → signal → options scan → paper order
- [ ] Implement `alert_system.py` with Telegram integration
- [ ] Full manual review of all paper trades for 2 weeks

### Phase 3 — ML Integration (Weeks 7–10)
- [ ] Collect historical training data (option prices + feature engineering)
- [ ] Label historical trades (profitable OTM expiry = 1, stopped out = 0)
- [ ] Train initial XGBoost classifier with walk-forward validation
- [ ] Integrate `ml_model.py` as a gate in the signal pipeline
- [ ] Benchmark: ML-gated vs. rules-only on paper trades
- [ ] Implement model retraining scheduler job

### Phase 4 — Scheduling & Automation (Weeks 11–12)
- [ ] Implement `scheduler.py` with all APScheduler cron jobs
- [ ] Implement `position_monitor.py` with WebSocket listener
- [ ] Full integration test: market-hours automated cycle
- [ ] 2-week paper trading period with full automation

### Phase 5 — Go-Live & Dashboard (Weeks 13–16)
- [ ] Live trading with minimal position sizes (1–2 contracts max)
- [ ] Next.js API routes for dashboard (if applicable)
- [ ] Monitoring, alerting, daily P&L review
- [ ] Performance review at 30 days; adjust ML confidence threshold and strategy params
- [ ] Full-size deployment after 60 days of live profitability

***

## Section 8: Risk Management Framework

### 8.1 Position-Level Controls
- **Max loss per trade:** 10% above premium collected (GTC stop)[^17][^18]
- **Max rolls:** 2 per original trade before accepting loss
- **No-roll conditions:** Signal flipped, ML confidence < threshold, earnings within 5 days

### 8.2 Portfolio-Level Controls
- **Max single-ticker concentration:** 10% of portfolio value
- **Max total short options notional:** 30% of portfolio
- **VIX spike protocol:** If VIX > 35, pause new entries; only manage existing positions
- **Earnings blackout:** Do not open new positions within 5 days of earnings

### 8.3 Known Strategy Risks

| Risk | Description | Mitigation |
|------|-------------|------------|
| Black Swan / Gap | Stock gaps through OTM strike overnight | Defined risk via credit spreads (add long leg 2–3 strikes further OTM) |
| IV Expansion on Entry | IV keeps rising after selling | Max 10% stop ensures bounded loss; roll to capture additional premium |
| Assignment Risk | American-style options can be assigned early | Use ETF options (SPY, QQQ) which have lower assignment risk; monitor for ITM situations |
| Anchoring Failure | 52w H/L broken significantly | ML model trained to recognize breakout vs. reversal patterns |
| Liquidity Gap | Wide bid-ask spreads increase slippage | Bid/ask spread ≤ 10% filter and OI ≥ 100 enforced[^42] |
| Overfitting ML | Model trained on limited data | Walk-forward validation; retrain monthly with new live data[^12][^28] |

***

## Section 9: Antigravity Agent Handoff Prompt

The following is the complete prompt to paste directly into Google Antigravity (or any agentic coder) to build this system:

***

### 🤖 ANTIGRAVITY / AGENTIC CODER PROMPT

```
You are building a complete Python-based automated options trading signal system 
called "HILO-IV Seller". This system identifies stocks near 52-week highs or lows, 
confirms overbought/oversold conditions using technical indicators, scans for 
out-of-the-money (OTM) options with IV Rank ≥ 80%, sells those options short, 
places a GTC stop-loss at 10% above the premium collected, and rolls to a further 
OTM strike if triggered. An ML classifier gates entries.

════════════════════════════════════════════
SYSTEM OVERVIEW
════════════════════════════════════════════

Build all of the following modules as individual Python files in a project called 
`hilo_iv_seller/`. Each module must be fully implemented (not stubbed), documented 
with docstrings, and include error handling.

════════════════════════════════════════════
PROJECT STRUCTURE
════════════════════════════════════════════

hilo_iv_seller/
├── config/
│   ├── universe.yaml     (ticker list + per-ticker params)
│   ├── strategy.yaml     (global strategy params)
│   └── credentials.yaml  (API keys - template only, gitignored)
├── modules/
│   ├── screener.py
│   ├── signal_engine.py
│   ├── options_scanner.py
│   ├── ml_model.py
│   ├── risk_engine.py
│   ├── order_manager.py
│   ├── position_monitor.py
│   ├── trade_logger.py
│   └── alert_system.py
├── models/               (directory for saved ML model)
├── data/                 (directory for CSVs)
├── db/                   (SQLite database directory)
├── api/
│   └── routes/           (Next.js API route templates)
├── tests/
│   └── test_*.py         (unit tests for each module)
├── scheduler.py          (main entry point)
├── requirements.txt
└── README.md

════════════════════════════════════════════
MODULE 1: screener.py
════════════════════════════════════════════

DEPENDENCIES: yfinance, pandas, PyYAML

FUNCTION: screen_universe(config_path="config/universe.yaml") -> pd.DataFrame

LOGIC:
- Load tickers from config YAML
- Use yfinance to download 1 year of daily OHLCV data for each ticker
- For each ticker, compute 52-week high = max(Close[-252:]) and 
  52-week low = min(Close[-252:])
- Tag as "near high" if current_price >= (1 - near_high_pct) * 52w_high
- Tag as "near low" if current_price <= (1 + near_low_pct) * 52w_low
- Also compute: volume vs 20-day avg, distance from 52w extreme as percentage
- Return DataFrame with columns: [ticker, current_price, 52w_high, 52w_low, 
  pct_from_high, pct_from_low, near_high, near_low, bias, avg_volume, current_volume]
- Write output to data/screener_output.csv

════════════════════════════════════════════
MODULE 2: signal_engine.py
════════════════════════════════════════════

DEPENDENCIES: pandas_ta, yfinance, pandas, PyYAML

FUNCTION: compute_signals(ticker, config) -> dict
FUNCTION: evaluate_signal(signals, bias) -> str (STRONG_SELL_CALL | MODERATE_SELL_CALL | 
                                                  STRONG_SELL_PUT | MODERATE_SELL_PUT | NO_SIGNAL)

INDICATORS TO COMPUTE (all via pandas_ta):
- RSI(14): overbought > 70 for SELL_CALL, oversold < 30 for SELL_PUT
- CCI(20): overbought > +100, oversold < -100
- EMA(short_period) and EMA(long_period): from per-ticker config YAML
- MACD(12,26,9): histogram direction as momentum confirm
- Stochastic(14,3,3): %K overbought > 80, oversold < 20
- ATR(14): for position sizing context

SIGNAL STRENGTH RULES:
- STRONG: RSI extreme + CCI extreme + Stoch extreme (all 3 aligned)
- MODERATE: Any 2 of the 3 indicators aligned
- NO_SIGNAL: Fewer than 2 indicators aligned

════════════════════════════════════════════
MODULE 3: options_scanner.py
════════════════════════════════════════════

DEPENDENCIES: yfinance, pandas, numpy

FUNCTION: get_iv_rank(ticker, current_iv) -> float
FUNCTION: scan_options_chain(ticker, bias, iv_rank_threshold=80.0) -> pd.DataFrame

SELECTION FILTERS:
- Expiration: 21–45 days to expiration (DTE)
- IV Rank: >= iv_rank_threshold (compute from 1yr historical HV proxy if live IV unavailable)
- Delta: absolute value between 0.15 and 0.30 (if available from chain data)
- Bid >= $0.20 (minimum premium filter)
- Open Interest >= 100 (liquidity)
- Bid/ask spread <= 10% of midpoint

SCORING: rank candidates by composite score = 
  (0.5 * iv_rank) + (0.3 * dte_score) + (0.2 * premium_score)
  where dte_score = 1 - abs(dte - 35)/35 (prefer ~35 DTE)

OUTPUT COLUMNS: [ticker, bias, expiration, strike, iv, iv_rank, delta, 
                 bid, ask, mid, open_interest, dte, score, contract_symbol]

════════════════════════════════════════════
MODULE 4: ml_model.py
════════════════════════════════════════════

DEPENDENCIES: scikit-learn, xgboost, pandas, joblib, numpy

FUNCTIONS:
- build_feature_vector(ticker, signals, option_row, vix_level) -> dict
- train_model(training_csv_path, model_output_path) -> XGBClassifier
- score_trade(features_dict, model_path, min_confidence=0.60) -> (bool, float)
- check_retrain(db_path, threshold=50) -> bool

FEATURE VECTOR (13 features):
  rsi_14, cci_20, iv_rank, dte, delta_abs, pct_from_52w_extreme,
  stoch_k, ema_spread_pct, macd_hist_norm, vol_ratio, hv_iv_ratio,
  vix_level, days_since_earnings

TARGET: binary 1=profitable (expired OTM or 50%+ profit), 0=loss (stopped out)

MODEL: XGBoostClassifier with:
  - n_estimators=200, max_depth=4, learning_rate=0.05
  - TimeSeriesSplit(n_splits=5) cross-validation (NO shuffle - financial time series)
  - Save model to models/ml_classifier.pkl via joblib

ON FIRST RUN (no training data): bypass ML gate, log all trades for 
  future training; activate ML after 200+ labeled examples

════════════════════════════════════════════
MODULE 5: risk_engine.py
════════════════════════════════════════════

FUNCTIONS:
- calculate_stop_price(premium, stop_pct=0.10) -> float
  # stop triggers at premium * (1 + stop_pct) = 10% loss
- calculate_position_size(portfolio_value, max_risk_pct, premium) -> int
  # floor(portfolio_value * max_risk_pct / (premium * 100))
- should_roll(signal, roll_count, max_rolls, new_credit, stop_risk) -> bool
- find_roll_target(chain_df, current_strike, bias, strikes_out=2) -> dict
- check_portfolio_limits(ticker, current_positions, portfolio_value, config) -> bool

ROLLING LOGIC:
- Roll only if: current signal is still valid (re-run signal evaluation), 
  roll count < max_rolls, new credit >= 50% of new stop risk
- Roll direction: further OTM (higher strike for calls, lower for puts)
- Maximum 2 rolls per original trade

════════════════════════════════════════════
MODULE 6: order_manager.py
════════════════════════════════════════════

DEPENDENCIES: alpaca-py

CLASS: OrderManager
- __init__(api_key, secret_key, paper=True)
- sell_option(symbol, qty, limit_price) -> Order  # STO limit order
- place_gtc_stop(symbol, qty, stop_price) -> Order  # BTC GTC limit order
- roll_position(close_symbol, open_symbol, qty, new_limit) -> tuple
- close_position(symbol, qty) -> Order  # BTC market order
- get_open_positions() -> list[Position]
- get_order_status(order_id) -> Order
- cancel_order(order_id) -> None

IMPORTANT:
- Always submit GTC stop immediately after STO fill confirmation
- Log all order submissions and fills to trade_logger
- Use paper=True for all testing; live=False environment variable guard

════════════════════════════════════════════
MODULE 7: position_monitor.py
════════════════════════════════════════════

FUNCTION: check_positions(order_manager, risk_engine, trade_logger, 
                           alert_system, config) -> None

LOGIC per open position:
1. Fetch current option market price via Alpaca Options API
2. Compare to stop_price stored in trades table
3. If current_price >= stop_price:
   a. Cancel existing GTC order
   b. Re-run screener + signal_engine for the ticker
   c. If roll conditions met: execute roll via order_manager
   d. If no roll: close and log as STOPPED_OUT
   e. Send alert via alert_system
4. Also check for positions approaching expiration (DTE <= 5):
   a. If profitable (current price <= 50% of entry premium): close for profit
   b. If at risk: evaluate roll or close

════════════════════════════════════════════
MODULE 8: trade_logger.py
════════════════════════════════════════════

DEPENDENCIES: sqlite3 (built-in)

DATABASE: db/trades.db

IMPLEMENT FULL SCHEMA:
- signals table: id, timestamp, ticker, bias, rsi, cci, iv_rank, ml_confidence, signal_type
- trades table: id, signal_id, ticker, option_symbol, direction, strike, expiration, dte, 
  premium_collected, qty, entry_time, stop_price, status, exit_premium, pnl, roll_count
- rolls table: id, original_trade_id, roll_number, closed_strike, new_strike, 
  new_expiration, credit_received, timestamp

FUNCTIONS:
- init_db(db_path="db/trades.db") -> None
- log_signal(signal_data) -> int (signal_id)
- log_trade_open(trade_data) -> int (trade_id)
- log_trade_close(trade_id, exit_data) -> None
- log_roll(roll_data) -> None
- get_open_trades() -> list[dict]
- get_performance_summary() -> dict
  # Returns: win_rate, total_pnl, avg_pnl, max_drawdown, sharpe_ratio, profit_factor

════════════════════════════════════════════
MODULE 9: alert_system.py
════════════════════════════════════════════

DEPENDENCIES: python-telegram-bot

CLASS: AlertSystem
- __init__(telegram_token, chat_id)
- send_message(text) -> None
- new_signal_alert(ticker, bias, rsi, iv_rank, confidence, option_info) -> None
- trade_opened_alert(trade_data) -> None
- stop_triggered_alert(ticker, loss, action) -> None
- roll_executed_alert(ticker, old_strike, new_strike, net_credit) -> None
- trade_closed_alert(ticker, pnl, reason) -> None
- daily_summary_alert(summary_stats) -> None

FORMAT: Use Telegram Markdown formatting.
ASYNC: Use asyncio.run() for all send_message calls.
FALLBACK: If Telegram fails, log to file alerts.log.

════════════════════════════════════════════
MODULE 10: scheduler.py (MAIN ENTRY POINT)
════════════════════════════════════════════

DEPENDENCIES: APScheduler, pytz

Use BlockingScheduler with timezone="America/New_York"

JOBS:
- pre_market_scan: cron, mon-fri, 8:30 AM → run screener
- signal_evaluation: cron, mon-fri, 9:35 AM → compute indicators for screener output
- options_scan: cron, mon-fri, 9:45 AM → scan option chains for qualifying candidates
- execute_signals: cron, mon-fri, 9:50 AM → ML gate → submit orders → place GTC stops
- position_monitor: interval, every 30 minutes (9:30 AM – 3:30 PM) → check positions
- daily_summary: cron, mon-fri, 3:30 PM → compute and send daily P&L summary
- ml_retrain_check: cron, mon-fri, 4:30 PM → check if retraining threshold met

All jobs: wrap in try/except, log errors to file, send alert if critical failure.

════════════════════════════════════════════
CONFIGURATION FILES
════════════════════════════════════════════

CREATE config/universe.yaml with example tickers:
  AAPL, MSFT, TSLA, NVDA, SPY, QQQ, AMZN, META, GOOGL, JPM
  with per-ticker ema_short and ema_long params

CREATE config/strategy.yaml with all params listed in the system 
  description (screening thresholds, signal thresholds, options filters,
  risk params, ML params, alert settings)

CREATE config/credentials.yaml.template (not actual keys):
  alpaca_api_key: "YOUR_KEY_HERE"
  alpaca_secret_key: "YOUR_SECRET_HERE"
  telegram_token: "YOUR_TOKEN_HERE"
  telegram_chat_id: "YOUR_CHAT_ID_HERE"

════════════════════════════════════════════
TESTS
════════════════════════════════════════════

Write pytest unit tests in tests/ for:
- test_screener.py: mock yfinance data, verify 52w H/L logic
- test_signal_engine.py: mock OHLCV data, verify indicator calculations
- test_risk_engine.py: verify stop price, position size, roll logic
- test_trade_logger.py: test all CRUD operations on in-memory SQLite

════════════════════════════════════════════
NEXT.JS API ROUTES (OPTIONAL)
════════════════════════════════════════════

Create api/routes/ with:
- signals.js: GET /api/signals/active → query SQLite for open trades
- trades.js: GET /api/trades/history → full trade history with P&L
- performance.js: GET /api/performance/summary → stats from trade_logger

Use 'sqlite' npm package to connect to the same trades.db file.

════════════════════════════════════════════
ADDITIONAL REQUIREMENTS
════════════════════════════════════════════

1. All API keys loaded from environment variables (python-dotenv), never hardcoded
2. All monetary values in USD; always use Decimal for financial calculations
3. Add a --paper flag to scheduler.py to switch between paper and live trading
4. Include a README.md with setup instructions, environment setup, and quick-start guide
5. Add logging to all modules using Python's logging module (output to logs/system.log)
6. Handle yfinance rate limiting with exponential backoff retry logic
7. For options data: if yfinance chain data is missing delta/IV, 
   compute IV using py_vollib Black-Scholes and delta from first-order approximation
8. Include a data/training_dataset_template.csv with the expected 
   feature column names and one example row

Build everything now. Start with the project structure, then implement 
each module in order. Confirm successful import of each module before 
proceeding to the next.
```

***

## Section 10: Performance Benchmarks & Realistic Expectations

Historical backtesting of similar strategies provides the following benchmarks:[^43][^25][^29]

| Metric | Benchmark (Similar Strategies) | Notes |
|--------|--------------------------------|-------|
| Win Rate (rules-only) | 70–80% | OTM options expire worthless majority of time |
| Win Rate (ML-enhanced) | 75–85% | Per SSRN ML strangle paper[^12] |
| Average Premium Collected | $0.50–$2.00 per contract | Depends on IV rank, DTE, delta |
| Average Loser | 2–4× average winner | Risk management critical |
| Max Drawdown Target | < 20% | Hard stop via GTC orders |
| Sharpe Ratio Target | ≥ 1.0 | Realistic for well-managed premium selling |
| Profit Factor Target | ≥ 1.5 | Gross profit / gross loss benchmark[^29] |

**Critical Note:** A strategy with 80% win rate but losers 4× the size of winners will underperform a strategy with 70% win rate and 2× losers. Focus on profit factor and Sharpe ratio over raw win rate.[^44][^29]

---

## References

1. [Trading Strategy: 52-Weeks High Effect in Stocks](https://blog.quantinsti.com/trading-strategy-52-weeks-high-effect-in-stocks/) - First, we set the backtest period, and the upper and lower thresholds values for determining whether...

2. [52-Week High Investing Strategy: A Powerful Momentum ...](https://www.linkedin.com/pulse/52-week-high-investing-strategy-powerful-momentum-approach-l4wwc) - Research shows stocks near their 52-week highs consistently outperform those trading far from their ...

3. [Backtest 52 Week Highs and Lows Option Strategy | Blog](https://optionsamurai.com/blog/backtest-52-week-highs-and-lows-option-strategy/) - Learn how to use a backtest on new stocks' 52-week highs and lows to trade options. Use our free bac...

4. [IV Rank vs. IV Percentile: Which is Best?](https://www.tradingblock.com/blog/iv-rank-vs-iv-percentile) - You use IV Percentile to judge whether options are historically cheap or expensive. A high percentil...

5. [Implied Volatility Explained: IV, HV, and IV Rank in Options ...](https://www.tastylive.com/news-insights/implied-volatility-explained-iv-hv-and-iv-rank-in-options-trading) - When IV is elevated, traders may sell premium, expecting option prices to contract as volatility coo...

6. [Implied Volatility: Formula, Options, Calculation and Python ...](https://www.quantinsti.com/articles/implied-volatility/) - We will create an implied volatility calculator using Python for easy calculation of implied volatil...

7. [Implied Volatility backtest - Predicting IV Change | Blog](https://optionsamurai.com/blog/implied-volatility-backtest-predicting-iv-change/) - If the IV rank is high, we can expect the IV to decrease, and if the IV is low, we can expect the IV...

8. [Selling Options Premium When the VIX is High vs LOW](https://optionsblackbelt.com/blog/selling-options-premium-when-the-vix-is-high-vs-low/) - Selling options premium is powerful in both low and high volatility markets. Just remember: higher p...

9. [How to Trade Options When IV Is in the 80th Percentile](https://groww.in/blog/how-to-trade-options-when-iv-is-in-the-80th-percentile) - If the IV is at the 80th percentile, it means that the current volatility is at the top 80% of the l...

10. [RSI Indicator: Buy and Sell Signals](https://www.investopedia.com/articles/active-trading/042114/overbought-or-oversold-use-relative-strength-index-find-out.asp) - An RSI reading below 30 indicates oversold conditions, while one above 70 indicates overbought condi...

11. [RSI Overbought and Oversold Condition](https://www.macroption.com/rsi-overbought-oversold/) - This page explains how to identify overbought and oversold conditions with RSI (Relative Strength In...

12. [Options Selling strategy using Machine Learning](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID4766370_code6587970.pdf?abstractid=4766370&mirid=1) - Abstract. The goal of this paper is to develop a dynamic standalone option selling strategy using te...

13. [i tested that "rsi oversold" strategy on 5000 trades. it failed ...](https://www.reddit.com/r/Daytrading/comments/1pdj9f1/i_tested_that_rsi_oversold_strategy_on_5000/) - Meaning, when it's overbought then don't buy or take a long position. When its oversold, don't sell ...

14. [How to Tell If a Market Is Overbought or Oversold](https://www.schwab.com/learn/story/how-to-tell-if-market-is-overbought-or-oversold) - RSI readings range from zero to 100, with 70 considered overbought and 30 considered oversold. Tradi...

15. [RSI Overbought Oversold Indicator for MT4 & MT5 - Best RSI ...](https://www.youtube.com/watch?v=XG28SvZ3a5A) - You'll learn how to interpret RSI signals and implement this information into your trading strategy....

16. [The Right Way to Use the RSI: Stop Misreading Overbought ...](https://www.youtube.com/watch?v=e80R9pxyScU) - Most traders use the RSI completely backwards, and it costs them money. In episode 156 of Let's Talk...

17. [Three Types of Options Exit Strategies](https://www.schwab.com/learn/story/three-types-options-exit-strategies) - Learn three different order types and how certain order types, like limit orders and stop orders, ca...

18. [5 Steps to BETTER Options Trading (Good Til Canceled ...](https://www.youtube.com/watch?v=uWcNlO-4LB8) - The Good-Til-Canceled (GTC) order type allows traders to pinpoint in advance levels at which they wo...

19. [A Beginner's Guide to Rolling Options](https://optionalpha.com/learn/rolling-options) - Rolling an option involves closing one option position and opening another position in the same unde...

20. [How to Roll an Option to Become a More Dynamic Investor](https://optionsamurai.com/blog/rolling-options/) - Rolling options is a strategic move that allows you to adjust your trades as the market evolves. It ...

21. [Options Roll Up Guide: Definition and Different Types](https://www.investopedia.com/terms/r/rollup.asp) - An options roll up refers to closing existing positions to open new ones at higher strike prices. Ex...

22. [Pulling Options Data with Python and yFinance](https://dev.to/dm8ry/pulling-options-data-with-python-and-yfinance-and-saving-it-like-a-pro-45l9) - In this post, we'll explore how to extract options chain data for a stock, then save it cleanly to C...

23. [Yahoo Finance Options Data Download with Python yfinance](https://www.macroption.com/yahoo-finance-options-python/) - This tutorial creates a short script to download option price quotes from Yahoo Finance, using the y...

24. [6 Simple RSI Trading Strategies You Can Use Today](https://tradethepool.com/technical-skill/rsi-strategies/) - Sell Signal: Sell when the RSI exceeds 70. (It indicates that the stock is potentially overbought, a...

25. [ldt9/PyOptionTrader: Options Trader written in Python ...](https://github.com/ldt9/PyOptionTrader) - An options trading strategy that involves simultaneously selling an out-of-the-money (OTM) call opti...

26. [Selling Deep OTM Cash-Secured Puts with Exit Strategy ...](https://www.thebluecollarinvestor.com/selling-deep-otm-cash-secured-puts-with-exit-strategy-enhancements/) - Selling deep OTM cash-secured puts can generate significant annualized returns in a low-risk manner....

27. [Implied Volatility (IV) Rank & Percentile Explained](https://www.tastylive.com/concepts-strategies/implied-volatility-rank-percentile) - Implied volatility (IV) rank is a statistic in options trading which reports how the current level o...

28. [Machine Learning for Stock Prediction: Solutions and Tips](https://www.itransition.com/machine-learning/stock-prediction) - Machine learning for stock market prediction involves the use of advanced algorithms to forecast the...

29. [Best Free Options Backtesting Tools in 2026](https://www.tradealgo.com/trading-guides/options/options-backtesting-free) - This guide ranks the best free options backtesting tools available in 2026, walks you through a Pyth...

30. [High IV vs. Low IV: Which Stocks Work Best for the Wheel?](https://www.theoptionpremium.com/p/high-iv-vs-low-iv-wheel-strategy) - High IV stocks offer bigger premiums but greater risk, while low IV provides stability and faster co...

31. [How To Trade Options with Alpaca's Dashboard and Trading ...](https://alpaca.markets/learn/how-to-trade-options-with-alpaca) - Learn how to sign up and trade options with Alpaca's dashboard, Trading API (with Python examples), ...

32. [Alpaca Markets - Options Trading](https://alpaca.markets/options) - Paper trade, backtest, and execute your multi-leg options trading strategies via API or dashboard. A...

33. [Algorithmic Trading in Python with Alpaca: Part 1](https://alpaca.markets/learn/algorithmic-trading-python-alpaca) - Build your first trading bot! This tutorial provides a step-by-step guide to algorithmic trading wit...

34. [Using SQLite for logging and ad-hoc profiling - rand[om]](https://ricardoanderegg.com/posts/sqlite-logging-profiling-programs/) - Using SQLite lets you write the logs from different threads/processes without having to worry about ...

35. [How to build a Trading bot with Python and SQlite.](https://dev.to/shadyshafik/algorithmic-trading-how-to-build-a-trading-bot-with-python-and-sqlite-4h55) - Today we will develop another trading bot, with the use of SQlite to save data and process this data...

36. [Build A Real-Time Stock Alert Telegram Bot with Python](https://www.insightbig.com/post/build-a-real-time-stock-alert-telegram-bot-with-python) - In this article, we are going to demonstrate how you can develop your custom-made alerting mechanism...

37. [Live Option Trading Bot with Telegram Alerts](https://www.linkedin.com/posts/shivam-mishra-5049ab192_optionstrading-algorithmictrading-pythondeveloper-activity-7363144218019569665-i1ee) - Project Showcase: Live Option Trading Bot with Telegram Alerts I'm thrilled to share that my Option ...

38. [Building a Telegram bot for automated trading alerts on ...](https://community.latenode.com/t/building-a-telegram-bot-for-automated-trading-alerts-on-binary-options-platform-guidance-needed/20665) - I'm trying to build a Telegram bot that delivers trading alerts for a binary options platform. The i...

39. [APScheduler](https://pypi.org/project/APScheduler/) - Advanced Python Scheduler (APScheduler) is a Python library that lets you schedule your Python code ...

40. [An Introduction to APScheduler: Task Scheduling in Python](https://www.devtooler.com/an-introduction-to-apscheduler-task-scheduling-in-python/) - In this blog post, we'll explore a powerful Python library called APScheduler, which allows us to sc...

41. [My method on making money trading mispriced options ...](https://www.reddit.com/r/options/comments/1o7prtk/my_method_on_making_money_trading_mispriced/) - TLDR: Find stocks with abnormal volatility skews using AI, then trade Vertical Spreads on them depen...

42. [Short Strangle](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/option-strategies/short-strangle) - Short Strangle is an Options trading strategy that consists of simultaneously selling an OTM put and...

43. [The High-Probability Options Strategy With an 80.4% Win ...](https://www.cabotwealth.com/daily/options-trading/high-probability-options-strategy-87-win-rate) - Using this high-probability options strategy led us to a win rate above 80%. Here's how we did it.

44. [Stock + Option Selling Myth: More Premium Does Not ...](https://www.barchart.com/story/news/1976463/stock-option-selling-myth-more-premium-does-not-always-mean-a-better-trade) - The market is not giving away free income. High option premiums usually signal higher expected volat...

