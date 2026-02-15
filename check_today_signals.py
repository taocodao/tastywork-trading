#!/usr/bin/env python3
"""Check if any signals were generated today."""

from datetime import datetime
from src.earnings_intelligence.database import SignalRepository

repo = SignalRepository()
signals = repo.get_all_signals(include_expired=True)

today = datetime.now().date()
today_signals = [s for s in signals if s.created_at.date() == today]

print(f"\n📊 Total signals generated today ({today}): {len(today_signals)}\n")

if today_signals:
    print("Time     | Strategy        | Symbol | Status")
    print("-" * 55)
    for s in sorted(today_signals, key=lambda x: x.created_at):
        time_str = s.created_at.strftime("%H:%M:%S")
        strategy_str = s.strategy[:15].ljust(15)
        symbol_str = s.symbol[:6].ljust(6)
        status_str = s.status
        print(f"{time_str} | {strategy_str} | {symbol_str} | {status_str}")
else:
    print("❌ No signals generated yet today.")
    print("\nChecking service logs for errors...")
