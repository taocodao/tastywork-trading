import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
conn = psycopg2.connect(db_url)
cur = conn.cursor()

# Get column info
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'signals'
    ORDER BY ordinal_position;
""")
print("=== signals TABLE COLUMNS ===")
for row in cur.fetchall():
    print(row)

# Get a sample signal to see the data shape
cur.execute("""
    SELECT * FROM signals 
    WHERE strategy IN ('TQQQ_TURBOCORE','TQQQ_TURBOCORE_PRO') 
    ORDER BY created_at DESC LIMIT 2
""")
print("\n=== RECENT TURBOCORE SIGNALS ===")
cols = [desc[0] for desc in cur.description]
print("Columns:", cols)
for row in cur.fetchall():
    print(dict(zip(cols, row)))

cur.close()
conn.close()
