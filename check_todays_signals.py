from src.earnings_intelligence.database import SignalRepository
from datetime import datetime, timezone

def check_signals():
    repo = SignalRepository()
    
    # get_all_signals returns Signal ORM objects; include_expired=True to see everything
    signals = repo.get_all_signals(include_expired=True)
    print(f"Total signals in DB (all): {len(signals)}")
    
    pending = repo.get_all_signals(status="pending")
    print(f"Pending (active, non-expired): {len(pending)}")
    
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    print(f"\n--- SIGNALS FOR TODAY ({today_str} UTC) ---")
    today_signals = [s for s in signals if s.created_at and s.created_at.strftime("%Y-%m-%d") == today_str]
    print(f"Count: {len(today_signals)}")
    
    for s in today_signals:
        print(f"  [{s.created_at.strftime('%H:%M:%S')}] {s.symbol} | {s.strategy} | Status: {s.status}")
    
    if not today_signals:
        print("  (none)")
    
    print(f"\n--- MOST RECENT SIGNALS (any date) ---")
    for s in signals[:10]:
        d = s.to_dict()
        print(f"  [{s.created_at}] {s.symbol} | {s.strategy} | Status: {s.status} | Action: {d.get('action', '?')}")

if __name__ == "__main__":
    check_signals()
