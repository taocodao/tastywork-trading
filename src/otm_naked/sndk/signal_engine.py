"""
SNDK Dynamic Ladder Strategy - Signal Engine
==========================================
Replaces HILO-IV proximity logic with SNDK-specific trigger conditions:
1. |daily_move| >= 5%
2. IVR >= 65
3. |SPY 5d return| <= 3%
4. Days to earnings > 14
"""
import logging
import pandas as pd
from typing import Optional
from dataclasses import dataclass
from src.otm_naked.sndk.config import SNDKLadderConfig

logger = logging.getLogger(__name__)

@dataclass
class SNDKSignal:
    should_enter: bool
    direction: str       # "call" or "put" or "none"
    reason: str
    target_dte: int

class SNDKLadderSignalEngine:
    def __init__(self, config: Optional[SNDKLadderConfig] = None):
        self.config = config or SNDKLadderConfig()
        
    def evaluate(self, feat_row: pd.Series, current_rungs_call: int, current_rungs_put: int) -> SNDKSignal:
        """
        Evaluate entry conditions based on feature row.
        """
        daily_move = float(feat_row.get("daily_move_pct", 0.0))
        ivr = float(feat_row.get("ivr", 0.0))
        spy_5d = float(feat_row.get("spy_5d_return", 0.0))
        earnings_days = float(feat_row.get("earnings_days_away", 999))
        
        # Base direction from move
        raw_direction = "call" if daily_move > 0 else "put"
        
        # 1. IVR gate (primary entry filter per Perplexity Q9 recommendation)
        # At 150% IV, the 0.5% trigger fires 96% of days — meaningless.
        # IVR > ivr_min is the real signal.
        if ivr < self.config.ivr_min:
            return SNDKSignal(False, "none", f"IVR {ivr:.1f} < {self.config.ivr_min}", 0)
        
        # 2. Daily move check (secondary filter)
        trigger_pct = getattr(self.config, 'intraday_trigger_pct', self.config.entry_trigger_pct)
        if abs(daily_move) < trigger_pct:
            return SNDKSignal(False, "none", f"Move {daily_move:.1f}% < {trigger_pct}%", 0)
            
        # === Regime gate ===
        regime = str(feat_row.get("regime", "SIDEWAYS"))
        
        if regime == "NO_TRADE":
            return SNDKSignal(False, "none", f"Regime NO_TRADE (ADX>40 or H>0.65)", 0)
        
        if regime in ("UPTREND", "EXTREME_UPTREND"):
            if raw_direction == "call":
                # It's a green day. We don't want to sell calls in a bull run.
                # Instead of blocking the trade, we just sell PUTS with the trend!
                direction = "put"
            else:
                direction = "put"
                
        elif regime in ("DOWNTREND", "EXTREME_DOWNTREND"):
            if raw_direction == "put":
                # It's a red day in a bear run. We don't want to sell puts.
                # Instead of blocking, we sell CALLS with the trend.
                direction = "call"
            else:
                direction = "call"
        else:
            direction = raw_direction  # SIDEWAYS uses raw mean-reversion direction
        # === END regime gate ===
            
        # 3. Macro filter
        if abs(spy_5d) > self.config.macro_filter_spy_pct:
            return SNDKSignal(False, "none", f"SPY 5d {spy_5d:.1f}% > limit", 0)
            
        # 4. Earnings blackout
        if earnings_days <= 14:
            return SNDKSignal(False, "none", f"Earnings in {earnings_days}d", 0)
            
        # 5. Concentration limit
        if direction == "call" and current_rungs_call >= self.config.max_rungs_per_side:
            return SNDKSignal(False, direction, f"Max call rungs ({current_rungs_call}) reached", 0)
        if direction == "put" and current_rungs_put >= self.config.max_rungs_per_side:
            return SNDKSignal(False, direction, f"Max put rungs ({current_rungs_put}) reached", 0)
            
        # Target DTE based on IVR
        from src.otm_naked.sndk.iv_regime import get_dte_for_ivr
        target_dte = get_dte_for_ivr(ivr)
        
        # Regime-adjusted delta: conservative in trending regimes
        if regime in ("UPTREND", "DOWNTREND", "EXTREME_UPTREND", "EXTREME_DOWNTREND"):
            # Use delta 0.15 and 30 DTE minimum in trending regimes
            target_dte = max(target_dte, 30)
        
        return SNDKSignal(True, direction, f"Valid setup ({regime})", target_dte)
