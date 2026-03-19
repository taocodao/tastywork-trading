import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("No DATABASE_URL found.")
    exit(1)

conn = psycopg2.connect(db_url)
cur = conn.cursor()

print("\n=== SIGNALS GENERATED TODAY ===")
cur.execute("""
    SELECT id, strategy, status, created_at, ts_rank 
    FROM (
        SELECT id, strategy, status, created_at, 1 as ts_rank FROM signals
    ) sub
    WHERE created_at > CURRENT_DATE
    ORDER BY created_at DESC
""")
rows = cur.fetchall()
if not rows:
    print("No signals found for today.")
else:
    for row in rows:
        print(row)

cur.close()
conn.close()
