import os
import json
import uuid
from datetime import datetime, timezone, timedelta
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

now = datetime.now(timezone.utc)
expires = now.replace(hour=19, minute=0, second=0, microsecond=0) + timedelta(days=1)

# ── Test Signal 1: TQQQ_TURBOCORE (BULL regime, aggressive allocation) ──────
core_id = str(uuid.uuid4())
core_data = {
    "id": core_id,
    "timestamp": now.isoformat(),
    "symbol": "TQQQ_PORT",
    "action": "REBALANCE",
    "strategy": "TQQQ_TURBOCORE",
    "type": "REBALANCE",
    "direction": "LONG",
    "confidence": 0.82,
    "rationale": "Regime: BULL | Conf: 82% | EMA Rising | SMA200 Gate: Pass",
    "expires_at": expires.isoformat(),
    "legs": [
        {"symbol": "TQQQ", "target_pct": 0.75},
        {"symbol": "QLD",  "target_pct": 0.15},
        {"symbol": "QQQ",  "target_pct": 0.10},
        {"symbol": "SGOV", "target_pct": 0.00},
    ],
    "cost": 0.0,
    "capital_required": 1000.0,
    "regime": "BULL",
    "ema_signal": 1,
    "sma200_gate": True,
}

# ── Test Signal 2: TQQQ_TURBOCORE_PRO (SIDEWAYS, conservative allocation) ──
pro_id = str(uuid.uuid4())
pro_data = {
    "id": pro_id,
    "timestamp": now.isoformat(),
    "symbol": "TQQQ_PORT",
    "action": "REBALANCE",
    "strategy": "TQQQ_TURBOCORE_PRO",
    "type": "REBALANCE",
    "direction": "LONG",
    "confidence": 0.68,
    "rationale": "Regime: SIDEWAYS | Conf: 68% | EMA Flat | SMA200 Gate: Pass",
    "expires_at": expires.isoformat(),
    "legs": [
        {"symbol": "TQQQ", "target_pct": 0.30},
        {"symbol": "QLD",  "target_pct": 0.20},
        {"symbol": "QQQ",  "target_pct": 0.20},
        {"symbol": "SGOV", "target_pct": 0.30},
    ],
    "cost": 0.0,
    "capital_required": 1000.0,
    "regime": "SIDEWAYS",
    "ema_signal": 0,
    "sma200_gate": True,
}

INSERT = """
    INSERT INTO signals (id, symbol, strategy, status, data, created_at, updated_at, expires_at)
    VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s)
"""

try:
    cur.execute(INSERT, (core_id, "TQQQ_PORT", "TQQQ_TURBOCORE",     json.dumps(core_data), now, now, expires))
    cur.execute(INSERT, (pro_id,  "TQQQ_PORT", "TQQQ_TURBOCORE_PRO", json.dumps(pro_data),  now, now, expires))
    conn.commit()
    print(f"✅ Inserted TURBOCORE signal    id={core_id}")
    print(f"✅ Inserted TURBOCORE_PRO signal id={pro_id}")
except Exception as e:
    conn.rollback()
    print(f"❌ Error: {e}")
finally:
    cur.close()
    conn.close()
