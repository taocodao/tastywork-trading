"""
OTM Naked Options Live Scanner (Production)
=============================================
Runs daily to scan the 35-stock universe for deep OTM put/call entry signals,
and monitor open positions for exit rules (stop-loss, profit-take, time exit).

Outputs:
  - VirtualPortfolio update (OTM_NAKED account)
  - signal_publisher/otm_naked.py → PostgreSQL DB
"""
import os
import sys
import logging
import warnings
import json
from pathlib import Path
from datetime import date, timedelta
from typing import Optional, List

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# Allow running from project root
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.expanduser("~"), "tastywork-trading", ".env"))
    load_dotenv(ROOT.parent.parent / ".env")
except ImportError:
    pass

logger = logging.getLogger("OTMNakedScanner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")

# Module imports
from src.otm_naked.config import OTMNakedConfig
from src.otm_naked.feature_engineering import build_all_features
from src.otm_naked.signal_engine import OTMSignalEngine, SignalType
from src.otm_naked.entry_classifier import OTMNakedEntryClassifier
from src.otm_naked.strike_selector import OTMStrikeSelector
from src.otm_naked.risk_manager import OTMNakedRiskManager
from src.otm_naked.backtest_engine import NakedPosition

from virtual_portfolio_manager import get_portfolio_manager
from signal_publisher.otm_naked import publish_otm_naked_signals

def run_daily_scan(config: Optional[OTMNakedConfig] = None, dry_run: bool = False):
    """Full daily scan for entries and exits."""
    cfg = config or OTMNakedConfig()

    logger.info("=" * 60)
    logger.info("OTM Naked Options Daily Scan")
    logger.info("=" * 60)

    # 1. Fetch Market Data (need 2 years of history for 252-day rolling features)
    end_dt = date.today()
    start_dt = end_dt - timedelta(days=730)
    symbols = cfg.universe
    all_tickers = symbols + ["^VIX", "^VIX3M", "^IRX"]
    
    logger.info(f"Downloading data for {len(all_tickers)} tickers...")
    raw = yf.download(all_tickers, start=start_dt.strftime("%Y-%m-%d"), end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
                      progress=False, auto_adjust=True, group_by="ticker")
                      
    def _extract(ticker: str, col: str = "Close") -> pd.Series:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                lvl1_vals = raw.columns.get_level_values(1)
                lvl0_vals = raw.columns.get_level_values(0)
                if ticker in lvl1_vals:
                    s = raw.xs(ticker, axis=1, level=1)
                elif ticker in lvl0_vals:
                    s = raw[ticker]
                else:
                    return pd.Series(dtype=float)
                s.columns = [c.capitalize() if isinstance(c, str) else c for c in s.columns]
                return s[col].dropna() if col in s.columns else pd.Series(dtype=float)
            else:
                return raw[col].dropna() if col in raw.columns else pd.Series(dtype=float)
        except Exception:
            return pd.Series(dtype=float)

    price_data = {}
    for sym in symbols:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if sym in raw.columns.get_level_values(1):
                    df = raw.xs(sym, axis=1, level=1).copy()
                elif sym in raw.columns.get_level_values(0):
                    df = raw[sym].copy()
                else:
                    continue
            else:
                df = raw.copy()
            df.columns = [c.capitalize() if isinstance(c, str) else c for c in df.columns]
            needed = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            if "Close" not in needed:
                continue
            df = df[needed].dropna(subset=["Close"])
            if len(df) > 50:
                price_data[sym] = df
        except Exception as e:
            logger.warning(f"  {sym}: download failed ({e})")

    vix   = _extract("^VIX")
    vix3m = _extract("^VIX3M")
    rf    = _extract("^IRX") / 100.0
    
    if vix.empty or not price_data:
        logger.error("Failed to fetch market data. Aborting.")
        return

    today_vix = float(vix.iloc[-1])
    today_rf = float(rf.iloc[-1]) if not rf.empty else 0.045
    logger.info(f"Market Context: VIX={today_vix:.2f}, RF={today_rf:.2%}")

    # 2. Build Features
    features = build_all_features(price_data, vix, vix3m, rf)
    if not features:
        logger.error("Failed to build features. Aborting.")
        return

    # Initialize engines
    signal_eng = OTMSignalEngine(cfg)
    strike_sel = OTMStrikeSelector(cfg)
    classifier = OTMNakedEntryClassifier()
    classifier.load() # Loads ML model if available

    pm = get_portfolio_manager()
    vp = pm.get("OTM_NAKED")
    current_nav = vp.nav_history[-1]["nav"] if vp.nav_history else vp.initial
    risk_mgr = OTMNakedRiskManager(cfg, current_nav)
    
    # Register open positions with Risk Manager
    open_positions = vp.positions
    existing_symbols = {p["symbol"] for p in open_positions}
    for p in open_positions:
        risk_mgr.record_open(p)

    signals_to_publish = []
    
    # ── 3. Monitor Exits ──────────────────────────────────────────────────────
    from src.otm_naked.backtest_engine import OTMNakedBacktestEngine
    bt_engine = OTMNakedBacktestEngine(cfg)
    today_ts = pd.Timestamp(end_dt)
    
    for pos_dict in list(open_positions):
        try:
            pos = NakedPosition(
                symbol=pos_dict["symbol"],
                option_type=pos_dict["option_type"],
                strike=pos_dict["strike"],
                entry_date=pd.Timestamp(pos_dict["entry_date"]),
                expiry_date=pd.Timestamp(pos_dict["expiry_date"]),
                entry_premium=pos_dict.get("entry_premium", 0.0),
                entry_spot=pos_dict.get("entry_spot", 0.0),
                entry_sigma=pos_dict.get("entry_sigma", 0.0),
                contracts=pos_dict["contracts"],
                regime=pos_dict.get("regime", "NORMAL"),
                ml_confidence=pos_dict.get("ml_confidence", 0.0),
                notional_risk=pos_dict.get("notional_risk", 0.0),
            )
            
            result = bt_engine._check_exits(pos, today_ts, features, today_vix, today_rf)
            if result:
                exit_premium, exit_reason = result
                pnl = (pos.entry_premium - exit_premium) * pos.contracts * 100
                logger.info(f"EXIT SIGNAL: {pos.symbol} {pos.option_type.upper()} {pos.strike} | Reason: {exit_reason} | P&L: ${pnl:.2f}")
                
                # Close in Virtual Portfolio
                if not dry_run:
                    vp.close_position(pos.symbol, exit_price=exit_premium, reason=exit_reason)
                
                signals_to_publish.append({
                    "action": "EXIT",
                    "symbol": pos.symbol,
                    "option_type": pos.option_type,
                    "strike": pos.strike,
                    "contracts": pos.contracts,
                    "exit_px": exit_premium,
                    "reason": exit_reason,
                    "regime": pos.regime,
                })
        except Exception as e:
            logger.error(f"Error checking exits for {pos_dict.get('symbol')}: {e}")

    # ── 4. Scan Entries (Ranked by 52W Proximity) ─────────────────────────────
    candidates = []
    for symbol, feat_df in features.items():
        if feat_df.empty:
            continue
        row = feat_df.iloc[-1]
        
        if symbol in existing_symbols:
            continue # Only 1 position per symbol
            
        signal = signal_eng.evaluate(symbol, row)
        if signal.signal_type == SignalType.NONE:
            continue
            
        ml_conf = classifier.predict_confidence(row) if cfg.use_ml_gate else signal.raw_confidence
        if ml_conf < cfg.ml_confidence_min and cfg.use_ml_gate:
            continue
            
        opt_type = "call" if signal.signal_type == SignalType.SELL_CALL else "put"
        regime = signal.vix_regime
        dte = strike_sel.select_dte(regime)
        T_years = dte / 365.0
        sigma = strike_sel.estimate_iv(float(row.get("hv_20", 0.20)), today_vix)
        spot = float(row.get("close", 0))
        
        if opt_type == "put":
            strike, premium, _ = strike_sel.select_put_strike(spot, T_years, sigma, regime, today_rf)
        else:
            strike, premium, _ = strike_sel.select_call_strike(spot, T_years, sigma, regime, today_rf)
            
        if premium < cfg.min_premium:
            continue
            
        candidates.append({
            "symbol": symbol,
            "opt_type": opt_type,
            "strike": strike,
            "premium": premium,
            "sigma": sigma,
            "regime": regime,
            "ml_conf": ml_conf,
            "spot": spot,
            "dte": dte,
            "iv_rank": float(row.get("iv_rank", 0.5)),
            "iv_hv_ratio": float(row.get("iv_hv_ratio", 1.1)),
            # Use distance to 52W high for ranking (most extreme first)
            "sort_score": abs(float(row.get("pct_from_52w_high", 0)))
        })
        
    # Sort candidates by distance from 52W high (descending)
    candidates.sort(key=lambda x: x["sort_score"], reverse=True)
    
    for cand in candidates:
        contracts = risk_mgr.calculate_contracts(cand["premium"], cand["strike"], current_nav)
        if contracts < 1:
            continue
            
        rcheck = risk_mgr.check_entry(
            cand["symbol"], cand["strike"], cand["premium"], contracts, today_vix,
            cand["iv_rank"], cand["iv_hv_ratio"], 999, cand["opt_type"]
        )
        if not rcheck:
            continue
            
        logger.info(f"ENTRY SIGNAL: {cand['symbol']} SELL {cand['opt_type'].upper()} {cand['strike']} | Premium: ${cand['premium']:.2f} | Conf: {cand['ml_conf']:.2f}")
        
        expiry_dt = end_dt + timedelta(days=cand["dte"])
        pos_dict = {
            "symbol": cand["symbol"],
            "type": "NAKED_SELL",
            "option_type": cand["opt_type"],
            "strike": cand["strike"],
            "contracts": contracts,
            "entry_price": cand["premium"], # Credit
            "entry_spot": cand["spot"],
            "entry_sigma": cand["sigma"],
            "entry_date": end_dt.isoformat(),
            "expiry_date": expiry_dt.isoformat(),
            "regime": cand["regime"],
            "ml_confidence": cand["ml_conf"],
            "notional_risk": cand["strike"] * contracts * 100
        }
        
        if not dry_run:
            vp.open_position(pos_dict)
            
        signals_to_publish.append({
            "action": "ENTER",
            "symbol": cand["symbol"],
            "option_type": cand["opt_type"],
            "strike": cand["strike"],
            "contracts": contracts,
            "entry_px": cand["premium"],
            "confidence": cand["ml_conf"],
            "regime": cand["regime"],
            "expiry_date": expiry_dt.isoformat(),
            "spot": cand["spot"],
            "vix": today_vix,
        })
        
    if not dry_run and signals_to_publish:
        try:
            publish_otm_naked_signals(signals_to_publish)
        except Exception as e:
            logger.error(f"Failed to publish signals: {e}")
            
    # MTM Portfolio
    if not dry_run:
        # We need to compute total liability to update account NAV
        total_liability = 0
        for p in vp.positions:
            try:
                # Approximate MTM using BS
                sym = p["symbol"]
                dte_remaining = max((date.fromisoformat(p["expiry_date"]) - end_dt).days, 0)
                T = dte_remaining / 365.0
                spot = float(price_data[sym]["Close"].iloc[-1]) if sym in price_data else p["entry_spot"]
                
                if p["option_type"] == "put":
                    from src.otm_naked.strike_selector import bs_put_price
                    px = bs_put_price(spot, p["strike"], T, today_rf, p["entry_sigma"])
                else:
                    from src.otm_naked.strike_selector import bs_call_price
                    px = bs_call_price(spot, p["strike"], T, today_rf, p["entry_sigma"])
                    
                total_liability += px * p["contracts"] * 100
            except Exception:
                pass
                
        # For naked selling, cash goes up at entry, NAV = Cash - Liabilities
        vp.record_nav(vp.cash - total_liability)
        pm.save()
        try:
            pm.publish_public_snapshot()
        except Exception as e:
            logger.warning(f"Failed to publish portfolio snapshot: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_daily_scan(dry_run=args.dry_run)
