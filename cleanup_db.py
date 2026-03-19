import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")

conn = psycopg2.connect(db_url)
cur = conn.cursor()

try:
    print("Starting DB duplicate cleanup...")
    cur.execute("""
        WITH duplicates AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY symbol, strategy, CAST(created_at AS DATE)
                       ORDER BY created_at DESC
                   ) as rn
            FROM signals s
            WHERE status = 'pending'
              AND NOT EXISTS (
                  SELECT 1 FROM user_signal_executions use 
                  WHERE use.signal_id = s.id
              )
        )
        DELETE FROM signals
        WHERE id IN (
            SELECT id FROM duplicates WHERE rn > 1
        )
        RETURNING id, strategy;
    """)
    
    deleted_rows = cur.fetchall()
    print(f"Deleted {len(deleted_rows)} duplicate pending signals.")
    for row in deleted_rows:
        print(row)
    
    conn.commit()
except Exception as e:
    print(f"Error: {e}")
    conn.rollback()
finally:
    cur.close()
    conn.close()
