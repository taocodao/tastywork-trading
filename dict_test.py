import os, json
from dotenv import load_dotenv
load_dotenv()
from src.earnings_intelligence.database import SignalRepository

repo = SignalRepository()
signals = repo.get_all_signals()

found = 0
for s in signals:
    s_dict = s.to_dict()
    if s_dict.get('strategy') == 'turbobounce':
        print(f"Found! Status: {s_dict.get('status')} | {s_dict}")
        found += 1
        if found >= 2: break

print(f"Total signals returned by get_all_signals: {len(signals)}")
