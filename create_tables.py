"""
create_tables.py
================
Creates iv_switching_positions and user_daily_orders tables directly
via SQLAlchemy — works on both SQLite and Postgres without any SQL parsing.
Run once on the server to set up the schema.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.db import engine
import sqlalchemy as sa

TABLES = [
    # user_daily_orders — one row per user per trade day
    """CREATE TABLE IF NOT EXISTS user_daily_orders (
        id               TEXT PRIMARY KEY,
        user_id          TEXT NOT NULL,
        trade_date       DATE NOT NULL,
        strategy_mode    VARCHAR(8),
        signal_type      VARCHAR(32),
        status           VARCHAR(16) DEFAULT 'pending',
        signal_json      TEXT,
        order_json       TEXT,
        generation_error TEXT,
        short_expiry_date DATE,
        stop_loss_price  FLOAT,
        profit_target    FLOAT,
        roll_delta_trigger FLOAT,
        created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # iv_switching_positions — tracks open virtual positions per user
    """CREATE TABLE IF NOT EXISTS iv_switching_positions (
        id               TEXT PRIMARY KEY,
        user_id          TEXT NOT NULL,
        mode             VARCHAR(8) NOT NULL,
        signal_type      VARCHAR(32) NOT NULL,
        symbol           VARCHAR(16),
        option_type      VARCHAR(16),
        contracts        INTEGER DEFAULT 0,
        long_strike      FLOAT,
        short_strike     FLOAT,
        expiry_date      DATE,
        entry_price      FLOAT,
        fill_price       FLOAT,
        current_price    FLOAT,
        unrealized_pnl   FLOAT DEFAULT 0,
        realized_pnl     FLOAT DEFAULT 0,
        overlay_contracts INTEGER DEFAULT 0,
        overlay_strike   FLOAT,
        overlay_expiry   DATE,
        overlay_premium  FLOAT,
        overlay_status   VARCHAR DEFAULT 'NONE',
        stop_loss_price  FLOAT,
        stop_loss_triggered INTEGER DEFAULT 0,
        status           VARCHAR(16) DEFAULT 'OPEN',
        tt_order_id      TEXT,
        opened_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        closed_at        TIMESTAMP,
        created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # Indexes
    "CREATE INDEX IF NOT EXISTS idx_udo_user_date ON user_daily_orders (user_id, trade_date)",
    "CREATE INDEX IF NOT EXISTS idx_ivs_user_status ON iv_switching_positions (user_id, status)",
]

if __name__ == "__main__":
    print("DB: " + str(engine.url))
    for ddl in TABLES:
        name = ddl.strip().split()[5] if "INDEX" in ddl else ddl.strip().split()[5]
        try:
            with engine.begin() as conn:
                conn.execute(sa.text(ddl))
            print("  OK: " + name)
        except Exception as e:
            print("  WARN " + name + ": " + str(e)[:80])

    # Verify
    with engine.begin() as conn:
        is_sqlite = "sqlite" in str(engine.url)
        q = "SELECT name FROM sqlite_master WHERE type='table'" if is_sqlite \
            else "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        rows = [r[0] for r in conn.execute(sa.text(q))]

    for t in ["user_daily_orders", "iv_switching_positions"]:
        print("  [" + ("OK" if t in rows else "MISSING") + "] " + t)

    print("Done.")
