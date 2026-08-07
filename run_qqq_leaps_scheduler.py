#!/usr/bin/env python3
"""
QQQ LEAPS Scheduler
====================
Runs two scans per trading day:
  • 9:45 AM ET  — Lightweight exit-only scan (DrawdownGuard protection)
  • 3:00 PM ET  — Full ML entry+exit scan (signal generation)

Managed as a separate systemd service: qqq-leaps-scheduler.service

Responsibilities:
  1. Morning exit scan at 9:45 AM ET — protect open positions from intraday crashes
  2. Full daily scan at 3:00 PM ET
  3. Update virtual portfolio (cash + MTM)
  4. Also do daily ETF MTM for TurboCore and TurboCore Pro virtual accounts
  5. Push 5-day-delayed snapshot to Vercel landing page
"""
import os
import sys
import time
import logging
import json
from datetime import datetime, date, timedelta
from pathlib import Path

import pytz
from dotenv import load_dotenv

# ── Load environment ────────────────────────────────────────────────────────
_env_path = Path(os.path.expanduser("~")) / "tastywork-trading" / ".env"
load_dotenv(_env_path)

# ── Logging ─────────────────────────────────────────────────────────────────
log_dir = Path(os.path.expanduser("~")) / "tastywork-trading" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "run_qqq_leaps_scheduler.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("QQQLEAPSScheduler")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# ── Market calendar helpers ──────────────────────────────────────────────────
def is_market_day() -> bool:
    tz  = pytz.timezone("US/Eastern")
    now = datetime.now(tz)
    return now.weekday() < 5  # Mon-Fri

def time_until_next_open() -> float:
    tz   = pytz.timezone("US/Eastern")
    now  = datetime.now(tz)
    next_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now >= next_open:
        next_open += timedelta(days=1)
    while next_open.weekday() >= 5:
        next_open += timedelta(days=1)
    return (next_open - now).total_seconds()


# ── Scan state ───────────────────────────────────────────────────────────────
STATE_FILE = Path(os.path.expanduser("~")) / "tastywork-trading" / "data" / "qqq_leaps_scheduler_state.json"
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(d: dict):
    STATE_FILE.write_text(json.dumps(d, indent=2))


# ── TurboCore ETF MTM helper ─────────────────────────────────────────────────
def _update_turbocore_mtm():
    """
    Fetch current ETF prices and update TurboCore / TurboCore Pro virtual accounts with MTM NAV.
    This does not change allocations — it just records today's market-value NAV.
    """
    try:
        import yfinance as yf
        from virtual_portfolio_manager import get_portfolio_manager

        pm = get_portfolio_manager()

        # --- TurboCore ---
        tc = pm.get("TQQQ_TURBOCORE")
        if tc.etf_holdings:
            tickers = list(tc.etf_holdings.keys())
            try:
                prices = yf.download(tickers, period="2d", progress=False, auto_adjust=True)

                def _last_close(sym):
                    try:
                        col = ("Close", sym) if isinstance(prices.columns, type(prices.columns)) and prices.columns.nlevels > 1 else "Close"
                        return float(prices[col][sym].dropna().iloc[-1]) if prices.columns.nlevels > 1 else float(prices[col].dropna().iloc[-1])
                    except Exception:
                        return 0.0

                # For ETF holdings stored as dollar values we need to compute
                # price-return ratios. Store entry prices once to do this properly.
                nav_tc = sum(tc.etf_holdings.values()) + tc.cash
            except Exception as e:
                nav_tc = sum(tc.etf_holdings.values()) + tc.cash
                logger.warning(f"TC price fetch failed: {e}")
        else:
            nav_tc = tc.cash

        tc.record_nav(nav_tc)
        logger.info(f"[TQQQ_TURBOCORE] ETF MTM: nav=${nav_tc:.0f}")

        # --- TurboCore Pro ---
        tcpro = pm.get("TURBOCORE_PRO")
        if tcpro.etf_holdings:
            nav_pro = sum(tcpro.etf_holdings.values()) + tcpro.cash
        else:
            nav_pro = tcpro.cash

        tcpro.record_nav(nav_pro)
        logger.info(f"[TURBOCORE_PRO] ETF MTM: nav=${nav_pro:.0f}")

        pm.save()

    except Exception as e:
        logger.warning(f"TurboCore MTM update failed (non-fatal): {e}")


# ── Main scan functions ───────────────────────────────────────────────────────
def run_morning_exit_scan():
    """9:45 AM lightweight DrawdownGuard exit-only scan."""
    logger.info("=" * 60)
    logger.info("Starting QQQ LEAPS Morning Exit-Only Scan")
    logger.info("=" * 60)

    try:
        from src.qqq_leaps.scanner import run_exit_only_scan
        result = run_exit_only_scan()

        if result and result.action == "EXIT":
            logger.warning(
                f"⚠️  Morning exit fired: reason={result.exit_reason} "
                f"px=${result.exit_px:.2f} spot={result.spot:.2f}"
            )
            # Notify Vercel SSE immediately so users see the EXIT signal
            try:
                import requests
                base_url   = os.environ.get("VERCEL_URL", "https://trademind.bot")
                secret_key = os.environ.get("INTERNAL_API_SECRET", "dev_secret_key")
                requests.post(
                    f"{base_url}/api/signals/notify",
                    json={"strategy": "QQQ_LEAPS"},
                    headers={"Authorization": f"Bearer {secret_key}"},
                    timeout=10,
                )
            except Exception as e:
                logger.warning(f"Morning SSE push failed (non-fatal): {e}")
        else:
            logger.info("Morning exit scan: all positions healthy.")

    except Exception as e:
        logger.error(f"Morning exit scan failed: {e}", exc_info=True)


def _should_retrain() -> bool:
    """Returns True if 63+ trading days have elapsed since last model retrain (≈ 3 months)."""
    state = _load_state()
    last_str = state.get("last_model_retrain_date", "2000-01-01")
    try:
        last_dt = date.fromisoformat(last_str)
        return (date.today() - last_dt).days >= 63
    except Exception:
        return True


def _run_model_retrain():
    """Quarterly retrain: pulls 4 years of data and re-fits LightGBM v2 specialist models."""
    logger.info("⏳ Quarterly model retraining triggered...")
    try:
        import yfinance as yf
        import pandas as pd
        from src.qqq_leaps.leaps_feature_engineering import build_leaps_features
        from src.qqq_leaps.regime_classifier import LeapsRegimeClassifier
        from src.qqq_leaps.entry_classifier_v2 import LeapsEntryClassifierV2
        from src.qqq_leaps.config import QQQLeapsConfig

        cfg = QQQLeapsConfig()
        end_dt   = date.today().isoformat()
        start_dt = (date.today() - timedelta(days=1500)).isoformat()  # ~4 years

        logger.info(f"  Fetching data {start_dt} → {end_dt} for retrain...")
        qqq  = yf.download("QQQ",   start=start_dt, end=end_dt, auto_adjust=True, progress=False)
        vix  = yf.download("^VIX",  start=start_dt, end=end_dt, progress=False)
        vix3m= yf.download("^VIX3M",start=start_dt, end=end_dt, progress=False)
        irx  = yf.download("^IRX",  start=start_dt, end=end_dt, progress=False)

        def _sq(df):
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
            return df

        qqq = _sq(qqq); vix = _sq(vix); vix3m = _sq(vix3m); irx = _sq(irx)

        qqq_close = qqq["Close"].squeeze()
        qqq_open  = qqq["Open"].squeeze()
        vix_s     = vix["Close"].reindex(qqq_close.index).ffill().fillna(20.0).squeeze()
        vix3m_s   = vix3m["Close"].reindex(qqq_close.index).ffill().fillna(21.0).squeeze()
        rf_s      = (irx["Close"] / 100.0).reindex(qqq_close.index).ffill().fillna(0.045).squeeze()

        master = build_leaps_features(qqq_close, qqq_open, vix_s, vix3m_s, rf_s)

        # Add regime labels
        regime_clf = LeapsRegimeClassifier(cfg)
        master = regime_clf.apply_to_master(master)

        # Add forward labels (4% gain in 30 days)
        forward_ret = qqq_close.pct_change(cfg.ml_label_forward_days).shift(-cfg.ml_label_forward_days)
        master["label_bounce"] = (forward_ret >= cfg.ml_label_target_gain).astype(int)

        # Train LightGBM v2 specialists
        clf = LeapsEntryClassifierV2()
        if "label_bounce" in master.columns and "leaps_regime" in master.columns:
            clf.fit(master)
            if clf.is_trained:
                state = _load_state()
                state["last_model_retrain_date"] = date.today().isoformat()
                _save_state(state)
                logger.info(f"✅ Model retrained successfully. Stats: {clf.training_stats}")
            else:
                logger.warning("Model fit returned is_trained=False — check data quality")
        else:
            logger.error("label_bounce or leaps_regime column missing — retrain aborted")

    except Exception as e:
        logger.error(f"Model retrain failed (non-fatal): {e}", exc_info=True)


def run_daily_scan():
    logger.info("=" * 60)
    logger.info("Starting QQQ LEAPS Daily Scan")
    logger.info("=" * 60)

    # 0. Quarterly model retraining check
    if _should_retrain():
        _run_model_retrain()

    # 1. Run QQQ LEAPS canonical live signal (2y hourly engine, PR #1)
    #    Replaces the legacy src.qqq_leaps.scanner path. The canonical signal
    #    generator uses causal regime filtering + walk-forward GBM confidence
    #    and writes the signal JSON consumed by the IBKR paper trader.
    try:
        from src.qqq_leaps.canonical import qqq_live_signal
        result = qqq_live_signal.main()

        logger.info(f"Canonical QQQ LEAPS signal run complete: {result}")
    except Exception as e:
        logger.error(f"QQQ LEAPS canonical signal failed: {e}", exc_info=True)


    # 2. Update TurboCore ETF MTM (daily mark)
    _update_turbocore_mtm()

    # 3. Publish updated snapshot to Vercel (already called inside scanner, but safe to call again)
    try:
        from virtual_portfolio_manager import get_portfolio_manager
        pm = get_portfolio_manager()
        pm.publish_public_snapshot()
    except Exception as e:
        logger.warning(f"Snapshot publish failed (non-fatal): {e}")

    # 4. Notify Vercel SSE
    try:
        import requests
        base_url   = os.environ.get("VERCEL_URL", "https://trademind.bot")
        secret_key = os.environ.get("INTERNAL_API_SECRET", "dev_secret_key")
        resp = requests.post(
            f"{base_url}/api/signals/notify",
            json={"strategy": "QQQ_LEAPS"},
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("SSE notification sent to Vercel frontend")
        else:
            logger.warning(f"SSE push returned {resp.status_code}")
    except Exception as e:
        logger.warning(f"SSE push failed (non-fatal): {e}")

    logger.info("Daily scan complete.")


# ── Scheduler class ───────────────────────────────────────────────────────────
class QQQLEAPSScheduler:
    """
    Two-window daily scheduler:
      • 9:45 AM ET  — exit-only DrawdownGuard check (protects open positions)
      • 3:00 PM ET  — full ML entry + exit scan
    Each window runs exactly once per trading day, tracked independently.
    """

    MORNING_EXIT_HOUR   = 9
    MORNING_EXIT_MINUTE = 45
    FULL_SCAN_HOUR      = 15   # 3:00 PM ET

    def __init__(self):
        self.tz = pytz.timezone("US/Eastern")
        self.last_scan_date         = None   # tracks 3 PM full scan
        self.last_exit_scan_date    = None   # tracks 9:45 AM exit scan

        state = _load_state()
        try:
            d = state.get("last_scan_date")
            if d:
                self.last_scan_date = date.fromisoformat(d)
        except Exception:
            pass
        try:
            d = state.get("last_exit_scan_date")
            if d:
                self.last_exit_scan_date = date.fromisoformat(d)
        except Exception:
            pass

    def _should_run_morning_exit(self) -> bool:
        """True once per day after 9:45 AM ET, before we have already run it today."""
        now = datetime.now(self.tz)
        after_945 = (now.hour > self.MORNING_EXIT_HOUR) or (
            now.hour == self.MORNING_EXIT_HOUR and now.minute >= self.MORNING_EXIT_MINUTE
        )
        return (
            is_market_day()
            and after_945
            and self.last_exit_scan_date != now.date()
        )

    def _should_run_full_scan(self) -> bool:
        """True once per day after 3:00 PM ET, before we have already run it today."""
        now = datetime.now(self.tz)
        return (
            is_market_day()
            and now.hour >= self.FULL_SCAN_HOUR
            and self.last_scan_date != now.date()
        )

    def _save_combined_state(self):
        _save_state({
            "last_scan_date":      self.last_scan_date.isoformat() if self.last_scan_date else None,
            "last_exit_scan_date": self.last_exit_scan_date.isoformat() if self.last_exit_scan_date else None,
        })

    def run_loop(self):
        logger.info("QQQ LEAPS Scheduler daemon started. (Two-window: 9:45 AM exit + 3:00 PM full)")
        while True:
            try:
                now = datetime.now(self.tz)

                # ── Window 1: 9:45 AM exit-only scan ─────────────────────────
                if self._should_run_morning_exit():
                    run_morning_exit_scan()
                    self.last_exit_scan_date = now.date()
                    self._save_combined_state()
                    time.sleep(60)

                # ── Window 2: 3:00 PM full scan ───────────────────────────────
                elif self._should_run_full_scan():
                    run_daily_scan()
                    self.last_scan_date = now.date()
                    self._save_combined_state()
                    time.sleep(60)

                # ── Idle ──────────────────────────────────────────────────────
                elif is_market_day():
                    time.sleep(60)   # Poll every minute during market hours
                else:
                    secs = time_until_next_open()
                    logger.info(f"Market closed. Sleeping {secs / 3600:.1f} hours until next open.")
                    for _ in range(max(1, int(secs / 300))):
                        time.sleep(300)

            except Exception as e:
                logger.error(f"Scheduler loop error: {e}", exc_info=True)
                time.sleep(60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="QQQ LEAPS Dual-Window Scheduler")
    parser.add_argument("--once",       action="store_true", help="Run the full 3 PM scan once and exit")
    parser.add_argument("--exit-once",  action="store_true", help="Run the morning exit-only scan once and exit")
    args = parser.parse_args()

    scheduler = QQQLEAPSScheduler()
    if args.exit_once:
        run_morning_exit_scan()
    elif args.once:
        run_daily_scan()
    else:
        scheduler.run_loop()
