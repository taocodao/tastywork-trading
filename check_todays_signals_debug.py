import sys
import os
from datetime import datetime
import pytz

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from src.earnings_intelligence.database import SignalRepository

def check_todays_signals():
    print(f"Checking for signals generated today ({datetime.now().date()})...")
    
    try:
        repo = SignalRepository()
        # include_expired=True so we see everything that was generated, 
        # even if it somehow already expired
        signals = repo.get_all_signals(include_expired=True)
        
        # Filter for today's signals locally just to be safe with timezones
        tz = pytz.timezone('US/Eastern')
        today_date = datetime.now(tz).date()
        
        todays_signals = []
        for s in signals:
            if s.created_at:
                # Convert UTC created_at to ET date
                dt_et = s.created_at.replace(tzinfo=pytz.utc).astimezone(tz)
                if dt_et.date() >= today_date:
                     todays_signals.append(s)
        
        print(f"\nFound {len(todays_signals)} signals generated today (ET).")
        
        for s in todays_signals:
            print(f"- {s.symbol} | Strategy: {s.strategy} | Status: {s.status}")
            print(f"  Created: {s.created_at} UTC")
            print(f"  Expires: {s.expires_at} UTC")
            
    except Exception as e:
        print(f"Error checking DB: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    check_todays_signals()
