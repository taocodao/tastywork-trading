import yfinance as yf
import pandas as pd
import numpy as np
from datetime import timedelta
import sys

from src.qqq_leaps.leaps_feature_engineering import build_leaps_features
from src.qqq_leaps.regime_classifier import LeapsRegimeClassifier
from src.qqq_leaps.entry_classifier_v2 import LeapsEntryClassifierV2
from src.qqq_leaps.config import QQQLeapsConfig

# Import from the existing backtest script for the PMCC evaluation logic
sys.path.append("qqq-leaps/leaps rule set")
from qqq_pmcc_backtest_v2 import (  # type: ignore
    Regime, LeapsStatus, PmccStatus, DrawdownTier, drawdown_guard, manage_pmcc, 
    bs_call_price, bs_delta, bs_extrinsic, find_strike_by_delta, slippage_pct, bci_initialization_check, size_position, Position, compute_metrics
)

print("Downloading data...")
qqq = yf.download("QQQ", start="2018-01-01", end="2026-04-01", auto_adjust=True, progress=False)
vix = yf.download("^VIX", start="2018-01-01", end="2026-04-01", progress=False)
vix3m = yf.download("^VIX3M", start="2018-01-01", end="2026-04-01", progress=False)
irx = yf.download("^IRX", start="2018-01-01", end="2026-04-01", progress=False)

def _sq(df):
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
    return df

qqq = _sq(qqq); vix = _sq(vix); vix3m = _sq(vix3m); irx = _sq(irx)

qqq_close = qqq["Close"].squeeze()
qqq_open  = qqq["Open"].squeeze()
vix_s     = vix["Close"].reindex(qqq_close.index).ffill().squeeze()
vix3m_s   = vix3m["Close"].reindex(qqq_close.index).ffill().squeeze()
rf_s      = (irx["Close"] / 100.0).reindex(qqq_close.index).ffill().squeeze()

print("Building features...")
master = build_leaps_features(qqq_close, qqq_open, vix_s, vix3m_s, rf_s)

cfg = QQQLeapsConfig()
regime_clf = LeapsRegimeClassifier(cfg)
master = regime_clf.apply_to_master(master)

# Fix missing column prev_close
master["prev_close"] = master["qqq_close"].shift(1)

ml_clf = LeapsEntryClassifierV2()
ml_loaded = ml_clf.load()
print(f"ML Model loaded: {ml_loaded}")

# Slice to 2019-2026
df = master.loc["2019-01-01":].copy()
df = df.reset_index() # make date a column
if "Date" in df.columns:
    df = df.rename(columns={"Date": "date"})
elif "index" in df.columns:
    df = df.rename(columns={"index": "date"})

results = []
positions = []
cash = 25_000.0
virtual_nav = 25_000.0
r = 0.045
max_positions = 3

for idx, row in df.iterrows():
    date    = row["date"]
    S       = row["qqq_close"]
    S_open  = row["qqq_open"]
    vix     = row["vix"]
    sigma   = vix / 100.0   
    q52low  = row.get("qqq_52w_low", S)
    regime_str = row.get("leaps_regime", "CHOPPY")
    if regime_str == "BEAR_SMA_FORCED":
        regime = Regime.BEAR_SMA_FORCED
    else:
        try:
            regime = Regime(regime_str)
        except ValueError:
            regime = Regime.CHOPPY

    gap_pct = row["gap_pct"]
    slip = slippage_pct(vix)
    
    pmcc_income_today = 0.0
    
    # ────── MORNING EXIT SCAN ──────
    active_positions = []
    for pos in positions:
        dg_morning = drawdown_guard(pos.leaps_delta, pos.leaps_dte, S_open, q52low)
        if dg_morning == DrawdownTier.TIER3_EMERGENCY_EXIT:
            T_rem = pos.leaps_dte / 365.0
            leaps_val = bs_call_price(S_open, pos.leaps_strike, T_rem, r, sigma)
            leaps_exit = leaps_val * (1 - 0.04) * 100 * pos.leaps_contracts
            cash += leaps_exit
            if pos.pmcc_status != PmccStatus.NONE:
                T_s = pos.short_call_dte / 365.0
                short_val = bs_call_price(S_open, pos.short_strike, T_s, r, sigma)
                short_exit = short_val * (1 + 0.04) * 100 * pos.leaps_contracts
                cash -= short_exit
            results.append({"date": date, "nav": cash, "regime": regime.value, "action": "TIER3_EXIT", "pmcc_income": 0})
        else:
            active_positions.append(pos)
    positions = active_positions

    # ────── UPDATE LEAPS MARK-TO-MARKET ──────
    for pos in positions:
        pos.leaps_dte = max(0, (pos.leaps_expiry_date - date).days)
        T_l = pos.leaps_dte / 365.0
        pos.leaps_delta = bs_delta(S, pos.leaps_strike, T_l, r, sigma)
        if pos.pmcc_status != PmccStatus.NONE:
            pos.short_call_dte = max(0, (pos.short_expiry_date - date).days)
            T_s = pos.short_call_dte / 365.0
            pos.short_call_delta = bs_delta(S, pos.short_strike, T_s, r, sigma)

    # ────── AFTERNOON DRAWDOWN GUARD / PROFIT TAKING ──────
    active_positions = []
    for pos in positions:
        T_l = pos.leaps_dte / 365.0
        leaps_mark = bs_call_price(S, pos.leaps_strike, T_l, r, sigma)
        
        # Profit Take Exit Check (>50% ROI)
        roi = (leaps_mark - pos.leaps_entry_price) / pos.leaps_entry_price if pos.leaps_entry_price > 0 else 0
        is_profit_take = roi > 0.40
        is_dte_exit = pos.leaps_dte < 60
        
        if is_profit_take or is_dte_exit:
            T_rem = max(1, pos.leaps_dte) / 365.0
            leaps_exit = bs_call_price(S, pos.leaps_strike, T_rem, r, sigma) * (1 - slip) * 100 * pos.leaps_contracts
            cash += leaps_exit
            if pos.pmcc_status != PmccStatus.NONE:
                T_s = max(1, pos.short_call_dte) / 365.0
                short_exit = bs_call_price(S, pos.short_strike, T_s, r, sigma) * (1 + slip) * 100 * pos.leaps_contracts
                cash -= short_exit
            
            action_str = "PROFIT_TAKE" if is_profit_take else "TIME_EXIT"
            results.append({"date": date, "nav": cash, "regime": regime.value, "action": action_str, "pmcc_income": 0})
            continue
            
        dg = drawdown_guard(pos.leaps_delta, pos.leaps_dte, S, q52low)
        if dg == DrawdownTier.TIER2_EXIT:
            T_rem = pos.leaps_dte / 365.0
            leaps_exit = bs_call_price(S, pos.leaps_strike, T_rem, r, sigma) * (1 - slip) * 100 * pos.leaps_contracts
            cash += leaps_exit
            if pos.pmcc_status != PmccStatus.NONE:
                T_s = pos.short_call_dte / 365.0
                short_exit = bs_call_price(S, pos.short_strike, T_s, r, sigma) * (1 + slip) * 100 * pos.leaps_contracts
                cash -= short_exit
            results.append({"date": date, "nav": cash, "regime": regime.value, "action": "TIER2_EXIT", "pmcc_income": 0})
            continue

        if dg == DrawdownTier.TIER1_ROLL_SHORT_DOWN and pos.pmcc_status == PmccStatus.ACTIVE:
            T_s = pos.short_call_dte / 365.0
            short_mark = bs_call_price(S, pos.short_strike, T_s, r, sigma)
            new_strike = find_strike_by_delta(S, T_s, r, sigma, 0.15)
            buyback_cost = short_mark * (1 + slip) * 100 * pos.leaps_contracts
            new_credit   = bs_call_price(S, new_strike, T_s, r, sigma) * (1 - slip) * 100 * pos.leaps_contracts
            cash -= (buyback_cost - new_credit)
            pos.short_strike = new_strike
            pos.short_call_credit = bs_call_price(S, new_strike, T_s, r, sigma)
            pos.pmcc_status = PmccStatus.DEFENSIVE

        active_positions.append(pos)
    positions = active_positions

    # ────── PMCC MANAGEMENT ──────
    for pos in positions:
        if pos.pmcc_status != PmccStatus.NONE:
            T_s = pos.short_call_dte / 365.0
            short_price = bs_call_price(S, pos.short_strike, T_s, r, sigma)
            days_elapsed = pos.pmcc_days_elapsed(date)

            action = manage_pmcc(
                short_price, pos.short_call_credit, days_elapsed,
                pos.short_call_dte, pos.short_call_delta,
                S, pos.short_strike, regime, pos.leaps_delta
            )

            if action in ["PROFIT_TAKE_EARLY", "PROFIT_TAKE_LATE", "EXPIRE_WORTHLESS"]:
                buyback = short_price * (1 + slip) * 100 * pos.leaps_contracts
                gross_credit = pos.short_call_credit * 100 * pos.leaps_contracts
                net_income = gross_credit - buyback
                cash += net_income
                pos.pmcc_credit_cumulative += (pos.short_call_credit - short_price)
                pmcc_income_today += net_income
                pos.pmcc_status = PmccStatus.NONE
                pos.short_strike = 0.0
                qqq_vs_entry = (S - pos.leaps_entry_qqq) / pos.leaps_entry_qqq
                can_reenter = (
                    regime in [Regime.BULL_STRONG, Regime.BULL_MODERATE] and
                    pos.leaps_age(date) >= 5 and
                    pos.leaps_dte > 60 and
                    qqq_vs_entry >= 0.02 and
                    16 <= vix <= 35
                )
                if can_reenter:
                    dte_target = 30 if vix > 20 else 35
                    delta_tgt  = 0.28 if regime == Regime.BULL_STRONG else 0.23
                    T_new = dte_target / 365.0
                    new_strike  = find_strike_by_delta(S, T_new, r, sigma, delta_tgt)
                    new_premium = bs_call_price(S, new_strike, T_new, r, sigma)
                    if new_premium >= 0.50:
                        credit_received = new_premium * (1 - slip) * 100 * pos.leaps_contracts
                        cash += credit_received
                        pos.short_strike          = new_strike
                        pos.short_call_credit     = new_premium
                        pos.short_call_entry_date = date
                        pos.short_expiry_date     = date + pd.Timedelta(days=dte_target)
                        pos.pmcc_status           = PmccStatus.ACTIVE

            elif action == "GAMMA_MANAGE":
                buyback = short_price * (1 + slip) * 100 * pos.leaps_contracts
                cash -= buyback
                pos.pmcc_credit_cumulative += (pos.short_call_credit - short_price)
                pos.pmcc_status = PmccStatus.NONE
                T_new = 32 / 365.0
                delta_tgt = 0.28 if regime == Regime.BULL_STRONG else 0.23
                new_strike  = find_strike_by_delta(S, T_new, r, sigma, delta_tgt)
                new_premium = bs_call_price(S, new_strike, T_new, r, sigma)
                if new_premium >= 0.50:
                    cash += new_premium * (1 - slip) * 100 * pos.leaps_contracts
                    pos.short_strike          = new_strike
                    pos.short_call_credit     = new_premium
                    pos.short_call_entry_date = date
                    pos.short_expiry_date     = date + pd.Timedelta(days=32)
                    pos.pmcc_status           = PmccStatus.ACTIVE

            elif action == "ROLL_UP_OUT":
                buyback = short_price * (1 + slip) * 100 * pos.leaps_contracts
                new_expiry_days = pos.short_call_dte + 21
                T_new   = new_expiry_days / 365.0
                delta_tgt = 0.25
                new_strike  = find_strike_by_delta(S, T_new, r, sigma, delta_tgt)
                new_premium = bs_call_price(S, new_strike, T_new, r, sigma)
                net = (new_premium - short_price) * 100 * pos.leaps_contracts
                if net >= -10.0:  
                    cash += net * (1 - slip)
                    pos.short_strike          = new_strike
                    pos.short_call_credit     = new_premium
                    pos.short_call_entry_date = date
                    pos.short_expiry_date     = date + pd.Timedelta(days=new_expiry_days)
                else:
                    cash -= buyback
                    pos.pmcc_status = PmccStatus.NONE

            elif action == "LOSS_LIMIT_CLOSE":
                buyback = short_price * (1 + slip) * 100 * pos.leaps_contracts
                cash -= buyback
                pos.pmcc_credit_cumulative -= pos.short_call_credit
                pos.pmcc_status = PmccStatus.NONE

            elif action in ["EMERGENCY_CLOSE", "DEFENSIVE_ROLL"]:
                buyback = short_price * (1 + slip) * 100 * pos.leaps_contracts
                cash -= buyback
                if action == "DEFENSIVE_ROLL":
                    T_s2 = pos.short_call_dte / 365.0
                    def_strike  = find_strike_by_delta(S, T_s2, r, sigma, 0.15)
                    def_premium = bs_call_price(S, def_strike, T_s2, r, sigma)
                    if def_premium >= 0.15:
                        cash += def_premium * (1 - slip) * 100 * pos.leaps_contracts
                        pos.short_strike          = def_strike
                        pos.short_call_credit     = def_premium
                        pos.short_expiry_date     = date + pd.Timedelta(days=pos.short_call_dte)
                        pos.pmcc_status           = PmccStatus.DEFENSIVE
                else:
                    pos.pmcc_status = PmccStatus.NONE

    # ────── LEAPS ENTRY CHECK ──────
    if len(positions) < max_positions:
        # Use LightGBM instead of stub
        if ml_loaded and regime_str in ["BULL_STRONG", "BULL_MODERATE", "CHOPPY"]:
            ml_conf, _ = ml_clf.predict_with_threshold(row, regime_str)
        else:
            ml_conf = 0.0

        threshold = 0.45
        is_gap    = gap_pct <= -0.003 # IMPROVED THRESHOLD: 0.3% gap down

        if regime_str in ["BULL_STRONG", "BULL_MODERATE", "CHOPPY"] and ml_conf >= threshold and is_gap:

            if regime_str == "BULL_STRONG":
                delta_tgt, dte_tgt = 0.85, 365
            elif regime_str == "BULL_MODERATE":
                delta_tgt, dte_tgt = 0.80, 365
            else:
                delta_tgt, dte_tgt = 0.80, 540

            T_l = dte_tgt / 365.0
            strike_l   = find_strike_by_delta(S, T_l, r, sigma, delta_tgt)
            leaps_price = bs_call_price(S, strike_l, T_l, r, sigma)
            leaps_cost  = leaps_price * (1 + slip)   

            total_leaps_mark = sum(bs_call_price(S, p.leaps_strike, max(0, p.leaps_dte)/365.0, r, sigma)*100*p.leaps_contracts for p in positions)
            contracts = size_position(cash + total_leaps_mark, leaps_cost)
            
            if contracts >= 1:
                total_cost = leaps_cost * 100 * contracts
                cash -= total_cost
                new_pos = Position()
                new_pos.leaps_status      = LeapsStatus.OPEN
                new_pos.leaps_entry_price = leaps_cost
                new_pos.leaps_entry_date  = date
                new_pos.leaps_strike      = strike_l
                new_pos.leaps_expiry_date = date + pd.Timedelta(days=dte_tgt)
                new_pos.leaps_contracts   = contracts
                new_pos.leaps_entry_qqq   = S
                new_pos.leaps_delta       = delta_tgt
                new_pos.leaps_dte         = dte_tgt
                positions.append(new_pos)

    # ────── PMCC ENTRY CHECK ──────
    for pos in positions:
        if pos.leaps_status == LeapsStatus.OPEN and pos.pmcc_status == PmccStatus.NONE:
            qqq_vs_entry = (S - pos.leaps_entry_qqq) / pos.leaps_entry_qqq
            can_enter = (
                regime_str in ["BULL_STRONG", "BULL_MODERATE"] and
                pos.leaps_age(date) >= 5 and
                pos.leaps_dte > 60 and
                qqq_vs_entry >= 0.02 and
                16 <= vix <= 35
            )
            if can_enter:
                dte_s   = 30 if vix > 20 else 35
                delta_s = 0.28 if regime_str == "BULL_STRONG" else 0.23
                T_s     = dte_s / 365.0
                short_strike  = find_strike_by_delta(S, T_s, r, sigma, delta_s)
                short_premium = bs_call_price(S, short_strike, T_s, r, sigma)
                if short_premium >= 0.50:
                    credit = short_premium * (1 - slip) * 100 * pos.leaps_contracts
                    cash  += credit
                    pos.short_strike          = short_strike
                    pos.short_call_credit     = short_premium
                    pos.short_call_entry_date = date
                    pos.short_expiry_date     = date + pd.Timedelta(days=dte_s)
                    pos.pmcc_status           = PmccStatus.ACTIVE
                    pmcc_income_today        += credit

    # ────── DAILY NAV ──────
    lm = 0.0
    sm = 0.0
    for p in positions:
        t_l = max(p.leaps_dte, 0) / 365.0 if p.leaps_status == LeapsStatus.OPEN else 0
        t_s = max(p.short_call_dte, 0) / 365.0 if p.pmcc_status != PmccStatus.NONE else 0
        lm += bs_call_price(S, p.leaps_strike, t_l, r, sigma) * 100 * p.leaps_contracts if p.leaps_status == LeapsStatus.OPEN else 0
        sm += bs_call_price(S, p.short_strike, t_s, r, sigma) * 100 * p.leaps_contracts if p.pmcc_status != PmccStatus.NONE else 0
        
    nav = cash + lm - sm

    results.append({
        "date":             date,
        "nav":              nav,
        "cash":             cash,
        "leaps_mark":       lm,
        "short_mark":       sm,
        "regime":           regime.value,
        "positions_open":   len(positions),
        "pmcc_income_today":pmcc_income_today,
    })

results_df = pd.DataFrame(results)
metrics = compute_metrics(results_df)

print("\n=== REAL DATA PMCC BACKTEST (2019-2026) -> GAP 0.3%, ML CONF 0.45 ===")
for k, v in metrics.items():
    print(f"  {k:<25}: {v}")

results_df.to_csv("improved_qqq_leaps_backtest.csv", index=False)
print("Saved to improved_qqq_leaps_backtest.csv")
