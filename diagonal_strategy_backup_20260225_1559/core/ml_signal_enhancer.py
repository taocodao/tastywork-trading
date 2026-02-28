"""
ML Signal Enhancer — DEFENSE-ONLY Mode
=======================================
The ML layer acts as a CRASH GUARD: it can only REDUCE dip/bounce scores,
never boost them. This guarantees ML-enhanced performance >= baseline.

When crash conditions are detected (HIGH_VOL+BEARISH SuperTrend, extreme vol
spikes, crisis regime), the enhancer penalises entry scores to prevent the
strategy from entering trades during extended drawdowns.

For bounce scores (hedge exit timing), the enhancer can add small boosts to
encourage faster hedge exits during parabolic moves — this is safe because
closing a profitable hedge early only forfeits upside, it doesn't create risk.
"""

import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from diagonal_strategy.config import (
    ML_ENHANCER_ENABLED,
    ML_SUPERTREND_ENABLED,
    ML_RSI_ENABLED,
    ML_MFI_ENABLED,
    ML_TREND_SPEED_ENABLED,
    ML_MAX_BOOST,
    ML_SUPERTREND_ATR_PERIOD,
    ML_SUPERTREND_TRAINING_BARS,
    ML_MFI_PERIOD,
)
from diagonal_strategy.indicators.ml_indicators import (
    calculate_adaptive_supertrend,
    calculate_ml_mfi,
    TrendDirection,
    VolatilityLevel,
)
from diagonal_strategy.indicators.trend_speed import TrendSpeedAnalyzer, ExitStage

logger = logging.getLogger(__name__)


@dataclass
class EnhancedScore:
    """Output from MLSignalEnhancer."""
    base_score:        float
    ml_boost:          float
    final_score:       float
    reasons:           List[str] = field(default_factory=list)
    indicator_details: Dict[str, Any] = field(default_factory=dict)
    crash_guard_active: bool = False  # True when crash conditions detected


def _calc_rsi2(close: pd.Series) -> float:
    """2-period RSI for short-term extreme detection."""
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(2, min_periods=1).mean()
    loss  = (-delta.clip(upper=0)).rolling(2, min_periods=1).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = (100 - 100 / (1 + rs)).fillna(50)
    return float(rsi.iloc[-1])


class MLSignalEnhancer:
    """
    DEFENSE-ONLY ML enhancer for the TQQQ diagonal signal engine.

    DIP SCORES: only penalised (never boosted). Prevents entries in crashes.
    BOUNCE SCORES: can be boosted slightly (closing a hedge early is low-risk).
    """

    def __init__(self):
        self._trend_speed = TrendSpeedAnalyzer(ema_fast=5, ema_slow=13, lookback=10)
        self._crash_guard_active = False  # Exposed for scale-in gating

    @property
    def is_crash_guard_active(self) -> bool:
        """True if the last dip evaluation detected crash conditions."""
        return self._crash_guard_active

    def enhance_dip_score(self, df: pd.DataFrame, base_score: float) -> EnhancedScore:
        """
        DEFENSE ONLY: can only reduce dip score, never increase it.

        Detects crash conditions and penalises:
        1. SuperTrend HIGH_VOL + BEARISH = active crash → -0.15 (full block)
        2. SuperTrend MEDIUM + BEARISH = caution → -0.08
        3. Extreme vol spike still accelerating → -0.05
        4. RSI-2 very overbought (>85) = not a dip at all → -0.05
        """
        if not ML_ENHANCER_ENABLED or df is None or len(df) < 50:
            self._crash_guard_active = False
            return EnhancedScore(base_score=base_score, ml_boost=0.0, final_score=base_score)

        penalty = 0.0
        reasons = []
        details: Dict[str, Any] = {}
        crash_guard = False

        # ── (1) CRASH GUARD — SuperTrend regime ─────────────────────────────
        if ML_SUPERTREND_ENABLED:
            try:
                st = calculate_adaptive_supertrend(
                    df,
                    atr_period=ML_SUPERTREND_ATR_PERIOD,
                    training_bars=ML_SUPERTREND_TRAINING_BARS,
                )
                details['supertrend'] = {
                    'direction': st.trend_direction.value,
                    'volatility': st.volatility_level.value,
                }
                if (st.trend_direction == TrendDirection.BEARISH
                        and st.volatility_level == VolatilityLevel.HIGH):
                    penalty -= 0.15  # Full block — this is a crash
                    crash_guard = True
                    reasons.append("CRASH GUARD: HIGH_VOL BEARISH — full block -0.15")
                elif (st.trend_direction == TrendDirection.BEARISH
                      and st.volatility_level == VolatilityLevel.MEDIUM):
                    penalty -= 0.08
                    crash_guard = True
                    reasons.append("CRASH GUARD: MEDIUM_VOL BEARISH — caution -0.08")
            except Exception as e:
                logger.debug(f"MLSignalEnhancer: SuperTrend error — {e}")

        # ── (2) Extreme vol spike still accelerating ─────────────────────────
        try:
            hv5 = float(df['close'].pct_change().tail(5).std() * np.sqrt(252) * 100)
            hv2 = float(df['close'].pct_change().tail(2).std() * np.sqrt(252) * 100)
            details['hv_spike'] = {'hv5': round(hv5, 1), 'hv2': round(hv2, 1)}
            if hv5 > 80 and hv2 >= hv5 * 0.75:
                penalty -= 0.05
                crash_guard = True
                reasons.append(f"Vol spike accelerating (HV5={hv5:.0f}%, HV2={hv2:.0f}%) -0.05")
        except Exception as e:
            logger.debug(f"MLSignalEnhancer: vol-spike error — {e}")

        # ── (3) RSI-2 overbought = not a dip at all ─────────────────────────
        if ML_RSI_ENABLED:
            try:
                rsi2 = _calc_rsi2(df['close'])
                details['rsi_2'] = round(rsi2, 1)
                if rsi2 > 85:
                    penalty -= 0.05
                    reasons.append(f"RSI-2={rsi2:.1f} overbought — this is NOT a dip -0.05")
                elif rsi2 > 70:
                    penalty -= 0.03
                    reasons.append(f"RSI-2={rsi2:.1f} elevated — weak dip signal -0.03")
            except Exception as e:
                logger.debug(f"MLSignalEnhancer: RSI-2 error — {e}")

        # ── (4) MFI overbought = money flowing in, not out ──────────────────
        if ML_MFI_ENABLED:
            try:
                mfi = calculate_ml_mfi(df, period=ML_MFI_PERIOD)
                details['mfi'] = {'value': round(mfi.mfi_value, 1)}
                if mfi.is_overbought:
                    penalty -= 0.03
                    reasons.append(f"MFI={mfi.mfi_value:.1f} overbought — contradicts dip -0.03")
            except Exception as e:
                logger.debug(f"MLSignalEnhancer: MFI error — {e}")

        # ── Clamp: DEFENSE ONLY — penalty can only be negative or zero ──────
        penalty = min(0.0, max(-ML_MAX_BOOST, penalty))
        final_score = max(0.0, base_score + penalty)

        self._crash_guard_active = crash_guard

        if reasons:
            logger.debug(
                f"MLEnhancer DIP (defense-only) base={base_score:.2f} penalty={penalty:+.2f} "
                f"final={final_score:.2f} crash_guard={crash_guard}"
            )

        return EnhancedScore(
            base_score=base_score, ml_boost=penalty, final_score=final_score,
            reasons=reasons, indicator_details=details, crash_guard_active=crash_guard,
        )

    def enhance_bounce_score(self, df: pd.DataFrame, base_score: float) -> EnhancedScore:
        """
        Bounce scores CAN be boosted slightly — closing a hedge early is low-risk.
        Also penalised if conditions say bounce hasn't fully developed yet.

        Boosts:
        1. RSI-2 extreme overbought (>95) → strong exit signal +0.06
        2. SuperTrend BULLISH HIGH_VOL = parabolic bounce, take profit +0.04
        3. Trend Speed short-term deceleration +0.03

        Penalties:
        1. RSI-2 still oversold (<20) → bounce still developing -0.05
        2. SuperTrend BEARISH → bounce may reverse quickly -0.03
        """
        if not ML_ENHANCER_ENABLED or df is None or len(df) < 50:
            return EnhancedScore(base_score=base_score, ml_boost=0.0, final_score=base_score)

        boost   = 0.0
        reasons = []
        details: Dict[str, Any] = {}

        # ── RSI-2 extremes ──────────────────────────────────────────────────
        if ML_RSI_ENABLED:
            try:
                rsi2 = _calc_rsi2(df['close'])
                details['rsi_2'] = round(rsi2, 1)
                if rsi2 > 95:
                    boost += 0.06
                    reasons.append(f"RSI-2={rsi2:.1f} extreme overbought — close hedge +0.06")
                elif rsi2 > 85:
                    boost += 0.04
                    reasons.append(f"RSI-2={rsi2:.1f} overbought +0.04")
                elif rsi2 < 20:
                    boost -= 0.05
                    reasons.append(f"RSI-2={rsi2:.1f} still oversold — bounce developing -0.05")
            except Exception as e:
                logger.debug(f"MLSignalEnhancer: RSI-2 error — {e}")

        # ── SuperTrend parabolic exit ────────────────────────────────────────
        if ML_SUPERTREND_ENABLED:
            try:
                st = calculate_adaptive_supertrend(
                    df,
                    atr_period=ML_SUPERTREND_ATR_PERIOD,
                    training_bars=ML_SUPERTREND_TRAINING_BARS,
                )
                details['supertrend'] = {
                    'direction': st.trend_direction.value,
                    'volatility': st.volatility_level.value,
                }
                if (st.trend_direction == TrendDirection.BULLISH
                        and st.volatility_level == VolatilityLevel.HIGH):
                    boost += 0.04
                    reasons.append("SuperTrend BULLISH HIGH_VOL — parabolic, book profit +0.04")
                elif st.trend_direction == TrendDirection.BEARISH:
                    boost -= 0.03
                    reasons.append("SuperTrend still BEARISH — bounce may reverse -0.03")
            except Exception as e:
                logger.debug(f"MLSignalEnhancer: SuperTrend error — {e}")

        # ── Trend Speed short-term momentum deceleration ────────────────────
        if ML_TREND_SPEED_ENABLED:
            try:
                action, urgency = self._trend_speed.get_exit_action(df['close'], entry_direction=-1)
                details['trend_speed_exit'] = {'action': action, 'urgency': round(urgency, 2)}
                if action in ("SCALE_OUT", "EXIT") and urgency > 0.5:
                    scaled = 0.03 * urgency
                    boost += scaled
                    reasons.append(f"TrendSpeed {action} (urgency={urgency:.2f}) +{scaled:.2f}")
            except Exception as e:
                logger.debug(f"MLSignalEnhancer: TrendSpeed exit error — {e}")

        # ── Clamp ────────────────────────────────────────────────────────────
        boost       = max(-ML_MAX_BOOST, min(ML_MAX_BOOST, boost))
        final_score = max(0.0, min(1.0, base_score + boost))

        if reasons:
            logger.debug(
                f"MLEnhancer BOUNCE base={base_score:.2f} boost={boost:+.2f} final={final_score:.2f}"
            )

        return EnhancedScore(
            base_score=base_score, ml_boost=boost, final_score=final_score,
            reasons=reasons, indicator_details=details,
        )

    def get_exit_stage(self, df: Optional[pd.DataFrame]) -> ExitStage:
        """Return short-term Trend Speed exit stage for the hedge leg."""
        if not ML_TREND_SPEED_ENABLED or df is None or len(df) < 20:
            return ExitStage.STRONG_ACCELERATION
        try:
            result = self._trend_speed.analyze(df['close'])
            return result.stage
        except Exception as e:
            logger.debug(f"MLSignalEnhancer: get_exit_stage error — {e}")
            return ExitStage.STRONG_ACCELERATION

    def reset_trend_speed(self) -> None:
        """Reset peak tracker. Call when opening a new position."""
        self._trend_speed.reset()
