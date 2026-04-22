#!/usr/bin/env python3
"""
Run on EC2 to apply PMCC schema migration to PostgreSQL.
Usage: python3 run_pmcc_migration.py
"""
import os
import sys
import psycopg2

try:
    from dotenv import load_dotenv
    for p in [os.path.expanduser("~/tastywork-trading/.env"), ".env"]:
        if os.path.exists(p):
            load_dotenv(p)
            break
except ImportError:
    pass

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

SQL = """
-- Add PMCC state tracking to shadow_positions
ALTER TABLE shadow_positions
    ADD COLUMN IF NOT EXISTS pmcc_state VARCHAR(20) DEFAULT 'LEAPS_ONLY',
    ADD COLUMN IF NOT EXISTS pmcc_credit_cumulative FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pmcc_credit_c0 FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pmcc_short_strike FLOAT DEFAULT 0.0,
    ADD COLUMN IF NOT EXISTS pmcc_short_expiry DATE,
    ADD COLUMN IF NOT EXISTS pmcc_short_entry_date DATE,
    ADD COLUMN IF NOT EXISTS leaps_entry_qqq FLOAT DEFAULT 0.0;

-- Short-call cycle ledger
CREATE TABLE IF NOT EXISTS pmcc_cycles (
    id                   SERIAL PRIMARY KEY,
    user_id              VARCHAR(50) NOT NULL,
    strategy             VARCHAR(30) DEFAULT 'QQQ_LEAPS',
    leaps_position_id    INTEGER,
    short_strike         FLOAT,
    short_expiry         DATE,
    short_dte_at_entry   INTEGER,
    short_delta_at_entry FLOAT,
    credit_collected     FLOAT,
    credit_buyback       FLOAT,
    net_credit           FLOAT,
    entry_date           DATE,
    exit_date            DATE,
    exit_reason          VARCHAR(50),
    tastytrade_order_id  VARCHAR(60),
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pmcc_cycles_user
    ON pmcc_cycles (user_id, strategy, entry_date DESC);
"""

print("Connecting to PostgreSQL...")
try:
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        # Execute each statement individually
        for stmt in SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                print(f"  Running: {stmt[:60]}...")
                cur.execute(stmt)
    conn.commit()
    conn.close()
    print("\n✅  DB migration COMPLETE")
    print("Tables/columns added:")
    print("  • shadow_positions: pmcc_state, pmcc_credit_cumulative, pmcc_credit_c0,")
    print("                      pmcc_short_strike, pmcc_short_expiry, pmcc_short_entry_date,")
    print("                      leaps_entry_qqq")
    print("  • pmcc_cycles (new table with index)")
except Exception as e:
    print(f"\n❌  DB migration FAILED: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)
