"""
Test Signal Publisher
=====================
Manually publish a test theta signal to WebSocket for frontend testing.
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from signal_publisher.theta import ThetaEntrySignal, publish_theta_entry_signal
import uuid


def publish_test_theta_signal():
    """Publish a sample theta signal for frontend testing."""
    
    # Create a realistic test signal
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
    print("📡 Publishing Test Theta Signal to WebSocket")
    print("=" * 60)
    print(f"Symbol: {signal.symbol}")
    print(f"Strike: ${signal.strike}")
    print(f"Expiration: {signal.expiration} ({signal.dte} DTE)")
    print(f"Premium: ${signal.entry_price}")
    print(f"Delta: {signal.delta:.2f}")
    print(f"Theta: ${signal.theta:.2f}")
    print(f"IV: {signal.iv * 100:.0f}%")
    print(f"P(OTM): {signal.probability_otm * 100:.0f}%")
    print(f"Contracts: {signal.contracts}")
    print(f"Total Premium: ${signal.total_premium:.2f}")
    print(f"Capital Required: ${signal.capital_required:,.0f}")
    print("=" * 60)
    
    # Publish to WebSocket
    success = publish_theta_entry_signal(signal)
    
    if success:
        print("✅ Signal published successfully!")
        print("   Check frontend at: http://localhost:3000/signals")
        print("   Or production: https://trademind.bot/signals")
    else:
        print("❌ Failed to publish signal")
        print("   Make sure WebSocket server is running on port 8004")
        print("   Run: python websocket_server.py")
    
    print("=" * 60)
    return success


if __name__ == "__main__":
    publish_test_theta_signal()
