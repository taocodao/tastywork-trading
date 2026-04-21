#!/usr/bin/env python3
"""
QQQ LEAPS Scheduler
====================
Runs the QQQ LEAPS live scanner at 3:00 PM ET on every trading day.
Managed as a separate systemd service: qqq-leaps-scheduler.service

Responsibilities:
  1. Run daily scan at 3:00 PM ET
  2. Update virtual portfolio (cash + MTM)
  3. Also do daily ETF MTM for TurboCore and TurboCore Pro virtual accounts
  4. Push 5-day-delayed snapshot to Vercel landing page
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


# ── Main scan function ────────────────────────────────────────────────────────
def run_daily_scan():
    logger.info("=" * 60)
    logger.info("Starting QQQ LEAPS Daily Scan")
    logger.info("=" * 60)

    # 1. Run QQQ LEAPS scanner
    try:
        from src.qqq_leaps.scanner import run_qqq_leaps_scan
        result = run_qqq_leaps_scan()

        if result:
            logger.info(f"Scan complete: action={result.action} | regime={result.regime} | conf={result.confidence:.2f}")
        else:
            logger.warning("Scanner returned None — market data issue?")
    except Exception as e:
        logger.error(f"QQQ LEAPS scanner failed: {e}", exc_info=True)

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


# ── Scheduler loop ────────────────────────────────────────────────────────────
class QQQLEAPSScheduler:
    def __init__(self):
        self.tz             = pytz.timezone("US/Eastern")
        self.last_scan_date = None
        state = _load_state()
        d = state.get("last_scan_date")
        if d:
            try:
                self.last_scan_date = date.fromisoformat(d)
            except Exception:
                pass

    def _should_scan(self) -> bool:
        now = datetime.now(self.tz)
        return (
            is_market_day()
            and now.hour >= 15           # After 3:00 PM ET
            and self.last_scan_date != now.date()
        )

    def run_loop(self):
        logger.info("QQQ LEAPS Scheduler daemon started.")
        while True:
            try:
                if self._should_scan():
                    run_daily_scan()
                    self.last_scan_date = datetime.now(self.tz).date()
                    _save_state({"last_scan_date": self.last_scan_date.isoformat()})
                    time.sleep(60)   # Brief pause after scan
                elif is_market_day():
                    time.sleep(60)   # Check every minute during market hours
                else:
                    secs = time_until_next_open()
                    logger.info(f"Market closed. Sleeping {secs / 3600:.1f} hours until next open.")
                    # Sleep in 5-min chunks so we can catch manual signals
                    for _ in range(int(secs / 300)):
                        time.sleep(300)
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}", exc_info=True)
                time.sleep(60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="QQQ LEAPS Scheduler")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    args = parser.parse_args()

    scheduler = QQQLEAPSScheduler()
    if args.once:
        run_daily_scan()
    else:
        scheduler.run_loop()
