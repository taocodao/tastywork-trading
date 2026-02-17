
"""
DVO Signal Generator
====================
Generates Deep Value Overlay entry signals.
Orchestrates:
1. Regime Check (Classifier)
2. Fundamental Valuation (GravityEngine)
3. Risk Check (RiskGuardian)
4. Quality Filtering
"""

import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional

from .gravity_engine import GravityEngine, ValuationResult
from .regime_classifier import DvorRegimeClassifier
from .risk_guardian import RiskGuardian

logger = logging.getLogger(__name__)

@dataclass
class DVOSignal:
    symbol: str
    signal_type: str = "ENTRY" # ENTRY
    strategy: str = "dvo"
    
    # Fundamental
    current_price: float = 0.0
    fair_value: float = 0.0
    margin_of_safety: float = 0.0
    quality_score: float = 0.0
    
    # Context
    regime: str = "UPTREND"
    confidence: float = 0.0
    
    # Trade Plan
    suggested_action: str = "SELL_PUT"
    suggested_structure: str = "PORTFOLIO_SECURED_PUT" # or +LEAPS_RECYCLING
    
    # Status
    created_at: str = ""

    def to_dict(self):
        return asdict(self)

class DVOSignalGenerator:
    def __init__(self, risk_level="MEDIUM"):
        self.gravity = GravityEngine()
        self.regime_clf = DvorRegimeClassifier()
        self.risk = RiskGuardian(risk_level)
        self.regime_clf.fetch_market_data() # Pre-load market data
        
    def generate_signals(self, universe: List[str], current_leverage: float = 0.0) -> List[DVOSignal]:
        """
        Scan universe for DVO opportunities.
        """
        signals = []
        
        # 1. Check Regime
        regime, reasoning = self.regime_clf.get_regime()
        logger.info(f"DVO Regime: {regime} ({reasoning})")
        
        # Global Kill Switch for Crisis
        if regime == "CRISIS":
            logger.warning("DVO Halted: CRISIS Regime.")
            return []
            
        # 2. Iterate Universe
        for symbol in universe:
            try:
                # A. Valuation (The heavy lift)
                val: ValuationResult = self.gravity.analyze(symbol)
                if not val: continue
                
                # B. Logic Gate
                
                # Gate 1: Margin of Safety vs Risk Profile
                # E.g. Medium risk needs 20% MoS
                min_mos = self.risk.profile.min_margin_of_safety
                if val.margin_of_safety_pct < min_mos:
                    logger.debug(f"{symbol}: MoS {val.margin_of_safety_pct:.2f} < {min_mos} (Skipping)")
                    continue
                    
                # Gate 2: Regime Filtering
                # LATE_CYCLE: Be very selective (maybe force higher MoS or skip)
                if regime == "LATE_CYCLE" and val.margin_of_safety_pct < (min_mos * 1.5):
                     logger.debug(f"{symbol}: LATE_CYCLE requires higher MoS (Skipping)")
                     continue
                     
                # C. Construct Signal
                sig = DVOSignal(
                    symbol=symbol,
                    current_price=val.current_price,
                    fair_value=val.fair_value_price,
                    margin_of_safety=val.margin_of_safety_pct,
                    quality_score=val.confidence_score, # Using confidence as proxy for now
                    regime=regime,
                    confidence=val.confidence_score,
                    suggested_action="INITIATE_OVERLAY",
                    created_at=datetime.utcnow().isoformat()
                )
                
                # Determine Structure (Recycling?)
                # If Aggressive/Medium profile AND Deep Value -> Enable Recycling
                if self.risk.profile.leaps_recycling_pct > 0 and val.margin_of_safety_pct > (min_mos + 0.05):
                     sig.suggested_structure = "SELL_PUT_PLUS_LEAPS"
                else:
                     sig.suggested_structure = "PORTFOLIO_SECURED_PUT_ONLY"
                     
                signals.append(sig)
                logger.info(f"✅ DVO Signal Generated: {symbol} (MoS {val.margin_of_safety_pct:.0%})")
                
            except Exception as e:
                logger.error(f"Signal gen error for {symbol}: {e}")
                
        return signals
