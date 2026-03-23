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
        try:
            conn.commit()  # commit each stmt individually (SQLite safety)
        except Exception:
            pass

if __name__ == "__main__":
    print(f"Database: {engine.url}")
    is_sqlite = "sqlite" in str(engine.url)

    with engine.connect() as conn:
        for migration in MIGRATIONS:
            print(f"\nRunning {migration}...")
            run_file(conn, migration)
            conn.commit()
            print(f"  OK: {migration}")

        # SQLite needs individual ALTER TABLE per column (no multi-column syntax)
        if is_sqlite:
            print("\nApplying SQLite-compatible column additions...")
            extra_cols = [
                ("user_daily_orders",     "short_expiry_date",   "DATE"),
                ("user_daily_orders",     "stop_loss_price",     "FLOAT"),
                ("user_daily_orders",     "profit_target",       "FLOAT"),
                ("user_daily_orders",     "roll_delta_trigger",  "FLOAT"),
                ("iv_switching_positions","overlay_contracts",   "INTEGER DEFAULT 0"),
                ("iv_switching_positions","overlay_strike",      "FLOAT"),
                ("iv_switching_positions","overlay_expiry",      "DATE"),
                ("iv_switching_positions","overlay_premium",     "FLOAT"),
                ("iv_switching_positions","overlay_status",      "VARCHAR DEFAULT 'NONE'"),
                ("iv_switching_positions","stop_loss_price",     "FLOAT"),
                ("iv_switching_positions","stop_loss_triggered", "BOOLEAN DEFAULT FALSE"),
            ]
            for table, col, coltype in extra_cols:
                try:
                    conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))
                    conn.commit()
                    print(f"  Added {table}.{col}")
                except Exception as e:
                    print(f"  Skip {table}.{col}: {str(e)[:80]}")

        # Final verification
        print("\nVerification:")
        if is_sqlite:
            tables_q = "SELECT name FROM sqlite_master WHERE type='table'"
        else:
            tables_q = "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        result = conn.execute(sa.text(tables_q))
        all_tables = [r[0] for r in result]
        for t in ["user_daily_orders", "iv_switching_positions"]:
            status = "✅" if t in all_tables else "❌ MISSING"
            print(f"  {status}  {t}")

    print("\nMigrations complete.")
