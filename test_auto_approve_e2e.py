#!/usr/bin/env python3
"""
Test Auto-Approve End-to-End Flow
==================================
Creates a realistic test signal and pushes it through the complete pipeline:
1. Generate ThetaEntrySignal
2. Publish to WebSocket + Save to DB
3. Auto-approve check
4. Execute on Tastytrade (if criteria met)
5. Verify results

This tests the COMPLETE production flow.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
import uuid

# Import signal publisher (which has auto-approve wired in)
from signal_publisher.theta import ThetaEntrySignal, publish_theta_entry_signal

print("=" * 70)
print("🧪 AUTO-APPROVE END-TO-END TEST")
print("=" * 70)
print()

# Create a realistic test signal for SPY
# These parameters are designed to PASS auto-approve criteria
test_signal = ThetaEntrySignal(
    # Identity
    id=str(uuid.uuid4()),
    symbol="SPY",
    # Option details
    strike=580.0,  # ~30 delta assuming SPY around $595
    expiration=(datetime.now() + timedelta(days=30)).date(),
    dte=30,
    # Pricing
    entry_price=2.50,  # Bid price - $250 premium per contract
    ask=2.55,
    mid=2.525,
    # Greeks
    delta=0.30,
    theta=-0.05,
    vega=0.15,
    iv=0.22,  # 22% IV
    # Risk metrics
    confidence=75.0,  # High confidence to meet auto-approve threshold
    probability_otm=70.0,
    expected_premium=250.0,
    capital_required=58000.0,  # Strike * 100
    # Position sizing
    contracts=1,
    total_premium=250.0,  # $250 total
    total_capital_required=58000.0,  # Strike * 100
    # Metadata
    created_at=datetime.now()
)

print("📊 Test Signal Created:")
print(f"   Symbol: {test_signal.symbol}")
print(f"   Strike: ${test_signal.strike}")
print(f"   Premium: ${test_signal.total_premium}")
print(f"   Confidence: {test_signal.confidence}%")
print(f"   DTE: {test_signal.dte}")
print()

print("🚀 Publishing signal through production pipeline...")
print("   This will:")
print("   1. Save to database")
print("   2. Check auto-approve criteria")
print("   3. Execute on Tastytrade if approved")
print("   4. Broadcast to WebSocket")
print()

# Publish the signal - this triggers the ENTIRE flow including auto-approve
success = publish_theta_entry_signal(test_signal)

print()
print("=" * 70)
if success:
    print("✅ Signal published successfully!")
else:
    print("⚠️  Signal publish had issues (check logs above)")

print()
print("📋 Next Steps:")
print("   1. Check the logs above for auto-approve attempt")
print("   2. Look for: '🤖 Auto-approved theta signal' (success)")
print("   3. Or: 'Auto-approve skipped' (criteria not met)")
print("   4. Query database to see signal status:")
print()
print("      python3 -c \"")
print("      from src.earnings_intelligence.database import SignalRepository")
print(f"      repo = SignalRepository()")
print(f"      s = repo.get_signal('{test_signal.id}')")
print("      print(f'Status: {{s.status}}')")
print("      print(f'Data: {{s.data}}')\"")
print()
print("   5. Check frontend - signal should appear if not auto-approved")
print("=" * 70)
