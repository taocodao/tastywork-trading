"""
Send a test Calendar Spread signal to the WebSocket server.
This simulates what the production scanner would send.
"""

import sys
import os
sys.path.insert(0, os.getcwd())

from datetime import datetime, timedelta
import uuid

from signal_publisher.websocket_client import broadcast_to_channel

def send_test_calendar_signal():
    """Send a test calendar spread signal."""
    
    # Calculate realistic dates
    today = datetime.now()
    front_expiry = today + timedelta(days=7)  # 1 week out
    back_expiry = today + timedelta(days=30)  # 1 month out
    
    # Create a realistic test signal
    signal = {
        "id": str(uuid.uuid4()),
        "symbol": "SPY",
        "strategy": "Calendar Spread",
        "direction": "neutral",
        "strike": 605,  # Near current SPY price
        "stockPrice": 604.50,
        "frontExpiry": front_expiry.strftime("%Y-%m-%d"),
        "backExpiry": back_expiry.strftime("%Y-%m-%d"),
        "cost": 285,  # $2.85 per spread
        "potentialReturn": 100,  # $1.00 target
        "returnPercent": 35.0,
        "winRate": 72,
        "riskLevel": "Medium",
        "status": "pending",
        "createdAt": today.isoformat(),
        "expiresAt": (front_expiry - timedelta(days=1)).isoformat(),
        "score": 78.5,
        "iv": 18.5,
        "thetaEdge": 0.12,
        "rationale": "Theta edge $0.12/day, IV 18.5%, Score 78.5 - Test signal for approval flow"
    }
    
    print(f"📡 Sending test calendar spread signal...")
    print(f"   Symbol: {signal['symbol']}")
    print(f"   Strike: ${signal['strike']}")
    print(f"   Front Expiry: {signal['frontExpiry']}")
    print(f"   Back Expiry: {signal['backExpiry']}")
    print(f"   Cost: ${signal['cost']}")
    print(f"   ID: {signal['id']}")
    
    # Broadcast to WebSocket
    success = broadcast_to_channel("calendar_spread", signal)
    
    if success:
        print(f"\n✅ Signal sent successfully!")
        print(f"   Check https://www.trademind.bot/signals to see it")
    else:
        print(f"\n❌ Failed to send signal")
        print(f"   Is the WebSocket server running?")
    
    return success

if __name__ == "__main__":
    send_test_calendar_signal()
