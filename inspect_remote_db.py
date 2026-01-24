
import os
import sys
import logging
from sqlalchemy import create_engine, text

# Add path for src imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.earnings_intelligence.database import SignalRepository, get_db

logging.basicConfig(level=logging.INFO)

def inspect_signals():
    print("--- Inspecting Signals Table ---")
    try:
        repo = SignalRepository()
        signals = repo.get_all_signals()
        print(f"Total Signals: {len(signals)}")
        
        pending = [s for s in signals if s.status == 'pending']
        print(f"Pending Signals: {len(pending)}")
        
        for s in pending[:5]:
            print(f"  - {s.symbol} {s.strategy} ({s.created_at})")
            
    except Exception as e:
        print(f"Error accessing DB: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    inspect_signals()
