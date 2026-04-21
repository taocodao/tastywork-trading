#!/usr/bin/env python3
"""
================================================================
QQQ LEAPS ML-Optimized Strategy — Backtest Engine
================================================================
Proof-of-concept backtest demonstrating all 6 ML layers:
  Layer A: Regime Classifier (HMM + SMA)
  Layer B: Entry Classifier (XGBoost primary + meta)
  Layer C: Strike & Roll Optimizer (event-driven rolling)
  Layer D: PMCC Manager (deterministic short call overlay)
  Layer E: Drawdown Guard (protective put triggers)
  Layer F: Liquidity Scorer (pre-trade gate)

Walk-forward ML training:
  - Train on 48-month window ending at current date
  - Retrain every 3 months (quarterly updates)
  - 5-day embargo between training end and test start
  - Never uses future data in features or training labels

Run:
  python -m src.qqq_leaps.backtest_engine
  python -m src.qqq_leaps.backtest_engine --mode baseline --capital 50000

Modes:
  baseline      : Replicate backtest_leaps.py (gap-down + SMA only)
  ml_optimized  : All 6 ML layers active (default)
================================================================
"""
import sys
import math
import warnings
import logging
import argparse
from pathlib import Path
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

ROOT     = Path(__file__).parent
SRC_ROOT = ROOT.parent
sys.path.insert(0, str(SRC_ROOT.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[
        logging.FileHandler(ROOT.parent.parent / "qqq-leaps" / "backtest_ml.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("QQQ_LEAPS_BT")

# ── Local imports ──────────────────────────────────────────────────────────────
from .config import QQQLeapsConfig
from .leaps_feature_engineering import build_leaps_features, add_forward_labels
from .regime_classifier import LeapsRegimeClassifier, REGIME_PARAMS
from .entry_classifier import LeapsEntryClassifier          # v1: heuristic fallback
from .entry_classifier_v2 import LeapsEntryClassifierV2     # v2: LightGBM specialists
from .strike_optimizer import StrikeOptimizer, bs_call_price, bs_call_delta, find_call_strike
from .pmcc_manager import PMCCManager, _next_monthly_friday
from .drawdown_guard import DrawdownGuard, DrawdownAction
from .liquidity_scorer import estimate_qqq_leaps_liquidity


# ── Position Data Structure ────────────────────────────────────────────────────
@dataclass
class LeapsPosition:
    position_id:      int
    open_date:        pd.Timestamp
    strike:           float
    expiry:           pd.Timestamp
    entry_price:      float       # Per share
    entry_spot:       float       # QQQ price at entry (for roll trigger Signal C)
    contracts:        int
    iv_at_entry:      float
    rf_at_entry:      float
    regime_at_entry:  str
    ml_confidence:    float       # Layer B confidence at entry

    short_call:              Optional[dict] = None   # Active PMCC short call
    protective_put_active:   bool           = False   # Layer E: put hedge active
    rolls:                   int            = 0
    pmcc_income:             float          = 0.0
    protective_put_cost:     float          = 0.0
    last_bear_roll_date:     Optional[pd.Timestamp] = None  # Bear-regime roll cooldown (60d)

    def dte(self, current_date: pd.Timestamp) -> int:
        return (self.expiry - current_date).days

    def current_value(self, spot, current_date, iv, rf) -> float:
        T = max(self.dte(current_date) / 365.0, 1 / 365.0)
        return bs_call_price(spot, self.strike, T, rf, iv)

    def pnl_pct(self, current_price: float) -> float:
        if self.entry_price <= 0:
            return 0.0
        return (current_price - self.entry_price) / self.entry_price


# ── Data Loading ───────────────────────────────────────────────────────────────
def load_market_data(start: str = "2010-01-01", end: str = "2026-04-18") -> dict:
    """Downloads and aligns QQQ, VIX, VIX3M, IRX data."""
    log.info(f"Downloading market data ({start} -> {end})...")

    def _squeeze(df):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        return df

    qqq_raw  = _squeeze(yf.download("QQQ",   start="2008-01-01", end=end, auto_adjust=True, progress=False))
    vix_raw  = _squeeze(yf.download("^VIX",  start="2008-01-01", end=end, progress=False))
    vix3m_raw= _squeeze(yf.download("^VIX3M",start="2008-01-01", end=end, progress=False))
    vix1y_raw= _squeeze(yf.download("^VIX1Y",start="2008-01-01", end=end, progress=False))
    irx_raw  = _squeeze(yf.download("^IRX",  start="2008-01-01", end=end, progress=False))

    qqq_close = qqq_raw["Close"].squeeze()
    qqq_open  = qqq_raw["Open"].squeeze()
    vix       = vix_raw["Close"].reindex(qqq_close.index).ffill().fillna(20.0).squeeze()
    vix3m     = vix3m_raw["Close"].reindex(qqq_close.index).ffill().fillna(21.0).squeeze()
    if not vix1y_raw.empty and "Close" in vix1y_raw:
        vix1y = vix1y_raw["Close"].reindex(qqq_close.index).ffill().squeeze()
    else:
        vix1y = None
        
    rf        = (irx_raw["Close"] / 100.0).reindex(qqq_close.index).ffill().fillna(0.045).squeeze()

    log.info(f"Data loaded: {len(qqq_close)} QQQ trading days.")
    data_dict = {
        "qqq_close": qqq_close,
        "qqq_open":  qqq_open,
        "vix":       vix,
        "vix3m":     vix3m,
        "rf":        rf,
    }
    if vix1y is not None:
        data_dict["vix1y"] = vix1y
    return data_dict


# ── Walk-Forward ML Training ───────────────────────────────────────────────────
def build_walk_forward_models(
    master: pd.DataFrame,
    config: QQQLeapsConfig,
    mode: str = "ml_optimized",
) -> dict:
    """
    Pre-trains v2 LightGBM regime-specialist entry classifiers on rolling windows.
    Returns: {date -> LeapsEntryClassifierV2} — one ensemble per quarterly retrain point.

    Walk-forward schedule:
      - Train window: 48 months
      - Retrain every 3 months
      - 5-day embargo between train end and first prediction
    """
    if mode == "baseline":
        log.info("Baseline mode — skipping ML training.")
        return {}

    log.info("=" * 60)
    log.info("Walk-Forward ML Training (Layer B v2 — LightGBM Regime Specialists)")
    log.info(f"  Train window: {config.wf_train_months} months | "
             f"Retrain every: {config.wf_step_months} months | "
             f"Embargo: {config.wf_embargo_days} days")
    log.info("=" * 60)

    # Label the FULL dataset (we'll use only the training slice when fitting)
    master_labeled = add_forward_labels(
        master,
        forward_days=config.ml_label_forward_days,
        target_gain=config.ml_label_target_gain,
    )

    models = {}
    all_dates = master_labeled.index

    # Find quarterly retrain points from ~2014 onward (need 4y training data from 2010)
    start_model = pd.Timestamp("2014-01-01")

    current = start_model
    while current < all_dates[-1]:
        train_end   = current - timedelta(days=config.wf_embargo_days)
        train_start = train_end - pd.DateOffset(months=config.wf_train_months)

        train_slice = master_labeled.loc[train_start:train_end].copy()

        if len(train_slice) < 200:
            current += pd.DateOffset(months=config.wf_step_months)
            continue

        log.info(f"  Training model -> active from {current.date()} "
                 f"(train: {train_start.date()} – {train_end.date()}, n={len(train_slice)})")

        clf = LeapsEntryClassifierV2()
        clf.fit(train_slice,
                target_gain=config.ml_label_target_gain,
                forward_days=config.ml_label_forward_days)

        if clf.is_trained:
            for specialist, stats in clf.training_stats.items():
                log.info(f"    [{specialist}] n={stats.n_samples} PR-AUC={stats.pr_auc:.3f} "
                         f"({stats.n_pos}p/{stats.n_neg}n)")
            models[current] = clf
        else:
            log.warning(f"    Training failed for window ending {train_end.date()}")

        current += pd.DateOffset(months=config.wf_step_months)

    log.info(f"Walk-forward complete: {len(models)} model ensembles trained.\n")
    return models


def get_active_model(models: dict, date: pd.Timestamp) -> Optional[LeapsEntryClassifierV2]:
    """Returns the most recently trained model ensemble active at `date`."""
    active_dates = sorted([d for d in models.keys() if d <= date], reverse=True)
    if not active_dates:
        return None
    return models[active_dates[0]]


# ── Main Backtest Loop ─────────────────────────────────────────────────────────
def run_backtest(
    mode: str = "ml_optimized",
    capital: float = 25_000.0,
    start: str = "2019-01-01",
    end: str = "2026-04-18",
) -> dict:
    config = QQQLeapsConfig(initial_capital=capital)

    # Load data
    data = load_market_data(start="2010-01-01", end=end)

    # Build feature matrix
    log.info("Computing feature matrix...")
    master = build_leaps_features(
        data["qqq_close"], data["qqq_open"],
        data["vix"], data["vix3m"], data["rf"]
    )

    # Layer A: Regime classification
    regime_clf = LeapsRegimeClassifier(config)
    master     = regime_clf.apply_to_master(master)

    # Walk-forward ML training
    models = build_walk_forward_models(master, config, mode)

    # Instantiate layers
    strike_opt   = StrikeOptimizer(config)
    pmcc_mgr     = PMCCManager(config)
    dd_guard     = DrawdownGuard(config)

    # IV scaling
    vix1y = data.get("vix1y")
    if vix1y is not None:
        iv_long = (vix1y / 100.0) * config.iv_qqq_premium  # QQQ vol premium over SPX
    else:
        # Regime-conditional fallback from Perplexity research
        v_vals = data["vix"]
        iv_long = pd.Series(index=v_vals.index, dtype=float)
        iv_long[v_vals < 18] = (v_vals[v_vals < 18] / 100.0) * 1.30
        iv_long[(v_vals >= 18) & (v_vals < 25)] = (v_vals[(v_vals >= 18) & (v_vals < 25)] / 100.0) * 1.22
        iv_long[(v_vals >= 25) & (v_vals < 35)] = (v_vals[(v_vals >= 25) & (v_vals < 35)] / 100.0) * 1.10
        iv_long[v_vals >= 35] = (v_vals[v_vals >= 35] / 100.0) * 0.65

    iv_short = data["vix"] / 100.0 * config.iv_scale_short

    # ── Backtest loop ──────────────────────────────────────────────────────────
    trading_days = master.loc[start:end].index
    cash         = capital
    positions:   List[LeapsPosition] = []
    trade_log    = []
    daily_rows   = []
    pos_counter  = 0

    # Counters
    total_entries      = 0
    total_exits_profit = 0
    total_exits_roll   = 0
    total_exits_bear   = 0
    total_exits_dd     = 0
    total_pmcc_opened  = 0
    total_pmcc_closed  = 0
    total_rolls_event  = 0
    ml_blocks          = 0   # Entries blocked by Layer B (confidence too low)
    liq_blocks         = 0   # Entries blocked by Layer F

    log.info(f"\n{'='*60}")
    log.info(f"  QQQ LEAPS BACKTEST: {mode.upper()}")
    log.info(f"  Capital: ${capital:,.0f} | Period: {start} -> {end}")
    log.info(f"{'='*60}\n")

    for i, date in enumerate(trading_days):
        row    = master.loc[date]
        spot   = float(row["qqq_close"])
        iv_l   = float(iv_long.reindex(master.index).loc[date])
        iv_s   = float(iv_short.reindex(master.index).loc[date])
        rf     = float(data["rf"].reindex(master.index).loc[date])
        vix    = float(row["vix"])
        regime = str(row["leaps_regime"])
        above_100 = bool(row["above_sma100"])

        # ── Layer E: Evaluate drawdown guard on all positions ─────────────────
        qqq_52w_low = float(master["qqq_52w_low"].loc[date]) if "qqq_52w_low" in master.columns else 0.0

        for pos in positions:
            cur_val  = pos.current_value(spot, date, iv_l, rf)
            pnl_pct  = pos.pnl_pct(cur_val)
            l_dte    = pos.dte(date)
            l_delta  = bs_call_delta(spot, pos.strike, max(l_dte / 365.0, 1 / 365.0), rf, iv_l)
            
            action   = dd_guard.evaluate(
                l_delta, l_dte, spot, qqq_52w_low, regime, pos.short_call is not None
            )

            if action == DrawdownAction.ROLL_SHORT_CALL_DOWN and pos.short_call:
                # Bear-market adjustment: roll short call from current delta -> 0.50 delta
                roll_dict = pmcc_mgr.roll_short_call_down(pos, spot, date, rf, iv_s, config.dd_rolldown_target_delta)
                if roll_dict:
                    cash -= roll_dict["close_cost"]
                    premium_net = roll_dict["new_call"]["contracts"] * 100 * roll_dict["new_call"]["entry_price"] - config.slippage_for_vix(vix, roll_dict["new_call"]["entry_price"]) * roll_dict["new_call"]["contracts"] - config.commission * roll_dict["new_call"]["contracts"]
                    cash += premium_net
                    roll_dict["new_call"]["premium_collected"] = premium_net
                    pos.short_call = roll_dict["new_call"]
                    trade_log.append({"date": date.date(), "type": "PMCC_ROLL_DOWN",
                                       "cost": round(roll_dict["close_cost"], 2), "new_prem": round(premium_net, 2)})

            elif action == DrawdownAction.EXIT_POSITION:
                # Structural impairment: exit entirely
                proceeds = pos.contracts * 100 * cur_val - config.slippage_for_vix(vix, cur_val) * pos.contracts - config.commission * pos.contracts
                cash += proceeds
                if pos.short_call:
                    sc = pos.short_call
                    T_sc = max((sc["expiry"] - date).days / 365.0, 1 / 365.0)
                    sc_val = bs_call_price(spot, sc["strike"], T_sc, rf, iv_s)
                    cash -= sc["contracts"] * 100 * sc_val
                
                trade_log.append({"date": date.date(), "type": "LEAPS_EXIT_IMPAIRED",
                                  "entry_px": round(pos.entry_price, 2), "exit_px": round(cur_val, 2),
                                  "pnl": round(proceeds - pos.contracts * 100 * pos.entry_price, 2)})
                pos.contracts = 0 # Mark for removal
                
            elif action == DrawdownAction.CLOSE_52W_LOW:
                # Emergency full liquidation due to regime change
                proceeds = pos.contracts * 100 * cur_val - config.slippage_for_vix(vix, cur_val) * pos.contracts - config.commission * pos.contracts
                cash += proceeds
                if pos.short_call:
                    sc = pos.short_call
                    T_sc = max((sc["expiry"] - date).days / 365.0, 1 / 365.0)
                    sc_val = bs_call_price(spot, sc["strike"], T_sc, rf, iv_s)
                    cash -= sc["contracts"] * 100 * sc_val
                    
                trade_log.append({"date": date.date(), "type": "LEAPS_EXIT_52W_LOW",
                                  "entry_px": round(pos.entry_price, 2), "exit_px": round(cur_val, 2),
                                  "pnl": round(proceeds - pos.contracts * 100 * pos.entry_price, 2)})
                pos.contracts = 0

        # Remove closed positions
        positions = [p for p in positions if p.contracts > 0]


        # ── Layer D: PMCC — manage existing short calls ───────────────────────
        if config.pmcc_enabled:
            for pos in positions:
                action_str, cost_val = pmcc_mgr.manage_short_call(pos, spot, date, rf, iv_s)
                sc = pos.short_call

                if action_str in ("CLOSE_50PCT", "FORCE_CLOSE"):
                    cash          -= cost_val + config.commission * (sc["contracts"] if sc else 1)
                    premium_gain   = (sc["premium_collected"] - cost_val) if sc else 0
                    pos.pmcc_income += max(premium_gain, 0)
                    pos.short_call  = None
                    total_pmcc_closed += 1

                elif action_str == "EXPIRED_WORTHLESS":
                    income = sc["premium_collected"] if sc else 0
                    pos.pmcc_income += income
                    pos.short_call   = None
                    total_pmcc_closed += 1

                elif action_str == "EXPIRED_ITM":
                    cash         -= cost_val + config.commission
                    pos.short_call = None
                    total_pmcc_closed += 1

        # ── Layer D: Open new short calls ─────────────────────────────────────
        if config.pmcc_enabled:
            for pos in positions:
                sc_dict = pmcc_mgr.maybe_open_short_call(pos, spot, date, rf, iv_s, above_100)
                if sc_dict:
                    premium = sc_dict["contracts"] * 100 * sc_dict["entry_price"]
                    premium_net = premium - config.slippage_for_vix(vix, sc_dict["entry_price"]) * sc_dict["contracts"] - config.commission * sc_dict["contracts"]
                    cash   += premium_net
                    sc_dict["premium_collected"] = premium_net
                    pos.short_call = sc_dict
                    total_pmcc_opened += 1

        # ── Profit target exits ────────────────────────────────────────────────
        surviving = []
        for pos in positions:
            cur_val = pos.current_value(spot, date, iv_l, rf)
            pnl_ratio = cur_val / pos.entry_price if pos.entry_price > 0 else 1.0

            # Profit target: 60% gain (higher than 50% to let winners run on LEAPS)
            if pnl_ratio >= 1.60:
                proceeds = pos.contracts * 100 * cur_val - config.slippage_for_vix(vix, cur_val) * pos.contracts - config.commission * pos.contracts
                cash    += proceeds
                pnl      = proceeds - pos.contracts * 100 * pos.entry_price

                if pos.short_call:
                    sc   = pos.short_call
                    T_sc = max((sc["expiry"] - date).days / 365.0, 1 / 365.0)
                    sc_val = bs_call_price(spot, sc["strike"], T_sc, rf, iv_s)
                    cash  -= sc["contracts"] * 100 * sc_val
                    total_pmcc_closed += 1

                trade_log.append({
                    "open_date":  pos.open_date.date(), "close_date": date.date(),
                    "type":       "LEAPS_PROFIT", "contracts": pos.contracts,
                    "entry_px":   round(pos.entry_price, 2), "exit_px": round(cur_val, 2),
                    "pnl":        round(pnl, 2), "pmcc_income": round(pos.pmcc_income, 2),
                    "rolls":      pos.rolls, "regime": pos.regime_at_entry,
                    "ml_conf":    round(pos.ml_confidence, 3),
                })
                total_exits_profit += 1
            else:
                surviving.append(pos)
        positions = surviving

        # ── Phase 6: Structural Exit (DTE + Delta) ────────────────────────────
        # Exit any position where time AND delta structural impairment is confirmed
        # separately from the Delta-Guard (which fires earlier at delta < 0.65)
        # This catches positions the guard missed (e.g. no active short call)
        structurally_sound = []
        for pos in positions:
            l_dte   = pos.dte(date)
            l_delta = bs_call_delta(spot, pos.strike, max(l_dte / 365.0, 1 / 365.0), rf, iv_l)
            cur_val = pos.current_value(spot, date, iv_l, rf)

            if l_dte < config.dd_dte_exit_trigger and l_delta < config.dd_delta_exit_trigger:
                # Structural impairment: theta acceleration with no recovery path
                proceeds = pos.contracts * 100 * cur_val - config.slippage_for_vix(vix, cur_val) * pos.contracts - config.commission * pos.contracts
                cash += proceeds
                if pos.short_call:
                    sc = pos.short_call
                    T_sc = max((sc["expiry"] - date).days / 365.0, 1 / 365.0)
                    cash -= sc["contracts"] * 100 * bs_call_price(spot, sc["strike"], T_sc, rf, iv_s)
                trade_log.append({"date": date.date(), "type": "LEAPS_STRUCTURAL_EXIT",
                                  "dte": l_dte, "delta": round(l_delta, 3),
                                  "entry_px": round(pos.entry_price, 2), "exit_px": round(cur_val, 2),
                                  "pnl": round(proceeds - pos.contracts * 100 * pos.entry_price, 2)})
                total_exits_dd += 1
                log.info(f"  Phase6 STRUCTURAL_EXIT: DTE={l_dte} delta={l_delta:.2f} pnl={proceeds - pos.contracts * 100 * pos.entry_price:.0f}")
            else:
                structurally_sound.append(pos)
        positions = structurally_sound

        # ── Layer C: Event-driven roll check ──────────────────────────────────
        rolled = []
        for pos in positions:
            should_roll, reason = strike_opt.evaluate_roll_triggers(pos, spot, date, rf, iv_l)

            if should_roll and above_100 and cash > 0:
                old_val  = pos.current_value(spot, date, iv_l, rf)
                old_proceeds = pos.contracts * 100 * old_val - config.slippage_for_vix(vix, old_val) * pos.contracts
                cash    += old_proceeds

                # New LEAPS: regime-appropriate delta/DTE
                leaps_params = REGIME_PARAMS.get(regime, REGIME_PARAMS["CHOPPY"])
                T_new    = leaps_params.dte / 365.0
                new_str  = find_call_strike(spot, T_new, rf, iv_l, leaps_params.delta)
                new_px   = bs_call_price(spot, new_str, T_new, rf, iv_l)
                roll_cost= pos.contracts * 100 * new_px + config.slippage_for_vix(vix, new_px) * pos.contracts + config.commission * pos.contracts

                if cash >= roll_cost:
                    cash -= roll_cost
                    pos.strike      = new_str
                    pos.expiry      = date + pd.Timedelta(days=leaps_params.dte)
                    pos.entry_price = new_px
                    pos.entry_spot  = spot
                    pos.iv_at_entry = iv_l
                    pos.short_call  = None  # Reset PMCC after roll
                    pos.rolls      += 1
                    total_rolls_event += 1

                    trade_log.append({
                        "date": date.date(), "type": "LEAPS_ROLL_EVENT",
                        "reason": reason, "new_strike": round(new_str, 2),
                        "new_dte": leaps_params.dte, "roll_pnl": round((old_val - pos.entry_price) * pos.contracts * 100, 2),
                    })

                rolled.append(pos)
            else:
                rolled.append(pos)
        positions = rolled

        # ── ENTRY LOGIC ───────────────────────────────────────────────────────
        n_pos = len(positions)

        # Regime gate
        leaps_params = REGIME_PARAMS.get(regime, REGIME_PARAMS["CHOPPY"])
        if not leaps_params.allow_entry:
            pass  # BEAR regime — no entries

        elif vix > config.entry_vix_max:
            pass  # VIX panic gate

        elif n_pos < config.max_positions:
            # ── Check entry signal ─────────────────────────────────────────
            rsi_14     = float(row.get("rsi_14", 50))
            is_gap_dn  = bool(row.get("is_gap_down", False))

            if mode == "baseline":
                # Baseline: simple gap-down + SMA rule (replicate backtest_leaps.py)
                signal_fires = is_gap_dn and above_100
                ml_conf      = 0.75 if signal_fires else 0.0
            else:
                # ML-optimized v2: Regime-specialist LightGBM with per-regime thresholds
                active_model = get_active_model(models, date)
                if active_model:
                    ml_conf, ml_threshold = active_model.predict_with_threshold(row, regime)
                else:
                    # Pre-warmup: use v1 heuristic with standard threshold
                    ml_conf     = LeapsEntryClassifier()._heuristic_confidence(row)
                    ml_threshold = config.entry_ml_confidence_min

                # ML v2 uses regime-conditional threshold; model incorporates RSI already
                signal_fires = ml_conf >= ml_threshold

                if ml_conf < ml_threshold and (rsi_14 < 35 or is_gap_dn):
                    ml_blocks += 1

            if signal_fires:
                # Layer F: Liquidity gate
                T_entry = leaps_params.dte / 365.0
                strike  = find_call_strike(spot, T_entry, rf, iv_l, leaps_params.delta)
                liq     = estimate_qqq_leaps_liquidity(spot, strike, vix, leaps_params.dte)

                if not liq["passes"]:
                    liq_blocks += 1
                else:
                    # Compute entry price and size
                    entry_px = bs_call_price(spot, strike, T_entry, rf, iv_l)
                    entry_px = max(entry_px, 0.01)

                    # NAV for sizing
                    leaps_mktval = sum(
                        p.current_value(spot, date, iv_l, rf) * p.contracts * 100
                        for p in positions
                    )
                    sc_liability = 0.0
                    for p in positions:
                        if p.short_call:
                            sc = p.short_call
                            T_sc = max((sc["expiry"] - date).days / 365.0, 1 / 365.0)
                            sc_liability += sc["contracts"] * 100 * bs_call_price(spot, sc["strike"], T_sc, rf, iv_s)
                    nav = cash + leaps_mktval - sc_liability

                    # Position cap (Phase 5: research-validated sizing)
                    size_mult   = leaps_params.size_multiplier
                    max_outlay  = nav * config.max_position_pct * size_mult

                    # Standard contract count from budget
                    contracts = max(1, int(max_outlay / (100 * entry_px + config.slippage_for_vix(vix, entry_px) + config.commission)))

                    # BULL_STRONG boost: allow 2 contracts if ML is confident
                    if regime == "BULL_STRONG" and ml_conf >= 0.80 and n_pos < 2:
                        raw_budget_contracts = max(1, int(max_outlay / (100 * entry_px + config.slippage_for_vix(vix, entry_px) + config.commission)))
                        contracts = min(raw_budget_contracts, 2)

                    # Hard structural cap: max 5 contracts
                    contracts = min(contracts, config.max_contracts_hard_cap)

                    # Phase 5: 5% NAV cap — only active when NAV > $150k
                    # At smaller sizes, the max_position_pct budget is already the binding constraint.
                    # This prevents runaway concentration as the account compounds.
                    if nav > 150_000:
                        nav_5pct_cap = max(1, int(0.05 * nav / (100 * entry_px)))
                        contracts = min(contracts, nav_5pct_cap)

                    total_cost = contracts * 100 * entry_px + config.slippage_for_vix(vix, entry_px) * contracts + config.commission * contracts

                    if cash >= total_cost and total_cost > 0:
                        cash -= total_cost
                        expiry = date + pd.Timedelta(days=leaps_params.dte)
                        pos_counter += 1

                        new_pos = LeapsPosition(
                            position_id=pos_counter,
                            open_date=date,
                            strike=strike,
                            expiry=expiry,
                            entry_price=entry_px,
                            entry_spot=spot,
                            contracts=contracts,
                            iv_at_entry=iv_l,
                            rf_at_entry=rf,
                            regime_at_entry=regime,
                            ml_confidence=ml_conf,
                        )
                        positions.append(new_pos)
                        total_entries += 1

                        log.debug(
                            f"  {date.date()} ENTRY: {regime} | strike={strike:.1f} "
                            f"px={entry_px:.2f} δ={leaps_params.delta} DTE={leaps_params.dte} "
                            f"ml={ml_conf:.2f} ctrcts={contracts}"
                        )

        # ── Daily NAV ─────────────────────────────────────────────────────────
        leaps_mv = sum(p.current_value(spot, date, iv_l, rf) * p.contracts * 100 for p in positions)
        sc_liab  = 0.0
        for p in positions:
            if p.short_call:
                sc = p.short_call
                T_sc = max((sc["expiry"] - date).days / 365.0, 1 / 365.0)
                sc_liab += sc["contracts"] * 100 * bs_call_price(spot, sc["strike"], T_sc, rf, iv_s)
        nav = cash + leaps_mv - sc_liab

        daily_rows.append({
            "date":           date.date(),
            "nav":            round(nav, 2),
            "cash":           round(cash, 2),
            "leaps_value":    round(leaps_mv, 2),
            "open_positions": len(positions),
            "qqq_close":      round(spot, 2),
            "vix":            round(vix, 1),
            "regime":         regime,
            "total_ret_pct":  round((nav / capital - 1) * 100, 2),
        })

        if i % 250 == 0 or i == len(trading_days) - 1:
            log.info("  %s | NAV=$%8.0f | pos=%d | ret=%+.1f%% | regime=%s | vix=%.0f",
                     str(date.date()), nav, len(positions),
                     (nav / capital - 1) * 100, regime, vix)

    # ── RESULTS ───────────────────────────────────────────────────────────────
    df = pd.DataFrame(daily_rows)
    tlog = pd.DataFrame(trade_log)

    final_nav = df["nav"].iloc[-1]
    peak_nav  = df["nav"].max()
    roll_max  = df["nav"].cummax()
    drawdown  = (df["nav"] - roll_max) / roll_max * 100
    max_dd    = drawdown.min()
    years     = (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25
    cagr      = ((final_nav / capital) ** (1 / max(years, 0.1)) - 1) * 100
    total_ret = (final_nav / capital - 1) * 100

    # QQQ buy-and-hold comparison (use slices to handle non-trading day dates)
    qqq_slice_start = master.loc[start:].head(1)
    qqq_slice_end   = master.loc[:end].tail(1)
    qqq_start = float(qqq_slice_start["qqq_close"].iloc[0]) if len(qqq_slice_start) > 0 else float(master["qqq_close"].iloc[0])
    qqq_end   = float(qqq_slice_end["qqq_close"].iloc[-1])  if len(qqq_slice_end) > 0  else float(master["qqq_close"].iloc[-1])
    qqq_cagr  = ((qqq_end / qqq_start) ** (1 / max(years, 0.1)) - 1) * 100

    # Win rate on closed LEAPS trades
    leaps_trades = tlog[tlog.get("type", pd.Series()).str.startswith("LEAPS_", na=False)] if len(tlog) > 0 else pd.DataFrame()
    win_rate = avg_win = avg_loss = 0.0
    if len(leaps_trades) > 0 and "pnl" in leaps_trades.columns:
        profitable = leaps_trades[leaps_trades["pnl"] > 0]
        losing     = leaps_trades[leaps_trades["pnl"] <= 0]
        win_rate   = len(profitable) / len(leaps_trades) * 100
        avg_win    = profitable["pnl"].mean() if len(profitable) > 0 else 0
        avg_loss   = losing["pnl"].mean()     if len(losing)     > 0 else 0

    # Sharpe ratio (annualized)
    daily_rets = df["nav"].pct_change().dropna()
    sharpe     = (daily_rets.mean() / daily_rets.std() * math.sqrt(252)) if daily_rets.std() > 0 else 0

    # Calmar ratio
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0

    # Roll frequency
    n_event_rolls = len(tlog[tlog.get("type", pd.Series()) == "LEAPS_ROLL_EVENT"]) if len(tlog) > 0 else 0
    roll_freq = n_event_rolls / max(years, 0.1)

    # Output
    line = "=" * 68
    print(f"\n{line}")
    print(f"  QQQ LEAPS ML-OPTIMIZED STRATEGY — BACKTEST RESULTS")
    print(f"  Mode: {mode.upper()}")
    print(line)
    print(f"  Start Capital     : ${capital:>12,.2f}")
    print(f"  Final NAV         : ${final_nav:>12,.2f}")
    print(f"  Total Return      : {total_ret:>12.1f}%")
    print(f"  CAGR              : {cagr:>12.1f}%")
    print(f"  Max Drawdown      : {max_dd:>12.1f}%")
    print(f"  Sharpe Ratio      : {sharpe:>12.2f}")
    print(f"  Calmar Ratio      : {calmar:>12.2f}")
    print(f"  Peak NAV          : ${peak_nav:>12,.2f}")
    print(f"  Period            : {start} -> {end} ({years:.1f} yrs)")
    print("-" * 68)
    print(f"  QQQ Buy-and-Hold  : {qqq_cagr:>11.1f}% CAGR (benchmark)")
    print(f"  LEAPS Alpha       : {cagr - qqq_cagr:>+11.1f}pp vs. QQQ B&H")
    print("=" * 68)
    print(f"\n  Trade Summary:")
    print(f"    Total LEAPS Entries    : {total_entries:>5d}")
    print(f"    Profit Target Exits    : {total_exits_profit:>5d}")
    print(f"    Event-Driven Rolls     : {total_rolls_event:>5d}  (freq={roll_freq:.2f}/yr)")
    print(f"    Bear-Regime Exits      : {total_exits_bear:>5d}")
    print(f"    PMCC Opened            : {total_pmcc_opened:>5d}")
    print(f"    PMCC Closed            : {total_pmcc_closed:>5d}")
    if mode == "ml_optimized":
        print(f"    ML Blocks (conf<{config.entry_ml_confidence_min})   : {ml_blocks:>5d}")
        print(f"    Liquidity Blocks       : {liq_blocks:>5d}")
    print(f"\n  Win Rate (closed trades): {win_rate:>6.1f}%")
    print(f"  Avg Winning Trade       : ${avg_win:>8,.0f}")
    print(f"  Avg Losing Trade        : ${avg_loss:>8,.0f}")
    if avg_loss < 0:
        wl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        print(f"  Win/Loss Ratio          : {wl_ratio:>8.2f}x")
    print("=" * 68)

    # Save results
    out_dir = ROOT.parent.parent / "qqq-leaps"
    out_dir.mkdir(exist_ok=True)
    df.to_csv(out_dir / f"backtest_{mode}_results.csv", index=False)
    if len(tlog) > 0:
        tlog.to_csv(out_dir / f"backtest_{mode}_trades.csv", index=False)
    print(f"\n  Saved: backtest_{mode}_results.csv")

    return {
        "final_nav": final_nav,
        "cagr": cagr,
        "total_return": total_ret,
        "max_drawdown": max_dd,
        "sharpe": sharpe,
        "calmar": calmar,
        "win_rate": win_rate,
        "qqq_cagr": qqq_cagr,
        "alpha": cagr - qqq_cagr,
        "total_entries": total_entries,
        "roll_freq": roll_freq,
        "ml_blocks": ml_blocks,
        "daily_df": df,
    }


# ── Comparison runner ──────────────────────────────────────────────────────────
def run_comparison(capital: float = 25_000.0, start: str = "2019-01-01", end: str = "2026-04-18"):
    """Run baseline then ML-optimized and print side-by-side comparison."""
    print("\n" + "=" * 68)
    print("  RUNNING BASELINE (gap-down + SMA only)...")
    print("=" * 68)
    base = run_backtest(mode="baseline", capital=capital, start=start, end=end)

    print("\n" + "=" * 68)
    print("  RUNNING ML-OPTIMIZED (all 6 layers)...")
    print("=" * 68)
    ml = run_backtest(mode="ml_optimized", capital=capital, start=start, end=end)

    print("\n" + "=" * 68)
    print("  SIDE-BY-SIDE COMPARISON")
    print("=" * 68)
    print(f"  {'Metric':<28} {'Baseline':>12} {'ML-Optimized':>14} {'Improvement':>12}")
    print(f"  {'-'*67}")
    metrics = [
        ("CAGR",       f"{base['cagr']:.1f}%",        f"{ml['cagr']:.1f}%",        f"{ml['cagr']-base['cagr']:+.1f}pp"),
        ("Total Return",f"{base['total_return']:.1f}%",f"{ml['total_return']:.1f}%",f"{ml['total_return']-base['total_return']:+.1f}pp"),
        ("Max Drawdown",f"{base['max_drawdown']:.1f}%",f"{ml['max_drawdown']:.1f}%",f"{ml['max_drawdown']-base['max_drawdown']:+.1f}pp"),
        ("Sharpe Ratio",f"{base['sharpe']:.2f}",       f"{ml['sharpe']:.2f}",       f"{ml['sharpe']-base['sharpe']:+.2f}"),
        ("Calmar Ratio",f"{base['calmar']:.2f}",       f"{ml['calmar']:.2f}",       f"{ml['calmar']-base['calmar']:+.2f}"),
        ("Win Rate",    f"{base['win_rate']:.1f}%",    f"{ml['win_rate']:.1f}%",    f"{ml['win_rate']-base['win_rate']:+.1f}pp"),
        ("Alpha vs QQQ",f"{base['alpha']:+.1f}pp",     f"{ml['alpha']:+.1f}pp",     f"{ml['alpha']-base['alpha']:+.1f}pp"),
        ("QQQ CAGR",    f"{base['qqq_cagr']:.1f}%",    f"{ml['qqq_cagr']:.1f}%",    "—"),
        ("Roll Freq/yr",f"{base['roll_freq']:.2f}",    f"{ml['roll_freq']:.2f}",    f"{ml['roll_freq']-base['roll_freq']:+.2f}"),
    ]
    for m, b_val, ml_val, diff in metrics:
        print(f"  {m:<28} {b_val:>12} {ml_val:>14} {diff:>12}")
    print("=" * 68)


# ── CLI entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QQQ LEAPS ML Backtest")
    parser.add_argument("--mode",    choices=["baseline", "ml_optimized", "compare"],
                        default="compare")
    parser.add_argument("--capital", type=float, default=25_000.0)
    parser.add_argument("--start",   type=str,   default="2019-01-01")
    parser.add_argument("--end",     type=str,   default="2026-04-18")
    args = parser.parse_args()

    if args.mode == "compare":
        run_comparison(args.capital, args.start, args.end)
    else:
        run_backtest(args.mode, args.capital, args.start, args.end)
