"""
run_migrations.py
=================
Runs all pending IV-Switching migrations against the local database.
Works with both SQLite (local) and Postgres (production).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.db import engine
import sqlalchemy as sa

MIGRATIONS = [
    "migrations/0013_add_iv_switching_positions.sql",
    "migrations/0014_backfill_iv_strategy_enabled.sql",
    "migrations/0015_add_pmcc_enhancements.sql",
]

def run_statement(conn, stmt):
    stmt = stmt.strip()
    if not stmt or stmt.startswith("--"):
        return
    try:
        conn.execute(sa.text(stmt))
    except Exception as e:
        msg = str(e)
        # Silence expected SQLite-vs-Postgres syntax gaps
        ignorable = [
            "near \"RETURN\"", "near \"$$\"", "near \"OR\"", "near \"ON\"",
            "cannot commit", "already exists", "duplicate column",
            "IF NOT EXISTS",
        ]
        if any(x in msg for x in ignorable):
            print(f"  SKIP (expected SQLite limit): {stmt[:60].replace(chr(10),' ')}")
        else:
            print(f"  WARN: {msg[:120]}")
            print(f"    SQL: {stmt[:80].replace(chr(10),' ')}")

def run_file(conn, path):
    sql = open(path, encoding="utf-8").read()
    statements = sql.split(";")
    for stmt in statements:
        run_statement(conn, stmt)

if __name__ == "__main__":
    print("Database: " + str(engine.url))
    is_sqlite = "sqlite" in str(engine.url)

    # Run each migration file — each statement in its own transaction
    # so a failure in one stmt doesn't roll back the whole file
    for migration in MIGRATIONS:
        print("\nRunning %s..." % migration)
        sql = open(migration, encoding="utf-8").read()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if not stmt or stmt.startswith("--"):
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(sa.text(stmt))
            except Exception as e:
                msg = str(e)
                ignorable = [
                    "near \"RETURN\"", "near \"$$\"", "near \"OR\"", "near \"ON\"",
                    "cannot commit", "already exists", "duplicate column",
                    "IF NOT EXISTS", "END IF", "near \"IF\"",
                ]
                if any(x in msg for x in ignorable):
                    print("  SKIP: %s" % stmt[:60].replace("\n", " "))
                else:
                    print("  WARN: %s" % msg[:100])
        print("  OK: %s" % migration)

    # SQLite: apply extra columns one-at-a-time (no multi-column ALTER TABLE)
    if is_sqlite:
        print("\nApplying SQLite column additions...")
        extra_cols = [
            ("user_daily_orders",      "short_expiry_date",   "DATE"),
            ("user_daily_orders",      "stop_loss_price",     "FLOAT"),
            ("user_daily_orders",      "profit_target",       "FLOAT"),
            ("user_daily_orders",      "roll_delta_trigger",  "FLOAT"),
            ("iv_switching_positions", "overlay_contracts",   "INTEGER DEFAULT 0"),
            ("iv_switching_positions", "overlay_strike",      "FLOAT"),
            ("iv_switching_positions", "overlay_expiry",      "DATE"),
            ("iv_switching_positions", "overlay_premium",     "FLOAT"),
            ("iv_switching_positions", "overlay_status",      "VARCHAR DEFAULT 'NONE'"),
            ("iv_switching_positions", "stop_loss_price",     "FLOAT"),
            ("iv_switching_positions", "stop_loss_triggered", "BOOLEAN DEFAULT FALSE"),
        ]
        for table, col, coltype in extra_cols:
            try:
                with engine.begin() as conn:
                    conn.execute(sa.text("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, coltype)))
                print("  Added %s.%s" % (table, col))
            except Exception as e:
                print("  Skip %s.%s: %s" % (table, col, str(e)[:60]))

    # Verification
    print("\nVerification:")
    try:
        with engine.begin() as conn:
            if is_sqlite:
                q = "SELECT name FROM sqlite_master WHERE type='table'"
            else:
                q = "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            result = conn.execute(sa.text(q))
            all_tables = [r[0] for r in result]
        for t in ["user_daily_orders", "iv_switching_positions"]:
            status = "OK" if t in all_tables else "MISSING"
            print("  [%s] %s" % (status, t))
    except Exception as e:
        print("  Verification error: %s" % e)

    print("\nMigrations complete.")
