"""
Candidate Logger
================
Logs all raw candidates to SQLite, including rejected ones,
to build datasets for future ML retraining.
"""
import sqlite3
import json
from pathlib import Path
from .types import SignalCandidate

DB_DIR = Path(__file__).parent.parent.parent / "db"

class CandidateLogger:
    def __init__(self, db_path: str = None):
        if db_path is None:
            DB_DIR.mkdir(exist_ok=True)
            db_path = str(DB_DIR / "ema_cci_macd_candidates.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp        TEXT,
                symbol           TEXT,
                timeframe        TEXT,
                direction        TEXT,
                entry_price      REAL,
                stop_loss        REAL,
                regime           TEXT,
                ml_score         REAL,
                publish_decision INTEGER,
                features_json    TEXT,
                realized_label   INTEGER DEFAULT NULL,
                realized_r       REAL DEFAULT NULL
            )
        """)
        conn.commit()
        conn.close()

    def log_candidate(self, candidate: SignalCandidate):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO candidates
            (timestamp, symbol, timeframe, direction, entry_price, stop_loss,
             regime, ml_score, publish_decision, features_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            candidate.timestamp,
            candidate.symbol,
            candidate.timeframe,
            candidate.direction,
            candidate.entry_price,
            candidate.stop_loss,
            candidate.regime,
            candidate.ml_score,
            1 if candidate.publish_decision else 0,
            json.dumps(candidate.features) if candidate.features else "{}"
        ))
        conn.commit()
        conn.close()
