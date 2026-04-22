#!/usr/bin/env python3
"""Diagnose why auto-execution isn't reflected in the UI."""
import os
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

ERIC = 'did:privy:cmkkla0tm03kzjm0d36dru'

print('=== TODAY\'s TURBOCORE Signals (last 4 hours) ===')
cur.execute("""
    SELECT id, strategy, status, created_at,
           data->>'regime' as regime,
           data->>'iv_switching_pending' as pending
    FROM signals
    WHERE strategy ILIKE '%TURBOCORE%'
      AND created_at > now() - INTERVAL '4 hours'
    ORDER BY created_at DESC LIMIT 10
""")
signals = cur.fetchall()
for s in signals:
    print(f"  id={str(s['id'])[:36]} | {s['strategy']:25s} | {s['regime']:10s} | pending={s['pending']} | {s['status']} | {s['created_at']}")

print()
print('=== Eric\'s Executions for those signals ===')
if signals:
    sig_ids = [str(s['id']) for s in signals]
    cur.execute("""
        SELECT user_id, signal_id::text, status, source, executed_at, created_at
        FROM user_signal_executions
        WHERE signal_id::text = ANY(%s)
        ORDER BY created_at DESC
    """, [sig_ids])
    rows = cur.fetchall()
    if not rows:
        print('  ⚠️  NONE — no execution records for any of those signal IDs')
    for r in rows:
        uid = r['user_id'][:28]
        print(f"  {uid:28s} | {r['signal_id']:36s} | {r['status']:10s} | {r['source']:15s} | exec={r['executed_at']}")

print()
print(f'=== ALL Executions for user {ERIC[:32]} ===')
cur.execute("""
    SELECT signal_id::text, status, source, executed_at, created_at
    FROM user_signal_executions
    WHERE user_id = %s
    ORDER BY created_at DESC LIMIT 10
""", [ERIC])
for r in cur.fetchall():
    print(f"  {r['signal_id']:36s} | {r['status']:10s} | {r['source']:15s} | {r['created_at']}")

print()
print('=== Latest signal the frontend would load ===')
cur.execute("""
    SELECT id, strategy, status, created_at,
           data->>'regime' as regime,
           data->>'legs' as legs,
           data->>'iv_switching_pending' as pending
    FROM signals
    WHERE strategy ILIKE '%TURBOCORE%'
      AND (data->>'iv_switching_pending')::boolean IS NOT TRUE
    ORDER BY created_at DESC LIMIT 3
""")
for s in cur.fetchall():
    print(f"  id={str(s['id'])[:36]} | {s['strategy']:25s} | {s['regime']} | pending={s['pending']} | {s['status']}")

print()
print('=== Checking if signal_id type mismatch (UUID vs text) ===')
cur.execute("""
    SELECT pg_typeof(id) as sig_type FROM signals LIMIT 1
""")
r = cur.fetchone()
print(f'  signals.id type: {r["sig_type"]}')

cur.execute("""
    SELECT pg_typeof(signal_id) as exec_type FROM user_signal_executions LIMIT 1
""")
r = cur.fetchone()
if r:
    print(f'  user_signal_executions.signal_id type: {r["exec_type"]}')

conn.close()
print()
print('DIAGNOSIS COMPLETE')
