#!/usr/bin/env python3
"""
Pre-3PM Fix Script
==================
1. Reset demo virtual accounts to starting balances ($5K core, $25K pro)
2. Clear stale shadow positions from demo accounts
3. Fix observer / canceled users who inadvertently have global_auto_approve=TRUE
"""
import os, sys
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get('DATABASE_URL')
if not DB_URL:
    print('ERROR: DATABASE_URL not set'); sys.exit(1)

conn = psycopg2.connect(DB_URL)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print('=' * 70)
print('FIX 1: Disable auto-approve for observer / canceled / None-status users')
cur.execute("""
    UPDATE user_settings
    SET global_auto_approve = FALSE
    WHERE global_auto_approve = TRUE
      AND (
        subscription_tier IN ('observer', 'free', 'trial')
        OR subscription_status NOT IN ('active', 'trialing')
        OR subscription_status IS NULL
      )
      AND user_id NOT LIKE 'demo_%'
    RETURNING user_id, email, subscription_tier, subscription_status
""")
rows = cur.fetchall()
if rows:
    print(f'  Disabled auto-approve for {len(rows)} user(s):')
    for r in rows:
        print(f'    {r["user_id"][:32]:32s} | {r["email"] or "(no email)":30s} | {r["subscription_tier"]} | {r["subscription_status"]}')
else:
    print('  No observer/canceled users with auto-approve found.')

print()
print('FIX 2: Reset demo_turbocore_pro cash balance to $25,000')
cur.execute("""
    UPDATE virtual_accounts
    SET cash_balance = 25000.00, updated_at = NOW()
    WHERE user_id = 'demo_turbocore_pro' AND strategy = 'TQQQ_TURBOCORE_PRO'
    RETURNING user_id, strategy, cash_balance
""")
r = cur.fetchone()
if r:
    print(f'  Reset: {r["user_id"]} | {r["strategy"]} | ${float(r["cash_balance"]):,.2f}')
else:
    print('  WARNING: demo_turbocore_pro not found — inserting...')
    cur.execute("""
        INSERT INTO virtual_accounts (user_id, strategy, cash_balance)
        VALUES ('demo_turbocore_pro', 'TQQQ_TURBOCORE_PRO', 25000.00)
        ON CONFLICT (user_id, strategy) DO UPDATE SET cash_balance = 25000.00, updated_at = NOW()
    """)
    print('  Inserted.')

print()
print('FIX 3: Clear stale shadow positions from demo_turbocore_pro')
cur.execute("""
    DELETE FROM shadow_positions WHERE user_id = 'demo_turbocore_pro'
    RETURNING symbol
""")
deleted = cur.fetchall()
if deleted:
    print(f'  Cleared {len(deleted)} position(s): {[r["symbol"] for r in deleted]}')
else:
    print('  No shadow positions to clear.')

print()
print('FIX 4: Also clear stale demo_turbocore_core shadow positions')
cur.execute("""
    DELETE FROM shadow_positions WHERE user_id = 'demo_turbocore_core'
    RETURNING symbol
""")
deleted = cur.fetchall()
if deleted:
    print(f'  Cleared {len(deleted)} position(s): {[r["symbol"] for r in deleted]}')
else:
    print('  No shadow positions to clear.')

print()
print('FIX 5: Clear any existing demo signal executions (so 3PM signal re-fires cleanly)')
cur.execute("""
    DELETE FROM user_signal_executions
    WHERE user_id IN ('demo_turbocore_core', 'demo_turbocore_pro')
    RETURNING id, signal_id
""")
deleted = cur.fetchall()
if deleted:
    print(f'  Cleared {len(deleted)} execution record(s) for demo accounts')
else:
    print('  No existing executions to clear.')

print()
print('FIX 6: Clear today demo_performance snapshots (will be refreshed at 3PM)')
cur.execute("""
    DELETE FROM demo_performance
    WHERE account_id IN ('demo_turbocore_core', 'demo_turbocore_pro')
      AND trade_date = CURRENT_DATE
    RETURNING account_id, trade_date
""")
deleted = cur.fetchall()
if deleted:
    print(f'  Cleared {len(deleted)} performance snapshot(s) for today')
else:
    print('  No today performance data to clear.')

conn.commit()
print()
print('All fixes committed.')
print()

# ── Verification pass ────────────────────────────────────────────────────────
print('=' * 70)
print('VERIFICATION: State after fixes')

print()
print('Auto-approve users (should only be real active subscribers + demo accounts):')
cur.execute("""
    SELECT user_id, email, subscription_tier, subscription_status, global_auto_approve
    FROM user_settings
    WHERE global_auto_approve = TRUE
    ORDER BY user_id
""")
rows = cur.fetchall()
for r in rows:
    mark = '✅' if r['subscription_status'] in ('active','trialing') else '⚠️'
    print(f'  {mark} {r["user_id"][:32]:32s} | {r["subscription_tier"]:20s} | {r["subscription_status"]}')
print(f'Total: {len(rows)} users')

print()
print('Demo virtual accounts:')
cur.execute("""
    SELECT user_id, strategy, cash_balance
    FROM virtual_accounts
    WHERE user_id IN ('demo_turbocore_core','demo_turbocore_pro')
""")
for r in cur.fetchall():
    print(f'  {r["user_id"]:30s} | ${float(r["cash_balance"]):>12,.2f}')

print()
print('Demo shadow positions (should be empty):')
cur.execute("SELECT symbol FROM shadow_positions WHERE user_id LIKE 'demo_%'")
rows = cur.fetchall()
print(f'  {len(rows)} position(s) — {"✅ Clean" if not rows else "⚠️ NOT CLEAN"}')

print()
print('=' * 70)
print('PRE-3PM FIXES COMPLETE')
print('=' * 70)
conn.close()
