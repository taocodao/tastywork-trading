#!/usr/bin/env python3
import os
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print('=== LIVE EXECUTION DETAIL (last 30 min) ===')
cur.execute("""
    SELECT use.user_id, use.signal_id, use.status, use.source, use.executed_at,
           s.data->>'regime' as regime, s.strategy
    FROM user_signal_executions use
    LEFT JOIN signals s ON s.id::text = use.signal_id::text
    WHERE use.created_at > NOW() - INTERVAL '30 minutes'
    ORDER BY use.created_at DESC
""")
for r in cur.fetchall():
    print(f"  {r['user_id'][:20]:20s} | {r['status']:10s} | {r['source']:15s} | {str(r['strategy'] or '?'):25s} | {r['regime']}")

print()
print('=== DEMO VIRTUAL ACCOUNTS (current) ===')
cur.execute("SELECT user_id, strategy, cash_balance FROM virtual_accounts WHERE user_id LIKE 'demo_%'")
for r in cur.fetchall():
    print(f"  {r['user_id']:30s} | {r['strategy']:25s} | ${float(r['cash_balance']):,.2f}")

print()
print('=== DEMO SHADOW POSITIONS ===')
cur.execute("SELECT user_id, strategy, symbol, quantity FROM shadow_positions WHERE user_id LIKE 'demo_%' ORDER BY user_id, symbol")
rows = cur.fetchall()
if not rows:
    print('  (empty — expected for fresh start)')
for r in rows:
    print(f"  {r['user_id']:30s} | {r['symbol']:15s} qty={r['quantity']}")

print()
print('=== REAL USER signal executions (last 30 min) ===')
cur.execute("""
    SELECT use.user_id, use.signal_id, use.status, use.source, use.executed_at
    FROM user_signal_executions use
    WHERE use.created_at > NOW() - INTERVAL '30 minutes'
      AND use.user_id NOT LIKE 'demo_%'
    ORDER BY use.created_at DESC
    LIMIT 10
""")
rows = cur.fetchall()
if not rows:
    print('  (none)')
for r in rows:
    print(f"  {r['user_id'][:32]:32s} | {r['status']:10s} | {r['source']:15s} | executed={r['executed_at']}")

conn.close()
print()
print('LIVE CHECK COMPLETE')
