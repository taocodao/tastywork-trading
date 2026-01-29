import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.append(os.getcwd())

try:
    from src.earnings_intelligence.database import get_session, Signal
except ImportError:
    sys.exit(1)

def check_signals():
    session = get_session()
    try:
        count = session.query(Signal).count()
        print(f"Signal count: {count}")
        
        signals = session.query(Signal).order_by(Signal.created_at.desc()).limit(1).all()
        for s in signals:
            print(f"Latest signal: {s.id} - {s.symbol} - {s.status}")
            
    finally:
        session.close()

if __name__ == "__main__":
    check_signals()
