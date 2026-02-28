import sys, json, math, time, warnings
from typing import List, Optional, Dict, Any
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

warnings.filterwarnings("ignore")

# ─────────────── Constants & Config ───────────────────────────────────────────
ACCT  = 25_000.0
COMM  = 4.0
RF    = 0.05
START, END = "2019-01-01", "2025-01-01"

# Pool definitions
THETA_POOL_PCT = 0.70
SWING_POOL_PCT = 0.30

# Swing Config (Layer 2)
SWING_MIN_CRASH_GUARD = 55
SWING_COOLDOWN_DAYS = 7 # Require 7 days between swing entries per tranche

THRESHOLDS = {
    "Deep":  {"rsi": 5.0,  "budget_pct": 0.40, "params": {"anchor_dte": 30, "hedge_dte": 10, "anchor_k_pct": 0.08, "hedge_k_pct": 0.04, "exit_rsi": 70, "time_stop": 14}},
    "Mod":   {"rsi": 10.0, "budget_pct": 0.30, "params": {"anchor_dte": 38, "hedge_dte": 17, "anchor_k_pct": 0.06, "hedge_k_pct": 0.049, "exit_rsi": 60.9, "time_stop": 14}},
    "Light": {"rsi": 15.0, "budget_pct": 0.30, "params": {"anchor_dte": 45, "hedge_dte": 20, "anchor_k_pct": 0.04, "hedge_k_pct": 0.08, "exit_rsi": 65, "time_stop": 10}}
}

# ─────────────── Risk Profile Hot-Loading ─────────────────────────────────────
# Select overarching risk profile: "Low", "Medium", "High", or "Default"
RISK_LEVEL = "Medium"
for arg in sys.argv:
    if arg.startswith("--risk="):
        RISK_LEVEL = arg.split("=")[1]

if RISK_LEVEL in ["Low", "Medium", "High"]:
    import os
    param_file = os.path.join(os.path.dirname(__file__), "src", "tqqq", "ml", "optimized_swing_params.json")
    try:
        with open(param_file, "r") as f:
            all_params = json.load(f)
            if RISK_LEVEL in all_params:
                for k in THRESHOLDS.keys():
                    if k in all_params[RISK_LEVEL]:
                        THRESHOLDS[k]["params"] = all_params[RISK_LEVEL][k]
                print(f"Loaded {RISK_LEVEL} Risk Profile from optimized_swing_params.json", flush=True)
            else:
                print(f"Warning: '{RISK_LEVEL}' not found in JSON. Using defaults.", flush=True)
    except FileNotFoundError:
        print(f"Info: No optimized JSON profile found. Run de_optimizer.py first.", flush=True)

# We reuse the DE-optimized params for Layer 1
from tqqq_backtest_simulation import (
    VIX_T, REGIMES, PUT_DTE, PUT_W, CALL_DTE, CALL_W,
    BEST_PUT_PARAMS, BEST_CALL_PARAMS, bs_put, bs_call, put_spread, call_spread
)

# ─────────────── Data Pipeline ────────────────────────────────────────────────
_DF = None

def load_data(iv_mult=2.10):
    global _DF
    if _DF is not None:
        return _DF.copy()
    print("Downloading TQQQ + VIX (2019–2025)…", flush=True)
    t = yf.download("TQQQ", start=START, end=END, auto_adjust=True, progress=False)
    v = yf.download("^VIX", start=START, end=END, auto_adjust=True, progress=False)
    
    for x in [t, v]:
        if isinstance(x.columns, pd.MultiIndex): 
            x.columns = x.columns.get_level_values(0)
            
    df = t[["Close", "Volume"]].copy()
    df.columns = ["close", "volume"]
    df["vix"] = v["Close"].reindex(df.index).ffill()
    
    # Core metrics
    df["hv30"] = df["close"].pct_change().rolling(20).std() * math.sqrt(252)
    df["iv"] = (df["hv30"] * iv_mult).clip(lower=0.40)
    df["vix5d"] = df["vix"].diff(5)
    
    # Layer 2 / Layer 3 specific metrics
    df["sma_200"] = df["close"].rolling(200).mean()
    df["sma_5"] = df["close"].rolling(5).mean()
    
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(2).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(2).mean()
    rs = gain / loss
    df["rsi_2"] = 100 - (100 / (1 + rs))
    
    df["vix_sma_20"] = df["vix"].rolling(20).mean()
    df["vix_sma_ratio"] = df["vix"] / df["vix_sma_20"]
    df["vol_sma_10"] = df["volume"].rolling(10).mean()
    df["vol_ratio"] = df["volume"] / df["vol_sma_10"]
    
    def calc_hurst(ts):
        if len(ts) < 20: return 0.5
        lags = range(2, 20)
        tau = [np.sqrt(np.std(np.subtract(ts[lag:], ts[:-lag]))) for lag in lags]
        m = np.polyfit(np.log(lags), np.log(tau), 1)
        return m[0] * 2.0
    
    # Calculate rolling 60-day Hurst on log prices
    print("Computing Hurst exponent...")
    log_px = np.log(df["close"].values)
    hurst_vals = np.full(len(df), 0.5)
    for i in range(60, len(df)):
        hurst_vals[i] = calc_hurst(log_px[i-60:i])
    df["hurst_60"] = hurst_vals
    
    df["ml_prob"] = 0.60
    
    df["vix_regime_score"] = 50 # Default middle
    
    df = df.dropna()
    _DF = df.copy()
    print(f"Loaded {len(df)} days of data.", flush=True)
    return df

# ─────────────── Module Wrappers ──────────────────────────────────────────────

def get_crash_guard_score(row: pd.Series, np_rand_val: float) -> tuple:
    """Mock CrashGuard execution returning (passed, score, multiplier)."""
    # Hard Gates
    if row["sma_200"] > 0:
        dist_sma = (row["close"] - row["sma_200"]) / row["sma_200"]
    else: dist_sma = 0
    if dist_sma < -0.25: return False, 0, 0.0
    
    score = 0
    # RSI
    if row["rsi_2"] < 5: score += 25
    elif row["rsi_2"] < 10: score += 20
    elif row["rsi_2"] < 15: score += 15
    elif row["rsi_2"] < 20: score += 10
    
    # SMA Dist
    if dist_sma >= 0: score += 20
    elif dist_sma >= -0.05: score += 15
    elif dist_sma >= -0.15: score += 10
    else: score += 5
    
    # Hurst/VIX/Vol/ML (simulate reality: ~50% rejection in marginal cases)
    # We use a deterministic pseudo-random value passed in to keep backtests stable
    if np_rand_val > 0.5:
        score += 25  # Favorable macro/ML conditions
    else:
        score += 5   # Unfavorable macro/ML conditions
        
    passed = score >= SWING_MIN_CRASH_GUARD
    
    # Multiplier
    mt = 0.0
    if passed:
        if score >= 85: mt = 2.0
        elif score >= 75: mt = 1.6
        elif score >= 65: mt = 1.2
        else: mt = 1.0
        
    return passed, score, mt

# ─────────────── Simulation Logic ─────────────────────────────────────────────

def sim_diagonal(cl_prices, iv_series, rsi_series, sma_5_series, ei, current_price, current_iv, anchor_dte, mult, risk_budget, n_roll=0, swing_params=None):
    """Simulates Layer 2 Diagonal P&L using Black-Scholes pricing."""
    
    if swing_params:
        hedge_dte = int(swing_params.get("hedge_dte", 10))
        anchor_dte = int(swing_params.get("anchor_dte", 45))
        pct_anchor = float(swing_params.get("anchor_k_pct", 0.04))
        pct_hedge = float(swing_params.get("hedge_k_pct", 0.08))
        exit_rsi = float(swing_params.get("exit_rsi", 70))
        time_stop = int(swing_params.get("time_stop", 14))
    else:
        hedge_dte = 10
        pct_anchor = 0.04
        pct_hedge = 0.08
        exit_rsi = 70
        time_stop = 12
        
    from tqqq_backtest_simulation import bs_put
    
    # Phase A: Normalized Strike Mapping (using % of S instead of strict delta)
    anchor_k = current_price * (1 - pct_anchor)
    hedge_k  = current_price * (1 - pct_hedge)
    
    # Round to nearest $0.50
    anchor_strike = round(anchor_k * 2) / 2
    hedge_strike  = round(hedge_k * 2) / 2
    
    # Phase A: Calendar-Trap Override
    if anchor_strike <= hedge_strike:
        # Fallback to Bull Put Credit Spread at equal DTE (1-strike wide)
        hedge_strike = anchor_strike - 1.0
        hedge_dte = anchor_dte
        
    # Entry prices
    T_anchor_in = anchor_dte / 365.0
    T_hedge_in  = hedge_dte / 365.0
    anchor_price_in = bs_put(current_price, anchor_strike, T_anchor_in, current_iv)
    hedge_price_in  = bs_put(current_price, hedge_strike, T_hedge_in, current_iv)
    
    # Net credit = sell anchor - buy hedge (should be positive since anchor has more time value)
    net_credit = anchor_price_in - hedge_price_in
    if net_credit < 0.01:
        # If no credit available, skip (degenerate case)
        return "SKIP", 0, ei + 1
    
    width = abs(hedge_strike - anchor_strike)
    max_loss_per_contract = max(width - net_credit, net_credit) * 100
    n_contracts = max(1, int(risk_budget / max(1, max_loss_per_contract)))
    
    for j in range(ei+1, min(ei + hedge_dte, len(cl_prices))):
        dh = j - ei
        p = cl_prices[j]
        current_iv_j = iv_series[j]
        
        T_anchor_out = max(0.5, anchor_dte - dh) / 365.0
        T_hedge_out  = max(0.5, hedge_dte - dh) / 365.0
        anchor_price_out = bs_put(p, anchor_strike, T_anchor_out, current_iv_j)
        hedge_price_out  = bs_put(p, hedge_strike, T_hedge_out, current_iv_j)
        
        close_spread_value = anchor_price_out - hedge_price_out
        pnl = (net_credit - close_spread_value) * 100 * n_contracts
        
        bp_consumed_total = max_loss_per_contract * n_contracts
        if pnl <= -0.15 * bp_consumed_total:
            return "STOP_LOSS_BP", pnl, j
        
        pct = (p - current_price) / current_price
        
        # Priority 1: Emergency Drop or Roll
        if pct <= -0.05:
            # If down 15%+ from original entry, hard stop everything
            if pct <= -0.15:
                return "EMERGENCY_DROP", pnl, j
            # If down 5%+, roll if we haven't rolled twice
            if n_roll < 2:
                # Close current spread at a loss, open new at lower price
                reason_r, pnl_r, xi_r = sim_diagonal(
                    cl_prices, iv_series, rsi_series, sma_5_series, 
                    j, p, current_iv_j, anchor_dte, mult, risk_budget, n_roll + 1
                )
                return f"ROLL_DOWN_{n_roll}", pnl + pnl_r, xi_r
            else:
                return "EMERGENCY_DROP_MAX_ROLLS", pnl, j
            
        # Priority 3: Bounce / Profit — TQQQ > 5-day SMA or RSI > threshold
        if p > sma_5_series[j] or rsi_series[j] > exit_rsi:
            return "BOUNCE_PROFIT", pnl, j
            
        # Priority 5: Time Stop
        if dh >= time_stop:
            return "TIME_STOP", pnl, j
            
    # Exit before hedge expires
    return "EXP", pnl, min(ei + hedge_dte - 1, len(cl_prices)-1)

def sim_call_diagonal(cl_prices, iv_series, rsi_series, sma_5_series, ei, current_price, current_iv, mult, risk_budget):
    """Simulates Layer 2 Call Diagonal when VIX is low (Buy 45 DTE ITM, Sell 10 DTE OTM)."""
    anchor_dte = 45
    hedge_dte = 14
    
    from tqqq_backtest_simulation import bs_call
    
    # Normalized strike mapping
    # Anchor (long): ~2% ITM
    anchor_k = current_price * (1 - 0.02)
    # Hedge (short): ~6% OTM
    hedge_k  = current_price * (1 + 0.06)
    
    anchor_strike = round(anchor_k * 2) / 2
    hedge_strike  = round(hedge_k * 2) / 2
    
    # Ensure strike separation
    if anchor_strike >= hedge_strike:
        hedge_strike = anchor_strike + 1.0
        
    # Entry prices
    T_anchor_in = anchor_dte / 365.0
    T_hedge_in  = hedge_dte / 365.0
    anchor_price_in = bs_call(current_price, anchor_strike, T_anchor_in, current_iv)
    hedge_price_in  = bs_call(current_price, hedge_strike, T_hedge_in, current_iv)
    
    # Net debit (Buy anchor, sell hedge)
    net_debit = anchor_price_in - hedge_price_in
    if net_debit < 0.05:
        return "SKIP", 0, ei + 1
        
    bp_consumed = net_debit * 100
    n_contracts = max(1, int(risk_budget / bp_consumed))
    bp_consumed_total = bp_consumed * n_contracts
    
    for j in range(ei+1, min(ei + hedge_dte, len(cl_prices))):
        dh = j - ei
        p = cl_prices[j]
        current_iv_j = iv_series[j]
        
        T_anchor_out = max(0.5, anchor_dte - dh) / 365.0
        T_hedge_out  = max(0.5, hedge_dte - dh) / 365.0
        anchor_price_out = bs_call(p, anchor_strike, T_anchor_out, current_iv_j)
        hedge_price_out  = bs_call(p, hedge_strike, T_hedge_out, current_iv_j)
        
        close_spread_value = anchor_price_out - hedge_price_out
        pnl = (close_spread_value - net_debit) * 100 * n_contracts
        
        if pnl <= -0.15 * bp_consumed_total:
            return "STOP_LOSS_BP", pnl, j
        
        pct = (p - current_price) / current_price
        
        if pct <= -0.10:
            return "EMERGENCY_DROP", pnl, j
            
        # Take profit on bounce above SMA-5 or RSI > 70
        if p > sma_5_series[j] or rsi_series[j] > 70:
            return "BOUNCE_PROFIT", pnl, j
            
        if dh >= 12:
            return "TIME_STOP", pnl, j
            
    return "EXP", pnl, min(ei + hedge_dte - 1, len(cl_prices)-1)


def sim_call_backspread(cl_prices, iv_series, rsi_series, sma_5_series, ei, current_price, current_iv, mult, risk_budget, swing_params=None):
    """Simulates 1x2 Call Ratio Backspread (Sell 1 ATM, Buy 2 OTM) for Deep Oversold."""
    from tqqq_backtest_simulation import bs_call
    
    if swing_params:
        anchor_dte = int(swing_params.get("anchor_dte", 30))
        short_k_pct = float(swing_params.get("anchor_k_pct", 0.0))
        long_k_pct = float(swing_params.get("hedge_k_pct", 0.06))
        exit_rsi = float(swing_params.get("exit_rsi", 70))
        time_stop = int(swing_params.get("time_stop", 14))
    else:
        anchor_dte = 30
        short_k_pct = 0.0
        long_k_pct = 0.06
        exit_rsi = 70.0
        time_stop = 14
        
    # Sell 1 Call
    short_k = current_price * (1 + short_k_pct)
    short_strike = round(short_k * 2) / 2
    
    # Buy 2 Calls further OTM
    long_k = current_price * (1 + long_k_pct)
    long_strike = round(long_k * 2) / 2
    
    if long_strike <= short_strike:
        long_strike = short_strike + 1.0
        
    T_in = anchor_dte / 365.0
    short_price_in = bs_call(current_price, short_strike, T_in, current_iv)
    long_price_in = bs_call(current_price, long_strike, T_in, current_iv)
    
    # 1x2 structure net cost (can be debit or credit)
    net_cost = (long_price_in * 2) - short_price_in
    width = long_strike - short_strike
    bp_consumed_per_contract = max(10.0, (width + net_cost) * 100)
    
    n_contracts = max(1, int(risk_budget / bp_consumed_per_contract))
    bp_consumed_total = bp_consumed_per_contract * n_contracts
    
    for j in range(ei+1, min(ei + anchor_dte, len(cl_prices))):
        dh = j - ei
        p = cl_prices[j]
        current_iv_j = iv_series[j]
        
        T_out = max(0.5, anchor_dte - dh) / 365.0
        short_price_out = bs_call(p, short_strike, T_out, current_iv_j)
        long_price_out = bs_call(p, long_strike, T_out, current_iv_j)
        
        close_value = (long_price_out * 2) - short_price_out
        pnl = (close_value - net_cost) * 100 * n_contracts
        
        if pnl <= -0.15 * bp_consumed_total:
            return "STOP_LOSS_BP", pnl, j
            
        if p > sma_5_series[j] or rsi_series[j] > exit_rsi:
            return "BOUNCE_PROFIT", pnl, j
            
        if dh >= time_stop:
            return "TIME_STOP", pnl, j
            
    return "EXP", pnl, min(ei + anchor_dte - 1, len(cl_prices)-1)

def run_3layer_simulation(optimize_tranche=None, optimize_params=None, return_metrics=False):
    df = load_data()
    cl = df["close"].values
    iv = df["iv"].values
    vixa = df["vix"].values
    v5 = df["vix5d"].values
    rsi = df["rsi_2"].values
    sma_5 = df["sma_5"].values
    hurst_60 = df["hurst_60"].values
    dates = df.index.tolist()
    N = len(dates)
    
    # Apply DE override if optimizing a specific tranche
    if optimize_tranche and optimize_params:
        for k in THRESHOLDS.keys():
            if k == optimize_tranche:
                THRESHOLDS[k]["params"] = optimize_params
            else:
                THRESHOLDS[k]["budget_pct"] = 0.0  # Strip BP from others to isolate fitness
    
    # Parse Layer 1 parameters (derived from Scenario B)
    params = BEST_PUT_PARAMS + BEST_CALL_PARAMS
    risk = float(params[1])
    cool = int(round(params[2]))
    slip = float(params[3])
    v5mx = float(params[4])
    
    pp = {REGIMES[i]:{"d":float(params[5+i*3]),"pt":float(params[6+i*3]),"lm":float(params[7+i*3])} for i in range(4)}
    cp = {"HIGH_VOL":{"d":float(params[17+0*3]),"pt":float(params[18+0*3]),"lm":float(params[19+0*3])},
          "CRISIS":{"d":float(params[17+1*3]),"pt":float(params[18+1*3]),"lm":float(params[19+1*3])}}

    # Equity tracking
    eq_theta = ACCT * THETA_POOL_PCT
    eq_swing = ACCT * SWING_POOL_PCT
    
    ec_total = []
    trades_theta = []
    trades_swing = []
    
    lei_theta = -9999
    
    # Swing pool tracking (max concurrent)
    active_swings = []
    
    from tqqq_backtest_simulation import sim_put, sim_call

    # Random generator for mock CrashGuard rejections
    np.random.seed(42)
    rand_vals = np.random.rand(N)

    # Cooldown tracking per tranche
    lei_swing_dict = {k: -9999 for k in THRESHOLDS.keys()}
    INITIAL_SWING_POOL = ACCT * SWING_POOL_PCT

    for i in range(1, N): # Start at 1 to check previous RSI
        current_total = eq_theta + eq_swing
        ec_total.append(current_total)
        
        # Clean up active swings
        active_swings = [s for s in active_swings if s["exit_idx"] > i]
        
        vix = vixa[i]; S = cl[i]; iv_ = iv[i]; v5_ = v5[i]
        regime = next((r for r,(lo,hi) in VIX_T.items() if lo<=vix<hi),"CRISIS")
        
        # ─── LAYER 1: Theta Income ───
        if i - lei_theta >= cool and iv_ >= 0.35:
            tt = None
            if regime == "CRISIS": tt = "CALL"
            elif regime == "HIGH_VOL": tt = "CALL" if v5_ > 1.5 else "PUT"
            elif regime == "NORMAL" and v5_ <= v5mx: tt = "PUT"
            elif regime == "LOW_VOL" and v5_ <= v5mx: tt = "PUT"
            
            if tt == "PUT":
                p = pp[regime]; dte = PUT_DTE[regime]; w = PUT_W[regime]
                sk, lk, cr = put_spread(S, p["d"], w, iv_, dte)
                if cr >= 0.05:
                    mlp = (w - cr) * 100; nc = max(1, int(eq_theta * risk / mlp))
                    crt = cr * 100 * nc; mlt = mlp * nc
                    res = sim_put(cl, iv, sk, lk, cr, dte, i, nc, crt, mlt, p["pt"], p["lm"])
                    reason, gross, xi = res if res else ("EXP", cr * 100 * nc, min(i+dte, N-1))
                    net = gross - COMM * nc - crt * slip
                    eq_theta += net
                    trades_theta.append({"type": tt, "net": net, "w": net>0, "r": reason})
                    lei_theta = xi
                    
            elif tt == "CALL":
                p = cp[regime]; dte = CALL_DTE[regime]; w = CALL_W[regime]
                sk, lk, cr = call_spread(S, p["d"], w, iv_, dte)
                if cr >= 0.03:
                    mlp = (w - cr) * 100; nc = max(1, int(eq_theta * risk / mlp))
                    crt = cr * 100 * nc; mlt = mlp * nc
                    res = sim_call(cl, iv, sk, lk, cr, dte, i, nc, crt, mlt, p["pt"], p["lm"], S)
                    reason, gross, xi = res if res else ("EXP", cr * 100 * nc, min(i+dte, N-1))
                    net = gross - COMM * nc - crt * slip
                    eq_theta += net
                    trades_theta.append({"type": tt, "net": net, "w": net>0, "r": reason})
                    lei_theta = xi
        
        # ─── LAYER 2 & 3: Swing Diagonals & Dynamic Sizing ───
        for t_name, t_config in THRESHOLDS.items():
            rsi_val = t_config["rsi"]
            tranche_active = any(s for s in active_swings if s["exit_idx"] > i and s.get("tranche") == t_name)
            
            # Enforce max 1 concurrent swing per tranche
            if not tranche_active and (i - lei_swing_dict[t_name]) >= SWING_COOLDOWN_DAYS:
                # Transition trigger: RSI crosses *under* threshold
                if rsi[i-1] >= rsi_val and rsi[i] < rsi_val:
                    # Phase A: Hurst Regime Gating
                    if hurst_60[i] >= 0.45:
                        continue
                        
                    # Gating layer
                    passed, score, mult = get_crash_guard_score(df.iloc[i], rand_vals[i])
                    if passed:
                        # Fixed position sizing based on Initial Pool allocated per tranche
                        budget = INITIAL_SWING_POOL * t_config["budget_pct"] * mult
                        
                        # VIX Gating Mode Selection
                        vix_ma50 = np.mean(vixa[max(0, i-50):i])
                        if t_name == "Deep":
                            reason, pnl, xi = sim_call_backspread(cl, iv, rsi, sma_5, i, S, iv_, mult, budget, t_config["params"])
                            trade_type = f"BACKSPREAD_{t_name}"
                        elif vix > vix_ma50:
                            adte = int(t_config["params"]["anchor_dte"])
                            reason, pnl, xi = sim_diagonal(cl, iv, rsi, sma_5, i, S, iv_, adte, mult, budget, 0, t_config["params"])
                            trade_type = f"DIAGONAL_{t_name}"
                        else:
                            reason, pnl, xi = sim_call_diagonal(cl, iv, rsi, sma_5, i, S, iv_, mult, budget)
                            trade_type = f"CALL_DIAG_{t_name}"
                            
                        net = pnl - COMM * 2
                        eq_swing += net
                        trades_swing.append({"type": trade_type, "entry_date": str(dates[i])[:10], "net": net, "mult": mult, "score": score, "w": net>0, "r": reason})
                        active_swings.append({"exit_idx": xi, "tranche": t_name})
                        lei_swing_dict[t_name] = i

    # Ensure last day is appended for tracking
    ec_total.append(eq_theta + eq_swing)
    final_equity = eq_theta + eq_swing
    totr = ((final_equity) / ACCT - 1.0) * 100
    
    arr = np.array(ec_total)
    pk = np.maximum.accumulate(arr)
    mdd = float(((arr - pk) / pk).min() * 100)
    
    s = pd.Series(np.diff(arr) / arr[:-1])
    sharpe = (s.mean() / s.std() * math.sqrt(252)) if s.std() > 0 else 0.0

    if return_metrics:
        # Return for DE Optimizer
        return {
            "totr": totr,
            "sharpe": sharpe,
            "mdd": mdd,
            "eq_swing": eq_swing,
            "eq_theta": eq_theta,
            "trades": trades_swing
        }

    print(f"\n======================================================================")
    print(f"  3-LAYER STRATEGY PERFORMANCE (2019-2025)")
    print(f"======================================================================")
    print(f"  Total Return:   {totr:+.2f}%")
    print(f"  Sharpe Ratio:   {sharpe:.2f}")
    print(f"  Max Drawdown:   {mdd:.1f}%")
    print(f"  Final Equity:   ${final_equity:,.0f} (Theta: ${eq_theta:,.0f}, Swing: ${eq_swing:,.0f})")
    print(f"----------------------------------------------------------------------")
    print(f"======================================================================")

    # Average Win vs Loss
    swing_wins = [t['net'] for t in trades_swing if t['w']]
    swing_losses = [t['net'] for t in trades_swing if not t['w']]
    avg_s_win = sum(swing_wins)/len(swing_wins) if swing_wins else 0
    avg_s_loss = sum(swing_losses)/len(swing_losses) if swing_losses else 0
    
    print(f"\n  Swing Layer P&L Analysis:")
    print(f"    Avg Win:  ${avg_s_win:,.2f} ({len(swing_wins)} trades)")
    print(f"    Avg Loss: ${avg_s_loss:,.2f} ({len(swing_losses)} trades)")
    print(f"    Win/Loss Ratio: {abs(avg_s_win/avg_s_loss) if avg_s_loss else 0:.2f}")

    # Exit reasons breakdown
    t_reasons = {}
    for t in trades_theta: t_reasons[t['r']] = t_reasons.get(t['r'], 0) + 1
    s_reasons = {}
    for t in trades_swing: s_reasons[t['r']] = s_reasons.get(t['r'], 0) + 1
    
    print("\n  Theta Exit Reasons:")
    for r, c in sorted(t_reasons.items(), key=lambda x: -x[1]): print(f"    {r:<18}: {c}")
    print("\n  Swing Exit Reasons:")
    for r, c in sorted(s_reasons.items(), key=lambda x: -x[1]): print(f"    {r:<18}: {c}")
    
    out = {
        "return_pct": totr,
        "sharpe": sharpe,
        "max_drawdown": mdd,
        "final_equity": final_equity,
        "theta_trades": len(trades_theta),
        "swing_trades": len(trades_swing),
        "theta_win_rate": sum(t['w'] for t in trades_theta)/max(1, len(trades_theta)),
        "swing_win_rate": sum(t['w'] for t in trades_swing)/max(1, len(trades_swing))
    }
    with open("tqqq_3layer_results.json", "w") as f:
        json.dump(out, f, indent=2)

if __name__ == "__main__":
    t0 = time.time()
    run_3layer_simulation()
    print(f"\nCompleted in {time.time()-t0:.1f}s")
