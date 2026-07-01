#!/usr/bin/env python3
"""
populate_signal_returns.py
===========================
EC2 cron script — run daily at 4:30 PM ET (after market close + buffer).
Fetches QQQ closing prices via yfinance and backfills the qqq_return_5d
columns on whop_posts for any signal that is at least 5 trading days old.

Crontab entry (EC2):
  30 20 * * 1-5  cd /home/ec2-user/trademind && python3 scripts/populate_signal_returns.py >> logs/signal_returns.log 2>&1

Dependencies: pip install yfinance psycopg2-binary python-dotenv
"""

import os
import sys
import logging
from datetime import date, timedelta

import yfinance as yf
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
LOOKBACK_DAYS = 90          # Only process signals from the last 90 days
TRADING_DAYS_FORWARD = 5    # 5 trading days after signal for return calculation
CALENDAR_DAYS_BUFFER = 9    # 9 calendar days ≈ 5 trading days (covers weekends + 1 holiday)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_nth_trading_day_close(start_date: date, n: int) -> tuple[float, float, date] | None:
    """
    Fetches QQQ closing prices.
    Returns (price_on_start, price_n_trading_days_later, actual_end_date) or None if data unavailable.
    """
    # Fetch a window of ~15 calendar days to ensure we capture n trading days
    end_date = start_date + timedelta(days=n * 3)
    ticker = yf.Ticker("QQQ")
    hist = ticker.history(start=start_date.isoformat(), end=end_date.isoformat())

    if hist.empty or len(hist) < n:
        return None

    price_start = float(hist["Close"].iloc[0])
    price_end   = float(hist["Close"].iloc[n - 1])
    actual_end  = hist.index[n - 1].date()

    return price_start, price_end, actual_end


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("Starting QQQ return enrichment job")

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Fetch signals missing return data that are old enough to have 5d outcome
        cutoff = date.today() - timedelta(days=CALENDAR_DAYS_BUFFER)

        cur.execute(
            """
            SELECT id, signal_date
            FROM whop_posts
            WHERE post_type = 'signal'
              AND regime IS NOT NULL
              AND qqq_return_5d IS NULL
              AND signal_date <= %s
              AND signal_date >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY signal_date DESC
            """,
            (cutoff, LOOKBACK_DAYS),
        )
        pending = cur.fetchall()
        log.info(f"Found {len(pending)} signals needing return data")

        updated = 0
        skipped = 0

        for row in pending:
            signal_date: date = row["signal_date"]
            result = get_nth_trading_day_close(signal_date, TRADING_DAYS_FORWARD)

            if result is None:
                log.warning(f"  [{signal_date}] Not enough QQQ data yet — skipping")
                skipped += 1
                continue

            price_start, price_end, actual_end = result
            return_pct = round(((price_end - price_start) / price_start) * 100, 2)

            cur.execute(
                """
                UPDATE whop_posts
                SET qqq_price_signal_date = %s,
                    qqq_price_5d_later    = %s,
                    qqq_return_5d         = %s,
                    return_populated_at   = NOW()
                WHERE id = %s
                """,
                (price_start, price_end, return_pct, row["id"]),
            )
            conn.commit()
            updated += 1
            direction = "+" if return_pct >= 0 else ""
            log.info(f"  [{signal_date}] QQQ ${price_start:.2f} → ${price_end:.2f} ({direction}{return_pct}%) [5d ending {actual_end}]")

        log.info(f"Done. Updated: {updated}, Skipped: {skipped}")

    except Exception as e:
        conn.rollback()
        log.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
