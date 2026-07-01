"""
Signal Logger — SQLite Audit Trail
====================================
Persists every signal evaluation to a local SQLite database.
"""
import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path

DB_DIR = Path(__file__).parent.parent.parent / "db"


class SignalLogger:
    def __init__(self, db_path: str = None):
        if db_path is None:
            DB_DIR.mkdir(exist_ok=True)
            db_path = str(DB_DIR / "ema_cci_macd_signals.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT,
                symbol      TEXT,
                timeframe   TEXT,
                signal_type TEXT,
                price       REAL,
                stop_loss   REAL,
                cci         REAL,
                macd_hist   REAL,
                ema1        REAL,
                raw_json    TEXT
            )
        """)
        conn.commit()
        conn.close()

    def log_signal(self, candidate, timeframe: str = ""):
        if candidate is None:
            return
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO signals
            (timestamp, symbol, timeframe, signal_type, price,
             stop_loss, cci, macd_hist, ema1, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            candidate.timestamp,
            candidate.symbol, timeframe or candidate.timeframe,
            candidate.direction, candidate.entry_price, candidate.stop_loss,
            candidate.cci_value, candidate.macd_hist, candidate.ema1_value,
            json.dumps(candidate.to_dict())
        ))
        conn.commit()
        conn.close()

    def get_recent(self, limit: int = 50):
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return rows
