"""
ML Indicator Functions for TQQQ Diagonal Strategy
===================================================
Ported from IB-program-trading/src/ai_signal_generator.py.

Includes:
  - K-Means 1D clustering (no sklearn required)
  - ML Adaptive SuperTrend  (volatility-regime adaptive)
  - ML Optimal RSI          (auto-selects best period + divergence detection)
  - ML Money Flow Index     (K-Means dynamic thresholds + volume confirmation)

All functions accept a pd.DataFrame with lowercase columns:
    open, high, low, close, volume
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# ─── Enums ────────────────────────────────────────────────────────────────────

class TrendDirection(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class VolatilityLevel(Enum):
    LOW    = "LOW"
    MEDIUM = "MEDIUM"
    HIGH   = "HIGH"


# ─── Result dataclasses ───────────────────────────────────────────────────────

@dataclass
class SuperTrendResult:
    """Result from ML Adaptive SuperTrend calculation."""
    trend_direction:  TrendDirection
    volatility_level: VolatilityLevel
    supertrend_line:  float
    atr_value:        float
    confidence:       float   # 0–100; % distance to SuperTrend line


@dataclass
class RSIResult:
    """Result from ML Optimal RSI calculation."""
    rsi_value:            float
    optimal_period:       int
    overbought_threshold: float   # Dynamic (not fixed 70)
    oversold_threshold:   float   # Dynamic (not fixed 30)
    is_overbought:        bool
    is_oversold:          bool
    has_divergence:       bool
    divergence_type:      Optional[str] = None   # "bullish" | "bearish"


@dataclass
class MFIResult:
    """Result from ML Money Flow Index calculation."""
    mfi_value:            float
    overbought_threshold: float
    oversold_threshold:   float
    is_overbought:        bool
    is_oversold:          bool
    volume_confirmation:  float   # 0–100


# ─── Core utilities ───────────────────────────────────────────────────────────

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR using True Range max of 3 methods."""
    high  = df['high']
    low   = df['low']
    close = df['close']

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low  - close.shift(1)).abs()

    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


def kmeans_cluster_1d(
    values: np.ndarray,
    n_clusters: int = 3,
    max_iter: int = 100,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Simple 1D K-Means — no sklearn dependency.

    Initialises centroids from quantiles so the result is always
    ordered LOW < MEDIUM < HIGH.

    Returns:
        labels    — integer array (0=LOW, 1=MEDIUM, 2=HIGH)
        centroids — sorted centroid values
    """
    centroids = np.percentile(values, np.linspace(0, 100, n_clusters + 2)[1:-1])

    for _ in range(max_iter):
        distances     = np.abs(values.reshape(-1, 1) - centroids.reshape(1, -1))
        labels        = np.argmin(distances, axis=1)
        new_centroids = np.array([
            values[labels == k].mean() if np.any(labels == k) else centroids[k]
            for k in range(n_clusters)
        ])
        if np.allclose(centroids, new_centroids):
            break
        centroids = new_centroids

    sorted_idx     = np.argsort(centroids)
    sorted_cents   = centroids[sorted_idx]
    label_map      = {old: new for new, old in enumerate(sorted_idx)}
    sorted_labels  = np.array([label_map[l] for l in labels])

    return sorted_labels, sorted_cents


# ─── ML Adaptive SuperTrend ───────────────────────────────────────────────────

def calculate_adaptive_supertrend(
    df: pd.DataFrame,
    atr_period: int = 10,
    training_bars: int = 300,
) -> SuperTrendResult:
    """
    ML Adaptive SuperTrend.

    Uses K-Means on recent ATR values to classify volatility into
    LOW / MEDIUM / HIGH and selects the SuperTrend multiplier accordingly:
        LOW  → factor 2.0
        MED  → factor 3.0
        HIGH → factor 4.0

    Confidence = % distance of close from the SuperTrend line (scaled 0–100).
    """
    if len(df) < 10:
        return SuperTrendResult(
            trend_direction  = TrendDirection.NEUTRAL,
            volatility_level = VolatilityLevel.MEDIUM,
            supertrend_line  = float(df['close'].iloc[-1]),
            atr_value        = 0.0,
            confidence       = 50.0,
        )

    training_bars = min(training_bars, len(df))
    atr           = calculate_atr(df, atr_period)
    current_atr   = float(atr.iloc[-1])

    atr_vals = atr.iloc[-training_bars:].dropna().values
    if len(atr_vals) < 10:
        vol_level = VolatilityLevel.MEDIUM
        factor    = 3.0
    else:
        labels, _ = kmeans_cluster_1d(atr_vals, n_clusters=3)
        current_label = labels[-1]
        vol_level = [VolatilityLevel.LOW, VolatilityLevel.MEDIUM, VolatilityLevel.HIGH][current_label]
        factor    = {
            VolatilityLevel.LOW:    2.0,
            VolatilityLevel.MEDIUM: 3.0,
            VolatilityLevel.HIGH:   4.0,
        }[vol_level]

    hl2         = (df['high'] + df['low']) / 2
    upper_band  = hl2 + (factor * atr)
    lower_band  = hl2 - (factor * atr)
    close       = float(df['close'].iloc[-1])

    if close > upper_band.iloc[-2]:
        trend           = TrendDirection.BULLISH
        supertrend_line = float(lower_band.iloc[-1])
    elif close < lower_band.iloc[-2]:
        trend           = TrendDirection.BEARISH
        supertrend_line = float(upper_band.iloc[-1])
    else:
        if close > float(hl2.iloc[-1]):
            trend           = TrendDirection.BULLISH
            supertrend_line = float(lower_band.iloc[-1])
        else:
            trend           = TrendDirection.BEARISH
            supertrend_line = float(upper_band.iloc[-1])

    dist_pct   = abs(close - supertrend_line) / close * 100 if close > 0 else 0.0
    confidence = min(100.0, dist_pct * 10)

    return SuperTrendResult(
        trend_direction  = trend,
        volatility_level = vol_level,
        supertrend_line  = supertrend_line,
        atr_value        = current_atr,
        confidence       = confidence,
    )


# ─── ML Optimal RSI ───────────────────────────────────────────────────────────

def calculate_optimal_rsi(
    df: pd.DataFrame,
    periods: List[int] = None,
    lookback: int = 50,
) -> RSIResult:
    """
    ML Optimal RSI.

    Tests RSI periods [7, 14, 21, 28] and picks the one with the most
    extreme current reading. Dynamic overbought / oversold thresholds
    are set at mean ± 1.5 * std of the recent RSI distribution.

    Additionally detects bullish / bearish RSI divergence over the last
    20 bars.
    """
    if periods is None:
        periods = [7, 14, 21, 28]

    close      = df['close']
    rsi_values = {}

    for period in periods:
        delta    = close.diff()
        gain     = delta.clip(lower=0)
        loss     = (-delta.clip(upper=0))
        avg_gain = gain.rolling(window=period, min_periods=1).mean()
        avg_loss = loss.rolling(window=period, min_periods=1).mean()
        rs       = avg_gain / avg_loss.replace(0, np.nan)
        rsi      = (100 - (100 / (1 + rs))).fillna(50)
        rsi_values[period] = rsi

    # Pick period with most extreme (farthest from 50) current reading
    current_readings = {p: abs(float(rsi_values[p].iloc[-1]) - 50) for p in periods}
    optimal_period   = max(current_readings, key=current_readings.get)
    rsi              = rsi_values[optimal_period]
    current_rsi      = float(rsi.iloc[-1])

    # Dynamic thresholds from recent distribution
    recent_rsi  = rsi.iloc[-lookback:]
    rsi_std     = float(recent_rsi.std()) if len(recent_rsi) > 1 else 15.0
    rsi_mean    = float(recent_rsi.mean())
    overbought  = min(80.0, rsi_mean + 1.5 * rsi_std)
    oversold    = max(20.0, rsi_mean - 1.5 * rsi_std)

    is_overbought = current_rsi > overbought
    is_oversold   = current_rsi < oversold

    # Divergence detection over last 20 bars
    has_divergence = False
    divergence_type: Optional[str] = None

    if len(close) >= 20:
        price_highs, rsi_highs = [], []
        price_lows,  rsi_lows  = [], []
        for i in range(-20, -1):
            if close.iloc[i] > close.iloc[i - 1] and close.iloc[i] > close.iloc[i + 1]:
                price_highs.append((i, float(close.iloc[i])))
                rsi_highs.append((i,  float(rsi.iloc[i])))
            if close.iloc[i] < close.iloc[i - 1] and close.iloc[i] < close.iloc[i + 1]:
                price_lows.append((i, float(close.iloc[i])))
                rsi_lows.append((i,  float(rsi.iloc[i])))

        # Bearish divergence: price makes higher high but RSI makes lower high
        if len(price_highs) >= 2:
            if price_highs[-1][1] > price_highs[-2][1] and rsi_highs[-1][1] < rsi_highs[-2][1]:
                has_divergence  = True
                divergence_type = "bearish"

        # Bullish divergence: price makes lower low but RSI makes higher low
        if len(price_lows) >= 2:
            if price_lows[-1][1] < price_lows[-2][1] and rsi_lows[-1][1] > rsi_lows[-2][1]:
                has_divergence  = True
                divergence_type = "bullish"

    return RSIResult(
        rsi_value            = current_rsi,
        optimal_period       = optimal_period,
        overbought_threshold = overbought,
        oversold_threshold   = oversold,
        is_overbought        = is_overbought,
        is_oversold          = is_oversold,
        has_divergence       = has_divergence,
        divergence_type      = divergence_type,
    )


# ─── ML Money Flow Index ──────────────────────────────────────────────────────

def calculate_ml_mfi(
    df: pd.DataFrame,
    period: int = 14,
    training_bars: int = 300,
) -> MFIResult:
    """
    ML Money Flow Index with K-Means dynamic thresholds.

    Uses cluster boundary between LOW and MEDIUM clusters as the oversold
    threshold and between MEDIUM and HIGH clusters as the overbought threshold.
    Volume confirmation measures current vs 20-bar average volume (0–100).
    """
    typ_price    = (df['high'] + df['low'] + df['close']) / 3
    raw_flow     = typ_price * df['volume']

    pos_flow     = raw_flow.where(typ_price > typ_price.shift(1), 0)
    neg_flow     = raw_flow.where(typ_price < typ_price.shift(1), 0)

    pos_sum      = pos_flow.rolling(window=period, min_periods=1).sum()
    neg_sum      = neg_flow.rolling(window=period, min_periods=1).sum()

    mf_ratio     = pos_sum / neg_sum.replace(0, 1)
    mfi          = (100 - (100 / (1 + mf_ratio))).fillna(50)
    current_mfi  = float(mfi.iloc[-1])

    training_bars = min(training_bars, len(df))
    mfi_vals      = mfi.iloc[-training_bars:].dropna().values

    if len(mfi_vals) < 20:
        overbought = 70.0
        oversold   = 30.0
    else:
        labels, centroids = kmeans_cluster_1d(mfi_vals, n_clusters=3)
        oversold   = float((centroids[0] + centroids[1]) / 2)
        overbought = float((centroids[1] + centroids[2]) / 2)

    is_overbought  = current_mfi > overbought
    is_oversold    = current_mfi < oversold

    recent_vol        = float(df['volume'].iloc[-20:].mean()) if len(df) >= 20 else float(df['volume'].mean())
    current_vol       = float(df['volume'].iloc[-1])
    vol_ratio         = current_vol / recent_vol if recent_vol > 0 else 1.0
    volume_confirmation = min(100.0, vol_ratio * 50)

    return MFIResult(
        mfi_value            = current_mfi,
        overbought_threshold = overbought,
        oversold_threshold   = oversold,
        is_overbought        = is_overbought,
        is_oversold          = is_oversold,
        volume_confirmation  = volume_confirmation,
    )
