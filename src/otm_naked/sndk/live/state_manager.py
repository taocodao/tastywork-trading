import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class LivePosition:
    id: str
    symbol: str
    opt_type: str
    strike: float
    expiry: str
    entry_premium: float
    entry_delta: float
    entry_iv: float
    entry_date: str
    contracts: int
    target_dte: int
    
class StateManager:
    """Persists open positions and trade logs to JSON."""
    
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.state_file = self.data_dir / "sndk_live_state.json"
        self.log_file = self.data_dir / "sndk_trades.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.positions = []
        self.load()
        
    def load(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.positions = [LivePosition(**p) for p in data]
                logger.info(f"Loaded {len(self.positions)} open positions from state file.")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
                self.positions = []
                
    def save(self):
        try:
            with open(self.state_file, 'w') as f:
                json.dump([asdict(p) for p in self.positions], f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            
    def log_trade(self, pos: LivePosition, action: str, price: float, realized_pnl: float = 0.0, reason: str = ""):
        """Append trade log to JSONL."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "id": pos.id,
            "symbol": pos.symbol,
            "type": pos.opt_type,
            "strike": pos.strike,
            "expiry": pos.expiry,
            "contracts": pos.contracts,
            "price": price,
            "realized_pnl": realized_pnl,
            "reason": reason
        }
        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"Failed to write trade log: {e}")
            
    def add_position(self, pos: LivePosition):
        self.positions.append(pos)
        self.save()
        self.log_trade(pos, "OPEN", pos.entry_premium, reason="Signal Entry")
        
    def remove_position(self, pos_id: str, exit_price: float, reason: str):
        pos = next((p for p in self.positions if p.id == pos_id), None)
        if pos:
            realized = (pos.entry_premium - exit_price) * pos.contracts * 100
            self.log_trade(pos, "CLOSE", exit_price, realized_pnl=realized, reason=reason)
            self.positions = [p for p in self.positions if p.id != pos_id]
            self.save()
            
    def get_positions(self) -> list:
        return self.positions
