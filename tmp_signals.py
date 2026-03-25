import sys
import os

# Add project root to path
sys.path.append(r'd:\Projects\tastywork-trading-1')

try:
    from signal_publisher.turbocore import publish_turbocore_rebalance_signal

    print("Publishing CORE test signal...")
    publish_turbocore_rebalance_signal(
        regime='TEST_CORE', 
        confidence=0.85, 
        alloc_dict={'TQQQ': 0.6, 'SGOV': 0.4}, 
        rationale='Manual Test Core', 
        ema_signal=1, 
        sma200_gate=True, 
        strategy='TQQQ_TURBOCORE'
    )
    
    print("Publishing PRO test signal...")
    publish_turbocore_rebalance_signal(
        regime='TEST_PRO', 
        confidence=0.95, 
        alloc_dict={'UPRO': 0.5, 'TMF': 0.5}, 
        rationale='Manual Test Pro', 
        ema_signal=1, 
        sma200_gate=True, 
        strategy='TURBOCORE_PRO'
    )
    
    print("✅ All test signals sent successfully.")
except Exception as e:
    print(f"Error: {e}")
