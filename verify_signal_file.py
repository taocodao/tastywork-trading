import sys
import os
import logging

sys.path.append(os.getcwd())

output_file = "verification_result.txt"

try:
    from src.earnings_intelligence.database import get_session, Signal
    
    session = get_session()
    count = session.query(Signal).count()
    
    with open(output_file, "w") as f:
        f.write(f"Signal count: {count}\n")
        if count > 0:
            signals = session.query(Signal).order_by(Signal.created_at.desc()).limit(5).all()
            for s in signals:
                f.write(f"Signal: {s.id}, Symbol: {s.symbol}, Status: {s.status}\n")

except Exception as e:
    with open(output_file, "w") as f:
        f.write(f"Error: {e}\n")

finally:
    try:
        session.close()
    except:
        pass
