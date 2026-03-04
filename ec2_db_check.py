import os
from dotenv import load_dotenv
load_dotenv()
from src.earnings_intelligence.database import SignalRepository

try:
    repo = SignalRepository()
    signals = repo.get_all_signals()
    turbo = [s for s in signals if dict(s.data).get('strategy') == "turbobounce" or getattr(s, 'strategy', '') == "turbobounce"]
    print(f"Total Postgres Signals: {len(signals)}")
    print(f"Total Turbobounce Signals: {len(turbo)}")
    for t in turbo[-3:]:
        print(f"ID: {t.id} | Symbol: {t.symbol} | Date: {t.created_at}")
except Exception as e:
    print(f"DB Error: {e}")
