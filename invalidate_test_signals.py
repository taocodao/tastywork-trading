"""
Invalidate Test Signals - Clean Database
=========================================
Marks old test signals as 'rejected' to clean up the queue.
"""

from src.earnings_intelligence.database import SignalRepository
from datetime import datetime, timedelta

repo = SignalRepository()

# Get all pending signals
all_pending = repo.get_all_signals(status='pending')
print(f"📊 Total pending signals: {len(all_pending)}\n")

# Mark signals older than 6 hours as rejected (test signals)
cutoff_time = datetime.utcnow() - timedelta(hours=6)

invalidated = 0
for signal in all_pending:
    if signal.created_at < cutoff_time:
        repo.update_signal_status(signal.id, 'rejected')
        print(f"❌ Invalidated: {signal.symbol:6} ({signal.strategy:15}) - {signal.created_at}")
        invalidated += 1

print(f"\n✅ Invalidated {invalidated} test signals")

# Show remaining
remaining = repo.get_all_signals(status='pending')
print(f"\n📈 Remaining pending signals: {len(remaining)}")

if remaining:
    print("\n=== ACTIVE SIGNALS ===")
    for s in remaining:
        age_hours = (datetime.utcnow() - s.created_at).total_seconds() / 3600
        print(f"{s.symbol:6} | {s.strategy:15} | {age_hours:.1f}h ago")
