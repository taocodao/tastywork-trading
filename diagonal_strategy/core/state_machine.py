"""
Active Diagonal State Machine
=============================
The core state machine for the TA-driven actively managed short put diagonal.
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)

class DiagonalState(Enum):
    IDLE = auto()
    FULL_DIAGONAL = auto()     # Both anchor (long-dated put) + hedge active
    ANCHOR_ONLY = auto()       # Hedge closed, only anchor remaining
    RE_HEDGED = auto()         # New hedge bought (cycle N+1)
    CLOSING = auto()           # Winding down, no new cycles

@dataclass
class DiagonalCycle:
    """Tracks a single hedge buy/close cycle within a position."""
    cycle_number: int
    hedge_entry_date: date
    hedge_entry_price: float         # debit paid for hedge
    hedge_close_date: Optional[date] = None
    hedge_close_price: Optional[float] = None  # credit received closing hedge
    hedge_strike: float = 0.0
    hedge_expiry: Optional[date] = None
    hedge_dte_at_entry: int = 0
    ta_score_at_entry: float = 0.0   # TA dip score when hedge was bought
    ta_score_at_close: float = 0.0   # TA bounce score when hedge was closed
    ml_confidence_at_entry: float = 0.0
    ml_confidence_at_close: float = 0.0

    @property
    def cycle_pnl(self) -> float:
        if self.hedge_close_price is not None:
            return self.hedge_close_price - self.hedge_entry_price
        return 0.0

@dataclass
class DiagonalPosition:
    """Full position state including anchor + all hedge cycles."""
    position_id: str
    state: DiagonalState = DiagonalState.IDLE
    contracts: int = 1
    
    # Anchor leg (long-dated short put - sold for credit)
    anchor_strike: float = 0.0
    anchor_expiry: Optional[date] = None
    anchor_entry_date: Optional[date] = None
    anchor_entry_credit: float = 0.0      # credit received selling anchor
    anchor_close_price: Optional[float] = None
    anchor_delta_at_entry: float = 0.0
    anchor_dte_at_entry: int = 0
    
    # Hedge cycles
    cycles: List[DiagonalCycle] = field(default_factory=list)
    max_cycles: int = 5                    # max re-hedge cycles
    
    # Tracking
    tqqq_price_at_entry: float = 0.0
    vix_at_entry: float = 0.0
    regime_at_entry: str = ""
    naked_since: Optional[datetime] = None  # when hedge was last closed
    max_naked_hours: int = 48               # force re-hedge after this
    
    # Targets
    anchor_profit_target_pct: float = 0.50
    anchor_stop_loss_mult: float = 2.0       # close at 2x credit received (meaning 1x loss)
    cycle_profit_target_pct: float = 0.60    # close hedge at 60% decay
    vix_spike_close_threshold: float = 3.0   # close anchor on 3pt VIX spike

    @property
    def current_cycle(self) -> Optional[DiagonalCycle]:
        return self.cycles[-1] if self.cycles else None
    
    @property
    def total_credits(self) -> float:
        """Total premium collected across all cycles."""
        total = self.anchor_entry_credit
        for c in self.cycles:
            total += c.cycle_pnl
        return total
    
    @property
    def is_risk_free(self) -> bool:
        """True if cumulative credits exceed spread max possible loss."""
        if not self.cycles:
            return False
        w = max(0, self.anchor_strike - self.cycles[0].hedge_strike)
        return self.total_credits >= w

    @property
    def cycles_completed(self) -> int:
        return sum(1 for c in self.cycles if c.hedge_close_date is not None)

class ActiveDiagonalManager:
    """
    Main state machine. Evaluates market conditions and transitions diagonal states.
    """
    def __init__(self, config, ta_engine, osc_predictor):
        self.config = config
        self.ta_engine = ta_engine
        self.osc_predictor = osc_predictor
    
    def evaluate(self, position: DiagonalPosition, market_data: Dict[str, Any]) -> str:
        """
        Returns one of: 'HOLD', 'OPEN_DIAGONAL', 'CLOSE_HEDGE', 'BUY_NEW_HEDGE',
        'CLOSE_ANCHOR', 'CLOSE_ALL', 'EMERGENCY_HEDGE'
        """
        ta_features = self.ta_engine.compute_features(market_data)
        if not ta_features:
            return 'HOLD'

        ml_pred = self.osc_predictor.predict(ta_features)
        
        if position.state == DiagonalState.IDLE:
            return self._evaluate_idle(position, ta_features, ml_pred, market_data)
            
        elif position.state in (DiagonalState.FULL_DIAGONAL, DiagonalState.RE_HEDGED):
            return self._evaluate_full_diagonal(position, ta_features, ml_pred, market_data)
            
        elif position.state == DiagonalState.ANCHOR_ONLY:
            return self._evaluate_anchor_only(position, ta_features, ml_pred, market_data)
            
        elif position.state == DiagonalState.CLOSING:
            return 'CLOSE_ALL'
            
        return 'HOLD'
    
    def _evaluate_idle(self, pos, ta, ml, mkt) -> str:
        dip_score = self.ta_engine.dip_score(ta)
        regime = mkt.get('regime', 'UNKNOWN')
        
        if regime not in ('LOW_VOL', 'NORMAL', 'HIGH_VOL'):
            return 'HOLD'
        
        # Core gate: TA dip score 
        threshold = self.config.TA_DIP_SCORE_THRESHOLD
        if regime == 'LOW_VOL':
            threshold *= 0.85  # 15% easier entry in calm markets
            
        if dip_score > threshold:
            # ML is a soft filter: only block if ML actively predicts DOWN with high confidence
            if ml['direction'] == 'DOWN' and ml['confidence'] > 0.60:
                return 'HOLD'
            return 'OPEN_DIAGONAL'
            
        return 'HOLD'

    def _evaluate_full_diagonal(self, pos, ta, ml, mkt) -> str:
        anchor_pnl_pct = self._anchor_pnl_pct(pos, mkt)
        
        # Priority 1: Stop Loss
        if anchor_pnl_pct <= -pos.anchor_stop_loss_mult:
            logger.info("FULL_DIAG: Stop loss breached.")
            return 'CLOSE_ALL'
            
        # Priority 2: Overall profit target
        if pos.total_credits > 0 and anchor_pnl_pct >= pos.anchor_profit_target_pct:
            logger.info("FULL_DIAG: Profit target met.")
            return 'CLOSE_ALL'
            
        # Priority 3: DTE Exit
        anchor_dte = (pos.anchor_expiry - mkt['current_date']).days if pos.anchor_expiry else 0
        if anchor_dte <= 7:
            logger.info("FULL_DIAG: Anchor DTE <= 7. Closing.")
            return 'CLOSE_ALL'
            
        # Priority 4: Hedge expiration
        hedge_dte = (pos.current_cycle.hedge_expiry - mkt['current_date']).days if (pos.current_cycle and pos.current_cycle.hedge_expiry) else 0
        if hedge_dte <= 1:
            logger.info("FULL_DIAG: Hedge about to expire. Closing hedge.")
            return 'CLOSE_HEDGE'

        # Priority 5: Bounce detected -> close hedge cheap
        bounce_score = self.ta_engine.bounce_score(ta)
        if bounce_score > self.config.TA_BOUNCE_SCORE_THRESHOLD:
            
            hedge_pnl_pct = self._hedge_pnl_pct(pos, mkt)
            if hedge_pnl_pct > pos.cycle_profit_target_pct:
                logger.info("FULL_DIAG: Bounce detected + hedge decayed. Closing hedge.")
                return 'CLOSE_HEDGE'
                
        return 'HOLD'

    def _evaluate_anchor_only(self, pos, ta, ml, mkt) -> str:
        anchor_pnl_pct = self._anchor_pnl_pct(pos, mkt)
        
        # Priority 1: Stop Loss
        if anchor_pnl_pct <= -pos.anchor_stop_loss_mult:
            logger.info("ANCHOR_ONLY: Stop loss breached.")
            return 'CLOSE_ALL'

        # Priority 2: Max Naked exposure
        if pos.naked_since:
            if isinstance(pos.naked_since, datetime):
                current_dt = datetime.combine(mkt['current_date'], datetime.min.time())
                hours_naked = (current_dt - pos.naked_since).total_seconds() / 3600
                if hours_naked > pos.max_naked_hours:
                    logger.info("ANCHOR_ONLY: Max naked hours exceeded.")
                    return 'EMERGENCY_HEDGE'
                
        # Priority 3: VIX Spike
        vix_change = mkt.get('vix_change_1d', 0.0)
        if vix_change > pos.vix_spike_close_threshold:
            logger.info("ANCHOR_ONLY: VIX Spike detected. Taking vega profit.")
            return 'CLOSE_ANCHOR'
            
        # Priority 4: Anchor Profit Target
        if anchor_pnl_pct >= pos.anchor_profit_target_pct:
            logger.info("ANCHOR_ONLY: Anchor profit target hit.")
            return 'CLOSE_ANCHOR'
            
        # Priority 5: New Dip -> Buy new hedge
        dip_score = self.ta_engine.dip_score(ta)
        if (dip_score > self.config.TA_DIP_SCORE_THRESHOLD and
            pos.cycles_completed < pos.max_cycles):
            # Only block re-hedge if ML confidently says UP (bounce continuing)
            if not (ml['direction'] == 'UP' and ml['confidence'] > 0.60):
                logger.info("ANCHOR_ONLY: New dip detected. Re-hedging.")
                return 'BUY_NEW_HEDGE'
            
        # Priority 6: Anchor DTE Exit
        anchor_dte = (pos.anchor_expiry - mkt['current_date']).days if pos.anchor_expiry else 0
        if anchor_dte <= 7:
            logger.info("ANCHOR_ONLY: Anchor DTE <= 7. Closing.")
            return 'CLOSE_ANCHOR'
            
        return 'HOLD'

    def _anchor_pnl_pct(self, pos, mkt) -> float:
        current = mkt.get('anchor_mid_price', pos.anchor_entry_credit)
        if pos.anchor_entry_credit == 0: return 0.0
        return (pos.anchor_entry_credit - current) / pos.anchor_entry_credit

    def _hedge_pnl_pct(self, pos, mkt) -> float:
        if not pos.current_cycle or pos.current_cycle.hedge_entry_price == 0:
            return 0.0
        current = mkt.get('hedge_mid_price', pos.current_cycle.hedge_entry_price)
        return (pos.current_cycle.hedge_entry_price - current) / pos.current_cycle.hedge_entry_price
