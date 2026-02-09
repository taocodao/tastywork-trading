"""
Check for New Valid Signals
============================
Shows all pending signals with details.
"""

from src.earnings_intelligence.database import SignalRepository
from datetime import datetime, timedelta
import json

repo = SignalRepository()

# Get all pending signals
all_pending = repo.get_all_signals(status='pending')

print("=" * 60)
print("SIGNAL STATUS REPORT")
print("=" * 60)
print(f"Total pending signals: {len(all_pending)}\n")

# Separate by age
now = datetime.utcnow()
recent = [s for s in all_pending if (now - s.created_at).total_seconds() < 3600 * 3]  # Last 3 hours
today = [s for s in all_pending if (now - s.created_at).total_seconds() < 3600 * 12]  # Last 12 hours
old = [s for s in all_pending if (now - s.created_at).total_seconds() >= 3600 * 12]

print(f"✅ NEW (last 3h):  {len(recent)}")
print(f"📅 TODAY (12h):    {len(today)}")
print(f"❌ OLD (>12h):     {len(old)}")
print()

if recent:
    print("=" * 60)
    print("NEW SIGNALS (Last 3 Hours)")
    print("=" * 60)
    for s in sorted(recent, key=lambda x: x.created_at, reverse=True):
        age_min = int((now - s.created_at).total_seconds() / 60)
        print(f"\n{s.symbol} - {s.strategy}")
        print(f"  Created: {s.created_at.strftime('%m/%d %H:%M UTC')} ({age_min}min ago)")
        print(f"  Data: {json.dumps(s.data, indent=4)}")
else:
    print("⚠️  NO NEW SIGNALS IN LAST 3 HOURS")

if today and not recent:
    print("\n" + "=" * 60)
    print("TODAY'S SIGNALS (3-12 hours ago)")
    print("=" * 60)
    for s in sorted(today, key=lambda x: x.created_at, reverse=True):
        if s not in recent:
            age_h = int((now - s.created_at).total_seconds() / 3600)
            print(f"\n{s.symbol} - {s.strategy} ({age_h}h ago)")

if old:
    print("\n" + "=" * 60)
    print("OLD TEST SIGNALS (Should be cleaned up)")
    print("=" * 60)
    for s in sorted(old, key=lambda x: x.created_at, reverse=True):
        age_d = int((now - s.created_at).total_seconds() / 86400)
        print(f"  {s.symbol:8} | {s.strategy:16} | {age_d} days ago")
