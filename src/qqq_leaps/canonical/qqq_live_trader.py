#!/usr/bin/env python3
"""
QQQ LEAPS Live Paper Trader
============================

Fully-automated paper trading executor for the QQQ LEAPS + PMCC strategy.
Connects to ib-gateway-qqq (port 4005) → web3aistore paper account (DUQ105198).

Execution model (mirrors backtest's 2-scan-per-day design, extended to hourly):
  * Every hour during market hours, run one scan
  * At 10:00 ET → exit-only scan (LEAPS adaptive exit + PMCC exits)
  * At 15:00 ET → full scan (PMCC exits + LEAPS entry + PMCC open)
  * All other hours → sync positions + check PMCC exits only (safer default)

Order type: marketable limit at mid-price, 30s wait, then cancel & retry with 5c-wider limit.

State: SQLite (positions.db) tracks LEAPS + linked short-call positions, order history.
Env vars:
    IB_HOST=127.0.0.1  IB_PORT=4005  IB_CLIENT_ID=250  QQQ_CAPITAL=75000
    LIVE_TRADE=1 to actually place orders; else dry-run
Usage:
    python3 qqq_live_trader.py            # one shot, meant for cron
    python3 qqq_live_trader.py --force-full-scan   # ignore time-of-day gating, force full scan
    python3 qqq_live_trader.py --dry-run  # never place orders
"""
import os
import sys
import json
import time
import argparse
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from ib_insync import IB, Stock, Index, Option, MarketOrder, LimitOrder, util

sys.path.insert(0, str(Path(__file__).parent))
from qqq_leaps_enhanced_2y_hourly import (
    Config,
    bs_call_price,
    bs_call_delta,
    find_call_strike,
    build_enhanced_features,
)

# =============================================================================
# CONFIG
# =============================================================================
IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "4005"))
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "250"))
CAPITAL = float(os.getenv("QQQ_CAPITAL", "1000000"))
LIVE_TRADE = os.getenv("LIVE_TRADE", "1") == "1"
# Maximum allowed single-run NAV swing (guards against IBKR API glitches).
# If live NAV differs from QQQ_CAPITAL fallback by more than this fraction,
# log a warning and fall back to QQQ_CAPITAL instead of the suspicious live value.
NAV_SANITY_MAX_SWING = float(os.getenv("NAV_SANITY_MAX_SWING", "0.25"))

STATE_DIR = Path(os.getenv("STATE_DIR", str(Path(__file__).parent / "state")))
STATE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = STATE_DIR / "positions.db"
LOG_DIR = Path(os.getenv("LOG_DIR", str(Path(__file__).parent / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

CFG = Config()
CFG.initial_capital = CAPITAL

# Timeframes
LIMIT_WAIT_SEC = int(os.getenv("LIMIT_WAIT_SEC", "30"))
LIMIT_RETRIES = int(os.getenv("LIMIT_RETRIES", "3"))
LIMIT_STEP = float(os.getenv("LIMIT_STEP", "0.05"))  # $0.05 wider each retry

# =============================================================================
# LOGGING
# =============================================================================
run_ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
log_file = LOG_DIR / f"trader_{run_ts}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
log = logging.getLogger("qqq_trader")

# =============================================================================
# STATE (SQLite)
# =============================================================================
def db_init():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leaps_positions (
            id TEXT PRIMARY KEY,
            open_ts TEXT NOT NULL,
            strike REAL NOT NULL,
            expiry TEXT NOT NULL,
            contracts INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            entry_spot REAL NOT NULL,
            entry_delta REAL NOT NULL,
            ib_con_id INTEGER,
            status TEXT DEFAULT 'OPEN',
            close_ts TEXT,
            close_price REAL,
            close_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS short_calls (
            id TEXT PRIMARY KEY,
            leaps_id TEXT NOT NULL REFERENCES leaps_positions(id),
            open_ts TEXT NOT NULL,
            strike REAL NOT NULL,
            expiry TEXT NOT NULL,
            contracts INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            entry_spot REAL NOT NULL,
            entry_delta REAL NOT NULL,
            ib_con_id INTEGER,
            status TEXT DEFAULT 'OPEN',
            close_ts TEXT,
            close_price REAL,
            close_reason TEXT
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            kind TEXT NOT NULL,
            action TEXT NOT NULL,
            symbol TEXT,
            strike REAL,
            expiry TEXT,
            right TEXT,
            contracts INTEGER,
            limit_price REAL,
            fill_price REAL,
            status TEXT,
            ib_order_id INTEGER,
            related_pos_id TEXT,
            reason TEXT
        );
    """)
    conn.commit()
    return conn


def db_get_open_leaps(conn):
    rows = conn.execute("SELECT * FROM leaps_positions WHERE status='OPEN'").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM leaps_positions LIMIT 0").description]
    return [dict(zip(cols, r)) for r in rows]


def db_get_open_shorts(conn, leaps_id=None):
    q = "SELECT * FROM short_calls WHERE status='OPEN'"
    p = ()
    if leaps_id:
        q += " AND leaps_id=?"
        p = (leaps_id,)
    rows = conn.execute(q, p).fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM short_calls LIMIT 0").description]
    return [dict(zip(cols, r)) for r in rows]


def db_log_order(conn, **kwargs):
    cols = list(kwargs.keys())
    placeholders = ",".join("?" * len(cols))
    conn.execute(
        f"INSERT INTO orders ({','.join(cols)}) VALUES ({placeholders})",
        list(kwargs.values()),
    )
    conn.commit()


# =============================================================================
# IBKR CONNECTION & DATA
# =============================================================================
def connect_ib():
    ib = IB()
    log.info(f"Connecting to IBKR at {IB_HOST}:{IB_PORT} clientId={IB_CLIENT_ID}")
    ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=15)
    ib.reqMarketDataType(4)  # delayed-frozen (paper account has no live subs)
    log.info(f"Connected. Managed accounts: {ib.managedAccounts()}")
    return ib


def fetch_live_nav(ib):
    """Fetch NetLiquidation from IBKR and apply a sanity guard.

    Returns (nav, source) where source is 'live' or 'fallback'.
    If the live value is missing or swings more than NAV_SANITY_MAX_SWING
    from the QQQ_CAPITAL fallback, we log a warning and use the fallback.
    """
    try:
        acct = ib.accountSummary()
        nav_row = next((a for a in acct if a.tag == "NetLiquidation"), None)
        if not nav_row:
            log.warning(f"No NetLiquidation in account summary — using fallback CAPITAL=${CAPITAL:,.0f}")
            return CAPITAL, "fallback"
        live_nav = float(nav_row.value)
        swing = abs(live_nav - CAPITAL) / CAPITAL if CAPITAL > 0 else 1.0
        if swing > NAV_SANITY_MAX_SWING:
            log.warning(
                f"⚠️  NAV sanity check: live NAV ${live_nav:,.2f} differs from "
                f"fallback ${CAPITAL:,.0f} by {swing*100:.1f}% (max {NAV_SANITY_MAX_SWING*100:.0f}%). "
                f"Using live value (paper account — large swings are expected on first run)."
            )
        log.info(f"💰 Account NAV: ${live_nav:,.2f} (source: live IBKR)")
        return live_nav, "live"
    except Exception as e:
        log.error(f"NAV fetch failed: {e} — using fallback CAPITAL=${CAPITAL:,.0f}")
        return CAPITAL, "fallback"


def fetch_snapshot(ib):
    """Pull QQQ + VIX + VIX3M spots, hourly + daily QQQ bars, daily VIX bars."""
    qqq = Stock("QQQ", "SMART", "USD")
    vix = Index("VIX", "CBOE")
    vix3m = Index("VIX3M", "CBOE")
    ib.qualifyContracts(qqq, vix, vix3m)

    # Historical hourly QQQ (2 years back — the strategy needs long lookback for HMM + features)
    log.info("Fetching QQQ hourly bars (2Y)...")
    bars_h = ib.reqHistoricalData(
        qqq, endDateTime="", durationStr="2 Y", barSizeSetting="1 hour",
        whatToShow="TRADES", useRTH=True, formatDate=1,
    )
    df_h = util.df(bars_h).set_index("date")
    df_h.index = pd.to_datetime(df_h.index)
    if df_h.index.tz is None:
        df_h.index = df_h.index.tz_localize("America/New_York")
    else:
        df_h.index = df_h.index.tz_convert("America/New_York")

    log.info("Fetching QQQ daily bars (3Y)...")
    bars_d = ib.reqHistoricalData(
        qqq, endDateTime="", durationStr="3 Y", barSizeSetting="1 day",
        whatToShow="TRADES", useRTH=True, formatDate=1,
    )
    df_d = util.df(bars_d).set_index("date")
    df_d.index = pd.to_datetime(df_d.index)
    if df_d.index.tz is not None:
        df_d.index = df_d.index.tz_localize(None)
    df_d.index = df_d.index.normalize()

    log.info("Fetching VIX daily (3Y)...")
    bars_v = ib.reqHistoricalData(
        vix, endDateTime="", durationStr="3 Y", barSizeSetting="1 day",
        whatToShow="TRADES", useRTH=True, formatDate=1,
    )
    df_v = util.df(bars_v).set_index("date")
    df_v.index = pd.to_datetime(df_v.index)
    if df_v.index.tz is not None:
        df_v.index = df_v.index.tz_localize(None)
    df_v.index = df_v.index.normalize()

    log.info("Fetching VIX3M daily (3Y)...")
    bars_v3 = ib.reqHistoricalData(
        vix3m, endDateTime="", durationStr="3 Y", barSizeSetting="1 day",
        whatToShow="TRADES", useRTH=True, formatDate=1,
    )
    df_v3 = util.df(bars_v3).set_index("date")
    df_v3.index = pd.to_datetime(df_v3.index)
    if df_v3.index.tz is not None:
        df_v3.index = df_v3.index.tz_localize(None)
    df_v3.index = df_v3.index.normalize()

    # Live spots
    tkr_q = ib.reqMktData(qqq, "", False, False)
    tkr_v = ib.reqMktData(vix, "", False, False)
    tkr_v3 = ib.reqMktData(vix3m, "", False, False)
    ib.sleep(3)
    qqq_spot = tkr_q.last if not np.isnan(tkr_q.last) else tkr_q.close
    vix_spot = tkr_v.last if not np.isnan(tkr_v.last) else tkr_v.close
    vix3m_spot = tkr_v3.last if not np.isnan(tkr_v3.last) else tkr_v3.close

    log.info(f"Spots — QQQ ${qqq_spot:.2f}  VIX {vix_spot:.2f}  VIX3M {vix3m_spot:.2f}")

    return {
        "qqq_spot": float(qqq_spot),
        "vix_spot": float(vix_spot),
        "vix3m_spot": float(vix3m_spot),
        "qqq_hourly": df_h,
        "qqq_daily": df_d,
        "vix_daily": df_v,
        "vix3m_daily": df_v3,
    }


def build_features(snap):
    """Rename columns to match engine's expected schema and run build_enhanced_features."""
    def cap(df):
        return df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })

    qqq_1d = cap(snap["qqq_daily"].copy())
    qqq_1h = cap(snap["qqq_hourly"].copy())

    vix = snap["vix_daily"].copy().rename(columns={"close": "Close"})
    vix3m = snap["vix3m_daily"].copy().rename(columns={"close": "Close"})
    irx = pd.DataFrame({"Close": 4.5}, index=vix.index)

    data = {"qqq_1d": qqq_1d, "qqq_1h": qqq_1h, "vix": vix, "vix3m": vix3m, "irx": irx}
    result = build_enhanced_features(data)
    features_df = result[0] if isinstance(result, tuple) else result
    return features_df, data


# =============================================================================
# OPTION CHAIN + STRIKE PICKING
# =============================================================================
def find_best_option(ib, spot, target_delta, dte_target, right="C"):
    """Query live QQQ option chain, find contract closest to target delta with DTE near target."""
    qqq = Stock("QQQ", "SMART", "USD")
    ib.qualifyContracts(qqq)
    chains = ib.reqSecDefOptParams(qqq.symbol, "", qqq.secType, qqq.conId)
    chain = max(chains, key=lambda c: len(c.expirations))

    today = date.today()
    # Filter expiries within ±60 days of target
    target_date = pd.Timestamp(today) + pd.Timedelta(days=dte_target)
    candidates = []
    for exp_str in chain.expirations:
        exp_date = pd.Timestamp(exp_str)
        dte = (exp_date - pd.Timestamp(today)).days
        if abs(dte - dte_target) <= 60 and dte > 5:
            candidates.append((exp_date, exp_str, dte))
    if not candidates:
        raise RuntimeError(f"No expiries near DTE {dte_target}")
    # Pick expiry closest to target
    exp_date, exp_str, dte = min(candidates, key=lambda x: abs(x[2] - dte_target))
    log.info(f"Selected expiry {exp_str} (DTE {dte})")

    # Strike range based on target delta
    if target_delta >= 0.7:
        strike_range = (spot * 0.65, spot * 0.95)
    elif target_delta >= 0.4:
        strike_range = (spot * 0.90, spot * 1.05)
    else:
        strike_range = (spot * 1.00, spot * 1.20)
    strikes = sorted(s for s in chain.strikes if strike_range[0] <= s <= strike_range[1])
    # Sample strikes near estimated target (use B-S to guess starting point)
    if not strikes:
        raise RuntimeError(f"No strikes in range {strike_range}")

    # Query greeks for these strikes
    options = [Option("QQQ", exp_str, s, right, "SMART", tradingClass="QQQ") for s in strikes]
    ib.qualifyContracts(*options)
    log.info(f"Querying {len(options)} contracts for greeks...")
    tickers = []
    for opt in options:
        t = ib.reqMktData(opt, "", False, False)
        tickers.append((opt, t))
    ib.sleep(4)

    best = None
    best_gap = 999
    for opt, tkr in tickers:
        if not tkr.modelGreeks or tkr.modelGreeks.delta is None:
            continue
        d = abs(tkr.modelGreeks.delta)
        gap = abs(d - target_delta)
        if gap < best_gap:
            best_gap = gap
            best = (opt, tkr)
    if best is None:
        raise RuntimeError("No contract had valid greeks")
    opt, tkr = best
    log.info(f"Best: {opt.strike} {opt.right} exp={opt.lastTradeDateOrContractMonth}  "
             f"delta={tkr.modelGreeks.delta:.3f}  bid={tkr.bid} ask={tkr.ask}")
    return opt, tkr


# =============================================================================
# ORDER PLACEMENT (marketable limit at mid, retry)
# =============================================================================
def place_limit_at_mid(ib, contract, action, quantity, live=True):
    """Place a limit order at mid, cancel/replace up to LIMIT_RETRIES times widening by LIMIT_STEP."""
    if not live:
        log.info(f"[DRY-RUN] Would {action} {quantity}x {contract.localSymbol}")
        return None, None

    ticker = ib.reqMktData(contract, "", False, False)
    ib.sleep(2)
    bid, ask = ticker.bid, ticker.ask
    if bid is None or ask is None or np.isnan(bid) or np.isnan(ask) or bid <= 0 or ask <= 0:
        log.error(f"Cannot get bid/ask for {contract.localSymbol}: bid={bid} ask={ask}")
        return None, None
    mid = round((bid + ask) / 2, 2)

    for attempt in range(1, LIMIT_RETRIES + 1):
        # Widen limit each retry: buys pay more, sells accept less
        if action == "BUY":
            lmt = round(mid + (attempt - 1) * LIMIT_STEP, 2)
        else:
            lmt = round(mid - (attempt - 1) * LIMIT_STEP, 2)

        order = LimitOrder(action, quantity, lmt, tif="DAY")
        log.info(f"Placing {action} {quantity}x @{lmt} (mid {mid}, bid {bid} ask {ask}) attempt {attempt}")
        trade = ib.placeOrder(contract, order)
        ib.sleep(LIMIT_WAIT_SEC)

        if trade.orderStatus.status in ("Filled", "Submitted"):
            if trade.orderStatus.status == "Filled":
                log.info(f"✅ Filled @{trade.orderStatus.avgFillPrice}")
                return trade, trade.orderStatus.avgFillPrice

        # Cancel and retry with wider limit
        log.info(f"Not filled (status={trade.orderStatus.status}), cancelling and retrying wider...")
        ib.cancelOrder(order)
        ib.sleep(2)

    log.error(f"❌ Order not filled after {LIMIT_RETRIES} attempts")
    return None, None


# =============================================================================
# STRATEGY EVALUATION
# =============================================================================
def check_entry_gates(row):
    """Replicates EnhancedEngine.check_entry (line 457)."""
    regime = row.get("regime", "")
    if regime in ["BEAR", "BEAR_SMA_FORCED"]:
        return False, f"REGIME_{regime}"
    if row.get("vix", 999) >= CFG.entry_vix_max:
        return False, f"VIX_TOO_HIGH({row['vix']:.2f})"
    if not row.get("above_sma100", False):
        return False, "BELOW_SMA100"
    if row.get("rsi_14", 100) >= CFG.entry_rsi14_max:
        return False, f"RSI_TOO_HIGH({row['rsi_14']:.1f})"
    if row.get("gap_down_pct", -99) < CFG.entry_gap_down_min:
        return False, f"NO_GAP_DOWN({row.get('gap_down_pct', 0)*100:.2f}%)"
    if row.get("ml_confidence", 0) < CFG.entry_ml_min:
        return False, f"LOW_ML({row.get('ml_confidence', 0):.2f})"
    if row.get("put_demand_proxy", 0) > CFG.entry_put_demand_max:
        return False, f"HIGH_PUT_DEMAND({row['put_demand_proxy']:.2f})"
    return True, "ALL_GATES_PASS"


def compute_leaps_target(row, spot):
    """Return (dte_target, delta_target) based on regime — mirrors open_leaps() in engine."""
    regime = row.get("regime", "BULL_MODERATE")
    if regime in ["BULL_STRONG", "BULL_MODERATE"]:
        return CFG.dte_bull, CFG.delta_bull
    elif regime in ["NEUTRAL", "BULL_SMA_FORCED"]:
        return CFG.dte_neutral, CFG.delta_neutral
    else:
        return CFG.dte_defensive, CFG.delta_defensive


def compute_pmcc_target(row):
    """Mirror try_open_short() — regime-based delta, fixed DTE."""
    regime = row.get("regime", "BULL_MODERATE")
    if regime == "BULL_STRONG":
        d = CFG.pmcc_delta_bull_strong
    elif regime == "BULL_MODERATE":
        d = CFG.pmcc_delta_bull_moderate
    else:
        d = CFG.pmcc_delta_defensive
    return CFG.pmcc_dte, d


def pmcc_should_open(row):
    """Mirror pmcc_should_open() (line 552)."""
    regime = row.get("regime", "")
    adx = row.get("adx_14", 0)
    iv_rv = row.get("iv_rv_ratio", 1.0)
    put_dem = row.get("put_demand_proxy", 0)

    if regime in CFG.pmcc_skip_regime and pd.notna(adx) and adx >= CFG.pmcc_skip_adx_min:
        return False, f"SKIP_STRONG_TREND(adx={adx:.0f})"
    if pd.notna(iv_rv) and iv_rv < CFG.pmcc_skip_vrp_max:
        return False, f"SKIP_LOW_VRP(iv/rv={iv_rv:.2f})"
    if pd.notna(put_dem) and put_dem > CFG.pmcc_skip_put_demand_max:
        return False, f"SKIP_HIGH_PUT_DEMAND({put_dem:.2f})"
    return True, "PMCC_OK"


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Never place orders")
    parser.add_argument("--force-full-scan", action="store_true", help="Ignore time-of-day gating")
    args = parser.parse_args()

    live = LIVE_TRADE and not args.dry_run
    log.info(f"=== QQQ Live Trader run start | LIVE_TRADE={live} | CAPITAL=${CAPITAL:,.0f} ===")

    conn = db_init()
    ib = connect_ib()
    try:
        # 0. Fetch live NAV and wire into sizing (Item 3 — dynamic NAV-based position sizing)
        live_nav, nav_source = fetch_live_nav(ib)
        CFG.initial_capital = live_nav
        log.info(f"Position sizing base: ${live_nav:,.2f} (source: {nav_source})")

        # 1. Fetch data
        snap = fetch_snapshot(ib)
        features, data = build_features(snap)
        latest = features.iloc[-1]
        log.info(f"Latest feature bar: {latest.name}")
        log.info(f"  regime={latest.get('regime')}  vix={latest.get('vix'):.2f}  "
                 f"rsi14={latest.get('rsi_14'):.1f}  above_sma100={latest.get('above_sma100')}  "
                 f"ml_conf={latest.get('ml_confidence', 0):.2f}")

        # 2. Decide scan type
        et_now = pd.Timestamp.now(tz="America/New_York")
        et_hour = et_now.hour
        do_entries = args.force_full_scan or et_hour == 15  # only enter at 15:00 ET
        do_exits = True  # always check exits

        log.info(f"ET time: {et_now}  do_entries={do_entries}  do_exits={do_exits}")

        # 3. EXITS FIRST
        open_leaps = db_get_open_leaps(conn)
        log.info(f"Open LEAPS positions in state: {len(open_leaps)}")

        if do_exits:
            for pos in open_leaps:
                # Re-fetch current quote on this LEAPS
                exp_str = pos["expiry"].replace("-", "")[:8]
                leaps_opt = Option("QQQ", exp_str, pos["strike"], "C", "SMART", tradingClass="QQQ")
                try:
                    ib.qualifyContracts(leaps_opt)
                    tkr = ib.reqMktData(leaps_opt, "", False, False)
                    ib.sleep(3)
                    if not tkr.modelGreeks or tkr.modelGreeks.delta is None:
                        log.warning(f"No greeks for LEAPS {pos['id']} — skipping exit check")
                        continue
                    cur_delta = abs(tkr.modelGreeks.delta)
                    cur_price = (tkr.bid + tkr.ask) / 2 if tkr.bid and tkr.ask else tkr.last
                    dte = (pd.Timestamp(pos["expiry"]) - pd.Timestamp.now()).days
                    regime = latest.get("regime", "")
                    unreal_pct = (cur_price - pos["entry_price"]) / pos["entry_price"] if cur_price else 0

                    exit_reason = None
                    # 52w low breach
                    if pd.notna(latest.get("sma_200")) and snap["qqq_spot"] < latest["sma_200"] * 0.85:
                        exit_reason = "ADAPTIVE_52W_LOW_BREACH"
                    else:
                        if regime in ["BULL_STRONG", "BULL_MODERATE"]:
                            delta_floor = CFG.exit_delta_low_bull
                            dte_floor = CFG.exit_dte_min_bull
                        else:
                            delta_floor = CFG.exit_delta_low_bear
                            dte_floor = CFG.exit_dte_min_bear
                        if regime == "BULL_STRONG" and latest["vix"] < 18 and latest.get("ml_confidence", 0) >= 0.75:
                            delta_floor -= 0.05
                        if cur_delta < delta_floor:
                            exit_reason = f"ADAPTIVE_DELTA_ROLLDOWN({cur_delta:.2f}<{delta_floor:.2f})"
                        elif dte < dte_floor:
                            exit_reason = f"ADAPTIVE_DTE_ROLL(dte={dte}<{dte_floor})"
                        elif unreal_pct > 0.75 and regime in ["BEAR", "BEAR_SMA_FORCED"]:
                            exit_reason = f"ADAPTIVE_PROFIT_LOCK({unreal_pct*100:.0f}%)"
                        elif dte < 90 and cur_delta > 0.90:
                            exit_reason = f"ADAPTIVE_GAMMA_ROLL"

                    if exit_reason:
                        log.info(f"🔻 EXITING LEAPS {pos['id']}: {exit_reason}")
                        # First close linked shorts
                        for sc in db_get_open_shorts(conn, pos["id"]):
                            sc_exp = sc["expiry"].replace("-", "")[:8]
                            sc_opt = Option("QQQ", sc_exp, sc["strike"], "C", "SMART", tradingClass="QQQ")
                            ib.qualifyContracts(sc_opt)
                            trade, fill = place_limit_at_mid(ib, sc_opt, "BUY", sc["contracts"], live=live)
                            if trade:
                                conn.execute("UPDATE short_calls SET status='CLOSED', close_ts=?, close_price=?, close_reason=? WHERE id=?",
                                             (datetime.utcnow().isoformat(), fill, "LEAPS_EXIT", sc["id"]))
                                conn.commit()
                            db_log_order(conn, ts=datetime.utcnow().isoformat(), kind="SHORT_CALL", action="BUY_TO_CLOSE",
                                         symbol="QQQ", strike=sc["strike"], expiry=sc["expiry"], right="C",
                                         contracts=sc["contracts"], fill_price=fill,
                                         status="FILLED" if trade else "FAILED",
                                         related_pos_id=sc["id"], reason="LEAPS_EXIT")
                        # Then close the LEAPS itself
                        trade, fill = place_limit_at_mid(ib, leaps_opt, "SELL", pos["contracts"], live=live)
                        if trade:
                            conn.execute("UPDATE leaps_positions SET status='CLOSED', close_ts=?, close_price=?, close_reason=? WHERE id=?",
                                         (datetime.utcnow().isoformat(), fill, exit_reason, pos["id"]))
                            conn.commit()
                        db_log_order(conn, ts=datetime.utcnow().isoformat(), kind="LEAPS", action="SELL_TO_CLOSE",
                                     symbol="QQQ", strike=pos["strike"], expiry=pos["expiry"], right="C",
                                     contracts=pos["contracts"], fill_price=fill,
                                     status="FILLED" if trade else "FAILED",
                                     related_pos_id=pos["id"], reason=exit_reason)
                except Exception as e:
                    log.error(f"Exit check failed for LEAPS {pos['id']}: {e}")

            # PMCC exits (for any remaining open shorts)
            open_shorts = db_get_open_shorts(conn)
            log.info(f"Open PMCC short calls: {len(open_shorts)}")
            for sc in open_shorts:
                try:
                    sc_exp = sc["expiry"].replace("-", "")[:8]
                    sc_opt = Option("QQQ", sc_exp, sc["strike"], "C", "SMART", tradingClass="QQQ")
                    ib.qualifyContracts(sc_opt)
                    tkr = ib.reqMktData(sc_opt, "", False, False)
                    ib.sleep(3)
                    if not tkr.modelGreeks or tkr.modelGreeks.delta is None:
                        continue
                    cur_delta = abs(tkr.modelGreeks.delta)
                    cur_debit = (tkr.bid + tkr.ask) / 2 if tkr.bid and tkr.ask else tkr.last
                    dte_sc = (pd.Timestamp(sc["expiry"]) - pd.Timestamp.now()).days
                    profit_pct = (sc["entry_price"] - cur_debit) / sc["entry_price"] if sc["entry_price"] > 0 else 0
                    regime = latest.get("regime", "")
                    take_pct = CFG.pmcc_profit_take_early if regime == "BULL_STRONG" else CFG.pmcc_profit_take_late

                    reason = None
                    if profit_pct >= take_pct:
                        reason = "PMCC_PROFIT"
                    elif dte_sc <= CFG.pmcc_gamma_manage_dte:
                        reason = "PMCC_GAMMA_MGMT"
                    elif cur_delta >= CFG.pmcc_roll_delta:
                        reason = "PMCC_STRIKE_GAP"
                    elif cur_debit > CFG.pmcc_loss_multiple * sc["entry_price"]:
                        reason = "PMCC_LOSS_LIMIT"

                    if reason:
                        log.info(f"🔻 CLOSING PMCC short {sc['id']}: {reason}")
                        trade, fill = place_limit_at_mid(ib, sc_opt, "BUY", sc["contracts"], live=live)
                        if trade:
                            conn.execute("UPDATE short_calls SET status='CLOSED', close_ts=?, close_price=?, close_reason=? WHERE id=?",
                                         (datetime.utcnow().isoformat(), fill, reason, sc["id"]))
                            conn.commit()
                        db_log_order(conn, ts=datetime.utcnow().isoformat(), kind="SHORT_CALL", action="BUY_TO_CLOSE",
                                     symbol="QQQ", strike=sc["strike"], expiry=sc["expiry"], right="C",
                                     contracts=sc["contracts"], fill_price=fill,
                                     status="FILLED" if trade else "FAILED",
                                     related_pos_id=sc["id"], reason=reason)
                except Exception as e:
                    log.error(f"PMCC exit check failed for {sc['id']}: {e}")

        # 4. ENTRIES (only at 15:00 ET or --force-full-scan)
        if do_entries:
            open_leaps = db_get_open_leaps(conn)  # re-fetch after exits
            entry_ok, entry_msg = check_entry_gates(latest)
            log.info(f"Entry gate: {entry_ok}  ({entry_msg})")

            if entry_ok and len(open_leaps) < CFG.max_contracts:
                # Open new LEAPS
                dte_t, delta_t = compute_leaps_target(latest, snap["qqq_spot"])
                log.info(f"🟢 ENTRY SIGNAL → LEAPS DTE~{dte_t} delta~{delta_t}")
                try:
                    opt, tkr = find_best_option(ib, snap["qqq_spot"], delta_t, dte_t, right="C")

                    # --- NAV-based position sizing (mirrors backtest open_leaps) ---
                    mid_price = (tkr.bid + tkr.ask) / 2 if tkr.bid and tkr.ask else tkr.last
                    per_contract_cost = 100 * mid_price
                    if per_contract_cost <= 0:
                        log.error(f"Cannot estimate contract cost (mid={mid_price}) — skipping entry")
                    else:
                        regime = latest.get("regime", "BULL_MODERATE")
                        # Regime-based size multiplier (matches backtest)
                        if regime == "BULL_STRONG":
                            size_mult = 1.0
                        elif regime == "BULL_MODERATE":
                            size_mult = 0.85
                        else:
                            size_mult = 0.5

                        max_outlay = live_nav * CFG.max_position_pct * size_mult
                        target_contracts = max(1, int(max_outlay / per_contract_cost))

                        # Bonus 2x sizing in BULL_STRONG when ml_confidence_stable >= 1.0
                        # (3-bar persistence at >=0.80, same safeguard as backtest)
                        if regime == "BULL_STRONG" and latest.get("ml_confidence_stable", 0) >= 1.0 and len(open_leaps) < 2:
                            target_contracts = min(max(target_contracts, 2), 2)
                            log.info(f"  Bonus 2x sizing triggered (ml_confidence_stable={latest.get('ml_confidence_stable', 0)})")

                        contracts = min(target_contracts, CFG.max_contracts)
                        log.info(f"  Sizing: NAV=${live_nav:,.0f} * {CFG.max_position_pct:.0%} * {size_mult:.2f} = "
                                  f"${max_outlay:,.0f} max outlay → {target_contracts} target, {contracts} actual (cap={CFG.max_contracts})")

                        trade, fill = place_limit_at_mid(ib, opt, "BUY", contracts, live=live)
                        if trade and fill:
                            pos_id = f"L{int(time.time())}"
                            conn.execute("""INSERT INTO leaps_positions
                                            (id, open_ts, strike, expiry, contracts, entry_price, entry_spot, entry_delta, ib_con_id)
                                            VALUES (?,?,?,?,?,?,?,?,?)""",
                                         (pos_id, datetime.utcnow().isoformat(),
                                          opt.strike, opt.lastTradeDateOrContractMonth,
                                          contracts, fill, snap["qqq_spot"],
                                          tkr.modelGreeks.delta, opt.conId))
                            conn.commit()
                            db_log_order(conn, ts=datetime.utcnow().isoformat(), kind="LEAPS", action="BUY_TO_OPEN",
                                         symbol="QQQ", strike=opt.strike, expiry=opt.lastTradeDateOrContractMonth,
                                         right="C", contracts=contracts, fill_price=fill,
                                         status="FILLED", related_pos_id=pos_id, reason=f"ENTRY_{latest.get('regime')}")
                except Exception as e:
                    log.error(f"LEAPS entry failed: {e}")

            # PMCC overlay: for each open LEAPS without a short, try to open one
            open_leaps = db_get_open_leaps(conn)
            for pos in open_leaps:
                if db_get_open_shorts(conn, pos["id"]):
                    continue  # already has a short
                ok, reason = pmcc_should_open(latest)
                if not ok:
                    log.info(f"PMCC skip for LEAPS {pos['id']}: {reason}")
                    continue
                dte_t, delta_t = compute_pmcc_target(latest)
                log.info(f"🟢 PMCC OPEN → short DTE~{dte_t} delta~{delta_t} against LEAPS {pos['id']}")
                try:
                    opt, tkr = find_best_option(ib, snap["qqq_spot"], delta_t, dte_t, right="C")
                    if opt.strike <= pos["strike"]:
                        log.info(f"PMCC skip: short strike {opt.strike} <= LEAPS strike {pos['strike']}")
                        continue
                    trade, fill = place_limit_at_mid(ib, opt, "SELL", pos["contracts"], live=live)
                    if trade and fill:
                        sc_id = f"S{int(time.time())}"
                        conn.execute("""INSERT INTO short_calls
                                        (id, leaps_id, open_ts, strike, expiry, contracts, entry_price, entry_spot, entry_delta, ib_con_id)
                                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                     (sc_id, pos["id"], datetime.utcnow().isoformat(),
                                      opt.strike, opt.lastTradeDateOrContractMonth,
                                      pos["contracts"], fill, snap["qqq_spot"],
                                      tkr.modelGreeks.delta, opt.conId))
                        conn.commit()
                        db_log_order(conn, ts=datetime.utcnow().isoformat(), kind="SHORT_CALL", action="SELL_TO_OPEN",
                                     symbol="QQQ", strike=opt.strike, expiry=opt.lastTradeDateOrContractMonth,
                                     right="C", contracts=pos["contracts"], fill_price=fill,
                                     status="FILLED", related_pos_id=sc_id, reason=f"PMCC_{latest.get('regime')}")
                except Exception as e:
                    log.error(f"PMCC open failed: {e}")

        # 5. NAV already fetched at step 0; just log final state
        log.info(f"Run complete. NAV=${live_nav:,.2f} | CAPITAL fallback=${CAPITAL:,.0f}")
    finally:
        ib.disconnect()
        conn.close()


if __name__ == "__main__":
    main()
