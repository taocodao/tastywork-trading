"""
Diagonal Position Tracker
=========================
Persists the Active Diagonal state machine to JSON to support multi-cycle loops
and restart capability.
"""

import json
import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, date
from diagonal_strategy.core.state_machine import DiagonalPosition, DiagonalCycle, DiagonalState

logger = logging.getLogger(__name__)

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, DiagonalState):
            return obj.name
        return super().default(obj)

def parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str: return None
    try:
        return date.fromisoformat(date_str[:10])
    except:
        return None

def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str: return None
    try:
        return datetime.fromisoformat(dt_str)
    except:
        return None

class DiagonalPositionTracker:
    def __init__(self, filepath: str = "data/diagonal_positions.json"):
        self.filepath = filepath
        self.positions: Dict[str, DiagonalPosition] = {}
        self.load()

    def load(self):
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath, 'r') as f:
                data = json.load(f)
            
            for pid, pdata in data.items():
                cycles = []
                for c in pdata.get('cycles', []):
                    cycle = DiagonalCycle(
                        cycle_number=c.get('cycle_number', 1),
                        hedge_entry_date=parse_date(c.get('hedge_entry_date')),
                        hedge_entry_price=c.get('hedge_entry_price', 0.0),
                        hedge_close_date=parse_date(c.get('hedge_close_date')),
                        hedge_close_price=c.get('hedge_close_price'),
                        hedge_strike=c.get('hedge_strike', 0.0),
                        hedge_expiry=parse_date(c.get('hedge_expiry')),
                        hedge_dte_at_entry=c.get('hedge_dte_at_entry', 0),
                        ta_score_at_entry=c.get('ta_score_at_entry', 0.0),
                        ta_score_at_close=c.get('ta_score_at_close', 0.0),
                        ml_confidence_at_entry=c.get('ml_confidence_at_entry', 0.0),
                        ml_confidence_at_close=c.get('ml_confidence_at_close', 0.0)
                    )
                    cycles.append(cycle)
                
                state_val = pdata.get('state', 'IDLE')
                if state_val.startswith('DiagonalState.'):
                    state_val = state_val.split('.')[1]
                
                pos = DiagonalPosition(
                    position_id=pid,
                    state=DiagonalState[state_val],
                    anchor_strike=pdata.get('anchor_strike', 0.0),
                    anchor_expiry=parse_date(pdata.get('anchor_expiry')),
                    anchor_entry_date=parse_date(pdata.get('anchor_entry_date')),
                    anchor_entry_credit=pdata.get('anchor_entry_credit', 0.0),
                    anchor_close_price=pdata.get('anchor_close_price'),
                    anchor_delta_at_entry=pdata.get('anchor_delta_at_entry', 0.0),
                    anchor_dte_at_entry=pdata.get('anchor_dte_at_entry', 0),
                    cycles=cycles,
                    max_cycles=pdata.get('max_cycles', 5),
                    tqqq_price_at_entry=pdata.get('tqqq_price_at_entry', 0.0),
                    vix_at_entry=pdata.get('vix_at_entry', 0.0),
                    regime_at_entry=pdata.get('regime_at_entry', ''),
                    naked_since=parse_datetime(pdata.get('naked_since')),
                    max_naked_hours=pdata.get('max_naked_hours', 48),
                    anchor_profit_target_pct=pdata.get('anchor_profit_target_pct', 0.50),
                    anchor_stop_loss_mult=pdata.get('anchor_stop_loss_mult', 2.0),
                    cycle_profit_target_pct=pdata.get('cycle_profit_target_pct', 0.60),
                    vix_spike_close_threshold=pdata.get('vix_spike_close_threshold', 3.0)
                )
                self.positions[pid] = pos
                
        except Exception as e:
            logger.error(f"Failed to load diagonal positions: {e}")

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
        try:
            data = {}
            for pid, pos in self.positions.items():
                pdict = pos.__dict__.copy()
                pdict['cycles'] = [c.__dict__ for c in pos.cycles]
                data[pid] = pdict
                
            with open(self.filepath, 'w') as f:
                json.dump(data, f, cls=CustomJSONEncoder, indent=2)
        except Exception as e:
            logger.error(f"Failed to save diagonal positions: {e}")

    def get_position(self, position_id: str) -> Optional[DiagonalPosition]:
        return self.positions.get(position_id)

    def update_position(self, pos: DiagonalPosition):
        self.positions[pos.position_id] = pos
        self.save()
        
    def get_active_positions(self) -> List[DiagonalPosition]:
        return [p for p in self.positions.values() if p.state != DiagonalState.IDLE]
