#!/usr/bin/env python3
"""
Position Guardian — Periodic Protective Closer
===============================================
Iterates every active user in the `users` DB table (same table the
daily_order_generator uses), fetches their live TastyTrade positions
using the SAME session pattern (decrypt tt_refresh_token → create_user_session),
and automatically closes any position that meets a danger criterion:

  DANGER-1  Orphaned short call leg (no paired long)   → BUY_TO_CLOSE
  DANGER-2  Any spread with DTE <= 3                   → close before OCC assignment
  DANGER-3  Net-short equity (QQQ/QLD/TQQQ/QQQM)      → BUY to flatten
  DANGER-4  Short call >10% ITM with DTE <= 21         → close spread
  DANGER-5  Orphaned long leg with DTE <= 7            → SELL_TO_CLOSE

Usage:
    python position_guardian.py --once          # single pass all users
    python position_guardian.py --daemon        # runs every 30 min, market hours
    python position_guardian.py --dry-run       # scan only, no orders placed
    python position_guardian.py --user-id <id>  # single user, useful for testing
"""

import os
import sys
import time
import logging
import argparse
import json
from datetime import date, datetime, timezone, timedelta
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Optional, Any

from dotenv import load_dotenv

# ── Path / env setup ──────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "position_guardian.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("PositionGuardian")

# ── Constants ─────────────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS = 30 * 60    # 30 min between daemon cycles
MARKET_OPEN_ET  = (9, 30)
MARKET_CLOSE_ET = (15, 45)        # stop new orders at 3:45 PM ET
ORDER_FILL_WAIT_SEC = 90           # seconds to wait before checking fill
ORDER_WIDEN_PCT     = 0.05         # widen limit 5% on each retry
ORDER_MAX_RETRIES   = 4

DANGEROUS_SHORT_EQUITIES = {"QQQ", "QLD", "TQQQ", "QQQM"}


# ── DB helpers — mirrors daily_order_generator pattern exactly ────────────────

def _get_db():
    """Return a SQLAlchemy session using the same models/db.py as the rest of the app."""
    from models.db import SessionLocal
    return SessionLocal()


def _load_all_active_users(db, user_id_filter: Optional[str] = None) -> list:
    """
    Return active User ORM rows that have tt_refresh_token set.
    Optionally filter to a single user for testing.
    """
    from models.user import User
    q = db.query(User).filter(
        User.is_active == True,
        User.tt_refresh_token != None,   # noqa: E711  (SQLAlchemy doesn't allow `is not`)
    )
    if user_id_filter:
        q = q.filter(User.id == user_id_filter)
    return q.all()


def _create_session_for_user(user):
    """
    Decrypt stored refresh token → create TastyTrade session.
    Exact same flow used by daily_order_generator.fetch_user_account_state().
    """
    from api.services.encryption import decrypt_credential
    from tastytrade_utils import create_user_session, get_user_account

    if not user.tt_refresh_token:
        raise ValueError(f"User {user.id} has no tt_refresh_token in DB")

    refresh_token = decrypt_credential(user.tt_refresh_token)
    session  = create_user_session(refresh_token)
    account  = get_user_account(session, getattr(user, "tt_account_number", None))
    return session, account


# ── OCC symbol parser ─────────────────────────────────────────────────────────

def _parse_occ(occ: str) -> Optional[Dict]:
    s = occ.strip()
    if len(s) < 15:
        return None
    try:
        expiry_str = s[6:12]
        opt_type   = s[12]          # C or P
        strike     = int(s[13:]) / 1000.0
        exp_y = 2000 + int(expiry_str[:2])
        exp_m = int(expiry_str[2:4])
        exp_d = int(expiry_str[4:6])
        exp_date = date(exp_y, exp_m, exp_d)
        dte = (exp_date - date.today()).days
        return {"expiry_str": expiry_str, "opt_type": opt_type,
                "strike": strike, "exp_date": exp_date, "dte": dte}
    except Exception:
        return None


# ── Danger detection ──────────────────────────────────────────────────────────

def _get_qqq_spot() -> float:
    """Quick spot price for ITM checks — fails gracefully."""
    try:
        import yfinance as yf
        return float(yf.Ticker("QQQ").fast_info.last_price)
    except Exception:
        return 0.0


def detect_dangers(positions: list) -> List[Dict]:
    """
    Scan a user's live positions. Return list of danger dicts:
        { "type", "reason", "priority", "orders": [{action, symbol, qty, instrument_type}] }
    """
    dangers    = []
    today      = date.today()
    qqq_spot   = _get_qqq_spot()

    equity_net: Dict[str, float] = {}
    qqq_call_shorts: Dict[str, list] = defaultdict(list)
    qqq_call_longs:  Dict[str, list] = defaultdict(list)

    # ── Pass 1: parse all positions ───────────────────────────────────────────
    for pos in positions:
        sym   = (getattr(pos, "underlying_symbol", "") or "").strip()
        qty   = float(getattr(pos, "quantity", 0) or 0)
        itype = (getattr(pos, "instrument_type", "") or "")
        occ   = (getattr(pos, "symbol", "") or "").strip()

        if qty == 0:
            continue

        is_option = "Option" in itype or itype == "Equity Option"

        if not is_option:
            equity_net[sym] = equity_net.get(sym, 0.0) + qty
            continue

        parsed = _parse_occ(occ)
        if not parsed:
            continue

        entry = {
            "pos": pos, "occ": occ,
            "strike":   parsed["strike"],
            "dte":      parsed["dte"],
            "exp_date": parsed["exp_date"],
            "exp_str":  parsed["expiry_str"],
            "qty":      qty,
        }

        if sym == "QQQ" and parsed["opt_type"] == "C":
            if qty < 0:
                qqq_call_shorts[parsed["expiry_str"]].append(entry)
            else:
                qqq_call_longs[parsed["expiry_str"]].append(entry)

    # ── DANGER-3: short equity ────────────────────────────────────────────────
    for sym, net in equity_net.items():
        if sym in DANGEROUS_SHORT_EQUITIES and net < 0:
            qty = abs(net)
            dangers.append({
                "type":     "DANGER_3_SHORT_EQUITY",
                "reason":   f"Net SHORT {qty:.0f} sh {sym} — uncapped risk",
                "priority": 1,
                "orders":   [{"action": "BUY", "symbol": sym,
                              "qty": int(qty), "instrument_type": "Equity"}],
            })

    # ── DANGER-1/2/4: QQQ call spreads ───────────────────────────────────────
    all_exps = set(qqq_call_shorts.keys()) | set(qqq_call_longs.keys())

    for exp_str in all_exps:
        shorts = sorted(qqq_call_shorts[exp_str], key=lambda x: x["strike"])
        longs  = list(sorted(qqq_call_longs[exp_str], key=lambda x: x["strike"]))
        exp_date = date(2000+int(exp_str[:2]), int(exp_str[2:4]), int(exp_str[4:6]))
        dte = (exp_date - today).days

        for sl in shorts:
            short_qty = abs(int(sl["qty"]))

            # Find paired long (nearest strike above)
            paired = next((ll for ll in longs if ll["strike"] > sl["strike"]), None)

            if not paired:
                # DANGER-1: naked/orphaned short call
                dangers.append({
                    "type":     "DANGER_1_ORPHANED_SHORT",
                    "reason":   f"Orphaned short {sl['occ']} DTE={dte} — no paired long",
                    "priority": 1,
                    "orders":   [{"action": "BUY_TO_CLOSE", "symbol": sl["occ"],
                                  "qty": short_qty, "instrument_type": "Equity Option"}],
                })
                continue

            longs.remove(paired)
            close_qty = min(short_qty, abs(int(paired["qty"])))

            # DANGER-2: too close to expiry
            if dte <= 3:
                dangers.append({
                    "type":     "DANGER_2_EXPIRY",
                    "reason":   f"CCS {sl['strike']}/{paired['strike']} exp={exp_str} DTE={dte}",
                    "priority": 1,
                    "orders":   [
                        {"action": "BUY_TO_CLOSE",  "symbol": sl["occ"],     "qty": close_qty, "instrument_type": "Equity Option"},
                        {"action": "SELL_TO_CLOSE", "symbol": paired["occ"], "qty": close_qty, "instrument_type": "Equity Option"},
                    ],
                })
                continue

            # DANGER-4: deep ITM
            if qqq_spot > 0 and sl["strike"] < qqq_spot:
                pct_itm = (qqq_spot - sl["strike"]) / sl["strike"] * 100
                if pct_itm >= 10 and dte <= 21:
                    max_loss = (paired["strike"] - sl["strike"]) * close_qty * 100
                    dangers.append({
                        "type":     "DANGER_4_DEEP_ITM",
                        "reason":   f"CCS {sl['strike']}/{paired['strike']} {pct_itm:.1f}% ITM DTE={dte} max-loss=${max_loss:,.0f}",
                        "priority": 2,
                        "orders":   [
                            {"action": "BUY_TO_CLOSE",  "symbol": sl["occ"],     "qty": close_qty, "instrument_type": "Equity Option"},
                            {"action": "SELL_TO_CLOSE", "symbol": paired["occ"], "qty": close_qty, "instrument_type": "Equity Option"},
                        ],
                    })

        # DANGER-5: orphaned long near expiry
        for ll in longs:
            if ll["dte"] <= 7:
                long_qty = abs(int(ll["qty"]))
                dangers.append({
                    "type":     "DANGER_5_ORPHANED_LONG",
                    "reason":   f"Orphaned long {ll['occ']} DTE={ll['dte']} — recover value",
                    "priority": 3,
                    "orders":   [{"action": "SELL_TO_CLOSE", "symbol": ll["occ"],
                                  "qty": long_qty, "instrument_type": "Equity Option"}],
                })

    return sorted(dangers, key=lambda d: d.get("priority", 9))


# ── Order execution ───────────────────────────────────────────────────────────

def _live_price(session, occ: str, action: str) -> Optional[float]:
    """Try to fetch bid (for STC) or ask (for BTC) from TT."""
    try:
        from tastytrade.instruments import Option
        opt = Option.get(session, occ)
        bid = float(getattr(opt, "bid", 0) or 0)
        ask = float(getattr(opt, "ask", 0) or 0)
        if ask > 0:
            return ask if "BUY" in action else max(bid, 0.01)
    except Exception:
        pass
    return None


def _submit_order(session, account, orders: List[Dict], dry_run: bool) -> Optional[str]:
    """
    Submit 1- or 2-leg closing order to TastyTrade.
    Retries with 5% wider price up to ORDER_MAX_RETRIES times.
    """
    from tastytrade.order import (
        NewOrder, OrderLeg, OrderAction, OrderType,
        OrderTimeInForce, PriceEffect,
    )

    action_map = {
        "BUY_TO_CLOSE":  OrderAction.BUY_TO_CLOSE,
        "SELL_TO_CLOSE": OrderAction.SELL_TO_CLOSE,
        "BUY":           OrderAction.BUY,
        "SELL":          OrderAction.SELL,
    }

    if dry_run:
        for o in orders:
            log.info(f"    [DRY-RUN] {o['action']} {o['qty']}x {o['symbol']}")
        return "dry-run"

    # Build legs + net price
    legs = []
    net_px = 0.0
    for o in orders:
        px = _live_price(session, o["symbol"], o["action"]) or 0.05
        net_px += px if "SELL" in o["action"] else -px
        legs.append(OrderLeg(
            instrument_type=o.get("instrument_type", "Equity Option"),
            symbol=o["symbol"],
            quantity=int(o["qty"]),
            action=action_map[o["action"]],
        ))

    price_effect = PriceEffect.CREDIT if net_px >= 0 else PriceEffect.DEBIT
    base_px = max(abs(net_px), 0.01)

    for attempt in range(1, ORDER_MAX_RETRIES + 1):
        limit_px = round(base_px * (1 + ORDER_WIDEN_PCT * (attempt - 1)), 2)
        limit_px = max(limit_px, 0.01)
        try:
            order = NewOrder(
                time_in_force=OrderTimeInForce.DAY,
                order_type=OrderType.LIMIT,
                legs=legs,
                price=Decimal(str(limit_px)),
                price_effect=price_effect,
            )
            resp = account.place_order(session, order, dry_run=False)
            order_id = str(resp.order.id) if hasattr(resp, "order") else "submitted"
            log.info(f"    Order submitted: {[o['action']+' '+o['symbol'] for o in orders]} @ ${limit_px:.2f} → id={order_id}")
            # Brief wait, check fill
            time.sleep(ORDER_FILL_WAIT_SEC)
            try:
                live = account.get_order(session, order_id)
                status = getattr(live, "status", "")
                log.info(f"    Fill status: {status}")
                if status in ("Cancelled", "Rejected") and attempt < ORDER_MAX_RETRIES:
                    log.warning(f"    Retrying with wider price (attempt {attempt+1})")
                    continue
            except Exception:
                pass
            return order_id
        except Exception as e:
            log.error(f"    Order attempt {attempt} failed: {e}")
            if attempt == ORDER_MAX_RETRIES:
                return None
            time.sleep(3)

    return None


# ── Per-user scan ─────────────────────────────────────────────────────────────

def scan_user(user, dry_run: bool = False) -> Dict:
    """Fetch positions for one user, detect dangers, submit closes."""
    result = {
        "user_id":       user.id,
        "account":       getattr(user, "tt_account_number", "?"),
        "scan_time":     datetime.now(timezone.utc).isoformat(),
        "positions":     0,
        "dangers_found": 0,
        "orders_placed": 0,
        "errors":        [],
    }

    try:
        session, account = _create_session_for_user(user)
    except Exception as e:
        msg = f"Auth failed: {e}"
        log.error(f"  [{user.id}] {msg}")
        result["errors"].append(msg)
        return result

    try:
        positions = account.get_positions(session)
    except Exception as e:
        msg = f"Could not fetch positions: {e}"
        log.error(f"  [{user.id}] {msg}")
        result["errors"].append(msg)
        return result

    result["positions"] = len(positions)
    dangers = detect_dangers(positions)
    result["dangers_found"] = len(dangers)

    if not dangers:
        log.info(f"  [{user.id}] CLEAR — {len(positions)} positions, no dangers")
        return result

    for d in dangers:
        log.warning(f"  [{user.id}] [{d['type']}] {d['reason']}")

    for d in dangers:
        try:
            order_id = _submit_order(session, account, d["orders"], dry_run=dry_run)
            if order_id:
                result["orders_placed"] += 1
                log.info(f"  [{user.id}] Closed: {d['type']} → order={order_id}")
            else:
                msg = f"Order failed for {d['type']}: {d['reason'][:80]}"
                log.error(f"  [{user.id}] {msg}")
                result["errors"].append(msg)
        except Exception as e:
            msg = f"Exception on {d['type']}: {e}"
            log.error(f"  [{user.id}] {msg}")
            result["errors"].append(msg)

    return result


# ── Full sweep across all users ───────────────────────────────────────────────

def run_sweep(dry_run: bool = False, user_id_filter: Optional[str] = None) -> List[Dict]:
    """One full pass: load all users from DB, scan each account."""
    db = _get_db()
    results = []
    try:
        users = _load_all_active_users(db, user_id_filter)
        log.info(f"=== Guardian sweep: {len(users)} users with linked TT accounts ===")
        for user in users:
            log.info(f"Scanning user {user.id} ({getattr(user, 'tt_account_number', '?')})...")
            r = scan_user(user, dry_run=dry_run)
            results.append(r)
    finally:
        db.close()

    total_dangers = sum(r.get("dangers_found", 0) for r in results)
    total_orders  = sum(r.get("orders_placed",  0) for r in results)
    log.info(f"=== Sweep done: {len(results)} accounts | {total_dangers} dangers | {total_orders} closes ===")
    return results


# ── Market hours ──────────────────────────────────────────────────────────────

def _is_trading_day(dt=None) -> bool:
    """True only if `dt` (ET, default now) is an NYSE trading day — skips holidays."""
    try:
        import pandas_market_calendars as mcal
        et_zone = _get_et_zone()
        day = (dt or datetime.now(et_zone)).date()
        nyse = mcal.get_calendar('NYSE')
        sched = nyse.schedule(start_date=str(day), end_date=str(day))
        return not sched.empty
    except Exception:
        # mcal unavailable — fall back to weekday check
        day = (dt or datetime.now()).date()
        return day.weekday() < 5



def _get_et_zone():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/New_York")
    except ImportError:
        import pytz
        return pytz.timezone("America/New_York")


def _is_market_hours() -> bool:
    """True if current ET time is within NYSE trading hours on an NYSE trading day."""
    et = _get_et_zone()
    now_et = datetime.now(et)
    if not _is_trading_day(now_et):
        return False
    h, m = now_et.hour, now_et.minute
    cur     = h * 60 + m
    open_m  = MARKET_OPEN_ET[0]  * 60 + MARKET_OPEN_ET[1]
    close_m = MARKET_CLOSE_ET[0] * 60 + MARKET_CLOSE_ET[1]
    return open_m <= cur <= close_m



# ── Entrypoint ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Position Guardian")
    parser.add_argument("--daemon",   action="store_true", help="Run every 30 min during market hours")
    parser.add_argument("--once",     action="store_true", help="Single sweep, then exit")
    parser.add_argument("--dry-run",  action="store_true", help="Scan only, no orders")
    parser.add_argument("--user-id",  default=None,        help="Limit to one user ID")
    args = parser.parse_args()

    dry_run = args.dry_run
    if dry_run:
        log.info("DRY-RUN mode — no orders will be placed")

    if args.daemon:
        log.info("Daemon started — scanning every 30 min during market hours")
        while True:
            if _is_market_hours():
                run_sweep(dry_run=dry_run, user_id_filter=args.user_id)
            else:
                log.debug("Outside market hours — skipping")
            log.info(f"Sleeping {SCAN_INTERVAL_SECONDS // 60} min...")
            time.sleep(SCAN_INTERVAL_SECONDS)
    else:
        results = run_sweep(dry_run=dry_run, user_id_filter=args.user_id)
        # Print JSON summary
        print(json.dumps(results, indent=2, default=str))
        has_errors = any(r.get("errors") for r in results)
        sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
