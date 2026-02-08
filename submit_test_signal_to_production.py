"""
Manual Test Signal Submission to Production
============================================
Submits a test theta signal directly to EC2 production database
via SSH, bypassing local network issues.

This script:
1. SSHs into EC2
2. Creates a test signal using the production database
3. Saves to database (which WebSocket clients can fetch)
4. Broadcasts via local WebSocket server
5. Does NOT interfere with the scheduler

Usage:
    python submit_test_signal_to_production.py
"""

import subprocess
import sys
import os

# EC2 connection details
EC2_HOST = "ubuntu@ec2-34-235-119-67.compute-1.amazonaws.com"
SSH_KEY = r"D:\Projects\IB-program-trading\tradecoin-bot-key.pem"

# Python script to run on EC2
REMOTE_SCRIPT = """
cd ~/tastywork-trading

python3 - <<'PYTHON_SCRIPT'
import sys
import os
sys.path.insert(0, '/home/ubuntu/tastywork-trading')

from datetime import datetime, timedelta
from signal_publisher.theta import ThetaEntrySignal, publish_theta_entry_signal
import uuid

# Create test signal
expiration_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

signal = ThetaEntrySignal(
    id=str(uuid.uuid4()),
    symbol="SPY",
    
    # Option details
    strike=575.0,
    expiration=expiration_date,
    dte=30,
    
    # Pricing
    entry_price=2.85,
    ask=2.90,
    mid=2.85,
    
    # Greeks
    delta=-0.32,
    theta=0.08,
    vega=0.15,
    iv=0.18,
    
    # Risk metrics
    confidence=78.5,
    probability_otm=0.68,
    expected_premium=285.0,
    capital_required=57500.0,
    
    # Position sizing
    contracts=1,
    total_premium=285.0,
    total_capital_required=57500.0,
    
    # Metadata
    created_at=datetime.now(),
    action="SELL_TO_OPEN",
    status="pending"
)

print("=" * 60)
print("📡 Publishing Test Theta Signal to Production")
print("=" * 60)
print(f"Signal ID: {signal.id}")
print(f"Symbol: {signal.symbol}")
print(f"Strike: ${signal.strike}")
print(f"Expiration: {signal.expiration} ({signal.dte} DTE)")
print(f"Premium: ${signal.entry_price}")
print(f"Delta: {signal.delta:.2f}")
print(f"Theta: ${signal.theta:.2f}")
print(f"IV: {signal.iv * 100:.0f}%")
print(f"P(OTM): {signal.probability_otm * 100:.0f}%")
print(f"Total Premium: ${signal.total_premium:.2f}")
print(f"Capital Required: ${signal.capital_required:,.0f}")
print("=" * 60)

# Publish (saves to DB + broadcasts to WebSocket)
success = publish_theta_entry_signal(signal)

if success:
    print("✅ Test signal published to production!")
    print("   - Saved to database")
    print("   - Broadcast to WebSocket clients")
    print("   - Visible at: https://trademind.bot/signals")
    print()
    print("🔍 Verify in browser:")
    print("   1. Open https://trademind.bot/signals")
    print("   2. Look for SPY ThetaSignalCard")
    print("   3. Check console for WebSocket message")
else:
    print("❌ Failed to publish test signal")
    sys.exit(1)

print("=" * 60)
PYTHON_SCRIPT
"""


def submit_test_signal():
    """Submit test signal to production via SSH."""
    
    print("=" * 70)
    print("🚀 Submitting Test Theta Signal to Production")
    print("=" * 70)
    print()
    print(f"Target: {EC2_HOST}")
    print(f"Method: SSH with remote Python execution")
    print(f"Impact: Creates ONE test signal in production database")
    print()
    print("⚠️  This will create a LIVE signal visible to all users!")
    print()
    
    # Confirm with user
    response = input("Continue? (yes/no): ").strip().lower()
    if response != "yes":
        print("❌ Cancelled by user")
        return
    
    print()
    print("📡 Connecting to EC2 and executing...")
    print()
    
    # Build SSH command
    ssh_cmd = [
        "ssh",
        "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        EC2_HOST,
        REMOTE_SCRIPT
    ]
    
    try:
        # Execute SSH command
        result = subprocess.run(
            ssh_cmd,
            capture_output=False,
            text=True,
            check=True
        )
        
        print()
        print("=" * 70)
        print("✅ Test signal submitted successfully!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Open https://trademind.bot/signals in browser")
        print("2. Verify ThetaSignalCard displays correctly")
        print("3. Check browser console for WebSocket messages")
        print("4. Test approval flow (optional)")
        print()
        
    except subprocess.CalledProcessError as e:
        print()
        print("=" * 70)
        print("❌ Failed to submit test signal")
        print("=" * 70)
        print()
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("1. Verify EC2 is accessible")
        print("2. Check SSH key path is correct")
        print("3. Ensure WebSocket server is running on EC2")
        print("4. Try SSH manually:")
        print(f"   ssh -i {SSH_KEY} {EC2_HOST}")
        print()
        sys.exit(1)
    
    except KeyboardInterrupt:
        print()
        print("❌ Cancelled by user (Ctrl+C)")
        sys.exit(1)


if __name__ == "__main__":
    submit_test_signal()
