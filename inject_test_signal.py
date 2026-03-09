import os
import sys

# Load environment to ensure DB connect works
from dotenv import load_dotenv
load_dotenv('.env')

# Add src to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from signal_publisher.turbocore import publish_turbocore_rebalance_signal

if __name__ == '__main__':
    print("Injecting test TurboCore Signal...")
    alloc = {
        "QQQ": 0.20,
        "QLD": 0.30,
        "TQQQ": 0.50,
        "SGOV": 0.00
    }
    
    data = publish_turbocore_rebalance_signal(
        regime="BULL",
        confidence=0.85,
        alloc_dict=alloc,
        rationale="Forced test signal to verify frontend display and execution E2E.",
        ema_signal=1,
        sma200_gate=True
    )
    
    print("Done. Signal ID is:", data.get('id'))
