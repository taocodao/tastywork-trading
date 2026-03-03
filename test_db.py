import os
from dotenv import load_dotenv
load_dotenv()
from src.earnings_intelligence.database import SignalRepository

repo = SignalRepository()
signals = repo.get_all_signals()
print(f"Total signals in DB: {len(signals)}")

turbo = [s for s in signals if s.strategy == 'turbobounce']
print(f"Total turbobounce signals: {len(turbo)}")

for t in turbo:
    print(f"- {t.symbol} | status={t.status} | expires_at={t.expires_at}")
