#!/usr/bin/env python3
"""Pre-flight DB check for 3:00 PM ET signal generation."""
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
print('=== AUTO-APPROVE USERS ===')
cur.execute("""
    SELECT user_id, email, subscription_tier, subscription_status, global_auto_approve
    FROM user_settings
    WHERE global_auto_approve = TRUE
    ORDER BY user_id
""")
rows = cur.fetchall()
for r in rows:
    uid = r['user_id']
    email = r['email'] or '(no email)'
    print(f"  {uid[:32]:32s} | {email[:28]:28s} | {r['subscription_tier']:20s} | {r['subscription_status']}")
print(f'Total auto-approve users: {len(rows)}')

print()
print('=== DEMO VIRTUAL ACCOUNTS ===')
cur.execute("""
    SELECT va.user_id, va.strategy, va.cash_balance, va.updated_at
    FROM virtual_accounts va
    WHERE va.user_id IN ('demo_turbocore_core','demo_turbocore_pro')
    ORDER BY va.user_id, va.strategy
""")
rows = cur.fetchall()
if not rows:
    print('  WARNING: Demo accounts do not exist in virtual_accounts!')
for r in rows:
    print(f"  {r['user_id']:30s} | {r['strategy']:25s} | ${float(r['cash_balance']):>12,.2f}")

print()
print('=== DEMO USER_SETTINGS ===')
cur.execute("""
    SELECT user_id, subscription_tier, subscription_status, global_auto_approve, email
    FROM user_settings
    WHERE user_id IN ('demo_turbocore_core','demo_turbocore_pro')
    ORDER BY user_id
""")
rows = cur.fetchall()
if not rows:
    print('  WARNING: Demo users not in user_settings — Ghost Executor will NOT process them!')
for r in rows:
    print(f"  {r['user_id']:30s} | tier={r['subscription_tier']:20s} | status={r['subscription_status']} | auto={r['global_auto_approve']}")

print()
print('=== DEMO SHADOW POSITIONS ===')
cur.execute("""
    SELECT user_id, strategy, symbol, quantity, avg_price, instrument_type
    FROM shadow_positions
    WHERE user_id LIKE 'demo_%'
    ORDER BY user_id, symbol
""")
rows = cur.fetchall()
if not rows:
    print('  (none — clean start, expected on first run)')
for r in rows:
    print(f"  {r['user_id']:30s} | {r['strategy']:25s} | {r['symbol']:15s} qty={r['quantity']}")

print()
print('=== DEMO PERFORMANCE TABLE ===')
cur.execute("""
    SELECT account_id, trade_date, portfolio_nlv, day_pnl, pct_return, strategy_mode
    FROM demo_performance
    ORDER BY account_id, trade_date DESC
    LIMIT 10
""")
rows = cur.fetchall()
if not rows:
    print('  (empty — will populate at 3:00 PM ET today)')
for r in rows:
    day_pnl = float(r['day_pnl'] or 0)
    print(f"  {r['account_id']:30s} | {str(r['trade_date']):12s} | NLV=${float(r['portfolio_nlv']):>10,.2f} | DayPnL=${day_pnl:+,.2f}")

print()
print('=== LAST 5 SIGNALS ===')
cur.execute("""
    SELECT id, strategy, COALESCE(data->>'regime', '?') as regime, status, created_at
    FROM signals
    ORDER BY created_at DESC
    LIMIT 5
""")
rows = cur.fetchall()
for r in rows:
    print(f"  {str(r['id'])[:36]:36s} | {r['strategy']:25s} | {r['regime']:10s} | {r['status']:10s} | {r['created_at']}")

print()
print('=== LAST 5 SIGNAL EXECUTIONS ===')
cur.execute("""
    SELECT use.user_id, use.signal_id, use.status, use.source, use.executed_at
    FROM user_signal_executions use
    ORDER BY use.created_at DESC
    LIMIT 8
""")
rows = cur.fetchall()
for r in rows:
    uid = r['user_id'][:28]
    print(f"  {uid:28s} | {str(r['signal_id'])[:36]:36s} | {r['status']:10s} | {r['source']:8s} | {r['executed_at']}")

print()
print('=== SCHEDULER LAST SCAN STATE ===')
try:
    import json, os
    base = '/home/ubuntu/taskywork-trading'
    for f in ['scheduler_state.json', 'pro_scheduler_state.json']:
        fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
        if os.path.exists(fp):
            print(f"  {f}: {open(fp).read().strip()}")
        else:
            print(f"  {f}: not found (will trigger scan at 3:00 PM ET today)")
except Exception as e:
    print(f'  State file check: {e}')

print()
print('=' * 70)
print('PRE-FLIGHT COMPLETE')
print('=' * 70)
conn.close()
