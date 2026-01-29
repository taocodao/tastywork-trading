import sys
import os
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure the current directory is in the python path
sys.path.append(os.getcwd())

try:
    from signal_publisher import spread_setup_to_signal, save_signal_to_db
except ImportError as e:
    logger.error(f"Failed to import signal_publisher: {e}")
    sys.exit(1)

# Create a mock setup for testing
class MockSetup:
    def __init__(self):
        self.symbol = 'AAPL'
        self.strike = 150.0
        self.short_expiry = (datetime.now() + timedelta(days=7)).date()
        self.long_expiry = (datetime.now() + timedelta(days=30)).date()
        self.net_debit = 2.50
        self.stock_price = 150.5
        self.score = 75.0
        self.iv = 0.25
        self.theta_edge = 0.15

def generate_signal():
    try:
        setup = MockSetup()
        signal = spread_setup_to_signal(setup)
        save_signal_to_db(signal)
        print(f"✅ Created test signal: {signal['id']} for {signal['symbol']}")
        return signal['id']
    except Exception as e:
        logger.error(f"Failed to generate signal: {e}")
        return None

if __name__ == "__main__":
    cid = generate_signal()
    if cid:
        print(f"Signal ID: {cid}")
    else:
        sys.exit(1)
