"""
QQQ LEAPS Live Signal Service — connects to ib-gateway-qqq (paper account
web3aistore, DUQ105198) and evaluates whether the strategy would enter or
exit positions RIGHT NOW.

Reuses feature computation + entry logic from qqq_leaps_enhanced_2y_hourly.py
so live behavior exactly matches backtest.

Usage:
    python3 qqq_live_signal.py                 # print current signal
    python3 qqq_live_signal.py --save          # also save JSON snapshot
    python3 qqq_live_signal.py --place-order   # actually place LEAPS order (requires confirmation flag)

Environment:
    IB_HOST      default 127.0.0.1
    IB_PORT      default 4005 (ib-gateway-qqq)
    IB_CLIENT_ID default 200
    QQQ_CAPITAL  default 75000
"""
import os
import sys
import json
import random
import argparse
from datetime import datetime, timedelta, date
from pathlib import Path
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from ib_insync import IB, Stock, Index, Option

# Reuse the strategy's own logic
sys.path.insert(0, str(Path(__file__).parent))
from qqq_leaps_enhanced_2y_hourly import (
    Config, bs_call_price, bs_call_delta, find_call_strike,
    fit_gaussian_hmm, build_enhanced_features, compute_options_features,
)


IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "4005"))
# Use a unique client ID per run by default. A fixed ID (e.g. 200) collides with
# any concurrent/leftover IB API session on the shared gateway, causing the
# connect to time out ("clientId already in use") and the signal run to fail.
# Set IB_CLIENT_ID explicitly to pin a specific ID.
_env_cid = os.getenv("IB_CLIENT_ID")
IB_CLIENT_ID = int(_env_cid) if _env_cid else random.randint(8000, 8999)
CAPITAL = float(os.getenv("QQQ_CAPITAL", "75000"))

CFG = Config()  # Same parameters as backtest (== "moderate" tier)
CFG.initial_capital = CAPITAL  # Override with runtime capital

# ─── Risk tiers ──────────────────────────────────────────────────────────────
# Per-account risk level (set by each user) selects one of these tiers. Each
# tier is a full Config with its own entry gate strictness, NAV sizing %, and
# PMCC skip-gate thresholds — "moderate" reproduces the CFG/backtest defaults
# exactly; conservative/aggressive shift entry strictness and position size
# in the same direction as TurboCore Pro's risk ladder.
RISK_TIERS = ("conservative", "moderate", "aggressive")


def _build_tier_config(risk: str) -> Config:
    """Return a Config for the given risk tier, based on CFG (moderate defaults).

    Conservative and aggressive values below are backtest-validated via the
    canonical 2-year hourly causal replay (qqq_leaps_enhanced_2y_hourly.py),
    same feature pipeline and walk-forward methodology as the moderate baseline.
    See qqq_leaps_tier_optimization_results.md for full results.
    """
    import copy
    tier_cfg = copy.copy(CFG)
    if risk == "conservative":
        # 2y hourly replay: 20.19% CAGR, -11.13% max DD, 1.49 Sharpe
        tier_cfg.entry_ml_min = 0.55             # require higher model confidence to enter
        tier_cfg.entry_vix_max = 30.0            # more cautious about elevated vol
        tier_cfg.entry_rsi14_max = 35.0          # require deeper pullback (higher conviction)
        tier_cfg.max_position_pct = 0.20         # smaller NAV allocation per position
        tier_cfg.max_contracts = 2
        tier_cfg.pmcc_skip_adx_min = 24.0        # fewer PMCC skips = less naked LEAPS exposure
        tier_cfg.pmcc_skip_vrp_max = 0.50
    elif risk == "aggressive":
        # 2y hourly replay: 33.94% CAGR, -15.70% max DD, 1.29 Sharpe
        tier_cfg.entry_ml_min = 0.40             # accept lower model confidence
        tier_cfg.entry_vix_max = 45.0
        tier_cfg.entry_rsi14_max = 38.0          # allow entries on shallower pullbacks
        tier_cfg.max_position_pct = 0.50
        tier_cfg.max_contracts = 8
        tier_cfg.pmcc_skip_adx_min = 12.0        # more PMCC skips = more naked long exposure
        tier_cfg.pmcc_skip_vrp_max = 0.90
    # "moderate" == CFG as-is (31.82% CAGR, -15.39% max DD, 1.28 Sharpe on fresh replay)
    return tier_cfg


# =============================================================================
# IBKR DATA FETCH
# =============================================================================

def fetch_market_snapshot(ib: IB) -> dict:
    """Pull QQQ, VIX, VIX3M spot + historical bars for feature engineering."""
    ib.reqMarketDataType(4)  # delayed-frozen for paper account
    snap = {}

    qqq = Stock('QQQ', 'SMART', 'USD', primaryExchange='NASDAQ')
    ib.qualifyContracts(qqq)
    snap["qqq_contract"] = qqq

    vix = Index('VIX', 'CBOE', 'USD')
    vix3m = Index('VIX3M', 'CBOE', 'USD')
    ib.qualifyContracts(vix, vix3m)

    # Live snapshot tickers
    tq = ib.reqMktData(qqq, '', False, False)
    tv = ib.reqMktData(vix, '', False, False)
    tv3 = ib.reqMktData(vix3m, '', False, False)
    ib.sleep(4)

    snap["qqq_last"] = tq.last if tq.last and not np.isnan(tq.last) else tq.close
    snap["qqq_close"] = tq.close if tq.close and not np.isnan(tq.close) else tq.last
    snap["vix"] = tv.last if tv.last and not np.isnan(tv.last) else tv.close
    snap["vix3m"] = tv3.last if tv3.last and not np.isnan(tv3.last) else tv3.close

    # Historical daily for feature engineering (need enough for SMA200 + HMM training)
    # 3 years is plenty
    daily_bars = ib.reqHistoricalData(
        qqq, endDateTime='', durationStr='3 Y', barSizeSetting='1 day',
        whatToShow='TRADES', useRTH=True, formatDate=1,
    )
    df_qqq = pd.DataFrame([
        dict(date=pd.Timestamp(b.date), open=b.open, high=b.high, low=b.low,
             close=b.close, volume=b.volume)
        for b in daily_bars
    ]).set_index("date")
    snap["qqq_daily"] = df_qqq

    # VIX + VIX3M daily
    vix_bars = ib.reqHistoricalData(
        vix, endDateTime='', durationStr='3 Y', barSizeSetting='1 day',
        whatToShow='TRADES', useRTH=True, formatDate=1,
    )
    df_vix = pd.DataFrame([
        dict(date=pd.Timestamp(b.date), close=b.close) for b in vix_bars
    ]).set_index("date")
    snap["vix_daily"] = df_vix

    vix3m_bars = ib.reqHistoricalData(
        vix3m, endDateTime='', durationStr='3 Y', barSizeSetting='1 day',
        whatToShow='TRADES', useRTH=True, formatDate=1,
    )
    df_vix3m = pd.DataFrame([
        dict(date=pd.Timestamp(b.date), close=b.close) for b in vix3m_bars
    ]).set_index("date")
    snap["vix3m_daily"] = df_vix3m

    # Hourly for the "now" bar
    hourly_bars = ib.reqHistoricalData(
        qqq, endDateTime='', durationStr='60 D', barSizeSetting='1 hour',
        whatToShow='TRADES', useRTH=True, formatDate=1,
    )
    df_hourly = pd.DataFrame([
        dict(ts=pd.Timestamp(b.date), open=b.open, high=b.high, low=b.low,
             close=b.close, volume=b.volume)
        for b in hourly_bars
    ]).set_index("ts")
    snap["qqq_hourly"] = df_hourly

    return snap


def fetch_leaps_candidate(ib: IB, qqq_contract, spot: float, cfg: Config,
                          target_dte: int, target_delta: float) -> dict:
    """Query the actual QQQ option chain and return the LEAPS closest to
    target_dte and target_delta."""
    chains = ib.reqSecDefOptParams(qqq_contract.symbol, '', qqq_contract.secType, qqq_contract.conId)
    best_chain = max(chains, key=lambda c: len(c.expirations))

    today = date.today()
    target_date = today + timedelta(days=target_dte)

    def parse_exp(e):
        return datetime.strptime(e[:8], "%Y%m%d").date()

    # candidate expiries within +/- 60 days of target
    exps = sorted([e for e in best_chain.expirations
                   if abs((parse_exp(e) - target_date).days) <= 90])
    if not exps:
        return {"error": f"No LEAPS expiries near {target_date}"}
    picked_exp = min(exps, key=lambda e: abs((parse_exp(e) - target_date).days))

    # Compute theoretical strike for target delta at estimated IV
    est_iv = 0.30  # rough placeholder; will refine below with live greek
    T = target_dte / 365.0
    r = 0.045  # short-term risk-free proxy
    theo_strike = find_call_strike(spot, T, r, est_iv, target_delta)

    # Snap to nearest available strike in the chain
    strikes = sorted(best_chain.strikes)
    picked_k = min(strikes, key=lambda s: abs(s - theo_strike))

    # Get its live greek + quote
    opt = Option('QQQ', picked_exp, picked_k, 'C', 'SMART')
    ib.qualifyContracts(opt)
    tk = ib.reqMktData(opt, '106', False, False)  # 106 = compute greeks
    ib.sleep(5)

    result = {
        "expiry": picked_exp,
        "strike": picked_k,
        "bid": tk.bid,
        "ask": tk.ask,
        "mid": (tk.bid + tk.ask) / 2 if tk.bid and tk.ask and not np.isnan(tk.bid) and not np.isnan(tk.ask) else None,
        "delta": None,
        "iv": None,
        "theta": None,
        "gamma": None,
        "days_to_expiry": (parse_exp(picked_exp) - today).days,
    }
    if tk.modelGreeks:
        result["delta"] = tk.modelGreeks.delta
        result["iv"] = tk.modelGreeks.impliedVol
        result["theta"] = tk.modelGreeks.theta
        result["gamma"] = tk.modelGreeks.gamma

    return result


# =============================================================================
# FEATURE COMPUTATION (reuse engine's build_enhanced_features)
# =============================================================================

def build_features_from_snapshot(snap: dict) -> pd.DataFrame:
    """Construct the data dict the engine expects and run its own feature builder.

    Engine expects (see load_market_data()):
      qqq_1h: index=DatetimeIndex tz='America/New_York', columns Open/High/Low/Close/Volume (capitalized)
      qqq_1d: index=DatetimeIndex normalized (no tz), Close column
      vix / vix3m / irx: single-column daily DataFrames indexed by normalized date
    """
    def cap_cols(df):
        """Rename lowercase OHLCV to capitalized to match yfinance/engine convention."""
        return df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })

    # QQQ daily — normalized date index, no tz
    qqq_1d = cap_cols(snap["qqq_daily"].copy())
    qqq_1d.index = pd.to_datetime(qqq_1d.index).tz_localize(None).normalize()

    # QQQ hourly — tz='America/New_York'
    qqq_1h = cap_cols(snap["qqq_hourly"].copy())
    if qqq_1h.index.tz is None:
        qqq_1h.index = pd.to_datetime(qqq_1h.index).tz_localize("America/New_York")
    else:
        qqq_1h.index = qqq_1h.index.tz_convert("America/New_York")

    # VIX / VIX3M — single Close column, normalized daily index
    vix = snap["vix_daily"].copy().rename(columns={"close": "Close"})
    vix.index = pd.to_datetime(vix.index).tz_localize(None).normalize()

    vix3m = snap["vix3m_daily"].copy().rename(columns={"close": "Close"})
    vix3m.index = pd.to_datetime(vix3m.index).tz_localize(None).normalize()

    # IRX (13-week T-bill): use a flat 4.5% placeholder (paper account lacks IRX subscription)
    irx = pd.DataFrame({"Close": 4.5}, index=vix.index)

    data = {
        "qqq_1d": qqq_1d,
        "qqq_1h": qqq_1h,
        "vix": vix,
        "vix3m": vix3m,
        "irx": irx,
    }

    # build_enhanced_features returns (df, hmm, labels)
    result = build_enhanced_features(data)
    if isinstance(result, tuple):
        features = result[0]
    else:
        features = result
    return features


# =============================================================================
# ENTRY EVALUATOR (mirrors EnhancedEngine.check_entry exactly)
# =============================================================================

def evaluate_entry(row, cfg: Config) -> dict:
    """Return dict with `enter: bool` and detailed gate breakdown."""
    gates = {}

    gates["regime_ok"] = row["regime"] not in ("BEAR", "BEAR_SMA_FORCED")
    gates["regime"] = row["regime"]

    gates["vix_ok"] = row["vix"] < cfg.entry_vix_max
    gates["vix"] = float(row["vix"])
    gates["vix_max"] = cfg.entry_vix_max

    gates["above_sma100_ok"] = bool(row["above_sma100"])

    gates["rsi_ok"] = row["rsi_14"] < cfg.entry_rsi14_max
    gates["rsi_14"] = float(row["rsi_14"])
    gates["rsi_max"] = cfg.entry_rsi14_max

    gates["gap_down_ok"] = row["gap_down_pct"] >= cfg.entry_gap_down_min
    gates["gap_down_pct"] = float(row["gap_down_pct"])
    gates["gap_down_min"] = cfg.entry_gap_down_min

    gates["ml_confidence_ok"] = row["ml_confidence"] >= cfg.entry_ml_min
    gates["ml_confidence"] = float(row["ml_confidence"])
    gates["ml_confidence_min"] = cfg.entry_ml_min

    put_demand = row.get("put_demand_proxy")
    if pd.notna(put_demand):
        gates["put_demand_ok"] = put_demand <= cfg.entry_put_demand_max
        gates["put_demand_proxy"] = float(put_demand)
    else:
        gates["put_demand_ok"] = True
        gates["put_demand_proxy"] = None

    enter = all([
        gates["regime_ok"], gates["vix_ok"], gates["above_sma100_ok"],
        gates["rsi_ok"], gates["gap_down_ok"], gates["ml_confidence_ok"],
        gates["put_demand_ok"],
    ])
    return {"enter": enter, "gates": gates}


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", action="store_true", help="Save JSON snapshot to signals/")
    parser.add_argument("--quiet", action="store_true", help="Only print JSON")
    args = parser.parse_args()

    ib = IB()
    ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=20)
    if not args.quiet:
        print(f"Connected to {IB_HOST}:{IB_PORT}, account: {ib.managedAccounts()}")

    try:
        # 1. Fetch snapshot
        snap = fetch_market_snapshot(ib)
        if not args.quiet:
            print(f"QQQ: ${snap['qqq_last']:.2f} (close ${snap['qqq_close']:.2f})")
            print(f"VIX: {snap['vix']:.2f}  VIX3M: {snap['vix3m']:.2f}")
            print(f"Daily bars: {len(snap['qqq_daily'])}, Hourly bars: {len(snap['qqq_hourly'])}")

        # 2. Build features
        features = build_features_from_snapshot(snap)
        latest = features.iloc[-1]
        if not args.quiet:
            print(f"\nLatest feature row: {features.index[-1]}")
            print(f"  regime={latest['regime']}  vix={latest['vix']:.2f}  rsi14={latest['rsi_14']:.1f}")
            print(f"  above_sma100={bool(latest['above_sma100'])}  gap_down_pct={latest['gap_down_pct']:.3%}")
            print(f"  ml_confidence={latest['ml_confidence']:.3f}")

        # 3. Evaluate entry (moderate tier == CFG defaults, used for top-level
        #    back-compat fields; all 3 tiers computed below for per-account routing)
        entry_result = evaluate_entry(latest, CFG)
        if not args.quiet:
            print(f"\n{'='*60}")
            print(f"ENTRY SIGNAL: {'YES — WOULD OPEN LEAPS' if entry_result['enter'] else 'NO'}")
            print(f"{'='*60}")
            for gate, val in entry_result["gates"].items():
                if gate.endswith("_ok"):
                    label = gate[:-3]
                    ok = "✓" if val else "✗"
                    detail = entry_result["gates"].get(label, "")
                    print(f"  {ok} {label}: {detail}")

        # 4. Determine target LEAPS (regardless of entry decision — informational)
        regime = latest["regime"]
        if regime == "BULL_STRONG":
            target_delta, target_dte = CFG.delta_bull, CFG.dte_bull
        elif regime == "BULL_MODERATE":
            target_delta, target_dte = CFG.delta_neutral, CFG.dte_neutral
        else:
            target_delta, target_dte = CFG.delta_bear, CFG.dte_bear

        leaps = fetch_leaps_candidate(
            ib, snap["qqq_contract"], snap["qqq_last"], CFG,
            target_dte, target_delta,
        )
        if not args.quiet:
            print(f"\nTarget LEAPS (regime={regime}, delta_target={target_delta}, dte_target={target_dte}):")
            for k, v in leaps.items():
                print(f"  {k}: {v}")

        # 5. Sizing (if entry triggered) — moderate tier, mirrors top-level fields
        contracts = 0
        est_cost = 0.0
        if entry_result["enter"] and leaps.get("mid"):
            nav = CAPITAL  # for fresh deployment; production would query IBKR account NAV
            max_outlay = nav * CFG.max_position_pct
            per_contract_cost = 100 * leaps["mid"] + CFG.commission
            contracts = max(1, int(max_outlay / per_contract_cost))
            contracts = min(contracts, CFG.max_contracts)
            est_cost = contracts * per_contract_cost

        # 5b. Per-risk-tier entry + sizing — reuses the SAME hourly-derived
        #     `latest` feature row and `leaps` candidate as above (identical
        #     hourly data/pipeline as the backtest); only the gate strictness
        #     and NAV sizing % vary per tier.
        tiers = {}
        for risk in RISK_TIERS:
            tier_cfg = _build_tier_config(risk)
            tier_entry = evaluate_entry(latest, tier_cfg)
            tier_contracts, tier_cost = 0, 0.0
            if tier_entry["enter"] and leaps.get("mid"):
                tier_nav = CAPITAL
                tier_max_outlay = tier_nav * tier_cfg.max_position_pct
                tier_per_contract_cost = 100 * leaps["mid"] + tier_cfg.commission
                tier_contracts = max(1, int(tier_max_outlay / tier_per_contract_cost))
                tier_contracts = min(tier_contracts, tier_cfg.max_contracts)
                tier_cost = tier_contracts * tier_per_contract_cost
            tiers[risk] = {
                "enter": tier_entry["enter"],
                "gates": tier_entry["gates"],
                "contracts": tier_contracts,
                "estimated_cost": tier_cost,
                "cost_pct_of_capital": tier_cost / CAPITAL if CAPITAL else 0,
                "max_position_pct": tier_cfg.max_position_pct,
                "entry_ml_min": tier_cfg.entry_ml_min,
            }
        if not args.quiet:
            print(f"\nPer-risk-tier sizing (same hourly feature row, tier-scaled gates):")
            for risk, t in tiers.items():
                print(f"  {risk}: enter={t['enter']} contracts={t['contracts']} cost=${t['estimated_cost']:.2f}")

        # 6. Assemble final signal
        signal = {
            "timestamp": datetime.now().isoformat(),
            "account": ib.managedAccounts()[0] if ib.managedAccounts() else None,
            "spot": {
                "qqq": snap["qqq_last"],
                "qqq_close": snap["qqq_close"],
                "vix": snap["vix"],
                "vix3m": snap["vix3m"],
            },
            "features": {
                "regime": str(latest["regime"]),
                "rsi_14": float(latest["rsi_14"]),
                "above_sma100": bool(latest["above_sma100"]),
                "above_sma200": bool(latest["above_sma200"]) if "above_sma200" in latest else None,
                "gap_down_pct": float(latest["gap_down_pct"]),
                "ml_confidence": float(latest["ml_confidence"]),
            },
            "entry_decision": entry_result,
            "target_leaps": leaps,
            "sizing": {
                "capital": CAPITAL,
                "contracts": contracts,
                "estimated_cost": est_cost,
                "cost_pct_of_capital": est_cost / CAPITAL if CAPITAL else 0,
            },
            # Per-risk-tier entry/sizing variants — the app selects the tier
            # matching each account's configured risk level.
            "tiers": tiers,
            "action": (
                f"BUY {contracts} QQQ {leaps['expiry']} ${leaps['strike']:.0f} CALL @ ~${leaps['mid']:.2f}"
                if entry_result["enter"] and contracts > 0
                else "NO ACTION"
            ),
        }

        if args.quiet:
            print(json.dumps(signal, indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"ACTION: {signal['action']}")
            print(f"{'='*60}")

        if args.save:
            outdir = Path("signals")
            outdir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            outfile = outdir / f"signal_{ts}.json"
            outfile.write_text(json.dumps(signal, indent=2, default=str))
            if not args.quiet:
                print(f"\n✓ Saved: {outfile}")

        return signal

    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
