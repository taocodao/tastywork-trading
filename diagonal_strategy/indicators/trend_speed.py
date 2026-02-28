"""
Trend Speed Analyzer
====================
Ported from IB-program-trading/src/trend_speed.py.

Measures momentum acceleration (2nd derivative of price via EMAs) to detect:
  - Entry confirmation  : Is momentum accelerating in trade direction?
  - Exit stage          : When should the hedge leg be closed?

4-Stage Exit Framework:
  1. STRONG_ACCELERATION (|histogram| > 50)  →  HOLD
  2. EARLY_WARNING       (decline > threshold from peak)  →  SCALE_OUT 50%
  3. CONFIRMATION        (histogram crosses 0)  →  EXIT remaining
  4. REVERSAL            (deeply on wrong side)  →  WATCH for next entry
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ExitStage(Enum):
    STRONG_ACCELERATION = "HOLD"
    EARLY_WARNING       = "SCALE_OUT"
    CONFIRMATION        = "EXIT"
    REVERSAL            = "WATCH"


@dataclass
class TrendSpeedResult:
    """Result from trend speed analysis."""
    histogram:       float
    histogram_change: float
    stage:           ExitStage
    action:          str
    bars_since_peak: int
    is_accelerating: bool


class TrendSpeedAnalyzer:
    """
    Measures acceleration of momentum via EMA convergence.

    Histogram = EMA_fast - EMA_slow (1st derivative = momentum).
    Histogram change = acceleration (2nd derivative).

    Positive + rising  → bullish acceleration
    Positive + falling → bullish deceleration (early exit warning)
    Negative + falling → bearish acceleration
    Negative + rising  → bearish deceleration (early exit warning)
    """

    def __init__(
        self,
        ema_fast: int = 12,
        ema_slow: int = 26,
        lookback: int = 20,
        scale_out_threshold: float = -15,
        exit_threshold: float = 0,
        reversal_threshold: float = -30,
    ):
        self.ema_fast            = ema_fast
        self.ema_slow            = ema_slow
        self.lookback            = lookback
        self.scale_out_threshold = scale_out_threshold
        self.exit_threshold      = exit_threshold
        self.reversal_threshold  = reversal_threshold
        self._peak_histogram: Optional[float] = None

    def calculate_histogram(self, close: pd.Series) -> pd.Series:
        """
        Histogram = (EMA_fast - EMA_slow), normalised to –100 … +100 via
        a rolling percentile rank over the lookback window.
        """
        ema_fast    = close.ewm(span=self.ema_fast, adjust=False).mean()
        ema_slow    = close.ewm(span=self.ema_slow, adjust=False).mean()
        raw_hist    = ema_fast - ema_slow

        # Normalise using rolling rank (percentile) so scale is comparable
        # across different price levels
        def pct_rank(s: pd.Series) -> pd.Series:
            result = pd.Series(index=s.index, dtype=float)
            for i in range(len(s)):
                if i < self.lookback:
                    result.iloc[i] = 50.0
                else:
                    window = s.iloc[i - self.lookback: i + 1]
                    pct    = (window < s.iloc[i]).mean() * 100
                    result.iloc[i] = pct
            return result

        normed = pct_rank(raw_hist)
        # Map 0-100 percentile to -100 … +100
        histogram = (normed - 50) * 2
        return histogram

    def detect_deceleration(self, histogram: pd.Series) -> pd.Series:
        """Detect when momentum is decelerating (histogram shrinking from peak)."""
        return histogram.diff() < 0

    def get_exit_stage(self, histogram: pd.Series) -> ExitStage:
        """
        Determine current exit stage from histogram series.

        Updates the internal peak tracker to measure decline from peak.
        """
        if len(histogram) < 2:
            return ExitStage.STRONG_ACCELERATION

        current_hist = float(histogram.iloc[-1])
        recent       = histogram.iloc[-self.lookback:] if len(histogram) >= self.lookback else histogram
        peak         = float(recent.abs().max()) * np.sign(float(recent.iloc[recent.abs().argmax()]))

        if self._peak_histogram is None or abs(current_hist) > abs(self._peak_histogram):
            self._peak_histogram = current_hist

        peak_val   = self._peak_histogram
        hist_change = float(histogram.iloc[-1]) - float(histogram.iloc[-2])

        # Stage classification
        if abs(current_hist) > 50:
            return ExitStage.STRONG_ACCELERATION

        if peak_val is not None and (current_hist - peak_val) < self.scale_out_threshold:
            if current_hist < self.exit_threshold:
                return ExitStage.CONFIRMATION
            if (current_hist - peak_val) < self.reversal_threshold:
                return ExitStage.REVERSAL
            return ExitStage.EARLY_WARNING

        return ExitStage.STRONG_ACCELERATION

    def analyze(self, close: pd.Series) -> TrendSpeedResult:
        """Full trend speed analysis — returns structured result."""
        if len(close) < self.ema_slow + 5:
            return TrendSpeedResult(
                histogram        = 0.0,
                histogram_change = 0.0,
                stage            = ExitStage.STRONG_ACCELERATION,
                action           = "HOLD — insufficient data",
                bars_since_peak  = 0,
                is_accelerating  = False,
            )

        histogram       = self.calculate_histogram(close)
        current_hist    = float(histogram.iloc[-1])
        hist_change     = float(histogram.iloc[-1]) - float(histogram.iloc[-2])
        is_accelerating = hist_change > 0 if current_hist >= 0 else hist_change < 0

        stage = self.get_exit_stage(histogram)

        action_map = {
            ExitStage.STRONG_ACCELERATION: "HOLD — momentum accelerating",
            ExitStage.EARLY_WARNING:       "SCALE_OUT — momentum decelerating",
            ExitStage.CONFIRMATION:        "EXIT — momentum crossed zero",
            ExitStage.REVERSAL:            "WATCH — momentum reversed",
        }

        # Count bars since peak
        recent = histogram.iloc[-self.lookback:] if len(histogram) >= self.lookback else histogram
        abs_hist = recent.abs()
        peak_idx = int(abs_hist.values.argmax())
        bars_since_peak = len(recent) - 1 - peak_idx

        return TrendSpeedResult(
            histogram        = current_hist,
            histogram_change = hist_change,
            stage            = stage,
            action           = action_map[stage],
            bars_since_peak  = bars_since_peak,
            is_accelerating  = is_accelerating,
        )

    def reset(self) -> None:
        """Reset peak tracking state. Call when opening a new position."""
        self._peak_histogram = None

    def should_enter(self, close: pd.Series, direction: int) -> Tuple[bool, float]:
        """
        Confirm trend speed supports a new entry.

        direction:  +1 for long CALL (bullish)
                    -1 for long PUT / dip entry (bearish)

        Returns:
            (should_enter, confidence)  confidence in 0.0–1.0
        """
        if len(close) < self.ema_slow + 5:
            return True, 0.5   # insufficient data → don't block

        histogram       = self.calculate_histogram(close)
        current_hist    = float(histogram.iloc[-1])
        hist_change     = float(histogram.iloc[-1]) - float(histogram.iloc[-2])

        # For PUT / dip entry (direction = -1) we want negative + declining histogram
        # For CALL entry (direction = +1) we want positive + rising histogram
        aligned     = (direction * current_hist) > 0
        accelerating = (direction * hist_change) > 0

        if aligned and accelerating:
            confidence = min(1.0, abs(current_hist) / 50)
        elif aligned:
            confidence = 0.5
        else:
            confidence = max(0.0, 0.5 - abs(current_hist) / 100)

        return aligned, confidence

    def get_exit_action(self, close: pd.Series, entry_direction: int) -> Tuple[str, float]:
        """
        Get exit action for an open position.

        entry_direction: +1 for long CALL, -1 for long PUT

        Returns:
            (action, urgency)   action in {"HOLD", "SCALE_OUT", "EXIT"}
                                urgency in 0.0–1.0
        """
        result = self.analyze(close)

        if result.stage == ExitStage.STRONG_ACCELERATION:
            return "HOLD", 0.0
        elif result.stage == ExitStage.EARLY_WARNING:
            urgency = min(1.0, result.bars_since_peak / 10)
            return "SCALE_OUT", urgency
        elif result.stage == ExitStage.CONFIRMATION:
            return "EXIT", 1.0
        else:
            return "EXIT", 1.0
