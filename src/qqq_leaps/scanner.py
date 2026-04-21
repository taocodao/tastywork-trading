"""
QQQ LEAPS Live Scanner (Production)
=====================================
Runs at 3:00 PM ET daily. Fetches live market data, builds features,
evaluates ML entry/exit signals, updates virtual portfolio with MTM.

Outputs:
  - VirtualPortfolio update (QQQ_LEAPS account)
  - signal_publisher/qqq_leaps.py → PostgreSQL DB
  - PortfolioManager.publish_public_snapshot() → Vercel
"""
import os
import sys
import math
import logging
import warnings
import json
from pathlib import Path
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# Allow running from project root
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent.parent))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.expanduser("~"), "tastywork-trading", ".env"))
    load_dotenv(ROOT.parent.parent / ".env")  # local dev fallback
except ImportError:
    pass

logger = logging.getLogger("QQQLEAPSScanner")

# Module imports
from .config import QQQLeapsConfig
from .leaps_feature_engineering import build_leaps_features
from .regime_classifier import LeapsRegimeClassifier, REGIME_PARAMS
from .entry_classifier import LeapsEntryClassifier
from .entry_classifier_v2 import LeapsEntryClassifierV2
from .strike_optimizer import bs_call_price, bs_call_delta, find_call_strike
from .drawdown_guard import DrawdownGuard, DrawdownAction
from .pmcc_manager import PMCCManager


# ── Persistent scan state (between runs) ──────────────────────────────────────
SCAN_STATE_FILE = Path(os.path.expanduser("~")) / "tastywork-trading" / "data" / "qqq_leaps_scan_state.json"
SCAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class ScanResult:
    action: str           # ENTER / EXIT / HOLD
    regime: str
    confidence: float
    spot: float
    vix: float
    iv_long: float
    signal_date: str

    # ENTER fields
    strike: float = 0.0
    expiry_date: str = ""
    entry_px: float = 0.0
    contracts: int = 0
    delta: float = 0.0

    # EXIT fields
    exit_px: float = 0.0
    exit_reason: str = ""

    rationale: str = ""


def _load_scan_state() -> dict:
    if SCAN_STATE_FILE.exists():
        try:
            return json.loads(SCAN_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_scan_state(state: dict):
    SCAN_STATE_FILE.write_text(json.dumps(state, indent=2))


def run_qqq_leaps_scan(config: QQQLeapsConfig = None) -> Optional[ScanResult]:
    """
    Production scanner — orchestrates all ML layers and updates virtual portfolio.

    Returns ScanResult describing the action taken (or HOLD).
    """
    config = config or QQQLeapsConfig()
    state  = _load_scan_state()

    logger.info("=" * 60)
    logger.info("QQQ LEAPS Live Scanner")
    logger.info(f"  Date: {date.today().isoformat()}")
    logger.info("=" * 60)

    # ── 1. Fetch live market data ────────────────────────────────────────────
    logger.info("Fetching live market data...")
    end_str  = date.today().isoformat()
    start_str = (date.today() - timedelta(days=400)).isoformat()  # 400 days for feature computation

    try:
        qqq_raw  = yf.download("QQQ",   start=start_str, end=end_str, auto_adjust=True, progress=False)
        vix_raw  = yf.download("^VIX",  start=start_str, end=end_str, progress=False)
        vix3m_raw= yf.download("^VIX3M",start=start_str, end=end_str, progress=False)
        irx_raw  = yf.download("^IRX",  start=start_str, end=end_str, progress=False)
    except Exception as e:
        logger.error(f"Market data download failed: {e}")
        return None

    # Squeeze multi-level columns
    def _sq(df):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        return df

    qqq_raw   = _sq(qqq_raw)
    vix_raw   = _sq(vix_raw)
    vix3m_raw = _sq(vix3m_raw)
    irx_raw   = _sq(irx_raw)

    if qqq_raw.empty:
        logger.error("QQQ data is empty — aborting scan.")
        return None

    qqq_close = qqq_raw["Close"].squeeze()
    qqq_open  = qqq_raw["Open"].squeeze()
    vix       = vix_raw["Close"].reindex(qqq_close.index).ffill().fillna(20.0).squeeze()
    vix3m     = vix3m_raw["Close"].reindex(qqq_close.index).ffill().fillna(21.0).squeeze()
    rf_series = (irx_raw["Close"] / 100.0).reindex(qqq_close.index).ffill().fillna(0.045).squeeze()

    # Current market values
    spot  = float(qqq_close.iloc[-1])
    vix_v = float(vix.iloc[-1])
    rf    = float(rf_series.iloc[-1])

    # IV: regime-conditional VIX multiplier (VIX1Y not available via yfinance)
    iv_mult = 1.30 if vix_v < 18 else (1.22 if vix_v < 25 else (1.10 if vix_v < 35 else 0.65))
    iv_long = (vix_v / 100.0) * iv_mult
    iv_short = (vix_v / 100.0) * config.iv_scale_short

    logger.info(f"  QQQ={spot:.2f}  VIX={vix_v:.1f}  IV(1Y proxy)={iv_long:.2%}  rf={rf:.3f}")

    # ── 2. Build feature matrix ──────────────────────────────────────────────
    logger.info("Building feature matrix...")
    master = build_leaps_features(qqq_close, qqq_open, vix, vix3m, rf_series)

    # Regime classification
    regime_clf = LeapsRegimeClassifier(config)
    master     = regime_clf.apply_to_master(master)

    today_row = master.iloc[-1]
    regime    = str(today_row.get("leaps_regime", "CHOPPY"))
    above_100 = bool(today_row.get("above_sma100", True))

    logger.info(f"  Regime: {regime} | Above SMA100: {above_100}")

    # ── 3. Load ML model (most recent checkpoint if available) ───────────────
    clf_v2 = LeapsEntryClassifierV2()
    ml_loaded = clf_v2.load()
    if not ml_loaded:
        logger.info("  No saved v2 model — using v1 heuristic")

    # ── 4. Evaluate DrawdownGuard on open positions ──────────────────────────
    from virtual_portfolio_manager import get_portfolio_manager
    pm  = get_portfolio_manager()
    vp  = pm.get("QQQ_LEAPS")

    # Check existing positions for drawdown/structural exits
    open_leaps = [p for p in vp.positions if p.get("type") == "LEAPS_CALL"]

    if open_leaps:
        dd_guard  = DrawdownGuard(config)
        qqq_52w   = float(qqq_close.tail(252).min()) if len(qqq_close) >= 252 else float(qqq_close.min())

        actions_taken = []
        for pos in open_leaps:
            try:
                expiry_dt = date.fromisoformat(pos["expiry"])
                l_dte     = (expiry_dt - date.today()).days
                T         = max(l_dte / 365.0, 1 / 365.0)
                l_delta   = bs_call_delta(spot, pos["strike"], T, rf, iv_long)

                action = dd_guard.evaluate(
                    l_delta, l_dte, spot, qqq_52w, regime,
                    has_short_call=False
                )
                actions_taken.append(action)
            except Exception as e:
                logger.warning(f"DrawdownGuard eval error: {e}")

        # If any position triggers EXIT, close all
        if any(a in (DrawdownAction.EXIT_POSITION, DrawdownAction.CLOSE_52W_LOW) for a in actions_taken):
            # Compute exit price from BS
            first_pos  = open_leaps[0]
            expiry_dt  = date.fromisoformat(first_pos["expiry"])
            l_dte      = max((expiry_dt - date.today()).days, 1)
            exit_px    = bs_call_price(spot, first_pos["strike"], l_dte / 365.0, rf, iv_long)
            exit_reason = "DRAWDOWN_GUARD_52W_LOW" if any(a == DrawdownAction.CLOSE_52W_LOW for a in actions_taken) else "STRUCTURAL_IMPAIRMENT"

            vp.leaps_exit(exit_px, reason=exit_reason)
            nav = pm.leaps_daily_mtm(spot, iv_long, rf)
            pm.publish_public_snapshot()

            _save_scan_state({
                "last_scan_date": date.today().isoformat(),
                "action": "EXIT",
                "reason": exit_reason,
                "exit_px": exit_px,
            })

            return ScanResult(
                action="EXIT", regime=regime, confidence=0.0,
                spot=spot, vix=vix_v, iv_long=iv_long,
                signal_date=date.today().isoformat(),
                exit_px=exit_px, exit_reason=exit_reason,
                rationale=f"DrawdownGuard triggered: {exit_reason}",
            )

        # MTM existing positions (no entry/exit)
        nav = pm.leaps_daily_mtm(spot, iv_long, rf)
        logger.info(f"  Existing positions MTM: nav=${nav:.0f}")

    # ── 5. Entry signal evaluation ────────────────────────────────────────────
    leaps_params = REGIME_PARAMS.get(regime, REGIME_PARAMS["CHOPPY"])
    n_open = len(open_leaps)

    if not leaps_params.allow_entry:
        logger.info(f"  No entry — BEAR regime gate")
        _save_scan_state({"last_scan_date": date.today().isoformat(), "action": "HOLD"})
        nav = pm.leaps_daily_mtm(spot, iv_long, rf)
        pm.publish_public_snapshot()
        return ScanResult(action="HOLD", regime=regime, confidence=0.0,
                          spot=spot, vix=vix_v, iv_long=iv_long,
                          signal_date=date.today().isoformat(),
                          rationale="BEAR regime — no entries")

    if vix_v > config.entry_vix_max:
        logger.info(f"  No entry — VIX panic gate ({vix_v:.1f} > {config.entry_vix_max})")
        _save_scan_state({"last_scan_date": date.today().isoformat(), "action": "HOLD"})
        nav = pm.leaps_daily_mtm(spot, iv_long, rf)
        pm.publish_public_snapshot()
        return ScanResult(action="HOLD", regime=regime, confidence=0.0,
                          spot=spot, vix=vix_v, iv_long=iv_long,
                          signal_date=date.today().isoformat(),
                          rationale=f"VIX panic gate: {vix_v:.1f}")

    if n_open >= config.max_positions:
        logger.info(f"  No entry — max positions reached ({n_open})")
        nav = pm.leaps_daily_mtm(spot, iv_long, rf)
        pm.publish_public_snapshot()
        _save_scan_state({"last_scan_date": date.today().isoformat(), "action": "HOLD"})
        return ScanResult(action="HOLD", regime=regime, confidence=0.0,
                          spot=spot, vix=vix_v, iv_long=iv_long,
                          signal_date=date.today().isoformat(),
                          rationale=f"Max positions {n_open}/{config.max_positions}")

    # Baseline gate: gap-down + above SMA100
    is_gap_down = bool(today_row.get("is_gap_down", False))
    baseline_signal = is_gap_down and above_100

    # ML gate
    if ml_loaded:
        ml_conf, ml_threshold = clf_v2.predict_with_threshold(today_row, regime)
    else:
        ml_conf = LeapsEntryClassifier()._heuristic_confidence(today_row)
        ml_threshold = config.entry_ml_confidence_min

    signal_fires = ml_conf >= ml_threshold
    logger.info(f"  Entry gate: baseline={baseline_signal} ml_conf={ml_conf:.3f} threshold={ml_threshold:.2f} signal={signal_fires}")

    if not signal_fires:
        nav = pm.leaps_daily_mtm(spot, iv_long, rf)
        pm.publish_public_snapshot()
        _save_scan_state({"last_scan_date": date.today().isoformat(), "action": "HOLD"})
        return ScanResult(action="HOLD", regime=regime, confidence=ml_conf,
                          spot=spot, vix=vix_v, iv_long=iv_long,
                          signal_date=date.today().isoformat(),
                          rationale=f"No entry signal: ml_conf={ml_conf:.3f} < {ml_threshold:.2f}")

    # ── 6. Size the trade ────────────────────────────────────────────────────
    T_entry  = leaps_params.dte / 365.0
    strike   = find_call_strike(spot, T_entry, rf, iv_long, leaps_params.delta)
    entry_px = bs_call_price(spot, strike, T_entry, rf, iv_long)
    entry_px = max(entry_px, 0.01)
    expiry_date = (date.today() + timedelta(days=leaps_params.dte)).isoformat()

    # NAV = cash + current positions MTM
    positions_mv = vp.leaps_mtm(spot, iv_long, rf)
    nav = vp.cash + positions_mv
    max_outlay = nav * config.max_position_pct * leaps_params.size_multiplier
    contracts  = max(1, int(max_outlay / (100 * entry_px)))
    contracts  = min(contracts, config.max_contracts_hard_cap)

    # 5% NAV cap above $150k
    if nav > 150_000:
        contracts = min(contracts, max(1, int(0.05 * nav / (100 * entry_px))))

    l_delta = bs_call_delta(spot, strike, T_entry, rf, iv_long)
    rationale = (
        f"Regime: {regime} | ML conf: {ml_conf:.2%} | "
        f"VIX: {vix_v:.1f} | Gap-dn: {is_gap_down} | "
        f"Strike: {strike:.1f} | DTE: {leaps_params.dte} | delta={l_delta:.2f}"
    )

    logger.info(f"  ENTRY SIGNAL | strike={strike:.1f} px=${entry_px:.2f} x{contracts} contracts")
    logger.info(f"  {rationale}")

    # ── 7. Execute on virtual account ────────────────────────────────────────
    ok = vp.leaps_enter(
        spot=spot, strike=strike, expiry_date=expiry_date,
        entry_px=entry_px, contracts=contracts,
        regime=regime, confidence=ml_conf,
    )

    if ok:
        nav = pm.leaps_daily_mtm(spot, iv_long, rf)
        pm.publish_public_snapshot()
        _save_scan_state({
            "last_scan_date": date.today().isoformat(),
            "action": "ENTER",
            "strike": strike,
            "expiry": expiry_date,
            "entry_px": entry_px,
            "contracts": contracts,
        })

        # Publish to DB
        try:
            from signal_publisher.qqq_leaps import publish_qqq_leaps_signal
            publish_qqq_leaps_signal(
                action="ENTER",
                regime=regime,
                confidence=ml_conf,
                spot=spot,
                strike=strike,
                expiry_date=expiry_date,
                entry_px=entry_px,
                contracts=contracts,
                delta=l_delta,
                rationale=rationale,
            )
        except Exception as e:
            logger.warning(f"Signal publish failed (non-fatal): {e}")

        return ScanResult(
            action="ENTER", regime=regime, confidence=ml_conf,
            spot=spot, vix=vix_v, iv_long=iv_long,
            signal_date=date.today().isoformat(),
            strike=strike, expiry_date=expiry_date,
            entry_px=entry_px, contracts=contracts, delta=l_delta,
            rationale=rationale,
        )
    else:
        logger.warning("Virtual account rejected ENTER — insufficient cash")
        nav = pm.leaps_daily_mtm(spot, iv_long, rf)
        pm.publish_public_snapshot()
        return ScanResult(action="HOLD", regime=regime, confidence=ml_conf,
                          spot=spot, vix=vix_v, iv_long=iv_long,
                          signal_date=date.today().isoformat(),
                          rationale="Insufficient cash in virtual account")
