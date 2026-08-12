"""
Quick Test Signal Generator
Runs the signal generator on EC2 to create a fresh test signal
"""

import subprocess
import sys

EC2_HOST = "ubuntu@ec2-34-203-194-137.compute-1.amazonaws.com"
SSH_KEY = r"D:\Projects\IB-program-trading\tradecoin-bot-key.pem"

# Simple command to run signal generator
REMOTE_CMD = """
cd ~/tastywork-trading
python3 src/theta_spreads/signal_generator.py
"""

print("=" * 70)
print("🚀 Running Signal Generator on EC2")
print("=" * 70)
print()
print("This will generate a fresh theta signal and save it to the database.")
print("The signal will be immediately visible at https://trademind.bot/signals")
print()

response = input("Continue? (yes/no): ").strip().lower()
if response != "yes":
    print("❌ Cancelled")
    sys.exit(0)

print()
print("📡 Connecting to EC2...")
print()

try:
    result = subprocess.run(
        [
            "ssh",
            "-i", SSH_KEY,
            "-o", "StrictHostKeyChecking=no",
            EC2_HOST,
            REMOTE_CMD
        ],
        capture_output=False,
        text=True,
        check=True
    )
    
    print()
    print("=" * 70)
    print("✅ Signal generator executed!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Go to https://trademind.bot/signals")
    print("2. You should see a new theta signal")
    print("3. Click 'Approve' to test the trade execution")
    print()
    
except subprocess.CalledProcessError as e:
    print()
    print("=" * 70)
    print("❌ Failed to run signal generator")
    print("=" * 70)
    print(f"Error: {e}")
    sys.exit(1)

except KeyboardInterrupt:
    print("\n❌ Cancelled by user")
    sys.exit(1)
