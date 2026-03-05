import sys
import os
import time

# Add src to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from signal_publisher.turbobounce import publish_turbobounce_entry_signal

def create_test_signal():
    print("Publishing fresh test TurboBounce signal...")
    
    # Create a fresh signal with tomorrow's expiration
    try:
        sig = publish_turbobounce_entry_signal(
            symbol="TEST_CIEN",
            action_type="BUY",
            direction="bullish",
            scanner_rank=1,
            total_score=85.5,
            rsi_2=15.2,
            iv_rank=30.4,
            category="TECH",
            rationale="Test signal to verify frontend rendering",
            target_anchor_dte=45,
            target_hedge_dte=14,
            target_delta=0.7
        )
        print(f"✅ Successfully published test signal: {sig.id}")
        print("Please check the TradeMind dashboard and signals page.")
    except Exception as e:
        print(f"❌ Failed to publish signal: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    create_test_signal()
