"""
OTM Naked Options — Feature Engineering
=========================================
Builds per-stock feature matrix for the entry classifier and signal engine.

Reuses ~70% of leaps_feature_engineering.py logic (RSI, BB, SMA, HV, IV rank,
VIX term structure, ATH drawdown). Adds OTM-naked-specific features:
  - 52-week high/low proximity
  - Stochastic(14)
  - Volume ratio
  - Per-stock IV rank (HV-based proxy)
  - Theta/Vega ratio proxy
  - Earnings days away
"""
import math
import logging
import numpy as np
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: RSI
# ---------------------------------------------------------------------------
def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ---------------------------------------------------------------------------
# Helper: Stochastic %K
# ---------------------------------------------------------------------------
def _stochastic(close: pd.Series, high: pd.Series, low: pd.Series,
                period: int = 14) -> pd.Series:
    lo14  = low.rolling(period).min()
    hi14  = high.rolling(period).max()
    denom = (hi14 - lo14).replace(0, np.nan)
    return ((close - lo14) / denom) * 100


# ---------------------------------------------------------------------------
# Helper: HV-based IV Rank (52-week)
# ---------------------------------------------------------------------------
def _iv_rank_proxy(close: pd.Series) -> pd.Series:
    """HV(30) rank over trailing 252 sessions — same formula as TurboCore Pro."""
    log_ret    = np.log(close / close.shift(1))
    hv30       = log_ret.rolling(30).std() * math.sqrt(252) * 100
    hv_min_52w = hv30.rolling(252).min()
    hv_max_52w = hv30.rolling(252).max()
    denom      = (hv_max_52w - hv_min_52w).replace(0, np.nan)
    return ((hv30 - hv_min_52w) / denom).clip(0, 1).fillna(0.5)


# ---------------------------------------------------------------------------
# Main feature builder — called per-symbol
# ---------------------------------------------------------------------------
def build_stock_features(
    close:  pd.Series,
    high:   pd.Series,
    low:    pd.Series,
    volume: pd.Series,
    vix:    pd.Series,
    vix3m:  Optional[pd.Series] = None,
    rf:     Optional[pd.Series] = None,
    earnings_days_away: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """
    Build a complete feature matrix for a single stock.

    Args:
        close:   Daily close prices (DatetimeIndex)
        high:    Daily high prices
        low:     Daily low prices
        volume:  Daily volume
        vix:     VIX close, aligned to close.index
        vix3m:   VIX3M close (optional; fallback = vix * 1.05)
        rf:      Risk-free rate series (optional; fallback = 0.045)
        earnings_days_away: Pre-computed days to next earnings per date

    Returns:
        pd.DataFrame with one row per trading day.
    """
    idx = close.index
    f   = pd.DataFrame(index=idx)

    f["close"]  = close
    f["high"]   = high
    f["low"]    = low
    f["volume"] = volume

    # ── VIX context ───────────────────────────────────────────────────────────
    vix_aligned = vix.reindex(idx).ffill()
    f["vix"]    = vix_aligned

    vix3m_aligned  = (vix3m.reindex(idx).ffill() if vix3m is not None
                      else vix_aligned * 1.05)
    f["vix_term_slope"] = ((vix3m_aligned - vix_aligned) / vix_aligned).fillna(0.0)

    f["vix_pct_rank"] = vix_aligned.rolling(252).rank(pct=True).fillna(0.5)
    f["vix_5d_change"] = vix_aligned.diff(5).fillna(0.0)
    f["vix_rel_50"]   = (vix_aligned / vix_aligned.rolling(50).mean() - 1).fillna(0.0)

    rf_aligned = (rf.reindex(idx).ffill() if rf is not None
                  else pd.Series(0.045, index=idx))
    f["rf"] = rf_aligned

    # ── Trend / SMA ───────────────────────────────────────────────────────────
    f["sma_20"]   = close.rolling(20).mean()
    f["sma_50"]   = close.rolling(50).mean()
    # Use min_periods=50 so recently-listed stocks (like SNDK) retain rows
    f["sma_200"]  = close.rolling(200, min_periods=50).mean()

    f["above_sma50"]  = (close > f["sma_50"]).astype(float)
    f["above_sma200"] = (close > f["sma_200"]).astype(float)

    f["dist_sma20"]  = ((close - f["sma_20"])  / f["sma_20"]).fillna(0.0)
    f["dist_sma50"]  = ((close - f["sma_50"])  / f["sma_50"]).fillna(0.0)
    f["dist_sma200"] = ((close - f["sma_200"]) / f["sma_200"]).fillna(0.0)  # 0 when not enough history

    # ── RSI (2, 5, 14, 30) ────────────────────────────────────────────────────
    f["rsi_2"]  = _rsi(close, 2)
    f["rsi_5"]  = _rsi(close, 5)
    f["rsi_14"] = _rsi(close, 14)
    f["rsi_30"] = _rsi(close, 30)

    # ── Stochastic(14) ────────────────────────────────────────────────────────
    f["stoch_14"] = _stochastic(close, high, low, 14)

    # ── CCI (20) ──────────────────────────────────────────────────────────────
    tp        = (high + low + close) / 3
    sma_tp    = tp.rolling(20).mean()
    mad_20    = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    f["cci_20"] = ((tp - sma_tp) / (0.015 * mad_20.replace(0, np.nan))).fillna(0.0)

    # ── MACD (12, 26, 9) ──────────────────────────────────────────────────────
    ema12            = close.ewm(span=12, adjust=False).mean()
    ema26            = close.ewm(span=26, adjust=False).mean()
    macd_line        = ema12 - ema26
    macd_signal_line = macd_line.ewm(span=9, adjust=False).mean()
    f["macd_hist"]       = (macd_line - macd_signal_line).fillna(0.0)
    # Normalize histogram by close price for cross-stock comparability
    f["macd_hist_norm"]  = (f["macd_hist"] / close.replace(0, np.nan)).fillna(0.0)

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    sma_20  = close.rolling(20).mean()
    std_20  = close.rolling(20).std()
    upper_bb = sma_20 + 2 * std_20
    lower_bb = sma_20 - 2 * std_20
    bb_width = (upper_bb - lower_bb).replace(0, np.nan)
    f["pct_b"]       = ((close - lower_bb) / bb_width).fillna(0.5)
    f["bb_width_pct"] = (bb_width / sma_20).fillna(0.02)

    # ── 52-Week High / Low Proximity (OTM Naked key signals) ─────────────────
    f["hi_52w"] = close.rolling(252).max()
    f["lo_52w"] = close.rolling(252).min()
    f["pct_from_52w_high"] = ((close - f["hi_52w"]) / f["hi_52w"]).fillna(0.0)   # ≤ 0
    f["pct_from_52w_low"]  = ((close - f["lo_52w"]) / f["lo_52w"]).fillna(0.0)   # ≥ 0

    # ── Returns / Momentum ────────────────────────────────────────────────────
    for n in [1, 3, 5, 10, 21, 63]:
        f[f"ret_{n}d"] = close.pct_change(n)

    # ── ATH Drawdown ──────────────────────────────────────────────────────────
    ath = close.cummax()
    f["ath_drawdown"] = ((close - ath) / ath).fillna(0.0)

    # ── Historical Volatility (10, 20, 60) ────────────────────────────────────
    log_ret = np.log(close / close.shift(1))
    f["hv_10"]  = log_ret.rolling(10).std()  * math.sqrt(252)
    f["hv_20"]  = log_ret.rolling(20).std()  * math.sqrt(252)
    f["hv_60"]  = log_ret.rolling(60).std()  * math.sqrt(252)

    # ── IV Rank proxy (HV-based) ───────────────────────────────────────────────
    f["iv_rank"] = _iv_rank_proxy(close)

    # ── IV / HV ratio (premium selling edge indicator) ────────────────────────
    # Using HV20 * sqrt(VIX/20) as IV proxy when live IV unavailable
    iv_proxy = f["hv_20"] * (vix_aligned / 20.0).clip(0.5, 3.0)
    f["iv_hv_ratio"] = (iv_proxy / f["hv_20"].replace(0, np.nan)).fillna(1.0)

    # ── Volume Ratio (current / 20d avg) ─────────────────────────────────────
    f["volume_ratio"] = (volume / volume.rolling(20).mean()).fillna(1.0)

    # ── Gap Detection ─────────────────────────────────────────────────────────
    f["gap_pct"]      = (close - close.shift(1)) / close.shift(1)
    f["is_gap_up"]    = (f["gap_pct"] >= 0.015).astype(float)
    f["is_gap_down"]  = (f["gap_pct"] <= -0.015).astype(float)

    # ── Earnings proximity ────────────────────────────────────────────────────
    if earnings_days_away is not None:
        f["earnings_days_away"] = earnings_days_away.reindex(idx).fillna(999)
        f["earnings_near"]      = (f["earnings_days_away"] < 21).astype(float)
    else:
        f["earnings_days_away"] = 999.0
        f["earnings_near"]      = 0.0

    return f.dropna(subset=["sma_20"])   # Require at least 20 bars (sma_200 uses min_periods=50)


# ---------------------------------------------------------------------------
# Multi-stock batch builder
# ---------------------------------------------------------------------------
def build_all_features(
    price_data: dict,   # {symbol: pd.DataFrame with OHLCV}
    vix:        pd.Series,
    vix3m:      Optional[pd.Series] = None,
    rf:         Optional[pd.Series] = None,
    earnings_map: Optional[dict] = None,  # {symbol: pd.Series of days_away}
) -> dict:
    """
    Build feature matrices for all symbols in the universe.

    Args:
        price_data:   {symbol: DataFrame with 'Close', 'High', 'Low', 'Volume'}
        vix:          VIX close series
        vix3m:        VIX3M close series
        rf:           Risk-free rate series
        earnings_map: {symbol: pd.Series mapping date → days_to_earnings}

    Returns:
        {symbol: feature_df}
    """
    results = {}
    for symbol, df in price_data.items():
        try:
            close  = df["Close"]
            high   = df.get("High",   close)
            low    = df.get("Low",    close)
            volume = df.get("Volume", pd.Series(0, index=close.index))
            earn   = earnings_map.get(symbol) if earnings_map else None

            feat_df = build_stock_features(
                close=close, high=high, low=low, volume=volume,
                vix=vix, vix3m=vix3m, rf=rf,
                earnings_days_away=earn,
            )
            if len(feat_df) >= 252:
                results[symbol] = feat_df
                logger.debug(f"[{symbol}] features: {feat_df.shape} rows")
            else:
                logger.warning(f"[{symbol}] insufficient history ({len(feat_df)} rows), skipping")
        except Exception as e:
            logger.error(f"[{symbol}] feature build error: {e}")
    logger.info(f"Built features for {len(results)}/{len(price_data)} symbols")
    return results
