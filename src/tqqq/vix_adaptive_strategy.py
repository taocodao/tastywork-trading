"""
VIX-Adaptive Strategy
=====================
Core state machine for the TQQQ Leg Management Strategy.
"""

import logging
from typing import Dict, Any, Optional, Tuple

from src.tqqq import TQQQStrategyState
from src.tqqq.leg_manager import TQQQLegManager
from src.tqqq.position_tracker import TQQQPosition

from config import (
    TQQQ_MIN_DTE_LEGOUT,
    TQQQ_MIN_ENTRY_CONFIDENCE,
    TQQQ_MIN_LEGOUT_CONFIDENCE,
    TQQQ_MIN_LONG_PUT_VALUE,
    TQQQ_CALL_PARAMS_BY_REGIME,
    TQQQ_CALL_RALLY_CIRCUIT_BREAKER_PCT,
)

logger = logging.getLogger(__name__)

class VIXAdaptiveStrategy:
    """
    Main state machine for evaluating a TQQQ spread position.

    Supports two spread directions (validated via 6-year backtest):
      PUT CREDIT SPREAD  — LOW_VOL / NORMAL / HIGH_VOL (VIX falling)
      CALL CREDIT SPREAD — HIGH_VOL (VIX rising) / CRISIS

    Action Types:
      NONE               — Do nothing
      ENTER_SPREAD       — Open a new put credit spread
      ENTER_CALL_SPREAD  — Open a new bear call credit spread
      CLOSE_SPREAD       — Close full put spread (profit/loss/expiry)
      CLOSE_CALL_SPREAD  — Close full call spread (profit/loss/circuit breaker)
      LEG_OUT            — Buy back short put, retain long put
      LEG_OUT_CALL       — Buy back short call, retain long call
      SELL_LONG_PUT      — Take profit on retained long put
      SELL_LONG_CALL     — Take profit on retained long call
      ABANDON_LONG_PUT   — Give up on retained long put (theta decay)
      ABANDON_LONG_CALL  — Give up on retained long call
      ROLL_SPREAD        — Roll to a future expiration
    """

    def __init__(self, leg_manager=None):
        self.leg_manager = leg_manager or TQQQLegManager()

    def evaluate(
        self,
        position: TQQQPosition,
        regime: str,
        vix_direction: str,
        vix_confidence: float,
        current_spread_value: float,
        short_put_value: float,
        long_put_value: float,
        dte: int,
        rl_agent_action: Optional[int] = None,
        use_ppo: bool = True,
        # Call spread live values (default None if no call spread open)
        tqqq_entry_price: Optional[float] = None,   # TQQQ price when call spread was entered
        tqqq_current_price: Optional[float] = None, # TQQQ price right now (for circuit breaker)
        short_call_value: Optional[float] = None,
        long_call_value: Optional[float] = None,
        # Diagonal spread live values
        rsi_2: Optional[float] = None,
        sma_5: Optional[float] = None,
        regime_score: Optional[int] = None,
        ml_prob: Optional[float] = None,
        days_held: Optional[int] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Evaluates the current state and returns an action + detail dict.
        """
        from config import TQQQ_PARAMS_BY_REGIME
        params         = TQQQ_PARAMS_BY_REGIME.get(regime, TQQQ_PARAMS_BY_REGIME["NORMAL"])
        profit_target  = params["profit_target"]
        loss_limit_mult= params["loss_limit_mult"]
        legout_thresh  = params["legout_short_threshold"]
        lp_profit_tgt  = params["long_put_profit_target"]

        # --- PPO Agent Inference (put spread actions only for now) ---
        if use_ppo and rl_agent_action is None:
            try:
                from src.tqqq.ml.ppo_agent import TQQQPPOAgent
                agent    = TQQQPPOAgent()
                ppo_state = {
                    "position_state":    position.state.value if hasattr(position.state, 'value') else 0,
                    "spread_pnl_pct":    (position.original_credit - current_spread_value) / position.original_credit if position.original_credit > 0 else 0.0,
                    "short_put_pnl_pct": (position.original_credit*0.8 - short_put_value) / (position.original_credit*0.8) if position.original_credit > 0 else 0.0,
                    "dte":               dte,
                    "vix_level":         20.0,
                    "vix_trend":         1.0 if vix_direction == "VIX_RISING" else (-1.0 if vix_direction == "VIX_FALLING" else 0.0),
                    "tqqq_trend":        0.0,
                }
                action_int, confidence = agent.get_action(ppo_state)
                if confidence > 0.8:
                    rl_agent_action = action_int
            except ImportError:
                logger.warning("PPO Agent dependencies missing. Falling back to rules.")

        # --- RL Agent Override ---
        if rl_agent_action is not None and rl_agent_action != 0:
            action_map = {
                0: "NONE",            1: "ENTER_SPREAD",         2: "ENTER_SPREAD_DELAYED",
                3: "LEG_OUT",         4: "LEG_OUT_DELAYED",      5: "SELL_LONG_PUT",
                6: "SELL_LONG_PUT_DELAYED", 7: "CLOSE_SPREAD",   8: "CLOSE_SPREAD_DELAYED",
                9: "ROLL_SPREAD",    10: "ENTER_CALL_SPREAD",    11: "CLOSE_CALL_SPREAD",
            }
            mapped = action_map.get(rl_agent_action, "NONE")
            # Safety gates
            if mapped == "ENTER_SPREAD" and position.state != TQQQStrategyState.IDLE:
                mapped = "NONE"
            elif mapped == "ENTER_CALL_SPREAD" and position.state != TQQQStrategyState.IDLE:
                mapped = "NONE"
            elif mapped in ("CLOSE_SPREAD", "LEG_OUT", "ROLL_SPREAD") and position.state != TQQQStrategyState.FULL_SPREAD:
                mapped = "NONE"
            elif mapped == "CLOSE_CALL_SPREAD" and position.state != TQQQStrategyState.FULL_CALL_SPREAD:
                mapped = "NONE"
            elif mapped == "SELL_LONG_PUT" and position.state != TQQQStrategyState.LONG_PUT_ONLY:
                mapped = "NONE"
            if mapped != "NONE":
                logger.info(f"RL Agent override: {mapped}")
                return mapped, {"reason": "PPO_RL_AGENT"}

        # ─────────────────────────────────────────────────────────────────────
        # RULE-BASED STATE MACHINE
        # ─────────────────────────────────────────────────────────────────────

        # ── IDLE: Entry Decision ──────────────────────────────────────────────
        if position.state == TQQQStrategyState.IDLE:
        
            # First check for Diagonal entries (highest edge)
            # Intraday 5-min RSI-2 < 20 triggers the signal, with Hybrid Score >= 55
            # Now supports multiple entries per day based on `concurrent_diagonals` count.
            concurrent_diagonals = getattr(position, "concurrent_diagonals", 0)
            max_diagonals = getattr(position, "max_diagonals", 3)
            time_since_last_entry = getattr(position, "minutes_since_last_entry", 999)
            
            if concurrent_diagonals < max_diagonals:
                if rsi_2 is not None and rsi_2 < 20.0 and regime_score is not None and regime_score >= 55:
                    if time_since_last_entry >= 15: # 15-minute cooldown
                        logger.info(f"DIAGONAL ENTRY met (RSI: {rsi_2:.1f}, Score: {regime_score}, Active: {concurrent_diagonals}/{max_diagonals})")
                        return "ENTER_DIAGONAL", {"regime_score": regime_score, "ml_prob": ml_prob or 0.5}
                    else:
                        logger.info(f"DIAGONAL ENTRY skipped: Cooldown active ({time_since_last_entry}m < 15m)")
            else:
                if rsi_2 is not None and rsi_2 < 20.0 and regime_score is not None and regime_score >= 55:
                    logger.info(f"DIAGONAL ENTRY skipped: Max concurrent positions reached ({max_diagonals})")

            if regime == "CRISIS":
                # CRISIS: ONLY sell call spreads — puts are too risky during freefall.
                if vix_confidence >= TQQQ_MIN_ENTRY_CONFIDENCE:
                    cp = TQQQ_CALL_PARAMS_BY_REGIME.get("CRISIS")
                    logger.info(f"CRISIS regime: entering CALL SPREAD (bear call).")
                    return "ENTER_CALL_SPREAD", {"regime_params": cp}

            elif regime == "HIGH_VOL":
                if vix_direction == "VIX_RISING" and vix_confidence >= TQQQ_MIN_ENTRY_CONFIDENCE:
                    # VIX rising + high vol → market heading lower → sell calls
                    cp = TQQQ_CALL_PARAMS_BY_REGIME.get("HIGH_VOL")
                    logger.info("HIGH_VOL + VIX_RISING: entering CALL SPREAD.")
                    return "ENTER_CALL_SPREAD", {"regime_params": cp}
                elif vix_direction == "VIX_FALLING" and vix_confidence >= TQQQ_MIN_ENTRY_CONFIDENCE:
                    # VIX falling + high vol → recovery → sell puts (existing logic)
                    logger.info("HIGH_VOL + VIX_FALLING: entering PUT SPREAD.")
                    return "ENTER_SPREAD", {"regime_params": params}

            elif regime in ("NORMAL", "LOW_VOL"):
                # Put spreads only in calm/recovery regimes
                if vix_direction == "VIX_FALLING" and vix_confidence >= TQQQ_MIN_ENTRY_CONFIDENCE:
                    logger.info(f"{regime} + VIX_FALLING: entering PUT SPREAD.")
                    return "ENTER_SPREAD", {"regime_params": params}

            return "NONE", None

        # ── FULL_SPREAD (Put Credit Spread) ───────────────────────────────────
        elif position.state == TQQQStrategyState.FULL_SPREAD:
            if current_spread_value <= position.original_credit * (1 - profit_target):
                logger.info(f"Put spread profit target ({profit_target:.0%}) hit.")
                return "CLOSE_SPREAD", {"reason": "PROFIT_TARGET"}
            if current_spread_value >= position.original_credit * loss_limit_mult:
                logger.info(f"Put spread loss limit ({loss_limit_mult}×) hit.")
                return "CLOSE_SPREAD", {"reason": "LOSS_LIMIT"}
            if dte <= 7:
                logger.info("Put spread DTE ≤ 7. Closing to avoid assignment.")
                return "CLOSE_SPREAD", {"reason": "EXPIRATION_RISK"}
            if self.leg_manager.evaluate_leg_out(
                short_put_value=short_put_value, original_credit=position.original_credit,
                dte=dte, regime=regime, vix_direction=vix_direction,
                confidence=vix_confidence, legout_threshold=legout_thresh,
                min_dte=TQQQ_MIN_DTE_LEGOUT, min_confidence=TQQQ_MIN_LEGOUT_CONFIDENCE
            ):
                return "LEG_OUT", {"reason": "VIX_COMPRESSION",
                                   "short_value": short_put_value,
                                   "long_value_at_legout": long_put_value}
            return "NONE", None

        # ── FULL_CALL_SPREAD (Bear Call Credit Spread) ────────────────────────
        elif position.state == TQQQStrategyState.FULL_CALL_SPREAD:
            cp = TQQQ_CALL_PARAMS_BY_REGIME.get(regime, TQQQ_CALL_PARAMS_BY_REGIME.get("HIGH_VOL", {}))
            c_profit_target   = cp.get("profit_target",   0.70)
            c_loss_mult       = cp.get("loss_limit_mult", 2.0)
            c_legout_thresh   = cp.get("legout_short_threshold", 0.12)
            sc_val = short_call_value or 0.0
            lc_val = long_call_value  or 0.0
            call_spread_val   = sc_val - lc_val   # current cost to close

            # Circuit breaker: TQQQ rallied 5%+ since entry → emergency close
            if (tqqq_current_price and tqqq_entry_price and
                    ((tqqq_current_price - tqqq_entry_price) / tqqq_entry_price)
                    >= TQQQ_CALL_RALLY_CIRCUIT_BREAKER_PCT):
                rally_pct = (tqqq_current_price - tqqq_entry_price) / tqqq_entry_price * 100
                logger.warning(f"CIRCUIT BREAKER: TQQQ up {rally_pct:.1f}% since call spread entry. Emergency CLOSE.")
                return "CLOSE_CALL_SPREAD", {"reason": "RALLY_CIRCUIT_BREAKER",
                                              "rally_pct": rally_pct}

            # Profit target
            if call_spread_val <= position.original_credit * (1 - c_profit_target):
                logger.info(f"Call spread profit target ({c_profit_target:.0%}) hit.")
                return "CLOSE_CALL_SPREAD", {"reason": "PROFIT_TARGET"}

            # Max loss stop
            if call_spread_val >= position.original_credit * c_loss_mult:
                logger.info(f"Call spread loss limit ({c_loss_mult}×) hit.")
                return "CLOSE_CALL_SPREAD", {"reason": "LOSS_LIMIT"}

            # DTE exit (shorter than puts: 3 days for calls)
            if dte <= 3:
                logger.info("Call spread DTE ≤ 3. Closing.")
                return "CLOSE_CALL_SPREAD", {"reason": "EXPIRATION_RISK"}

            # Leg-out: if short call near worthless, buy it back and ride long call
            if sc_val <= position.original_credit * c_legout_thresh:
                logger.info("Short call near worthless. Legging out to hold long call.")
                return "LEG_OUT_CALL", {"reason": "SHORT_CALL_DECAY",
                                        "short_call_value": sc_val,
                                        "long_call_value": lc_val}
            return "NONE", None

        # ── LONG_PUT_ONLY (Retained long put after leg-out) ───────────────────
        elif position.state == TQQQStrategyState.LONG_PUT_ONLY:
            if self.leg_manager.evaluate_long_put_sell(
                long_put_current_value=long_put_value,
                long_put_legout_value=position.long_put_legout_value or 0.0,
                profit_target_mult=lp_profit_tgt, regime=regime, vix_direction=vix_direction
            ):
                return "SELL_LONG_PUT", {"reason": "VIX_SPIKE_PROFIT"}
            if self.leg_manager.evaluate_abandon(
                long_put_current_value=long_put_value,
                min_value=TQQQ_MIN_LONG_PUT_VALUE, dte=dte
            ):
                return "ABANDON_LONG_PUT", {"reason": "THETA_DECAY"}
            return "NONE", None

        # ── LONG_CALL_ONLY (Retained long call after leg-out) ─────────────────
        elif position.state == TQQQStrategyState.LONG_CALL_ONLY:
            cp = TQQQ_CALL_PARAMS_BY_REGIME.get(regime, {})
            lc_profit_tgt = cp.get("long_call_profit_target", 2.0)
            lc_legout_val = getattr(position, "long_call_legout_value", None) or 0.01

            # Take profit if long call appreciated significantly (market dropped further)
            if long_call_value and lc_legout_val and long_call_value >= lc_legout_val * lc_profit_tgt:
                logger.info(f"Long call hit {lc_profit_tgt}× profit target. Selling.")
                return "SELL_LONG_CALL", {"reason": "VIX_SPIKE_PROFIT",
                                           "long_call_value": long_call_value}
            # Abandon if worthless or DTE too short
            if (long_call_value and long_call_value < 0.05) or dte <= 2:
                logger.info("Long call near worthless or expiring. Abandoning.")
                return "ABANDON_LONG_CALL", {"reason": "THETA_DECAY"}
            return "NONE", None

        # ── DIAGONAL_OPEN (Put Diagonal Swing Trade) ──────────────────────────
        elif position.state == TQQQStrategyState.DIAGONAL_OPEN:
            try:
                from src.tqqq.swing_exit_engine import SwingExitEngine, ExitDecisionType
                engine = SwingExitEngine()
                decision = engine.evaluate(
                    position=position,
                    current_price=tqqq_current_price or 0.0,
                    rsi_2=rsi_2 or 50.0,
                    sma_5=sma_5 or 0.0,
                    regime_score=regime_score or 50,
                    ml_prob=ml_prob or 0.5,
                    days_held=days_held or 0
                )
                
                if decision.decision == ExitDecisionType.CLOSE_ALL:
                    logger.info(f"Closing diagonal spread: {decision.reason}")
                    return "CLOSE_DIAGONAL", {"reason": decision.reason, "priority": decision.priority}
                elif decision.decision == ExitDecisionType.ROLL_HEDGE:
                    logger.info(f"Rolling diagonal hedge: {decision.reason}")
                    return "ROLL_HEDGE", {"reason": decision.reason, "priority": decision.priority}
                
                return "NONE", None
            except ImportError:
                logger.error("SwingExitEngine missing, cannot evaluate DIAGONAL_OPEN state.")
                return "NONE", None

        return "NONE", None

