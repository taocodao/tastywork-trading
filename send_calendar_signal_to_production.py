"""
Send Calendar Spread Test Signal to Production
===============================================
Submits a test calendar spread signal to EC2 via SSH.

Usage:
    python send_calendar_signal_to_production.py
"""

import subprocess
import sys

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
from signal_publisher.calendar import publish_calendar_signal
import uuid

# Mock SpreadSetup class
class SpreadSetup:
    def __init__(self):
        self.symbol = 'SPY'
        self.strike = 605.0
        self.short_expiry = (datetime.now() + timedelta(days=7)).date()
        self.long_expiry = (datetime.now() + timedelta(days=30)).date()
        self.net_debit = 2.85
        self.stock_price = 604.50
        self.score = 78.5
        self.iv = 0.185
        self.theta_edge = 0.12

setup = SpreadSetup()

print("=" * 60)
print("📡 Publishing Test Calendar Spread Signal to Production")
print("=" * 60)
print(f"Symbol: {setup.symbol}")
print(f"Strike: ${setup.strike}")
print(f"Front Expiry: {setup.short_expiry} (7 DTE)")
print(f"Back Expiry: {setup.long_expiry} (30 DTE)")
print(f"Cost: ${setup.net_debit * 100:.2f}")
print(f"IV: {setup.iv * 100:.0f}%")
print(f"Theta Edge: ${setup.theta_edge:.2f}/day")
print(f"Score: {setup.score:.1f}")
print("=" * 60)

# Publish (saves to DB + broadcasts to WebSocket)
success = publish_calendar_signal(setup, channel="calendar_spread")

if success:
    print("✅ Test calendar spread signal published!")
    print("   - Saved to in-memory store")
    print("   - Broadcast to WebSocket clients")
    print("   - Visible at: https://trademind.bot/signals")
    print()
    print("🔍 Verify in browser:")
    print("   1. Open https://trademind.bot/signals")
    print("   2. Look for SPY Calendar Spread")
    print("   3. Check browser console for WebSocket message")
    print("   4. Try approving it to test the flow")
else:
    print("❌ Failed to publish test signal")
    sys.exit(1)

print("=" * 60)
PYTHON_SCRIPT
"""


def send_calendar_signal():
    """Send calendar spread signal via SSH."""
    
    print("=" * 70)
    print("🚀 Sending Test Calendar Spread Signal to Production")
    print("=" * 70)
    print()
    print(f"Target: {EC2_HOST}")
    print(f"Method: SSH with remote Python execution")
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
        print("✅ Calendar spread signal sent successfully!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("1. Open https://trademind.bot/signals in browser")
        print("2. You should see the SPY calendar spread")
        print("3. Test the approval flow with the new fixes")
        print()
        
    except subprocess.CalledProcessError as e:
        print()
        print("=" * 70)
        print("❌ Failed to send signal")
        print("=" * 70)
        print(f"Error: {e}")
        sys.exit(1)
    
    except KeyboardInterrupt:
        print()
        print("❌ Cancelled by user (Ctrl+C)")
        sys.exit(1)


if __name__ == "__main__":
    send_calendar_signal()
