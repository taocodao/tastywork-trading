"""
SNDK Dynamic Directional Strangle (DDS) - Signal Engine V3
==========================================================
Replaces the one-sided directional engine with a state machine for Short Strangles.
Outputs a DDSEvaluation with a list of DDSAction instructions.
"""
import logging
import pandas as pd
import numpy as np
from typing import List, Optional
from dataclasses import dataclass, field
from src.otm_naked.sndk.config import SNDKLadderConfig
from src.otm_naked.sndk.live.state_manager import LivePosition

logger = logging.getLogger(__name__)

@dataclass
class DDSAction:
    action: str       # "SELL_TO_OPEN" | "BUY_TO_CLOSE" | "HOLD"
    side: str         # "put" | "call"
    quantity: int
    reason: str
    target_delta: float
    target_dte: int

@dataclass
class DDSEvaluation:
    dss_score: float           # -1.0 to +1.0
    state: str                 # FLAT | BALANCED | CALL_HEAVY | PUT_HEAVY | ONE_SIDED
    actions: List[DDSAction]   # What to do now

class SNDKLadderSignalEngine:
    def __init__(self, config: Optional[SNDKLadderConfig] = None):
        self.config = config or SNDKLadderConfig()
        self.dss_model = None
        try:
            from src.otm_naked.sndk.dss_model import DSSModel
            model = DSSModel()
            if model.load_model():
                self.dss_model = model
                logger.info("XGBoost DSS Model loaded in Signal Engine.")
        except Exception as e:
            logger.error(f"Failed to initialize XGBoost DSS Model: {e}")
        
    def _rule_based_dss(self, roc_1d: float, roc_3d: float, ivr: float, regime: str) -> float:
        """
        Phase 3 fallback: Simple DSS proxy using existing features until XGBoost is ready.
        Positive DSS -> UP (close puts, add calls)
        Negative DSS -> DOWN (close calls, add puts)
        """
        score = 0.0
        # 1. 1-day move is the primary signal
        if abs(roc_1d) > 3.0:
            score += 0.40 * np.sign(roc_1d)
        elif abs(roc_1d) > 1.5:
            score += 0.20 * np.sign(roc_1d)
            
        # 2. 3-day momentum confirmation (approximate with daily_move_pct + prev days if available)
        # Assuming roc_3d is available in features, but if not we might use regime or EMA cross
        if abs(roc_3d) > 5.0:
            score += 0.30 * np.sign(roc_3d)
            
        # 3. Regime confirmation
        if regime in ("EXTREME_UPTREND", "UPTREND"):
            score += 0.20
        elif regime in ("EXTREME_DOWNTREND", "DOWNTREND"):
            score -= 0.20
            
        return float(np.clip(score, -1.0, 1.0))

    def evaluate(self, feat_row: pd.Series, positions: List[LivePosition]) -> DDSEvaluation:
        """
        Evaluate market conditions and current state to determine actions.
        """
        daily_move = float(feat_row.get("daily_move_pct", 0.0))
        roc_3d = float(feat_row.get("roc_5d", 0.0)) * 0.6  # proxy if roc_3d is missing
        ivr = float(feat_row.get("ivr", 0.0))
        spy_5d = float(feat_row.get("spy_5d_return", 0.0))
        earnings_days = float(feat_row.get("earnings_days_away", 999))
        regime = str(feat_row.get("regime", "SIDEWAYS"))
        
        # Determine DSS Score
        if self.dss_model is not None and self.dss_model.is_loaded:
            try:
                dss_score = self.dss_model.predict_dss(feat_row)
                logger.info(f"Using XGBoost DSS Score: {dss_score:.3f}")
            except Exception as e:
                logger.error(f"XGBoost prediction failed: {e}. Falling back.")
                dss_score = self._rule_based_dss(daily_move, roc_3d, ivr, regime)
        else:
            dss_score = self._rule_based_dss(daily_move, roc_3d, ivr, regime)
            logger.info(f"Using Rule-based DSS Score: {dss_score:.3f}")
        
        # Determine current DDS State
        open_puts = sum(p.contracts for p in positions if p.opt_type == "put")
        open_calls = sum(p.contracts for p in positions if p.opt_type == "call")
        
        if open_calls == 0 and open_puts == 0:
            current_state = "FLAT"
        elif open_calls > open_puts and open_puts == 0:
            current_state = "ONE_SIDED"
        elif open_puts > open_calls and open_calls == 0:
            current_state = "ONE_SIDED"
        elif open_calls > open_puts:
            current_state = "CALL_HEAVY"
        elif open_puts > open_calls:
            current_state = "PUT_HEAVY"
        else:
            current_state = "BALANCED"

        actions = []
        
        # Target DTE based on IVR
        from src.otm_naked.sndk.iv_regime import get_dte_for_ivr
        target_dte = get_dte_for_ivr(ivr)
        if regime in ("UPTREND", "DOWNTREND", "EXTREME_UPTREND", "EXTREME_DOWNTREND"):
            target_dte = max(target_dte, 30)
            
        base_delta = 0.15 if regime in ("UPTREND", "DOWNTREND", "EXTREME_UPTREND", "EXTREME_DOWNTREND") else self.config.initial_delta

        # Global gates for any opening trade
        gate_blocked = False
        gate_reason = ""
        if regime == "NO_TRADE":
            gate_blocked, gate_reason = True, "Regime NO_TRADE"
        elif abs(spy_5d) > self.config.macro_filter_spy_pct:
            gate_blocked, gate_reason = True, f"SPY 5d {spy_5d:.1f}% > limit"
        elif earnings_days <= 14:
            gate_blocked, gate_reason = True, f"Earnings in {earnings_days}d"

        # DDS State Transitions
        if current_state == "FLAT":
            if not gate_blocked and ivr >= self.config.ivr_min:
                # Open balanced strangle (1 put + 1 call)
                actions.append(DDSAction("SELL_TO_OPEN", "put", 1, "Initial Strangle Entry", base_delta, target_dte))
                actions.append(DDSAction("SELL_TO_OPEN", "call", 1, "Initial Strangle Entry", base_delta, target_dte))
                
        elif current_state == "BALANCED":
            if dss_score > 0.55:
                # Up move: Flip to CALL_HEAVY (sell more calls)
                # Note: We rely on RiskManager exits to take profit on the puts that are now cheap
                if not gate_blocked:
                    actions.append(DDSAction("SELL_TO_OPEN", "call", 1, f"Flip CALL_HEAVY (DSS={dss_score:.2f})", base_delta, target_dte))
            elif dss_score < -0.55:
                # Down move: Flip to PUT_HEAVY (sell more puts)
                if not gate_blocked:
                    actions.append(DDSAction("SELL_TO_OPEN", "put", 1, f"Flip PUT_HEAVY (DSS={dss_score:.2f})", base_delta, target_dte))
                    
        elif current_state == "CALL_HEAVY":
            if dss_score > 0.72:
                # Extreme up move: Flip to ONE_SIDED
                # We would aggressively close puts, but RiskManager handles closures.
                # Just add more calls if allowed
                if not gate_blocked:
                    actions.append(DDSAction("SELL_TO_OPEN", "call", 1, f"Flip ONE_SIDED (DSS={dss_score:.2f})", base_delta, target_dte))
            elif abs(dss_score) < 0.20 and ivr >= self.config.ivr_min:
                # Rebalance toward balanced if we have room
                if open_puts < open_calls and not gate_blocked:
                    actions.append(DDSAction("SELL_TO_OPEN", "put", 1, f"Rebalance to BALANCED (DSS={dss_score:.2f})", base_delta, target_dte))
                    
        elif current_state == "PUT_HEAVY":
            if dss_score < -0.72:
                if not gate_blocked:
                    actions.append(DDSAction("SELL_TO_OPEN", "put", 1, f"Flip ONE_SIDED (DSS={dss_score:.2f})", base_delta, target_dte))
            elif abs(dss_score) < 0.20 and ivr >= self.config.ivr_min:
                if open_calls < open_puts and not gate_blocked:
                    actions.append(DDSAction("SELL_TO_OPEN", "call", 1, f"Rebalance to BALANCED (DSS={dss_score:.2f})", base_delta, target_dte))
                    
        elif current_state == "ONE_SIDED":
            if abs(dss_score) < 0.20 and ivr >= self.config.ivr_min and not gate_blocked:
                # Try to rebalance back to balanced
                side_to_add = "put" if open_calls > 0 else "call"
                actions.append(DDSAction("SELL_TO_OPEN", side_to_add, 1, f"Rebalance from ONE_SIDED (DSS={dss_score:.2f})", base_delta, target_dte))

        return DDSEvaluation(
            dss_score=dss_score,
            state=current_state,
            actions=actions
        )
