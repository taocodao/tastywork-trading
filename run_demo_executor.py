#!/usr/bin/env python3
"""
Demo Account Executor
=====================
Runs ~15 minutes after the TurboCore signal (3:15 PM ET daily).
Executes signals on two permanent demo virtual accounts:

  demo_turbocore_core → $5,000 Core strategy
  demo_turbocore_pro  → $25,000 Pro strategy

These accounts auto-execute every signal using the Ghost Executor webhook.
Their performance is published publicly at /api/performance/demo with a 3-day delay.

Usage:
    python3 run_demo_executor.py
    python3 run_demo_executor.py --date 2026-04-14   # backfill
"""

import os
import sys
import json
import logging
import argparse
import requests
from datetime import date, datetime, timedelta
from typing import Optional

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("DemoExecutor")

# ── Config ────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

VERCEL_URL      = os.getenv("NEXT_PUBLIC_APP_URL", "https://www.trademind.bot")
INTERNAL_SECRET = os.getenv("INTERNAL_API_SECRET", "dev_secret_key")
DB_URL          = os.getenv("DATABASE_URL")


DEMO_ACCOUNTS = [
    {"user_id": "demo_turbocore_core", "strategy": "TQQQ_TURBOCORE"},
    {"user_id": "demo_turbocore_pro",  "strategy": "TQQQ_TURBOCORE_PRO"},
]


def get_latest_signal(strategy: str) -> Optional[dict]:
    """Fetch the most recent signal for a strategy from the DB."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, data, strategy, status, created_at
                FROM signals
                WHERE strategy ILIKE %s
                  AND status IN ('pending', 'approved', 'executed')
                  AND created_at > NOW() - INTERVAL '24 hours'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [f"%{strategy.replace('TQQQ_', '')}%"],
            )
            row = cur.fetchone()
            if not row:
                return None
            signal = dict(row["data"]) if row["data"] else {}
            signal["id"] = str(row["id"])
            signal["strategy"] = row["strategy"]
            return signal
    finally:
        conn.close()


def snapshot_demo_nlv(user_id: str, strategy: str, trade_date: date, mode: Optional[str]) -> None:
    """Compute and persist today's NLV snapshot for a demo account."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(DB_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Get cash balance
            cur.execute(
                "SELECT cash_balance FROM virtual_accounts WHERE user_id = %s AND strategy = %s",
                [user_id, strategy],
            )
            row = cur.fetchone()
            if not row:
                log.warning(f"No virtual account found for {user_id} — skipping NLV snapshot")
                return
            cash = float(row["cash_balance"])

            # Get shadow positions
            cur.execute(
                "SELECT symbol, quantity, avg_price FROM shadow_positions WHERE user_id = %s AND strategy = %s",
                [user_id, strategy],
            )
            positions = cur.fetchall()

        # Fetch live prices for position symbols
        equity_symbols = [r["symbol"] for r in positions if not r["symbol"].startswith("OPT:")]
        nlv = cash
        if equity_symbols:
            try:
                resp = requests.get(
                    f"{VERCEL_URL}/api/quotes?symbols={','.join(equity_symbols)}",
                    timeout=10,
                )
                if resp.ok:
                    prices = resp.json()
                    for pos in positions:
                        sym = pos["symbol"]
                        price = prices.get(sym, float(pos["avg_price"]) or 0)
                        nlv += float(pos["quantity"]) * price
            except Exception as e:
                log.warning(f"Price fetch failed — using avg_price for NLV: {e}")
                for pos in positions:
                    nlv += float(pos["quantity"]) * float(pos["avg_price"] or 0)

        # Get yesterday's NLV for day_pnl calculation
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT portfolio_nlv FROM demo_performance
                WHERE account_id = %s AND trade_date < %s
                ORDER BY trade_date DESC LIMIT 1
                """,
                [user_id, trade_date.isoformat()],
            )
            prev = cur.fetchone()
            prev_nlv = float(prev["portfolio_nlv"]) if prev else (25000.0 if "pro" in user_id else 5000.0)

        starting_balance = 25000.0 if "pro" in user_id else 5000.0
        day_pnl = nlv - prev_nlv
        pct_return = (nlv - starting_balance) / starting_balance

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO demo_performance
                    (account_id, trade_date, portfolio_nlv, cash_balance, day_pnl, pct_return, strategy_mode)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (account_id, trade_date) DO UPDATE SET
                    portfolio_nlv = EXCLUDED.portfolio_nlv,
                    cash_balance  = EXCLUDED.cash_balance,
                    day_pnl       = EXCLUDED.day_pnl,
                    pct_return    = EXCLUDED.pct_return,
                    strategy_mode = EXCLUDED.strategy_mode
                """,
                [user_id, trade_date.isoformat(), round(nlv, 4), round(cash, 4),
                 round(day_pnl, 4), round(pct_return, 6), mode],
            )
            conn.commit()

        log.info(
            f"📊 Snapshot: {user_id} | {trade_date} | NLV=${nlv:.2f} | "
            f"DayPnL=${day_pnl:+.2f} | Return={pct_return*100:.2f}%"
        )
    except Exception as e:
        log.error(f"NLV snapshot failed for {user_id}: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()


def trigger_ghost_executor_for_demo(signal_id: str, signal: dict) -> bool:
    """Call the Ghost Executor webhook — demo accounts are included automatically
    because they have global_auto_approve = TRUE in user_settings."""
    url = f"{VERCEL_URL}/api/internal/signals/{signal_id}/auto-execute"
    try:
        resp = requests.post(
            url,
            json={"signal": signal},
            headers={"Authorization": f"Bearer {INTERNAL_SECRET}"},
            timeout=60,
        )
        if resp.ok:
            data = resp.json()
            log.info(f"✅ Ghost Executor: processed {data.get('processed', 0)} users")
            return True
        else:
            log.error(f"Ghost Executor returned {resp.status_code}: {resp.text[:300]}")
            return False
    except Exception as e:
        log.error(f"Ghost Executor call failed: {e}")
        return False


def run_demo_execution(trade_date: date) -> None:
    log.info(f"🤖 Demo Executor starting for {trade_date}")

    processed_signal_ids = set()

    for account in DEMO_ACCOUNTS:
        user_id  = account["user_id"]
        strategy = account["strategy"]

        log.info(f"  Processing: {user_id} ({strategy})")

        # 1. Fetch latest signal
        signal = get_latest_signal(strategy)
        if not signal:
            log.warning(f"  No recent signal found for {strategy} — skipping {user_id}")
            continue

        signal_id = signal["id"]
        log.info(f"  Signal: {signal_id} | regime={signal.get('regime', '?')}")

        # 2. Trigger Ghost Executor (only once per signal_id to avoid duplicate processing)
        if signal_id not in processed_signal_ids:
            triggered = trigger_ghost_executor_for_demo(signal_id, signal)
            if triggered:
                processed_signal_ids.add(signal_id)

        # 3. Snapshot NLV (wait a moment for DB writes to settle)
        import time
        time.sleep(5)

        mode = signal.get("options_intent", {}).get("mode") or signal.get("regime")
        snapshot_demo_nlv(user_id, strategy, trade_date, mode)

    log.info(f"✅ Demo Executor complete for {trade_date}")


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import pandas_market_calendars as mcal
    import pandas as pd

    parser = argparse.ArgumentParser(description="TradeMind Demo Account Executor")
    parser.add_argument("--date", type=str, help="Trade date (YYYY-MM-DD), default=today")
    args = parser.parse_args()

    if args.date:
        target_date = date.fromisoformat(args.date)
    else:
        target_date = date.today()

    # Only run on trading days
    nyse = mcal.get_calendar("NYSE")
    valid = nyse.valid_days(
        start_date=target_date.strftime("%Y-%m-%d"),
        end_date=target_date.strftime("%Y-%m-%d"),
    )
    if len(valid) == 0:
        log.info(f"⏭️ {target_date} is not a trading day — skipping")
        sys.exit(0)

    run_demo_execution(target_date)
