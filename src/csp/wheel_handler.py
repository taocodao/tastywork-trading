"""
Wheel Handler
=============

Post-assignment covered call logic.
Detects assignments from CSPs and scans for covered call candidates.
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.theta_spreads.options_analyzer import OptionsAnalyzer, PutScore

logger = logging.getLogger(__name__)

@dataclass
class CoveredCallCandidate:
    """Scored covered call candidate."""
    symbol: str
    underlying_price: float
    cost_basis: float
    strike: float
    expiration: datetime.date
    dte: int
    delta: float
    premium: float
    annualized_return_pct: float
    rationale: str

class WheelHandler:
    """
    Manages the 'covered call' phase of the Wheel strategy.
    """
    def __init__(self, data_provider=None):
        self.provider = data_provider
        # We repurpose OptionsAnalyzer but for Calls (requires slight adaptation)
        self.options_analyzer = OptionsAnalyzer(
            target_delta=0.30,
            delta_tolerance=0.10,
            dte_min=25,
            dte_max=45,
            min_premium=0.20
        )
        
    def scan_covered_calls(
        self, 
        symbol: str, 
        current_price: float, 
        cost_basis: float, 
        call_chain_data: List[Dict]
    ) -> List[CoveredCallCandidate]:
        """
        Scan a call chain for the best covered call above the cost basis.
        """
        logger.info(f"Scanning covered calls for {symbol} (Basis: ${cost_basis:.2f}, Price: ${current_price:.2f})")
        
        candidates = []
        for opt in call_chain_data:
            # 1. basic filters
            if opt.get('type') != 'C':
                continue
                
            strike = opt.get('strike', 0)
            
            # Rule: Strike MUST be above adjusted cost basis
            if strike <= cost_basis:
                continue
                
            # Filter by DTE
            expiration_str = opt.get('expiration')
            try:
                exp_date = datetime.strptime(expiration_str, '%Y-%m-%d').date()
            except:
                continue
                
            dte = (exp_date - datetime.now().date()).days
            if dte < 25 or dte > 45:
                continue
                
            # Filter by Delta
            delta = abs(opt.get('delta', 0))
            if delta < 0.20 or delta > 0.40:
                continue
                
            # Calculate metrics
            mid_price = (opt.get('bid', 0) + opt.get('ask', 0)) / 2
            if mid_price < 0.20:
                continue
                
            ann_return = (mid_price / current_price) * (365 / dte)
            
            candidates.append(CoveredCallCandidate(
                symbol=symbol,
                underlying_price=current_price,
                cost_basis=cost_basis,
                strike=strike,
                expiration=exp_date,
                dte=dte,
                delta=delta,
                premium=mid_price,
                annualized_return_pct=ann_return,
                rationale=f"Delta {delta:.2f} | Strike ${strike} > Basis ${cost_basis:.2f}"
            ))
            
        # Sort by annualized return
        candidates.sort(key=lambda x: x.annualized_return_pct, reverse=True)
        return candidates
