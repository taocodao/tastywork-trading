import sys
import os
import psycopg2
from datetime import datetime
import pytz

def check_ec2_db_signals():
    print(f"Checking EC2 Database for TurboBounce signals generated today...")
    
    # Load DB URL from env or use default if available locally
    # We will assume you have a local .env that points to the neon db, 
    # but let's query the production database specifically.
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        from dotenv import load_dotenv
        load_dotenv()
        db_url = os.environ.get("DATABASE_URL")
        
    if not db_url:
        print("DATABASE_URL not found in environment!")
        return
        
    print(f"Connecting to database...")
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Query for turbobounce signals
        cur.execute("""
            SELECT id, symbol, strategy, status, created_at, expires_at 
            FROM signals 
            WHERE strategy = 'turbobounce' 
            ORDER BY created_at DESC 
            LIMIT 20
        """)
        
        rows = cur.fetchall()
        
        tz = pytz.timezone('US/Eastern')
        today_date = datetime.now(tz).date()
        
        todays_signals = []
        for row in rows:
            signal_id, symbol, strategy, status, created_at, expires_at = row
            
            # Convert UTC created_at to ET date
            dt_et = created_at.replace(tzinfo=pytz.utc).astimezone(tz)
            if dt_et.date() >= today_date:
                 todays_signals.append(row)
                 
        print(f"\nFound {len(todays_signals)} TurboBounce signals generated today (ET).")
        
        for row in todays_signals:
            signal_id, symbol, strategy, status, created_at, expires_at = row
            print(f"- {symbol} | Status: {status}")
            print(f"  Created: {created_at} UTC")
            print(f"  Expires: {expires_at} UTC")
            
        cur.close()
        conn.close()
            
    except Exception as e:
        print(f"Error checking DB: {e}")

if __name__ == "__main__":
    check_ec2_db_signals()
