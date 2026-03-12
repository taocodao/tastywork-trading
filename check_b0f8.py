from src.earnings_intelligence.database import SignalRepository
try:
    repo = SignalRepository()
    sig = repo.get_signal("b0f82fbf-973e-4345-aaae-b42cda07a25a")
    print("Strategy is:", getattr(sig, "strategy", "None"))
    print(sig.to_dict() if sig else "Not found")
except Exception as e:
    print(e)
