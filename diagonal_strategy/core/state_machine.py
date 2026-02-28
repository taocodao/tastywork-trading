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

    # Scale-in tracking
    scale_in_used: bool = False              # True after one scale-in (max 1 per position)

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
        'CLOSE_ANCHOR', 'CLOSE_ALL', 'EMERGENCY_HEDGE', 'SCALE_IN'
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
        """
        SWING MODE entry: RSI-2 < 10 + price > 200 MA + volume confirmation
        Research: 72-77% win rate with this signal stack
        """
        regime = mkt.get('regime', 'UNKNOWN')
        if regime not in ('LOW_VOL', 'NORMAL', 'HIGH_VOL'):
            return 'HOLD'

        # === LAYER 1: 200 MA Gate (most important crash guard) ===
        tqqq_price = mkt.get('tqqq_price', 0)
        ma_200 = mkt.get('tqqq_200ma', 0)
        if ma_200 > 0 and tqqq_price < ma_200:
            logger.debug(f"IDLE: Price {tqqq_price:.2f} < 200MA {ma_200:.2f} — no new trades")
            return 'HOLD'

        # === LAYER 2: VIX regime gate ===
        vix = mkt.get('vix_level', 20)
        vix_50sma = mkt.get('vix_50sma', vix)
        crisis_mult = getattr(self.config, 'CRASH_GUARD_VIX_CRISIS_MULT', 1.15)
        if vix_50sma > 0 and vix > vix_50sma * crisis_mult:
            logger.debug(f"IDLE: VIX crisis regime ({vix:.1f} > {vix_50sma:.1f}x{crisis_mult}) — no new trades")
            return 'HOLD'

        # === LAYER 3: ML crash guard (SuperTrend HIGH_VOL BEARISH) ===
        crash_guard_active = False
        if hasattr(self.ta_engine, 'ml_enhancer') and self.ta_engine.ml_enhancer is not None:
            crash_guard_active = getattr(self.ta_engine.ml_enhancer, 'is_crash_guard_active', False)
        if crash_guard_active:
            logger.debug("IDLE: ML crash guard active — no new trades")
            return 'HOLD'

        # === PRIMARY ENTRY SIGNAL: RSI-2 < 10 ===
        rsi2 = ta.get('rsi_2', 50)
        rsi2_threshold = getattr(self.config, 'SWING_ENTRY_RSI2_THRESHOLD', 10)
        if rsi2 >= rsi2_threshold:
            return 'HOLD'

        # === OPTIONAL: Volume capitulation confirmation ===
        if getattr(self.config, 'SWING_ENTRY_USE_VOLUME_CONFIRM', False):
            vol_mult = getattr(self.config, 'SWING_ENTRY_VOLUME_MULTIPLIER', 2.0)
            if ta.get('volume_ratio', 1.0) < vol_mult:
                logger.debug(f"IDLE: RSI-2={rsi2:.1f} but volume insufficient — waiting for capitulation")
                return 'HOLD'

        # === ML soft filter: only veto on very high DOWN confidence ===
        if ml['direction'] == 'DOWN' and ml['confidence'] > 0.70:
            logger.debug(f"IDLE: RSI-2 signal blocked by ML DOWN confidence {ml['confidence']:.2f}")
            return 'HOLD'

        logger.debug(f"IDLE: RSI-2={rsi2:.1f} < {rsi2_threshold} + price {tqqq_price:.2f} > 200MA {ma_200:.2f} — OPEN_DIAGONAL")
        return 'OPEN_DIAGONAL'

    def _evaluate_full_diagonal(self, pos, ta, ml, mkt) -> str:
        """
        SWING MODE: Close BOTH legs on bounce.
        Exit signals: price > 5-day MA, RSI-2 > 70, max hold days, stop loss.
        No hedge cycling — position is closed as a unit.
        """
        anchor_pnl_pct = self._anchor_pnl_pct(pos, mkt)
        regime = mkt.get('regime', 'NORMAL')
        params = self.config.TQQQ_DIAGONAL_PARAMS.get(regime, self.config.TQQQ_DIAGONAL_PARAMS['NORMAL'])

        # Priority 1: Stop Loss
        if anchor_pnl_pct <= -pos.anchor_stop_loss_mult:
            logger.info(f"SWING: Stop loss breached ({anchor_pnl_pct:.1%})")
            return 'CLOSE_ALL'

        # Priority 2: DTE Exit (anchor about to expire)
        anchor_dte = (pos.anchor_expiry - mkt['current_date']).days if pos.anchor_expiry else 0
        if anchor_dte <= 7:
            logger.info("SWING: Anchor DTE <= 7. Closing.")
            return 'CLOSE_ALL'

        # Priority 3: Layer 4 crash guard — single day crash
        tqqq_daily_chg = mkt.get('tqqq_daily_change', 0.0)
        crash_threshold = getattr(self.config, 'CRASH_GUARD_DAILY_DROP_PCT', -0.15)
        if tqqq_daily_chg <= crash_threshold:
            logger.info(f"SWING: Single-day crash {tqqq_daily_chg:.1%} — emergency exit")
            return 'CLOSE_ALL'

        # Priority 4: Max hold days (force close to avoid overstaying)
        if pos.anchor_entry_date:
            days_held = (mkt['current_date'] - pos.anchor_entry_date).days
            max_hold = params.get('swing_max_hold_days',
                                  getattr(self.config, 'SWING_EXIT_MAX_HOLD_DAYS', 7))
            if days_held >= max_hold:
                logger.info(f"SWING: Max hold days ({days_held}d >= {max_hold}d) — closing")
                return 'CLOSE_ALL'

        # Priority 5: BOUNCE EXIT — primary swing exit
        rsi2 = ta.get('rsi_2', 50)
        rsi2_exit = getattr(self.config, 'SWING_EXIT_RSI2_ABOVE', 70)
        tqqq_price = mkt.get('tqqq_price', 0)
        ma_5 = mkt.get('tqqq_5ma', 0)

        bounce_rsi = rsi2 > rsi2_exit
        bounce_5ma = (getattr(self.config, 'SWING_EXIT_ABOVE_5MA', True)
                      and ma_5 > 0 and tqqq_price > ma_5)

        if bounce_rsi or bounce_5ma:
            reason = f"RSI-2={rsi2:.1f} > {rsi2_exit}" if bounce_rsi else f"price {tqqq_price:.2f} > 5MA {ma_5:.2f}"
            logger.info(f"SWING: Bounce detected ({reason}) — CLOSE_ALL")
            return 'CLOSE_ALL'

        # Priority 6: Hedge expiration (keep hedge protection alive)
        hedge_dte = (pos.current_cycle.hedge_expiry - mkt['current_date']).days if (pos.current_cycle and pos.current_cycle.hedge_expiry) else 0
        if hedge_dte <= 1:
            # In swing mode, if hedge expires without bounce, close the whole position
            logger.info("SWING: Hedge expired without bounce — closing whole position")
            return 'CLOSE_ALL'

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
