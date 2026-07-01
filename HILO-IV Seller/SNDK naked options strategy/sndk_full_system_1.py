#!/usr/bin/env python3
"""
=============================================================================
SNDK DYNAMIC LADDER OPTIONS STRATEGY — FULL ALGO TRADING SYSTEM
Developer memo: Antigravity Team | Strategy: ML-Optimized Naked OTM Ladder
=============================================================================
Install: pip install yfinance pandas numpy scipy xgboost optuna pandas_ta 
         apscheduler requests alpaca-py scikit-learn shap pyyaml
=============================================================================
"""

# ─── YAML CONFIG (embed or load from config.yaml) ──────────────────────────
YAML_CONFIG = """
ticker: SNDK
backtest_start: "2025-02-24"
backtest_end:   "2026-06-27"
initial_capital: 500000
entry_trigger_pct: 5.0
ivr_min: 65
ml_confidence_min: 0.62
max_rungs_per_side: 3
max_portfolio_delta: 0.45
dte_target: 60
initial_delta: 0.20
ladder_delta_step: 0.05
profit_target_pct: 0.50
stop_loss_multiplier: 2.0
delta_breach_threshold: 0.35
dte_roll_threshold: 21
position_size_pct: 0.01
macro_filter_spy_pct: 3.0
earnings_blackout_days: 14
alpaca_paper: true
alpaca_api_key: "YOUR_PAPER_API_KEY"
alpaca_secret_key: "YOUR_PAPER_SECRET_KEY"
telegram_token: "YOUR_TELEGRAM_BOT_TOKEN"
telegram_chat_id: "YOUR_CHAT_ID"
db_path: "sndk_ladder.db"
"""

import os, math, json, sqlite3, logging
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime
import warnings; warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("SNDKLadder")

# ─── MODULE 1: DATA PIPELINE ────────────────────────────────────────────────
def fetch_price_history(ticker="SNDK", start="2025-02-24", end="2026-06-27"):
    import yfinance as yf
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    df.columns = [c.lower() for c in df.columns]
    df = df.reset_index()
    df["date"] = pd.to_datetime(df["date"])
    df["daily_return"] = df["close"].pct_change()
    df["daily_move_pct"] = df["daily_return"] * 100
    return df

def fetch_spy_history(start="2025-02-24", end="2026-06-27"):
    import yfinance as yf
    spy = yf.download("SPY", start=start, end=end, progress=False, auto_adjust=True)
    spy = spy[["Close"]].reset_index()
    spy.columns = ["date", "spy_close"]
    spy["spy_5d_return"] = spy["spy_close"].pct_change(5) * 100
    return spy

def estimate_iv_history(df, hv_window=20):
    """
    Proxy IV = HV20 * 1.25 + 0.10 (VRP premium).
    PRODUCTION: Replace with ORATS or BlockScholes historical IV surface data.
    """
    df["hv_20"] = df["close"].pct_change().rolling(hv_window).std() * math.sqrt(252)
    df["iv_est"] = (df["hv_20"] * 1.25 + 0.10).clip(0.60, 2.00)
    iv_max = df["iv_est"].rolling(252, min_periods=50).max()
    iv_min = df["iv_est"].rolling(252, min_periods=50).min()
    df["ivr"] = ((df["iv_est"] - iv_min) / (iv_max - iv_min) * 100).clip(0, 100)
    return df

# ─── MODULE 2: BLACK-SCHOLES ENGINE ─────────────────────────────────────────
def bs_price(S, K, T, iv, r=0.045, opt="call"):
    if T <= 0:
        return max(0, S-K) if opt=="call" else max(0, K-S)
    d1 = (math.log(S/K) + (r + 0.5*iv**2)*T) / (iv*math.sqrt(T))
    d2 = d1 - iv*math.sqrt(T)
    if opt == "call":
        return max(0, S*norm.cdf(d1) - K*math.exp(-r*T)*norm.cdf(d2))
    return max(0, K*math.exp(-r*T)*norm.cdf(-d2) - S*norm.cdf(-d1))

def bs_delta(S, K, T, iv, r=0.045, opt="call"):
    if T <= 0 or iv <= 0:
        return 1.0 if (opt=="call" and S>K) else 0.0
    d1 = (math.log(S/K) + (r + 0.5*iv**2)*T) / (iv*math.sqrt(T))
    return norm.cdf(d1) if opt=="call" else norm.cdf(d1) - 1.0

def find_strike_for_delta(S, T, iv, target_delta=0.20, opt="call", r=0.045):
    lo = S*1.005 if opt=="call" else S*0.05
    hi = S*5.0 if opt=="call" else S*0.998
    for _ in range(80):
        mid = (lo + hi) / 2
        d_abs = abs(bs_delta(S, mid, T, iv, r, opt))
        if opt == "call":
            if d_abs > target_delta: lo = mid
            else: hi = mid
        else:
            if d_abs < target_delta: hi = mid
            else: lo = mid
    return round(mid / 5) * 5

def mark_to_market(rung, S, T_remaining, iv_current):
    T = max(T_remaining, 0.001)
    cp = bs_price(S, rung["strike"], T, iv_current, opt=rung["opt"])
    pnl = rung["entry_price"] - cp
    delta = abs(bs_delta(S, rung["strike"], T, iv_current, opt=rung["opt"]))
    return {"current_price": cp, "pnl": pnl,
            "pnl_pct": pnl/rung["entry_price"] if rung["entry_price"]>0 else 0,
            "current_delta": delta}

# ─── MODULE 3: FEATURE ENGINEERING ──────────────────────────────────────────
def compute_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta>0, 0).rolling(period).mean()
    loss = (-delta.where(delta<0, 0)).rolling(period).mean()
    return 100 - (100 / (1 + gain/(loss+1e-9)))

def compute_atr(df, period=14):
    tr = pd.concat([df["high"]-df["low"],
                    abs(df["high"]-df["close"].shift(1)),
                    abs(df["low"]-df["close"].shift(1))], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def build_features(df, spy_df=None):
    f = pd.DataFrame(index=df.index)
    f["daily_return"]    = df["close"].pct_change()
    f["return_3d"]       = df["close"].pct_change(3)
    f["return_5d"]       = df["close"].pct_change(5)
    f["return_10d"]      = df["close"].pct_change(10)
    f["return_20d"]      = df["close"].pct_change(20)
    f["daily_range_pct"] = (df["high"]-df["low"])/df["close"]
    f["gap_pct"]         = (df["open"]-df["close"].shift(1))/df["close"].shift(1)
    f["rsi_14"]          = compute_rsi(df["close"], 14)
    f["rsi_5"]           = compute_rsi(df["close"], 5)
    f["atr_14"]          = compute_atr(df, 14)
    f["above_20sma"]     = (df["close"]>df["close"].rolling(20).mean()).astype(int)
    f["dist_from_20sma"] = (df["close"]-df["close"].rolling(20).mean())/df["close"]
    f["iv"]              = df["iv_est"]
    f["ivr"]             = df["ivr"]
    f["hv_10"]           = df["close"].pct_change().rolling(10).std()*math.sqrt(252)
    f["iv_hv_spread"]    = f["iv"] - f["hv_10"]
    f["vol_ratio_5d"]    = df["volume"]/df["volume"].rolling(5).mean()
    if spy_df is not None:
        merged = pd.merge(df[["date"]], spy_df[["date","spy_5d_return"]], on="date", how="left")
        f["spy_5d_return"] = merged["spy_5d_return"].values
    else:
        f["spy_5d_return"] = 0.0
    return f.dropna()

def create_labels(df, feature_index, dte_at_entry=60, profit_target=0.50):
    labels, dates = [], []
    for i in feature_index:
        if i+30 >= len(df): continue
        row = df.iloc[i]
        if abs(row["daily_move_pct"]) < 5.0: continue
        S, iv = row["close"], row["iv_est"]
        opt = "call" if row["daily_move_pct"]>0 else "put"
        K = find_strike_for_delta(S, dte_at_entry/365, iv, target_delta=0.20, opt=opt)
        ep = bs_price(S, K, dte_at_entry/365, iv, opt=opt)
        good = False
        for j in range(1, 31):
            if i+j >= len(df): break
            fut = df.iloc[i+j]
            t_rem = max((dte_at_entry-j)/365, 0.001)
            cp = bs_price(fut["close"], K, t_rem, fut["iv_est"], opt=opt)
            if (ep-cp)/ep >= profit_target:
                good = True; break
        labels.append(1 if good else 0)
        dates.append(df.iloc[i]["date"])
    return pd.DataFrame({"date": dates, "label": labels})

# ─── MODULE 4: XGBOOST SIGNAL CLASSIFIER ────────────────────────────────────
def train_signal_model(X_train, y_train):
    import xgboost as xgb
    scale_pos = max(1, (y_train==0).sum()/max((y_train==1).sum(), 1))
    model = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, scale_pos_weight=scale_pos,
        eval_metric="logloss", random_state=42, verbosity=0)
    model.fit(X_train, y_train)
    return model

def get_signal(model, feature_row, threshold=0.62):
    prob = model.predict_proba([feature_row])[0][1]
    return prob >= threshold, round(prob, 3)

# ─── MODULE 5: OPTUNA PARAMETER OPTIMIZER ───────────────────────────────────
def run_optuna_optimization(df_train, spy_train, n_trials=200):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = {
            "dte_target":          trial.suggest_categorical("dte_target", [30, 45, 60, 90]),
            "initial_delta":       trial.suggest_categorical("initial_delta", [0.10, 0.15, 0.20, 0.25]),
            "profit_target_pct":   trial.suggest_categorical("profit_target_pct", [0.40, 0.50, 0.60]),
            "stop_loss_multiplier":trial.suggest_categorical("stop_loss_mult", [1.5, 2.0, 3.0]),
            "entry_trigger_pct":   trial.suggest_categorical("entry_trigger_pct", [3.0, 5.0, 7.0]),
            "ivr_min":             trial.suggest_categorical("ivr_min", [50, 60, 65, 70, 75]),
        }
        pnls = simulate_strategy(df_train, spy_train, params, use_ml=False)
        if len(pnls) < 5: return -999.0
        s = pd.Series(pnls)
        return float(s.mean()/(s.std()+1e-9)*math.sqrt(252))

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    log.info(f"Optuna best: {study.best_params} | Sharpe: {study.best_value:.3f}")
    return study.best_params

# ─── MODULE 6: STRATEGY SIMULATOR ───────────────────────────────────────────
def simulate_strategy(df, spy_df, params, use_ml=False, ml_model=None, ml_features=None):
    dte         = params.get("dte_target", 60)
    init_delta  = params.get("initial_delta", 0.20)
    delta_step  = params.get("ladder_delta_step", 0.05)
    profit_pct  = params.get("profit_target_pct", 0.50)
    sl_mult     = params.get("stop_loss_multiplier", 2.0)
    trigger_pct = params.get("entry_trigger_pct", 5.0)
    ivr_min     = params.get("ivr_min", 65)
    ml_thresh   = params.get("ml_confidence_min", 0.62)
    max_rungs   = params.get("max_rungs_per_side", 3)
    macro_filt  = params.get("macro_filter_spy_pct", 3.0)
    delta_br    = params.get("delta_breach_threshold", 0.35)
    dte_roll    = params.get("dte_roll_threshold", 21)

    spy_dict = {r["date"]: r.get("spy_5d_return", 0)
                for _, r in spy_df.iterrows()} if spy_df is not None else {}

    call_rungs, put_rungs, trade_pnls = [], [], []

    for i in range(20, len(df)):
        row = df.iloc[i]
        S, iv, ivr = row["close"], row["iv_est"], row["ivr"]
        date, daily_mv = row["date"], row.get("daily_move_pct", 0)

        # ── Manage existing positions ──────────────────────────────────
        for rung_list in [call_rungs, put_rungs]:
            to_remove = []
            for rung in rung_list:
                days_held = (pd.Timestamp(date) - pd.Timestamp(rung["entry_date"])).days
                T_rem = max((dte - days_held)/365, 0.001)
                mtm = mark_to_market(rung, S, T_rem, iv)
                if mtm["pnl_pct"] >= profit_pct:
                    trade_pnls.append(mtm["pnl_pct"]); to_remove.append(rung)
                elif mtm["pnl_pct"] <= -sl_mult:
                    trade_pnls.append(mtm["pnl_pct"]); to_remove.append(rung)
                elif T_rem*365 <= dte_roll:
                    trade_pnls.append(mtm["pnl_pct"]); to_remove.append(rung)
                elif mtm["current_delta"] > delta_br:
                    roll_credit = bs_price(S, rung["strike"], T_rem+30/365, iv, opt=rung["opt"]) -                                   bs_price(S, rung["strike"], T_rem, iv, opt=rung["opt"])
                    rung["entry_price"] += roll_credit*0.8
                    rung["entry_date"] = date
            for r in to_remove: rung_list.remove(r)

        # ── Entry filters ──────────────────────────────────────────────
        if abs(daily_mv) < trigger_pct: continue
        if ivr < ivr_min: continue
        if abs(spy_dict.get(date, 0)) > macro_filt: continue

        if use_ml and ml_model is not None and ml_features is not None:
            feat_row_df = ml_features[ml_features.index == i]
            if feat_row_df.empty: continue
            enter, conf = get_signal(ml_model, feat_row_df.iloc[0].values, ml_thresh)
            if not enter: continue

        direction = "call" if daily_mv > 0 else "put"
        rung_list = call_rungs if direction == "call" else put_rungs
        if len(rung_list) >= max_rungs: continue

        rung_num = len(rung_list)
        target_delta = max(0.08, init_delta - rung_num*delta_step)
        K = find_strike_for_delta(S, dte/365, iv, target_delta=target_delta, opt=direction)
        ep = bs_price(S, K, dte/365, iv, opt=direction)
        if ep <= 0: continue

        rung_list.append({"opt": direction, "strike": K, "entry_price": ep,
                          "entry_delta": abs(bs_delta(S, K, dte/365, iv, opt=direction)),
                          "entry_iv": iv, "entry_date": date, "rung_num": rung_num+1})

    # Close open at end
    for rl in [call_rungs, put_rungs]:
        for rung in rl:
            dh = (pd.Timestamp(df.iloc[-1]["date"])-pd.Timestamp(rung["entry_date"])).days
            T_rem = max((dte-dh)/365, 0.001)
            mtm = mark_to_market(rung, df.iloc[-1]["close"], T_rem, df.iloc[-1]["iv_est"])
            trade_pnls.append(mtm["pnl_pct"])
    return trade_pnls

# ─── MODULE 7: WALK-FORWARD BACKTEST ────────────────────────────────────────
def walk_forward_backtest(df, spy_df, base_params, n_trials_optuna=150):
    all_results = []
    window_train, window_test, step = 126, 63, 63
    i_start, window_num = 0, 0
    while i_start + window_train + window_test < len(df):
        i_te = i_start + window_train
        df_train = df.iloc[i_start:i_te].reset_index(drop=True)
        df_test  = df.iloc[i_te:i_te+window_test].reset_index(drop=True)
        spy_train = spy_df[(spy_df["date"] >= df_train["date"].min()) &
                           (spy_df["date"] <= df_train["date"].max())]
        spy_test  = spy_df[(spy_df["date"] >= df_test["date"].min()) &
                           (spy_df["date"] <= df_test["date"].max())]
        log.info(f"WFO Window {window_num+1}: train {df_train['date'].min().date()} – {df_train['date'].max().date()}")
        best_params = run_optuna_optimization(df_train, spy_train, n_trials=n_trials_optuna)
        merged = {**base_params, **best_params}
        features_train = build_features(df_train, spy_train)
        labels_df = create_labels(df_train, features_train.index, merged["dte_target"])
        ml_model = None
        if len(labels_df) > 10:
            X = features_train.loc[labels_df.index]
            y = labels_df["label"]
            ml_model = train_signal_model(X.values, y.values)
        features_test = build_features(df_test, spy_test)
        pnls = simulate_strategy(df_test, spy_test, merged,
                                 use_ml=(ml_model is not None),
                                 ml_model=ml_model, ml_features=features_test)
        if pnls:
            s = pd.Series(pnls)
            result = {"window": window_num+1,
                      "test_start": df_test["date"].min().date(),
                      "test_end":   df_test["date"].max().date(),
                      "n_trades":   len(pnls),
                      "win_rate":   round((s>0).mean()*100, 1),
                      "avg_win":    round(s[s>0].mean()*100, 2) if (s>0).any() else 0,
                      "avg_loss":   round(s[s<0].mean()*100, 2) if (s<0).any() else 0,
                      "sharpe":     round(s.mean()/(s.std()+1e-9)*math.sqrt(252), 3),
                      "max_dd":     round((s.cumsum()-s.cumsum().cummax()).min()*100, 2),
                      "best_params": best_params}
            all_results.append(result)
            log.info(f"  n_trades={len(pnls)} WinRate={result['win_rate']}% Sharpe={result['sharpe']}")
        i_start += step; window_num += 1
    return pd.DataFrame(all_results)

# ─── MODULE 8: TRADE DB ──────────────────────────────────────────────────────
class TradeDB:
    def __init__(self, db_path="sndk_ladder.db"):
        self.db_path = db_path; self._init_schema()
    def _init_schema(self):
        con = sqlite3.connect(self.db_path)
        con.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT,
                ticker TEXT, action TEXT, opt_type TEXT, strike REAL,
                entry_price REAL, exit_price REAL, dte_at_entry INTEGER,
                iv_at_entry REAL, delta_at_entry REAL, pnl REAL, pnl_pct REAL,
                ml_confidence REAL, params_snapshot TEXT);
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_timestamp TEXT,
                window_num INTEGER, test_start TEXT, test_end TEXT,
                n_trades INTEGER, win_rate REAL, sharpe REAL,
                max_dd_pct REAL, best_params TEXT);
            CREATE TABLE IF NOT EXISTS daily_snapshot (
                date TEXT PRIMARY KEY, sndk_close REAL, iv_est REAL, ivr REAL,
                n_open_calls INTEGER, n_open_puts INTEGER, portfolio_delta REAL);
        """); con.commit(); con.close()
    def log_trade(self, action, opt_type, strike, entry_price, exit_price,
                  dte, iv, delta, pnl, pnl_pct, ml_conf=None, params=None):
        con = sqlite3.connect(self.db_path)
        con.execute("""INSERT INTO trades (timestamp,ticker,action,opt_type,strike,
            entry_price,exit_price,dte_at_entry,iv_at_entry,delta_at_entry,pnl,
            pnl_pct,ml_confidence,params_snapshot) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(),"SNDK",action,opt_type,strike,entry_price,
             exit_price,dte,iv,delta,pnl,pnl_pct,ml_conf,json.dumps(params or {})))
        con.commit(); con.close()
    def log_backtest_window(self, run_ts, r):
        con = sqlite3.connect(self.db_path)
        con.execute("""INSERT INTO backtest_results (run_timestamp,window_num,test_start,
            test_end,n_trades,win_rate,sharpe,max_dd_pct,best_params) VALUES (?,?,?,?,?,?,?,?,?)""",
            (run_ts,r["window"],str(r.get("test_start","")),str(r.get("test_end","")),
             r["n_trades"],r["win_rate"],r["sharpe"],r.get("max_dd",0),json.dumps(r.get("best_params",{}))))
        con.commit(); con.close()

# ─── MODULE 9: ALERTS ────────────────────────────────────────────────────────
def send_telegram(msg, token, chat_id):
    import requests
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e: log.error(f"Telegram error: {e}")

def fmt_entry(rung, date, conf):
    return (f"SNDK LADDER ENTRY\n{date} | ML Conf: {conf:.2f}\n"
            f"SELL {rung['opt'].upper()} K=${rung['strike']:,.0f}\n"
            f"Prem=${rung['entry_price']:.1f} | Delta={rung['entry_delta']:.3f} | IV={rung['entry_iv']*100:.0f}%")

def fmt_exit(rung, pnl_pct, reason):
    return (f"SNDK LADDER EXIT ({reason})\n"
            f"{rung['opt'].upper()} K=${rung['strike']:,.0f} | PnL={pnl_pct*100:.1f}%")

# ─── MODULE 10: LIVE ALPACA ENGINE ───────────────────────────────────────────
def get_alpaca_client(api_key, secret, paper=True):
    from alpaca.trading.client import TradingClient
    return TradingClient(api_key, secret, paper=paper)

def get_nearest_contract(client, symbol, strike, expiry_str, opt_type="call"):
    from alpaca.trading.requests import GetOptionContractsRequest
    req = GetOptionContractsRequest(underlying_symbols=[symbol],
        expiration_date=expiry_str, type=opt_type,
        strike_price_gte=str(strike-50), strike_price_lte=str(strike+50))
    contracts = client.get_option_contracts(req)
    if contracts and contracts.option_contracts:
        return min(contracts.option_contracts, key=lambda c: abs(float(c.strike_price)-strike))
    return None

# ─── MODULE 11: SCHEDULER ────────────────────────────────────────────────────
def daily_signal_loop(config):
    import yfinance as yf, pickle
    df = fetch_price_history(config["ticker"])
    df = estimate_iv_history(df)
    spy = fetch_spy_history()
    features = build_features(df, spy)
    try:
        with open("ml_model.pkl", "rb") as f: ml_model = pickle.load(f)
    except FileNotFoundError: ml_model = None
    latest = df.iloc[-1]
    S, iv, ivr, daily_mv = latest["close"], latest["iv_est"], latest["ivr"], latest.get("daily_move_pct", 0)
    date = latest["date"]
    db = TradeDB(config["db_path"])
    if abs(daily_mv) >= config["entry_trigger_pct"] and ivr >= config["ivr_min"]:
        feat_row = features.iloc[-1].values
        enter, conf = get_signal(ml_model, feat_row, config["ml_confidence_min"]) if ml_model else (True, 0.0)
        if enter:
            direction = "call" if daily_mv>0 else "put"
            K = find_strike_for_delta(S, config["dte_target"]/365, iv, config["initial_delta"], opt=direction)
            ep = bs_price(S, K, config["dte_target"]/365, iv, opt=direction)
            delta = abs(bs_delta(S, K, config["dte_target"]/365, iv, opt=direction))
            rung = {"opt": direction, "strike": K, "entry_price": ep,
                    "entry_delta": delta, "entry_iv": iv, "entry_date": date, "rung_num": 1}
            alert = fmt_entry(rung, date, conf)
            log.info(alert)
            if config.get("telegram_token") and config.get("telegram_chat_id"):
                send_telegram(alert, config["telegram_token"], config["telegram_chat_id"])
            db.log_trade("ENTRY", direction, K, ep, None, config["dte_target"], iv, delta, 0, 0, conf, config)

def schedule_system(config):
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    s = BlockingScheduler(timezone="America/New_York")
    s.add_job(daily_signal_loop, args=[config],
              trigger=CronTrigger(day_of_week="mon-fri", hour=16, minute=5))
    log.info("Scheduler running. Fires 4:05 PM ET Mon-Fri.")
    s.start()

# ─── MODULE 12: METRICS ──────────────────────────────────────────────────────
def compute_metrics(pnls):
    if not pnls: return {}
    s = pd.Series(pnls)
    w, l = s[s>0], s[s<0]
    pf = w.sum()/abs(l.sum()) if len(l)>0 else float("inf")
    sh = s.mean()/(s.std()+1e-9)*math.sqrt(252)
    cum = (1+s).cumprod()
    dd = (cum/cum.cummax()-1).min()
    kelly = (len(w)/len(s)) - (1-len(w)/len(s))/(w.mean()/(abs(l.mean())+1e-9)+1e-9)
    return {"Trades": len(s), "WinRate": f"{len(w)/len(s)*100:.1f}%",
            "AvgWin": f"{w.mean()*100:.1f}%" if len(w)>0 else "N/A",
            "AvgLoss": f"{l.mean()*100:.1f}%" if len(l)>0 else "N/A",
            "ProfitFactor": f"{pf:.2f}", "Sharpe": f"{sh:.3f}",
            "MaxDD": f"{dd*100:.2f}%", "Kelly_25pct": f"{kelly*25:.1f}% of capital"}

# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import yaml
    cfg = yaml.safe_load(YAML_CONFIG)
    log.info("=== SNDK LADDER STRATEGY — 1-YEAR WALK-FORWARD BACKTEST ===")
    df   = fetch_price_history("SNDK", cfg["backtest_start"], cfg["backtest_end"])
    spy  = fetch_spy_history(cfg["backtest_start"], cfg["backtest_end"])
    df   = estimate_iv_history(df)
    df   = pd.merge(df, spy, on="date", how="left")
    log.info(f"Data: {len(df)} days | Price ${df['close'].min():.0f} – ${df['close'].max():.0f}")
    results = walk_forward_backtest(df, spy, cfg, n_trials_optuna=150)
    print("\n=== WALK-FORWARD RESULTS ===")
    print(results[["window","test_start","test_end","n_trades","win_rate","sharpe","max_dd"]].to_string())
    print(f"\nMean Sharpe: {results['sharpe'].mean():.3f}")
    print(f"Mean Win Rate: {results['win_rate'].mean():.1f}%")
    db = TradeDB(cfg["db_path"])
    for _, row in results.iterrows():
        db.log_backtest_window(datetime.now().isoformat(), row.to_dict())
    log.info("Backtest complete. Results logged to SQLite.")
    # Uncomment to start live trading:
    # schedule_system(cfg)
