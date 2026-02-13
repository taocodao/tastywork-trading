import sys
import os
import uuid
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.earnings_intelligence.database import Base, Signal

# Explicitly set the production DATABASE_URL
# database_url = "postgresql://erichuang2005:Ya2039349@travelwise-marketplace-db.curmg864eafo.us-east-1.rds.amazonaws.com:5432/ib_trading"
# Or read from env if preferred, but let's be explicit to avoid "NOT SET" errors
os.environ['DATABASE_URL'] = "postgresql://erichuang2005:Ya2039349@travelwise-marketplace-db.curmg864eafo.us-east-1.rds.amazonaws.com:5432/ib_trading"

print(f"Connecting to DB: {os.environ['DATABASE_URL']}")

engine = create_engine(os.environ['DATABASE_URL'])
Session = sessionmaker(bind=engine)
session = Session()

try:
    # Ensure tables exist (though they should)
    # Base.metadata.create_all(engine) 
    
    now = datetime.utcnow()
    # Expire at market close (4 PM ET = 21:00 UTC)
    today = now.date()
    # If it's past 21:00 UTC, expire tomorrow? No, let's just set it to 21:00 UTC today for testing.
    expires_at = datetime(today.year, today.month, today.day, 21, 0, 0)
    
    # 1. Theta Signal
    theta_id = f"theta_test_{uuid.uuid4().hex[:8]}"
    theta_data = {
        "id": theta_id,
        "symbol": "SPY",
        "strategy": "theta",
        "signal_type": "entry",
        "strike": 575.0, # Realistic strike
        "expiration": "2026-03-20",
        "dte": 36,
        "entry_price": 3.45,
        "contracts": 1,
        "status": "pending",
        "risk_level": "MODERATE",
        "createdAt": now.isoformat() + "Z", # Frontend expects ISO string with Z
        "expiresAt": expires_at.isoformat() + "Z",
        "rationale": "Test Theta Signal generated at " + now.isoformat()
    }
    
    theta_signal = Signal(
        id=theta_id,
        symbol="SPY",
        strategy="theta",
        status="pending",
        data=theta_data,
        created_at=now,
        expires_at=expires_at
    )
    session.add(theta_signal)
    
    # 2. Diagonal Signal
    diag_id = f"diag_test_{uuid.uuid4().hex[:8]}"
    diag_data = {
        "id": diag_id,
        "symbol": "SPY",
        "strategy": "diagonal-spread",
        "direction": "BULLISH",
        "strike": 580.0,
        "frontExpiry": "2026-02-27",
        "backExpiry": "2026-03-06",
        "cost": 2.15,
        "potentialReturn": 150.0,
        "returnPercent": 15.5,
        "winRate": 68.0,
        "riskLevel": "LOW",
        "status": "pending",
        "createdAt": now.isoformat() + "Z",
        "expiresAt": expires_at.isoformat() + "Z",
        "rationale": "Test Diagonal Signal generated at " + now.isoformat()
    }
    
    diag_signal = Signal(
        id=diag_id,
        symbol="SPY",
        strategy="diagonal-spread",
        status="pending",
        data=diag_data,
        created_at=now,
        expires_at=expires_at
    )
    session.add(diag_signal)
    
    session.commit()
    print("✅ Successfully inserted 2 signals into PRODUCTION DB.")
    print(f"Theta ID: {theta_id}")
    print(f"Diagonal ID: {diag_id}")

except Exception as e:
    session.rollback()
    print(f"❌ Error inserting signals: {e}")
finally:
    session.close()
