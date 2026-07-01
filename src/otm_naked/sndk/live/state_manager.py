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
    """Persists open positions to JSON."""
    
    def __init__(self, data_dir="data"):
        self.state_file = Path(data_dir) / "sndk_live_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
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
            
    def add_position(self, pos: LivePosition):
        self.positions.append(pos)
        self.save()
        
    def remove_position(self, pos_id: str):
        self.positions = [p for p in self.positions if p.id != pos_id]
        self.save()
        
    def get_positions(self) -> list:
        return self.positions
