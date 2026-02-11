"""
Delete all old signals from the database (older than 30 minutes)
"""
from src.earnings_intelligence.database import SignalRepository
from datetime import datetime, timedelta

repo = SignalRepository()

# Delete signals older than 30 minutes
cutoff = datetime.now() - timedelta(minutes=30)

signals = repo.get_all_signals(include_expired=True)
deleted = 0

print(f"\n{'='*80}")
print(f"Deleting signals older than 30 minutes (before {cutoff})")
print(f"{'='*80}\n")

for sig in signals:
    if sig.created_at < cutoff and sig.status == 'pending':
        age_minutes = (datetime.now() - sig.created_at).total_seconds() / 60
        print(f"Deleting: {sig.symbol} ({sig.strategy}) - {age_minutes:.0f} min old")
        
        # Delete from database
        try:
            repo.delete_signal(sig.id)
            deleted += 1
        except Exception as e:
            print(f"  ❌ Failed: {e}")

print(f"\n✅ Deleted {deleted} old signals")
print(f"Remaining signals: {len(repo.get_all_signals(include_expired=True))}")
