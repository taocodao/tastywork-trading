from src.earnings_intelligence.database import UserSignalRepository
try:
    repo = UserSignalRepository()
    executions = repo.session.query(repo.model).order_by(repo.model.executed_at.desc()).limit(10).all()
    for ex in executions:
        print(f"User: {ex.user_id}, Signal: {ex.signal_id}, Status: {ex.status}, Order: {ex.order_id}, Time: {ex.executed_at}")
except Exception as e:
    print(e)
