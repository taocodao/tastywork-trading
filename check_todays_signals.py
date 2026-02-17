
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.getcwd())

from src.earnings_intelligence.database import SignalRepository, init_db

def check_signals():
    print("🔍 Checking for signals generated today...")
    
    # Ensure DB is initialized
    init_db()
    
    repo = SignalRepository()
    
    # Get all signals
    all_signals = repo.get_all_signals(include_expired=True)
    
    # Filter for today (UTC)
    today = datetime.utcnow().date()
    todays_signals = [s for s in all_signals if s.created_at.date() == today]
    
    if not todays_signals:
        print("❌ No signals found for today (UTC).")
        return

    print(f"\n✅ Found {len(todays_signals)} signals generated today:\n")
    print(f"{'TIME (UTC)':<20} | {'SYMBOL':<8} | {'STRATEGY':<15} | {'STATUS':<10} | {'CONFIDENCE':<10}")
    print("-" * 80)
    
    for s in todays_signals:
        conf = s.data.get('confidence', s.data.get('winRate', 0))
        print(f"{s.created_at.strftime('%H:%M:%S'):<20} | {s.symbol:<8} | {s.strategy:<15} | {s.status:<10} | {conf:<10}")

    # Check for executions
    executed = [s for s in todays_signals if s.status == 'executed']
    if executed:
        print(f"\n🚀 {len(executed)} EXECUTED SIGNALS:")
        for s in executed:
            print(f"- {s.symbol} {s.strategy}")
    else:
        print("\nℹ️ No signals executed today.")

if __name__ == "__main__":
    check_signals()
