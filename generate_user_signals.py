import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from signal_publisher.turbocore import publish_turbocore_rebalance_signal

def generate_signals():
    print("Generating TurboCore signal...")
    publish_turbocore_rebalance_signal(
        regime='BULL', 
        confidence=0.88, 
        alloc_dict={'TQQQ': 0.70, 'QLD': 0.20, 'QQQ': 0.10}, 
        rationale='Manual generation: BULL regime detected with high confidence.', 
        ema_signal=1, 
        sma200_gate=True, 
        strategy='TQQQ_TURBOCORE'
    )
    
    print("Generating TurboCore Pro signal...")
    publish_turbocore_rebalance_signal(
        regime='SIDEWAYS', 
        confidence=0.75, 
        alloc_dict={'TQQQ': 0.30, 'QLD': 0.20, 'QQQ': 0.20, 'SGOV': 0.30}, 
        rationale='Manual generation: SIDEWAYS regime detected. Conservative allocation.', 
        ema_signal=0, 
        sma200_gate=True, 
        strategy='TQQQ_TURBOCORE_PRO'
    )
    
    print("✅ Signals generated successfully.")

if __name__ == "__main__":
    generate_signals()
