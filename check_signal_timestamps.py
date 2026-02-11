"""
Quick script to check signal timestamps in the database
"""
from src.earnings_intelligence.database import SignalRepository
from datetime import datetime

repo = SignalRepository()
signals = repo.get_all_signals(include_expired=True)

print(f"\n{'='*80}")
print(f"Total signals in database: {len(signals)}")
print(f"{'='*80}\n")

for sig in signals:
    created = sig.created_at if hasattr(sig, 'created_at') else None
    data_created = sig.data.get('created_at') if sig.data else None
    
    print(f"Signal ID: {sig.id}")
    print(f"  Symbol: {sig.symbol}")
    print(f"  Strategy: {sig.strategy}")
    print(f"  Status: {sig.status}")
    print(f"  DB created_at: {created}")
    print(f"  Data created_at: {data_created}")
    
    if created:
        # Check if created today
        today = datetime.now().date()
        created_date = created.date() if isinstance(created, datetime) else None
        if created_date == today:
            print(f"  ✅ CREATED TODAY")
        else:
            print(f"  ⏰ Age: {(datetime.now() - created).total_seconds() / 60:.1f} minutes ago")
    else:
        print(f"  ❌ NO TIMESTAMP")
    print()
