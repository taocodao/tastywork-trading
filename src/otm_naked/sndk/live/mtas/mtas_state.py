"""
Position state persistence for the MTAS ladder bot.

Deliberately a separate, minimal file from ../state_manager.py (used by bot_v41.py) --
LivePosition there has no spot_at_open field (needed here for the self-referencing
breakout-entry trigger) and mixing the two bots' state files would risk cross-contaminating
position tracking between two genuinely different strategies. Reuses nothing from
state_manager.py; ib_connector.py / market_data.py / order_executor.py ARE still reused
directly by mtas_ladder_manager.py since those are strategy-agnostic IB plumbing.
"""
import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MTASLeg:
    """One short-option rung in the ladder. Mirrors the `legs` dict entries created by
    open_leg() in real_rule_backtest_5m.py as closely as a live, broker-executed position
    allows."""
    id: str
    right: str                     # 'C' or 'P'
    strike: float
    expiry: str                    # IB format YYYYMMDD
    con_id: int
    quantity: int
    spot_at_open: float            # underlying price at fill -- used as the breakout trigger reference
    premium_open: float            # actual fill credit received per contract
    entry_date: str                # ISO timestamp
    rung_id: int                   # sequence number within this side's ladder, for logging only
    state: str = "OPEN"            # OPEN | CLOSED
    close_date: Optional[str] = None
    close_price: Optional[float] = None
    close_reason: Optional[str] = None
    realized_pnl: Optional[float] = None

    @property
    def dte(self) -> int:
        exp_date = datetime.strptime(self.expiry, "%Y%m%d").date()
        return max(0, (exp_date - datetime.now().date()).days)


class MTASStateManager:
    """Persists open/closed MTAS legs to JSON. Separate data_dir from the v4.1 bot."""

    def __init__(self, data_dir: str = "data_mtas"):
        self.data_dir = Path(data_dir)
        self.state_file = self.data_dir / "mtas_live_state.json"
        self.log_file = self.data_dir / "mtas_trades.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.legs: list[MTASLeg] = []
        self.load()

    def load(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    self.legs = [MTASLeg(**l) for l in data]
                logger.info(f"Loaded {len(self.legs)} open MTAS legs from state file.")
            except Exception as e:
                logger.error(f"Failed to load MTAS state: {e}")
                self.legs = []

    def save(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump([asdict(l) for l in self.legs], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save MTAS state: {e}")

    def log_trade(self, leg: MTASLeg, action: str, price: float, reason: str = ""):
        record = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "id": leg.id,
            "right": leg.right,
            "strike": leg.strike,
            "expiry": leg.expiry,
            "price": price,
            "reason": reason,
        }
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to write MTAS trade log: {e}")

    def add_leg(self, leg: MTASLeg):
        self.legs.append(leg)
        self.save()
        self.log_trade(leg, "OPEN", leg.premium_open, reason="entry")

    def close_leg(self, leg_id: str, close_price: float, reason: str, realized_pnl: float):
        leg = next((l for l in self.legs if l.id == leg_id), None)
        if leg is None:
            return
        leg.state = "CLOSED"
        leg.close_date = datetime.now().isoformat()
        leg.close_price = close_price
        leg.close_reason = reason
        leg.realized_pnl = realized_pnl
        self.log_trade(leg, "CLOSE", close_price, reason=reason)
        self.legs = [l for l in self.legs if l.id != leg_id]
        self.save()

    def get_open_legs(self, right: Optional[str] = None) -> list:
        legs = [l for l in self.legs if l.state == "OPEN"]
        return [l for l in legs if l.right == right] if right else legs

    def next_rung_id(self, right: str) -> int:
        existing = [l.rung_id for l in self.legs if l.right == right]
        return (max(existing) + 1) if existing else 1
