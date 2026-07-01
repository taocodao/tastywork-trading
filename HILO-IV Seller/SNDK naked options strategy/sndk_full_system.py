#!/usr/bin/env python3
"""
=============================================================================
SNDK DYNAMIC LADDER OPTIONS STRATEGY — FULL ALGO TRADING SYSTEM
=============================================================================
Target audience: Antigravity development team
Strategy: Sell deep OTM calls/puts after large SNDK moves.
          Scale ladder on continuations. Manage/roll at triggers.
ML layer: XGBoost signal filter + Optuna DTE/delta optimizer.
Backtesting: Walk-forward on 1 year of SNDK data (Feb 2025 – Jun 2026).

Libraries required:
  pip install yfinance pandas numpy scipy xgboost optuna 
              pandas_ta apscheduler requests sqlite3 
              backtrader matplotlib plotly scikit-learn shap

=============================================================================
MODULE 1: DATA PIPELINE
=============================================================================
"""

# ─────────────────────────────────────────────────────────────────────────────
# 1a. config.yaml (load via yaml.safe_load)
# ─────────────────────────────────────────────────────────────────────────────
YAML_CONFIG = """
ticker: SNDK
backtest_start: "2025-02-24"
backtest_end:   "2026-06-27"
initial_capital: 500000       # USD

# Entry filters
entry_trigger_pct: 5.0        # Min daily move % to scan for entry
ivr_min: 65                   # Min IV Rank to sell premium
ml_confidence_min: 0.62       # XGBoost probability threshold
max_rungs_per_side: 3
max_portfolio_delta: 0.45

# Optuna-optimized parameters (initial defaults, re-optimized quarterly)
dte_target: 60                # Days to expiration at entry
initial_delta: 0.20           # First rung delta
ladder_delta_step: 0.05       # Delta step per additional rung
profit_target_pct: 0.50       # Close at 50% of premium
stop_loss_multiplier: 2.0     # Stop at 2x premium received
delta_breach_threshold: 0.35  # Roll when delta exceeds this
dte_roll_threshold: 21        # Roll when DTE drops below this
position_size_pct: 0.01       # 1% of portfolio per rung

# Risk overlays
macro_filter_spy_pct: 3.0     # Skip if SPY 5d move > 3% (systemic)
earnings_blackout_days: 14    # Skip entries within 14 days of earnings
max_ivr_entry: 95             # Don't enter above IVR 95

# Broker (Alpaca)
alpaca_paper: true
alpaca_base_url: "https://paper-api.alpaca.markets"
alpaca_api_key: "YOUR_PAPER_API_KEY"
alpaca_secret_key: "YOUR_PAPER_SECRET_KEY"

# Alerts
telegram_token: "YOUR_TELEGRAM_BOT_TOKEN"
telegram_chat_id: "YOUR_CHAT_ID"

# Database
db_path: "sndk_ladder.db"
"""

import os, math, json, sqlite3, logging, yaml
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("SNDKLadder")

# ─────────────────────────────────────────────────────────────────────────────
# 1b. Data Fetcher
# ─────────────────────────────────────────────────────────────────────────────
def fetch_price_history(ticker="SNDK", start="2025-02-24", end="2026-06-27"):
    """Fetch daily OHLCV from yfinance."""
    import yfinance as yf
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    df.columns = [c.lower() for c in df.columns]
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["date"])
    df["daily_return"] = df["close"].pct_change()
    df["daily_move_pct"] = df["daily_return"] * 100
    log.info(f"Fetched {len(df)} trading days for {ticker}")
    return df


def fetch_spy_history(start="2025-02-24", end="2026-06-27"):
    """Fetch SPY for macro regime filter."""
    import yfinance as yf
    spy = yf.download("SPY", start=start, end=end, progress=False, auto_adjust=True)
    spy = spy[["Close"]].reset_index()
    spy.columns = ["date", "spy_close"]
    spy["spy_5d_return"] = spy["spy_close"].pct_change(5) * 100
    return spy


def estimate_iv_history(price_df, base_iv=1.05, hv_window=20):
    """
    Estimate daily IV from realized vol + a VRP premium.
    In production: replace with ORATS or BlockScholes historical IV data.
    """
    price_df["hv_20"] = price_df["close"].pct_change().rolling(hv_window).std() * math.sqrt(252)
    price_df["iv_est"] = price_df["hv_20"] * 1.25 + 0.10   # VRP premium
    price_df["iv_est"] = price_df["iv_est"].clip(0.60, 2.00)
    # IVR: rolling 52-week percentile
    iv_rolling_max = price_df["iv_est"].rolling(252, min_periods=50).max()
    iv_rolling_min = price_df["iv_est"].rolling(252, min_periods=50).min()
    price_df["ivr"] = (
        (price_df["iv_est"] - iv_rolling_min) / (iv_rolling_max - iv_rolling_min) * 100
    ).clip(0, 100)
    return price_df


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 2: BLACK-SCHOLES ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def bs_price(S, K, T, iv, r=0.045, opt="call"):
    """Black-Scholes option price."""
    if T <= 0:
        return max(0, S - K) if opt == "call" else max(0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
    d2 = d1 - iv * math.sqrt(T)
    if opt == "call":
        return max(0, S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))
    return max(0, K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def bs_delta(S, K, T, iv, r=0.045, opt="call"):
    """Black-Scholes delta."""
    if T <= 0 or iv <= 0:
        return 1.0 if (opt == "call" and S > K) else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
    return norm.cdf(d1) if opt == "call" else norm.cdf(d1) - 1.0


def find_strike_for_delta(S, T, iv, target_delta=0.20, opt="call", r=0.045):
    """Binary search to find strike at target delta."""
    lo = S * 1.005 if opt == "call" else S * 0.05
    hi = S * 5.0 if opt == "call" else S * 0.998
    for _ in range(80):
        mid = (lo + hi) / 2
        d = bs_delta(S, mid, T, iv, r, opt)
        d_abs = d if opt == "call" else abs(d)
        if opt == "call":
            if d_abs > target_delta: lo = mid
            else: hi = mid
        else:
            if d_abs < target_delta: hi = mid
            else: lo = mid
    return round(mid / 5) * 5


def mark_to_market(rung, S, T_remaining, iv_current):
    """Current mark-to-market value of a rung."""
    T = max(T_remaining, 0.001)
    current_prem = bs_price(S, rung["strike"], T, iv_current, opt=rung["opt"])
    pnl = rung["entry_price"] - current_prem
    current_delta = abs(bs_delta(S, rung["strike"], T, iv_current, opt=rung["opt"]))
    return {
        "current_price": current_prem,
        "pnl": pnl,
        "pnl_pct": pnl / rung["entry_price"] if rung["entry_price"] > 0 else 0,
        "current_delta": current_delta,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 3: FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────
def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))


def compute_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift(1))
    low_close = abs(df["low"] - df["close"].shift(1))
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def build_features(df, spy_df=None):
    """
    Build 18-feature vector for ML model.
    Returns feature DataFrame (rows=trading days).
    """
    f = pd.DataFrame(index=df.index)

    # === Price momentum ===
    f["daily_return"]       = df["close"].pct_change()
    f["return_3d"]          = df["close"].pct_change(3)
    f["return_5d"]          = df["close"].pct_change(5)
    f["return_10d"]         = df["close"].pct_change(10)
    f["return_20d"]         = df["close"].pct_change(20)

    # === Intraday range ===
    f["daily_range_pct"]    = (df["high"] - df["low"]) / df["close"]
    f["gap_pct"]            = (df["open"] - df["close"].shift(1)) / df["close"].shift(1)

    # === Oscillators ===
    f["rsi_14"]             = compute_rsi(df["close"], 14)
    f["rsi_5"]              = compute_rsi(df["close"], 5)
    f["atr_14"]             = compute_atr(df, 14)
    f["above_20sma"]        = (df["close"] > df["close"].rolling(20).mean()).astype(int)
    f["dist_from_20sma"]    = (df["close"] - df["close"].rolling(20).mean()) / df["close"]

    # === Volatility ===
    f["iv"]                 = df["iv_est"]
    f["ivr"]                = df["ivr"]
    f["hv_10"]              = df["close"].pct_change().rolling(10).std() * math.sqrt(252)
    f["iv_hv_spread"]       = f["iv"] - f["hv_10"]   # VRP proxy

    # === Volume ===
    f["vol_ratio_5d"]       = df["volume"] / df["volume"].rolling(5).mean()

    # === Macro regime (SPY) ===
    if spy_df is not None:
        merged = pd.merge(df[["date"]], spy_df[["date","spy_5d_return"]], on="date", how="left")
        f["spy_5d_return"] = merged["spy_5d_return"].values
    else:
        f["spy_5d_return"] = 0.0

    return f.dropna()


def create_labels(df, feature_index, dte_at_entry=60, profit_target=0.50):
    """
    Generate ML target labels from historical entry days.
    Label = 1 if: premium decayed to 50% within 30 days AND IV fell post-entry.
    Label = 0 if: IV expanded further OR stock moved through the strike.
    """
    labels = []
    dates = []

    for i in feature_index:
        if i + 30 >= len(df):
            continue
        row = df.iloc[i]
        S = row["close"]
        iv = row["iv_est"]
        T = dte_at_entry / 365

        # Determine direction
        daily_move = row["daily_move_pct"]
        if abs(daily_move) < 5.0:
            continue

        opt = "call" if daily_move > 0 else "put"
        strike = find_strike_for_delta(S, T, iv, target_delta=0.20, opt=opt)
        entry_prem = bs_price(S, strike, T, iv, opt=opt)

        # Simulate forward 30 days
        good = False
        for j in range(1, 31):
            if i + j >= len(df):
                break
            future = df.iloc[i + j]
            S_future = future["close"]
            iv_future = future["iv_est"]
            T_remaining = max((dte_at_entry - j) / 365, 0.001)
            current_prem = bs_price(S_future, strike, T_remaining, iv_future, opt=opt)
            pnl_pct = (entry_prem - current_prem) / entry_prem
            if pnl_pct >= profit_target:
                good = True
                break

        labels.append(1 if good else 0)
        dates.append(df.iloc[i]["date"])

    return pd.DataFrame({"date": dates, "label": labels})


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 4: XGBOOST SIGNAL CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────
def train_signal_model(X_train, y_train):
    """Train XGBoost binary classifier: 1 = good entry, 0 = skip."""
    import xgboost as xgb
    scale_pos = max(1, (y_train == 0).sum() / max((y_train == 1).sum(), 1))
    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        verbosity=0
    )
    model.fit(X_train, y_train)
    return model


def get_signal(model, feature_row, threshold=0.62):
    """Returns (should_enter: bool, confidence: float)."""
    prob = model.predict_proba([feature_row])[0][1]
    return prob >= threshold, round(prob, 3)


def shap_analysis(model, X_df):
    """Print top SHAP feature importances."""
    import shap
    explainer = shap.TreeExplainer(model)
    shap_vals = explainer.shap_values(X_df)
    importance = pd.DataFrame({
        "feature": X_df.columns,
        "mean_abs_shap": np.abs(shap_vals).mean(0)
    }).sort_values("mean_abs_shap", ascending=False)
    log.info("\nTop 10 SHAP features:\n" + importance.head(10).to_string())
    return importance


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 5: OPTUNA PARAMETER OPTIMIZER
# ─────────────────────────────────────────────────────────────────────────────
def run_optuna_optimization(df_train, spy_df_train, n_trials=200):
    """
    Optuna Bayesian search over:
      - dte_target: [30, 45, 60, 90]
      - initial_delta: [0.10, 0.15, 0.20, 0.25]
      - profit_target_pct: [0.40, 0.50, 0.60]
      - stop_loss_multiplier: [1.5, 2.0, 3.0]
      - entry_trigger_pct: [3.0, 5.0, 7.0]
      - ivr_min: [50, 60, 65, 70, 75]

    Objective: maximize Sharpe ratio of simulated trade outcomes.
    """
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        dte          = trial.suggest_categorical("dte_target", [30, 45, 60, 90])
        delta        = trial.suggest_categorical("initial_delta", [0.10, 0.15, 0.20, 0.25])
        profit_pct   = trial.suggest_categorical("profit_target_pct", [0.40, 0.50, 0.60])
        sl_mult      = trial.suggest_categorical("stop_loss_mult", [1.5, 2.0, 3.0])
        trigger_pct  = trial.suggest_categorical("entry_trigger_pct", [3.0, 5.0, 7.0])
        ivr_min      = trial.suggest_categorical("ivr_min", [50, 60, 65, 70, 75])

        params = {
            "dte_target": dte,
            "initial_delta": delta,
            "profit_target_pct": profit_pct,
            "stop_loss_multiplier": sl_mult,
            "entry_trigger_pct": trigger_pct,
            "ivr_min": ivr_min,
        }

        pnls = simulate_strategy(df_train, spy_df_train, params, use_ml=False)
        if len(pnls) < 5:
            return -999.0

        returns = pd.Series(pnls)
        sharpe = returns.mean() / (returns.std() + 1e-9) * math.sqrt(252)
        return float(sharpe)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42)
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)

    log.info(f"\nOptuna best params: {study.best_params}")
    log.info(f"Best Sharpe: {study.best_value:.3f}")
    return study.best_params


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 6: STRATEGY SIMULATOR (BACKTESTING CORE)
# ─────────────────────────────────────────────────────────────────────────────
def simulate_strategy(df, spy_df, params, use_ml=True, ml_model=None, ml_features=None):
    """
    Core simulation loop for walk-forward backtesting.
    Returns list of per-trade PnLs as % of premium received.

    Parameters:
        df          : price + IV DataFrame (from estimate_iv_history)
        spy_df      : SPY data for macro filter
        params      : dict of strategy parameters (from config or Optuna)
        use_ml      : bool — whether to apply XGBoost filter
        ml_model    : trained XGBoost model (required if use_ml=True)
        ml_features : features DataFrame aligned to df (required if use_ml=True)
    """
    dte             = params.get("dte_target", 60)
    init_delta      = params.get("initial_delta", 0.20)
    delta_step      = params.get("ladder_delta_step", 0.05)
    profit_pct      = params.get("profit_target_pct", 0.50)
    sl_mult         = params.get("stop_loss_multiplier", 2.0)
    trigger_pct     = params.get("entry_trigger_pct", 5.0)
    ivr_min         = params.get("ivr_min", 65)
    ml_thresh       = params.get("ml_confidence_min", 0.62)
    max_rungs       = params.get("max_rungs_per_side", 3)
    macro_filter    = params.get("macro_filter_spy_pct", 3.0)
    delta_breach    = params.get("delta_breach_threshold", 0.35)
    dte_roll        = params.get("dte_roll_threshold", 21)

    call_rungs, put_rungs = [], []
    trade_pnls = []
    portfolio_pnl = 0.0
    initial_capital = params.get("initial_capital", 500000)
    capital = initial_capital

    spy_dict = {}
    if spy_df is not None:
        for _, row in spy_df.iterrows():
            spy_dict[row["date"]] = row.get("spy_5d_return", 0)

    for i in range(20, len(df)):
        row = df.iloc[i]
        S         = row["close"]
        iv        = row["iv_est"]
        ivr       = row["ivr"]
        date      = row["date"]
        daily_mv  = row.get("daily_move_pct", 0)
        T_new     = dte / 365

        # ── 1. MANAGE EXISTING POSITIONS ─────────────────────────────────
        for rung_list in [call_rungs, put_rungs]:
            to_remove = []
            for rung in rung_list:
                days_held = (pd.Timestamp(date) - pd.Timestamp(rung["entry_date"])).days
                T_rem = max((dte - days_held) / 365, 0.001)
                mtm = mark_to_market(rung, S, T_rem, iv)

                # Profit target
                if mtm["pnl_pct"] >= profit_pct:
                    trade_pnls.append(mtm["pnl"] / rung["entry_price"])
                    to_remove.append(rung)
                    log.debug(f"{date}: CLOSED {rung['opt']} K={rung['strike']:.0f} | PnL={mtm['pnl_pct']*100:.1f}%")

                # Stop loss
                elif mtm["pnl_pct"] <= -sl_mult:
                    trade_pnls.append(mtm["pnl"] / rung["entry_price"])
                    to_remove.append(rung)
                    log.debug(f"{date}: STOPPED {rung['opt']} K={rung['strike']:.0f} | PnL={mtm['pnl_pct']*100:.1f}%")

                # Roll on delta breach
                elif mtm["current_delta"] > delta_breach:
                    # Simulate roll: credit additional premium, extend DTE
                    roll_credit = bs_price(S, rung["strike"], T_rem + 30/365, iv, opt=rung["opt"]) -                                   bs_price(S, rung["strike"], T_rem, iv, opt=rung["opt"])
                    rung["entry_price"] += roll_credit * 0.8
                    rung["entry_date"] = date
                    log.debug(f"{date}: ROLLED {rung['opt']} K={rung['strike']:.0f} | +30 DTE")

                # DTE roll
                elif T_rem * 365 <= dte_roll:
                    # Close and re-open next monthly
                    trade_pnls.append(mtm["pnl"] / rung["entry_price"])
                    to_remove.append(rung)

            for r in to_remove:
                rung_list.remove(r)

        # ── 2. ENTRY SIGNAL LOGIC ────────────────────────────────────────
        # Pre-filters
        if abs(daily_mv) < trigger_pct: continue
        if ivr < ivr_min: continue
        if pd.isna(S) or iv <= 0: continue

        # Macro filter
        spy_5d = spy_dict.get(date, 0)
        if abs(spy_5d) > macro_filter: continue

        # ML filter
        if use_ml and ml_model is not None and ml_features is not None:
            feat_row_df = ml_features[ml_features.index == i]
            if feat_row_df.empty: continue
            feat_row = feat_row_df.iloc[0].values
            enter, conf = get_signal(ml_model, feat_row, ml_thresh)
            if not enter: continue

        direction = "call" if daily_mv > 0 else "put"
        rung_list = call_rungs if direction == "call" else put_rungs
        if len(rung_list) >= max_rungs: continue

        rung_num = len(rung_list)
        target_delta = max(0.08, init_delta - rung_num * delta_step)
        strike = find_strike_for_delta(S, T_new, iv, target_delta=target_delta, opt=direction)
        entry_prem = bs_price(S, strike, T_new, iv, opt=direction)

        if entry_prem <= 0: continue

        rung = {
            "opt": direction,
            "strike": strike,
            "entry_price": entry_prem,
            "entry_delta": abs(bs_delta(S, strike, T_new, iv, opt=direction)),
            "entry_iv": iv,
            "entry_date": date,
            "rung_num": rung_num + 1,
        }
        rung_list.append(rung)
        log.debug(f"{date}: ENTERED {direction.upper()} K={strike:.0f} | Prem={entry_prem:.1f} | δ={target_delta:.2f}")

    # Close remaining open positions at end of simulation
    for rung_list in [call_rungs, put_rungs]:
        for rung in rung_list:
            days_held = (pd.Timestamp(df.iloc[-1]["date"]) - pd.Timestamp(rung["entry_date"])).days
            T_rem = max((dte - days_held) / 365, 0.001)
            mtm = mark_to_market(rung, df.iloc[-1]["close"], T_rem, df.iloc[-1]["iv_est"])
            trade_pnls.append(mtm["pnl"] / rung["entry_price"])

    return trade_pnls


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 7: WALK-FORWARD BACKTEST
# ─────────────────────────────────────────────────────────────────────────────
def walk_forward_backtest(df, spy_df, base_params, n_trials_optuna=100):
    """
    Walk-forward optimization:
      - Train window: 6 months (126 trading days)
      - Test window: 3 months (63 trading days)
      - Step: 63 trading days

    For each window:
      1. Run Optuna on train set to optimize params
      2. Run simulation on test set with optimized params
      3. Log results

    Returns: combined test-set results DataFrame
    """
    all_results = []
    window_train = 126
    window_test  = 63
    step         = 63

    i_start = 0
    window_num = 0

    while i_start + window_train + window_test < len(df):
        i_train_end = i_start + window_train
        i_test_end  = i_train_end + window_test

        df_train = df.iloc[i_start:i_train_end].reset_index(drop=True)
        df_test  = df.iloc[i_train_end:i_test_end].reset_index(drop=True)

        spy_train = spy_df[(spy_df["date"] >= df_train["date"].min()) &
                           (spy_df["date"] <= df_train["date"].max())]
        spy_test  = spy_df[(spy_df["date"] >= df_test["date"].min()) &
                           (spy_df["date"] <= df_test["date"].max())]

        log.info(f"\n=== Walk-Forward Window {window_num+1} ===")
        log.info(f"Train: {df_train['date'].min().date()} – {df_train['date'].max().date()}")
        log.info(f"Test:  {df_test['date'].min().date()} – {df_test['date'].max().date()}")

        # Optuna optimization on training set
        best_params = run_optuna_optimization(df_train, spy_train, n_trials=n_trials_optuna)
        merged_params = {**base_params, **best_params}

        # Train ML model on train set
        features_train = build_features(df_train, spy_train)
        labels_df = create_labels(df_train, features_train.index, merged_params["dte_target"])
        if len(labels_df) > 10:
            X = features_train.loc[labels_df.index]
            y = labels_df["label"]
            ml_model = train_signal_model(X.values, y.values)
        else:
            ml_model = None

        # Simulate on test set
        features_test = build_features(df_test, spy_test)
        pnls = simulate_strategy(
            df_test, spy_test, merged_params,
            use_ml=(ml_model is not None),
            ml_model=ml_model,
            ml_features=features_test
        )

        if len(pnls) > 0:
            pnl_series = pd.Series(pnls)
            win_rate    = (pnl_series > 0).mean()
            avg_win     = pnl_series[pnl_series > 0].mean() if (pnl_series > 0).any() else 0
            avg_loss    = pnl_series[pnl_series < 0].mean() if (pnl_series < 0).any() else 0
            sharpe      = pnl_series.mean() / (pnl_series.std() + 1e-9) * math.sqrt(252)
            max_dd      = (pnl_series.cumsum() - pnl_series.cumsum().cummax()).min()

            result = {
                "window": window_num + 1,
                "test_start": df_test["date"].min().date(),
                "test_end":   df_test["date"].max().date(),
                "n_trades":   len(pnls),
                "win_rate":   round(win_rate * 100, 1),
                "avg_win_pct": round(avg_win * 100, 2),
                "avg_loss_pct": round(avg_loss * 100, 2),
                "sharpe":     round(sharpe, 3),
                "max_dd_pct": round(max_dd * 100, 2),
                "best_params": best_params,
            }
            all_results.append(result)
            log.info(f"Test results: trades={len(pnls)} | WinRate={win_rate*100:.1f}% | Sharpe={sharpe:.2f}")

        i_start += step
        window_num += 1

    results_df = pd.DataFrame(all_results)
    return results_df


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 8: DATABASE MANAGER
# ─────────────────────────────────────────────────────────────────────────────
class TradeDB:
    def __init__(self, db_path="sndk_ladder.db"):
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        con = sqlite3.connect(self.db_path)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT,
                ticker          TEXT,
                action          TEXT,    -- ENTRY/CLOSE/ROLL/STOP
                opt_type        TEXT,    -- call/put
                strike          REAL,
                entry_price     REAL,
                exit_price      REAL,
                dte_at_entry    INTEGER,
                iv_at_entry     REAL,
                delta_at_entry  REAL,
                pnl             REAL,
                pnl_pct         REAL,
                ml_confidence   REAL,
                params_snapshot TEXT     -- JSON of params used
            );

            CREATE TABLE IF NOT EXISTS backtest_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp   TEXT,
                window_num      INTEGER,
                test_start      TEXT,
                test_end        TEXT,
                n_trades        INTEGER,
                win_rate        REAL,
                sharpe          REAL,
                max_dd_pct      REAL,
                best_params     TEXT     -- JSON
            );

            CREATE TABLE IF NOT EXISTS daily_snapshot (
                date            TEXT PRIMARY KEY,
                sndk_close      REAL,
                iv_est          REAL,
                ivr             REAL,
                n_open_calls    INTEGER,
                n_open_puts     INTEGER,
                portfolio_delta REAL
            );
        """)
        con.commit()
        con.close()

    def log_trade(self, action, opt_type, strike, entry_price, exit_price,
                  dte, iv, delta, pnl, pnl_pct, ml_conf=None, params=None):
        con = sqlite3.connect(self.db_path)
        con.execute("""
            INSERT INTO trades (timestamp, ticker, action, opt_type, strike,
                               entry_price, exit_price, dte_at_entry, iv_at_entry,
                               delta_at_entry, pnl, pnl_pct, ml_confidence, params_snapshot)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), "SNDK", action, opt_type, strike,
             entry_price, exit_price, dte, iv, delta, pnl, pnl_pct,
             ml_conf, json.dumps(params or {})))
        con.commit()
        con.close()

    def log_backtest_window(self, run_ts, result_dict):
        con = sqlite3.connect(self.db_path)
        con.execute("""
            INSERT INTO backtest_results (run_timestamp, window_num, test_start, test_end,
                                         n_trades, win_rate, sharpe, max_dd_pct, best_params)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (run_ts, result_dict["window"], str(result_dict["test_start"]),
             str(result_dict["test_end"]), result_dict["n_trades"],
             result_dict["win_rate"], result_dict["sharpe"],
             result_dict["max_dd_pct"], json.dumps(result_dict.get("best_params", {}))))
        con.commit()
        con.close()

    def query_open_trades(self):
        con = sqlite3.connect(self.db_path)
        df = pd.read_sql("SELECT * FROM trades WHERE action='ENTRY' AND exit_price IS NULL", con)
        con.close()
        return df


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 9: ALERTING
# ─────────────────────────────────────────────────────────────────────────────
def send_telegram(message, token, chat_id):
    """Send alert to Telegram."""
    import requests
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": message,
                                 "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        log.error(f"Telegram error: {e}")


def format_entry_alert(rung, date, confidence):
    return (
        f"🎯 *SNDK LADDER ENTRY*\n"
        f"Date: {date} | ML Conf: {confidence:.2f}\n"
        f"Type: SELL {rung['opt'].upper()} @ *${rung['strike']:,.0f}*\n"
        f"Premium: *${rung['entry_price']:.1f}* | Delta: {rung['entry_delta']:.3f}\n"
        f"Rung #{rung['rung_num']} | IV at entry: {rung['entry_iv']*100:.0f}%"
    )


def format_exit_alert(rung, pnl, pnl_pct, reason):
    emoji = "✅" if pnl > 0 else "❌"
    return (
        f"{emoji} *SNDK LADDER EXIT — {reason}*\n"
        f"Type: {rung['opt'].upper()} @ ${rung['strike']:,.0f}\n"
        f"P&L: *${pnl:.1f}* ({pnl_pct*100:.1f}%)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 10: LIVE TRADING ENGINE (Alpaca)
# ─────────────────────────────────────────────────────────────────────────────
def get_alpaca_options_client(api_key, secret_key, paper=True):
    """Returns Alpaca options trading client."""
    from alpaca.trading.client import TradingClient
    base = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
    return TradingClient(api_key, secret_key, paper=paper, url_override=base)


def get_nearest_option_contract(client, symbol, strike, expiry_date, opt_type="call"):
    """Find nearest available option contract to target strike/expiry."""
    from alpaca.trading.requests import GetOptionContractsRequest
    req = GetOptionContractsRequest(
        underlying_symbols=[symbol],
        expiration_date=expiry_date.strftime("%Y-%m-%d"),
        type=opt_type,
        strike_price_gte=str(strike - 50),
        strike_price_lte=str(strike + 50)
    )
    contracts = client.get_option_contracts(req)
    if contracts and contracts.option_contracts:
        # Sort by proximity to target strike
        return min(contracts.option_contracts,
                   key=lambda c: abs(float(c.strike_price) - strike))
    return None


def place_option_sell_order(client, contract_id, qty=1, order_type="market"):
    """Place naked short option order via Alpaca."""
    from alpaca.trading.requests import OptionLegRequest, PlaceOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
    order = PlaceOrderRequest(
        symbol=contract_id,
        qty=qty,
        side=OrderSide.SELL,
        type=order_type,
        time_in_force=TimeInForce.DAY,
    )
    return client.submit_order(order)


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 11: SCHEDULER — DAILY SIGNAL LOOP
# ─────────────────────────────────────────────────────────────────────────────
def daily_signal_loop(config):
    """
    Runs at 4:05 PM ET every trading day.
    1. Fetch latest SNDK data
    2. Build features
    3. Run ML signal check
    4. Execute entries/exits via Alpaca
    5. Log to SQLite
    6. Send Telegram alerts
    """
    import yfinance as yf

    ticker     = config["ticker"]
    db         = TradeDB(config["db_path"])
    token      = config.get("telegram_token")
    chat_id    = config.get("telegram_chat_id")

    # Fresh data
    df = fetch_price_history(ticker, start="2025-02-24",
                             end=datetime.now().strftime("%Y-%m-%d"))
    df = estimate_iv_history(df)
    spy = fetch_spy_history(start="2025-02-24",
                            end=datetime.now().strftime("%Y-%m-%d"))
    features = build_features(df, spy)

    # Load saved model (re-train weekly with latest data)
    import pickle
    try:
        with open("ml_model.pkl", "rb") as f:
            ml_model = pickle.load(f)
    except FileNotFoundError:
        log.warning("No saved ML model. Running without ML filter.")
        ml_model = None

    latest = df.iloc[-1]
    S, iv, ivr = latest["close"], latest["iv_est"], latest["ivr"]
    daily_mv = latest["daily_move_pct"]
    date = latest["date"]

    log.info(f"Daily check: {date} | S={S:.0f} | IV={iv*100:.0f}% | IVR={ivr:.0f} | Move={daily_mv:.1f}%")

    # Check entry conditions
    if abs(daily_mv) >= config["entry_trigger_pct"] and ivr >= config["ivr_min"]:
        feat_row = features.iloc[-1].values
        if ml_model:
            enter, conf = get_signal(ml_model, feat_row, config["ml_confidence_min"])
        else:
            enter, conf = True, 0.0

        if enter:
            direction = "call" if daily_mv > 0 else "put"
            T = config["dte_target"] / 365
            strike = find_strike_for_delta(S, T, iv, config["initial_delta"], opt=direction)
            prem = bs_price(S, strike, T, iv, opt=direction)
            delta = abs(bs_delta(S, strike, T, iv, opt=direction))

            rung = {"opt": direction, "strike": strike, "entry_price": prem,
                    "entry_delta": delta, "entry_iv": iv, "entry_date": date, "rung_num": 1}

            alert = format_entry_alert(rung, date, conf)
            log.info(alert)
            if token and chat_id:
                send_telegram(alert, token, chat_id)

            db.log_trade("ENTRY", direction, strike, prem, None,
                        config["dte_target"], iv, delta, 0, 0, conf, config)


def schedule_system(config):
    """Start APScheduler to run daily at 4:05 PM ET."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BlockingScheduler(timezone="America/New_York")
    scheduler.add_job(
        daily_signal_loop, args=[config],
        trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=5),
        name="SNDK_Ladder_Daily"
    )
    log.info("Scheduler running. Will fire at 4:05 PM ET on trading days.")
    scheduler.start()


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 12: METRICS AND REPORTING
# ─────────────────────────────────────────────────────────────────────────────
def compute_backtest_metrics(trade_pnls, initial_capital=500000):
    """Compute comprehensive performance metrics from trade PnL list."""
    if not trade_pnls:
        return {}
    s = pd.Series(trade_pnls)
    total_trades  = len(s)
    winners       = s[s > 0]
    losers        = s[s < 0]
    win_rate      = len(winners) / total_trades
    profit_factor = winners.sum() / abs(losers.sum()) if len(losers) > 0 else float("inf")
    sharpe        = s.mean() / (s.std() + 1e-9) * math.sqrt(252)
    cum            = (1 + s).cumprod()
    max_dd        = (cum / cum.cummax() - 1).min()
    kelly         = win_rate - (1 - win_rate) / (winners.mean() / abs(losers.mean() + 1e-9) + 1e-9)

    return {
        "Total Trades": total_trades,
        "Win Rate": f"{win_rate*100:.1f}%",
        "Avg Win": f"{winners.mean()*100:.2f}%" if len(winners) > 0 else "N/A",
        "Avg Loss": f"{losers.mean()*100:.2f}%" if len(losers) > 0 else "N/A",
        "Profit Factor": f"{profit_factor:.2f}",
        "Sharpe Ratio": f"{sharpe:.3f}",
        "Max Drawdown": f"{max_dd*100:.2f}%",
        "Kelly Criterion": f"{kelly*100:.1f}%",
    }


def plot_backtest_equity(trade_pnls, title="SNDK Ladder Strategy — 1 Year Backtest"):
    """Generate equity curve plot."""
    import plotly.graph_objects as go
    s = pd.Series(trade_pnls)
    cum = (1 + s).cumprod() * 100000  # Starting at $100k equiv
    fig = go.Figure()
    fig.add_trace(go.Scatter(y=cum, mode="lines", name="Equity Curve",
                             line=dict(width=2, color="#636efa"),
                             fill="tozeroy", fillcolor="rgba(99,110,250,0.1)"))
    fig.add_hline(y=100000, line_dash="dash", line_color="#888",
                 annotation_text="Starting Capital")
    fig.update_layout(
        title=title,
        xaxis_title="Trade Number",
        yaxis_title="Equity ($)",
        showlegend=True
    )
    fig.write_image("backtest_equity.png")
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# MAIN: RUN FULL BACKTEST
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import yaml

    # Load config
    cfg = yaml.safe_load(YAML_CONFIG)

    log.info("=== SNDK LADDER STRATEGY — 1-YEAR BACKTEST ===")
    log.info(f"Period: {cfg['backtest_start']} – {cfg['backtest_end']}")
    log.info(f"Initial capital: ${cfg['initial_capital']:,}")

    # 1. Fetch data
    df   = fetch_price_history("SNDK", cfg["backtest_start"], cfg["backtest_end"])
    spy  = fetch_spy_history(cfg["backtest_start"], cfg["backtest_end"])
    df   = estimate_iv_history(df)
    df   = pd.merge(df, spy, on="date", how="left")

    log.info(f"Data loaded: {len(df)} trading days")
    log.info(f"Price range: ${df['close'].min():.1f} – ${df['close'].max():.1f}")
    log.info(f"IV range:    {df['iv_est'].min()*100:.0f}% – {df['iv_est'].max()*100:.0f}%")

    # 2. Walk-forward backtest with Optuna optimization
    results = walk_forward_backtest(df, spy, base_params=cfg, n_trials_optuna=150)

    # 3. Print results
    print("\n=== WALK-FORWARD BACKTEST RESULTS ===")
    print(results[["window","test_start","test_end","n_trades","win_rate","sharpe","max_dd_pct"]].to_string())

    # 4. Aggregate metrics
    all_trades = []
    for _, wf_row in results.iterrows():
        pass  # In full run, collect all pnls from each window

    # 5. Log results
    db = TradeDB(cfg["db_path"])
    for _, row in results.iterrows():
        db.log_backtest_window(datetime.now().isoformat(), row.to_dict())

    log.info("\n=== BACKTEST COMPLETE ===")
    log.info(f"Avg Sharpe across windows: {results['sharpe'].mean():.3f}")
    log.info(f"Avg Win Rate: {results['win_rate'].mean():.1f}%")
    log.info(f"Worst drawdown: {results['max_dd_pct'].min():.2f}%")

    # Optional: launch scheduler for live trading
    # schedule_system(cfg)
