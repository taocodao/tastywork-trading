"""
RegimeBase Dynamic Ladder Strategy - Signal Engine
==========================================
Replaces HILO-IV proximity logic with RegimeBase-specific trigger conditions:
1. |daily_move| >= 5%
2. IVR >= 65
3. |SPY 5d return| <= 3%
4. Days to earnings > 14
"""
import logging
import pandas as pd
from typing import Optional
from dataclasses import dataclass
from src.otm_naked.regime_base.config import RegimeBaseLadderConfig

logger = logging.getLogger(__name__)

@dataclass
class RegimeBaseSignal:
    should_enter: bool
    direction: str       # "call" or "put" or "none"
    reason: str
    target_dte: int

class RegimeBaseLadderSignalEngine:
    def __init__(self, config: Optional[RegimeBaseLadderConfig] = None):
        self.config = config or RegimeBaseLadderConfig()
        
    def evaluate(self, feat_row: pd.Series, current_rungs_call: int, current_rungs_put: int) -> RegimeBaseSignal:
        """
        Evaluate entry conditions based on feature row.
        """
        daily_move = float(feat_row.get("daily_move_pct", 0.0))
        ivr = float(feat_row.get("ivr", 0.0))
        spy_5d = float(feat_row.get("spy_5d_return", 0.0))
        earnings_days = float(feat_row.get("earnings_days_away", 999))
        
        # Base direction from move
        raw_direction = "call" if daily_move > 0 else "put"
        
        # 1. Daily move check
        if abs(daily_move) < self.config.entry_trigger_pct:
            return RegimeBaseSignal(False, "none", f"Move {daily_move:.1f}% < {self.config.entry_trigger_pct}%", 0)
            
        # === NEW: Regime gate ===
        regime = str(feat_row.get("regime", "SIDEWAYS"))
        
        if regime == "NO_TRADE":
            return RegimeBaseSignal(False, "none", f"Regime NO_TRADE (ADX>40 or H>0.65)", 0)
        
        if regime in ("UPTREND", "EXTREME_UPTREND") and raw_direction == "call":
            return RegimeBaseSignal(False, "none", f"{regime}: blocked short call", 0)
        
        if regime in ("DOWNTREND", "EXTREME_DOWNTREND") and raw_direction == "put":
            return RegimeBaseSignal(False, "none", f"{regime}: blocked short put", 0)
        
        direction = raw_direction  # Allowed by regime
        # === END regime gate ===
        
        # 2. IVR check
        if ivr < self.config.ivr_min:
            return RegimeBaseSignal(False, "none", f"IVR {ivr:.1f} < {self.config.ivr_min}", 0)
            
        # 3. Macro filter
        if abs(spy_5d) > self.config.macro_filter_spy_pct:
            return RegimeBaseSignal(False, "none", f"SPY 5d {spy_5d:.1f}% > limit", 0)
            
        # 4. Earnings blackout
        if earnings_days <= 14:
            return RegimeBaseSignal(False, "none", f"Earnings in {earnings_days}d", 0)
            
        # 5. Concentration limit
        if direction == "call" and current_rungs_call >= self.config.max_rungs_per_side:
            return RegimeBaseSignal(False, direction, f"Max call rungs ({current_rungs_call}) reached", 0)
        if direction == "put" and current_rungs_put >= self.config.max_rungs_per_side:
            return RegimeBaseSignal(False, direction, f"Max put rungs ({current_rungs_put}) reached", 0)
            
        # Target DTE based on IVR
        from src.otm_naked.regime_base.iv_regime import get_dte_for_ivr
        target_dte = get_dte_for_ivr(ivr)
        
        # Regime-adjusted delta: conservative in trending regimes
        if regime in ("UPTREND", "DOWNTREND", "EXTREME_UPTREND", "EXTREME_DOWNTREND"):
            # Use delta 0.15 and 30 DTE minimum in trending regimes
            target_dte = max(target_dte, 30)
        
        return RegimeBaseSignal(True, direction, f"Valid setup ({regime})", target_dte)
