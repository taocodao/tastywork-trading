"""
Positions & P&L database for TurboCore Pro live paper trading.

Tracks every executed trade, running per-symbol positions (shares + cost basis),
and allocation snapshots — independent of the trade_log audit table in
paper_trader.py (which logs full-cycle context but not running P&L state).

Schema:
    trades              — append-only ledger of every filled order
    positions           — current running position per symbol (shares, cost basis, avg price)
    allocation_history  — snapshot of target vs actual allocation per cycle
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,          -- BUY, SELL
    shares INTEGER NOT NULL,
    price REAL NOT NULL,
    amount REAL NOT NULL,          -- shares * price, signed (+buy cost / -sell proceeds)
    commission REAL DEFAULT 0.0,
    regime TEXT,
    ml_confidence REAL,
    target_pct REAL,
    order_id INTEGER,
    source TEXT DEFAULT 'live'     -- live, manual, backfill
);

CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY,
    shares REAL NOT NULL DEFAULT 0,
    cost_basis REAL NOT NULL DEFAULT 0.0,   -- total $ spent on currently-open shares
    avg_price REAL NOT NULL DEFAULT 0.0,
    realized_pnl REAL NOT NULL DEFAULT 0.0, -- cumulative realized P&L from sells
    updated_ts TEXT
);

CREATE TABLE IF NOT EXISTS allocation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    target_pct REAL NOT NULL,
    actual_shares REAL,
    actual_value REAL,
    nav REAL,
    regime TEXT,
    ml_confidence REAL
);
"""


def get_conn(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def record_trade(conn: sqlite3.Connection, symbol: str, action: str, shares: float,
                  price: float, regime: str = None, ml_confidence: float = None,
                  target_pct: float = None, order_id: int = None,
                  commission: float = 0.0, source: str = "live",
                  ts: str = None) -> None:
    """Record a filled trade and update the running position (FIFO-style avg cost)."""
    ts = ts or datetime.now(timezone.utc).isoformat()
    action = action.upper()
    signed_amount = shares * price * (1 if action == "BUY" else -1)

    conn.execute(
        """INSERT INTO trades
           (ts, symbol, action, shares, price, amount, commission,
            regime, ml_confidence, target_pct, order_id, source)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ts, symbol, action, shares, price, signed_amount, commission,
         regime, ml_confidence, target_pct, order_id, source),
    )

    row = conn.execute(
        "SELECT shares, cost_basis, realized_pnl FROM positions WHERE symbol = ?",
        (symbol,),
    ).fetchone()
    cur_shares, cur_cost_basis, cur_realized = row if row else (0.0, 0.0, 0.0)

    if action == "BUY":
        new_shares = cur_shares + shares
        new_cost_basis = cur_cost_basis + shares * price
        new_avg_price = new_cost_basis / new_shares if new_shares > 0 else 0.0
        new_realized = cur_realized
    else:  # SELL
        # Realized P&L on the portion sold = (sell_price - avg_cost) * shares_sold
        avg_cost = (cur_cost_basis / cur_shares) if cur_shares > 0 else price
        shares_sold = min(shares, cur_shares) if cur_shares > 0 else shares
        realized_gain = (price - avg_cost) * shares_sold
        new_realized = cur_realized + realized_gain
        new_shares = cur_shares - shares
        new_cost_basis = max(0.0, cur_cost_basis - avg_cost * shares_sold)
        new_avg_price = (new_cost_basis / new_shares) if new_shares > 0 else 0.0
        if new_shares < 0:
            # Went short (e.g. flipped from long to short in one order) — reset basis
            new_cost_basis = abs(new_shares) * price
            new_avg_price = price

    conn.execute(
        """INSERT INTO positions (symbol, shares, cost_basis, avg_price, realized_pnl, updated_ts)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(symbol) DO UPDATE SET
               shares = excluded.shares,
               cost_basis = excluded.cost_basis,
               avg_price = excluded.avg_price,
               realized_pnl = excluded.realized_pnl,
               updated_ts = excluded.updated_ts""",
        (symbol, new_shares, new_cost_basis, new_avg_price, new_realized, ts),
    )
    conn.commit()


def record_allocation_snapshot(conn: sqlite3.Connection, ts: str, target_allocation: dict,
                                current_positions: dict, prices: dict, nav: float,
                                regime: str = None, ml_confidence: float = None) -> None:
    """Record target vs actual allocation for one trading cycle."""
    symbols = set(list(target_allocation.keys()) + list(current_positions.keys()))
    for sym in symbols:
        shares = current_positions.get(sym, 0)
        price = prices.get(sym, 0.0)
        conn.execute(
            """INSERT INTO allocation_history
               (ts, symbol, target_pct, actual_shares, actual_value, nav, regime, ml_confidence)
               VALUES (?,?,?,?,?,?,?,?)""",
            (ts, sym, target_allocation.get(sym, 0.0), shares, shares * price,
             nav, regime, ml_confidence),
        )
    conn.commit()


def get_all_positions(conn: sqlite3.Connection) -> dict:
    """Return {symbol: {shares, cost_basis, avg_price, realized_pnl}} for all tracked symbols."""
    rows = conn.execute(
        "SELECT symbol, shares, cost_basis, avg_price, realized_pnl FROM positions"
    ).fetchall()
    return {
        r[0]: {"shares": r[1], "cost_basis": r[2], "avg_price": r[3], "realized_pnl": r[4]}
        for r in rows
    }
