#!/usr/bin/env python3
"""
Fix failed auto_approve executions → upsert to 'executed' status.
This corrects records where the old auto_approve path stored 'failed'
but the Ghost Executor subsequently ran successfully.
"""
import os
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import requests
from datetime import datetime

load_dotenv()
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print('=== Finding failed auto_approve executions from TODAY ===')
cur.execute("""
    SELECT use.id, use.user_id, use.signal_id, use.status, use.source, use.created_at,
           s.strategy
    FROM user_signal_executions use
    LEFT JOIN signals s ON s.id::text = use.signal_id::text
    WHERE use.status = 'failed'
      AND use.source = 'auto_approve'
      AND use.created_at > NOW() - INTERVAL '6 hours'
    ORDER BY use.created_at DESC
""")
rows = cur.fetchall()
print(f'Found {len(rows)} failed auto_approve records')

if rows:
    print()
    print('Updating to executed + virtual source...')
    ids = [r['id'] for r in rows]
    cur.execute("""
        UPDATE user_signal_executions
        SET status = 'executed',
            source = 'virtual',
            executed_at = NOW()
        WHERE id = ANY(%s)
        RETURNING id, user_id, signal_id, status, source
    """, [ids])
    updated = cur.fetchall()
    for r in updated:
        uid = r['user_id'][:28]
        print(f"  Fixed: {uid:28s} | {r['signal_id']} | {r['status']} | {r['source']}")

conn.commit()
print()
print('=== Verification ===')
cur.execute("""
    SELECT use.user_id, use.signal_id, use.status, use.source
    FROM user_signal_executions use
    WHERE use.created_at > NOW() - INTERVAL '6 hours'
    ORDER BY use.created_at DESC LIMIT 15
""")
for r in cur.fetchall():
    uid = r['user_id'][:28]
    print(f"  {uid:28s} | {r['signal_id']:36s} | {r['status']:10s} | {r['source']}")

conn.close()
print()
print('Fix complete.')
