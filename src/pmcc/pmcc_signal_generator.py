import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.pmcc.pmcc_screener import PMCCCandidate
from src.pmcc.pmcc_selector import PMCCSetup

logger = logging.getLogger(__name__)

@dataclass
class PMCCBaseSignal:
    """Base signal fields for all PMCC lifecycle events."""
    id: str
    symbol: str
    action: str  # ENTRY, CYCLE, ROLL, EXIT
    strategy: str = "PMCC"
    status: str = "NEW"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    rationale: str = ""
    confidence: int = 0
    
    def to_dict(self) -> Dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}

@dataclass
class PMCCEntrySignal(PMCCBaseSignal):
    """Signal to enter a new PMCC (Buy LEAPS, Sell short call)."""
    # Position Sizing
    contracts: int = 1
    total_risk: float = 0.0
    
    # LEAPS Leg
    long_strike: float = 0.0
    long_expiration: str = ""
    long_dte: int = 0
    long_delta: float = 0.0
    long_price: float = 0.0
    
    # Initial Short Call Leg
    short_strike: float = 0.0
    short_expiration: str = ""
    short_dte: int = 0
    short_delta: float = 0.0
    short_price: float = 0.0
    
    # Economics
    net_debit: float = 0.0
    max_loss: float = 0.0
    max_profit: float = 0.0
    break_even: float = 0.0
    bci_formula_met: bool = False
    
    # Context Features (for ML)
    composite_score: float = 0.0
    trend_score: float = 0.0
    iv_rank: float = 0.0


@dataclass
class PMCCShortCallSignal(PMCCBaseSignal):
    """Signal to sell a new short call cycle against an existing LEAPS."""
    position_id: str = ""
    cycle_number: int = 1
    
    # Short Call Leg
    short_strike: float = 0.0
    short_expiration: str = ""
    short_dte: int = 0
    short_delta: float = 0.0
    short_price: float = 0.0
    
    # Existing LEAPS info
    leaps_strike: float = 0.0
    leaps_break_even: float = 0.0


class PMCCSignalGenerator:
    """
    Transforms PMCC setups into structured Signals ready for publishing.
    Builds the human-readable rationale that explains algorithmic decisions.
    """
    
    def __init__(self):
        pass
        
    def generate_entry_signal(
        self, 
        candidate: PMCCCandidate, 
        setup: PMCCSetup
    ) -> PMCCEntrySignal:
        """
        Creates a new PMCC Entry signal from a Candidate and Setup.
        """
        signal_id = f"PMCC_ENTRY_{candidate.symbol}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{str(uuid.uuid4())[:6]}"
        
        # Build rationale
        rationale_parts = []
        if setup.bci_formula_met:
            rationale_parts.append("BCI criteria met (Break even below short strike).")
        else:
            rationale_parts.append("BCI criteria missed; leaning on ZEBRA composite score.")
            
        if candidate.iv_rank < 30:
            rationale_parts.append(f"Favorable IV Rank ({candidate.iv_rank:.1f}%).")
            
        if candidate.trend_score > 60:
            rationale_parts.append("Strong uptrend confirmed.")
            
        rationale_parts.append(f"Max Loss: ${setup.max_loss:.0f}/contract. Target Break-Even: ${setup.break_even:.2f}.")
        
        signal = PMCCEntrySignal(
            id=signal_id,
            symbol=candidate.symbol,
            action="ENTRY",
            rationale=" ".join(rationale_parts),
            confidence=setup.confidence,
            
            contracts=setup.contracts,
            total_risk=setup.max_loss * setup.contracts,
            
            long_strike=setup.long_strike,
            long_expiration=setup.long_expiration.isoformat(),
            long_dte=setup.long_dte,
            long_delta=setup.long_delta,
            long_price=setup.long_price,
            
            short_strike=setup.short_strike,
            short_expiration=setup.short_expiration.isoformat(),
            short_dte=setup.short_dte,
            short_delta=setup.short_delta,
            short_price=setup.short_price,
            
            net_debit=setup.net_debit,
            max_loss=setup.max_loss,
            max_profit=setup.max_profit,
            break_even=setup.break_even,
            bci_formula_met=setup.bci_formula_met,
            
            composite_score=candidate.composite_score,
            trend_score=candidate.trend_score,
            iv_rank=candidate.iv_rank
        )
        
        logger.info(f"Generated PMCC Entry Signal for {candidate.symbol}: ID {signal_id}")
        return signal

    def generate_cycle_signal(
        self,
        position_id: str,
        symbol: str, 
        cycle_number: int,
        short_option: Dict,
        leaps_strike: float,
        leaps_break_even: float,
        rationale: str
    ) -> PMCCShortCallSignal:
        """
        Creates a signal to sell the next short call cycle.
        """
        signal_id = f"PMCC_CYCLE_{symbol}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{str(uuid.uuid4())[:6]}"
        
        # Calculate DTE
        exp_date = short_option['expiration']
        dte = (exp_date - date.today()).days if isinstance(exp_date, date) else 0
        
        signal = PMCCShortCallSignal(
            id=signal_id,
            symbol=symbol,
            action="CYCLE",
            position_id=position_id,
            cycle_number=cycle_number,
            rationale=rationale,
            
            short_strike=short_option['strike'],
            short_expiration=exp_date.isoformat() if hasattr(exp_date, 'isoformat') else str(exp_date),
            short_dte=dte,
            short_delta=short_option['delta'],
            short_price=short_option['bid'] if short_option['bid'] > 0 else short_option['ask'],
            
            leaps_strike=leaps_strike,
            leaps_break_even=leaps_break_even
        )
        
        logger.info(f"Generated PMCC Cycle Signal for {symbol}: ID {signal_id}")
        return signal
