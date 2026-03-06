
import os
import sys
import time
from datetime import datetime, timezone

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.earnings_intelligence.database import SignalRepository

def profile_signals():
    print(f"DEBUG: Starting profile at {datetime.now()}")
    start_total = time.time()
    
    try:
        # 1. Init repo
        t1 = time.time()
        repo = SignalRepository()
        print(f"DEBUG: Repo init took {time.time() - t1:.4f}s")
        
        # 2. Query DB
        t2 = time.time()
        from src.earnings_intelligence.database import Signal
        total_count = repo.session.query(Signal).count()
        print(f"DEBUG: Total records in DB: {total_count}")
        
        t3 = time.time()
        signals = repo.get_all_signals(status='pending')
        print(f"DEBUG: DB Query (pending) took {time.time() - t3:.4f}s (Count: {len(signals)})")
        
        # 3. Serialization
        t4 = time.time()
        signal_dicts = [s.to_dict() for s in signals]
        print(f"DEBUG: Serialization took {time.time() - t4:.4f}s")
        
        # 4. Total
        print(f"DEBUG: Total logic took {time.time() - start_total:.4f}s")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    profile_signals()
