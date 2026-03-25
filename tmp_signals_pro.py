import sys
import os

sys.path.append(r'd:\Projects\tastywork-trading-1')

try:
    from signal_publisher.turbocore import publish_turbocore_rebalance_signal

    print("Publishing PRO test signal...")
    publish_turbocore_rebalance_signal(
        regime='TEST_PRO_CORRECTED', 
        confidence=0.98, 
        alloc_dict={'QQQ_LEAPS': 0.6, 'SGOV': 0.4}, 
        rationale='Manual Test Pro Corrected ID', 
        ema_signal=1, 
        sma200_gate=True, 
        strategy='TQQQ_TURBOCORE_PRO'
    )
    
    print("✅ Pro test signal sent successfully.")
except Exception as e:
    print(f"Error: {e}")
