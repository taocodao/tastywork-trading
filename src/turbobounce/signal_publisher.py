"""
TurboBounce Options: Signal Publisher
=====================================

Formats scanner/router outputs into standardized JSON signals that the 
Trademind frontend can consume via the backend API.
"""

import json
import logging
from datetime import datetime
from uuid import uuid4
import os
from typing import Dict, Any, List
from .strategy_router import RoutedStrategy
from .scoring import SymbolScore

logger = logging.getLogger(__name__)

class TurboBouncePublisher:
    def __init__(self, filename="turbobounce_signals.json"):
        # Default to ~/tastywork-trading/ directory
        home_dir = os.path.expanduser("~")
        tastywork_dir = os.path.join(home_dir, "tastywork-trading")
        self.filepath = os.path.join(tastywork_dir, filename)
        
        # Ensure directory exists
        os.makedirs(tastywork_dir, exist_ok=True)

    def publish_scanned_signals(self, 
                              oversold_picks: List[SymbolScore], 
                              overbought_picks: List[SymbolScore], 
                              routed_strategies: Dict[str, RoutedStrategy]):
        """
        Takes the day's top scanner picks and their routed strategies,
        formats them, and appends to the JSON file.
        """
        signals = []
        
        all_picks = oversold_picks + overbought_picks
        
        for rank, pick in enumerate(all_picks):
            sym = pick.symbol
            route = routed_strategies.get(sym)
            if not route:
                continue
                
            # Internal rank: 1-3 for oversold, 1-3 for overbought
            display_rank = rank + 1 if rank < 3 else (rank - 3) + 1
            
            signal_dict = {
                "id": str(uuid4()),
                "timestamp": datetime.now().isoformat(),
                "symbol": sym,
                "type": route.strategy_type,
                "strategy_name": "TurboBounce Multi-Ticker",
                "pool": "MULTI_TICKER",
                
                # Metrics for frontend display
                "direction": route.direction,
                "scanner_rank": display_rank,
                "total_score": round(pick.total_score, 1),
                "rsi_2": round(pick.rsi_2, 1),
                "iv_rank": round(pick.iv_rank, 1),
                "category": pick.category,
                "rationale": route.rationale,
                
                # Trade parameters for execution engine
                "target_anchor_dte": route.target_anchor_dte,
                "target_hedge_dte": route.target_hedge_dte,
                "target_delta": route.target_delta,
                
                "status": "PENDING"
            }
            signals.append(signal_dict)
            
        self._append_to_file(signals)
        logger.info(f"Published {len(signals)} TurboBounce Multi-Ticker signals to {self.filepath}")
        
    def _append_to_file(self, new_signals: List[Dict[str, Any]]):
        """Appends new signals array to existing JSON file, maintaining a flat list."""
        existing = []
        try:
            if os.path.exists(self.filepath):
                with open(self.filepath, "r") as f:
                    content = f.read().strip()
                    if content:
                        existing = json.loads(content)
                        if not isinstance(existing, list):
                            existing = [existing]
        except Exception as e:
            logger.error(f"Error reading {self.filepath}: {e}. Starting fresh.")
            
        # Add new signals
        existing.extend(new_signals)
        
        # Keep only the last 50 signals to prevent indefinite growth
        if len(existing) > 50:
            existing = existing[-50:]
            
        try:
            with open(self.filepath, "w") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write signals to {self.filepath}: {e}")
