"""
RegimeBase Dynamic Ladder Strategy - Feature Engineering
================================================
Extends the base HILO-IV feature engineering with RegimeBase-specific features:
- daily_move_pct
- gap_pct
- daily_range_pct
- atr_14
- spy_5d_return
- iv_hv_spread
"""
import math
import pandas as pd
import numpy as np
from typing import Optional

from src.otm_naked.feature_engineering import build_stock_features

def _compute_days_since_large_move(daily_move_pct: pd.Series, threshold: float = 3.0) -> pd.Series:
    """Count trading days since last move >= threshold%."""
    is_large = daily_move_pct.abs() >= threshold
    groups = is_large.cumsum()
    days_since = groups.groupby(groups).cumcount()
    # If no large move has occurred yet, return a large number
    days_since[~is_large.cumsum().astype(bool)] = 999
    return days_since

def _compute_adx(high, low, close, period=14):
    """Compute ADX (Average Directional Index)."""
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    # Zero out when opposite DM is larger
    plus_dm[minus_dm > plus_dm] = 0
    minus_dm[plus_dm > minus_dm] = 0
    
    atr = pd.concat([high - low, (high - close.shift(1)).abs(),
                     (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_smooth = atr.rolling(period).mean()
    
    plus_di = 100 * (plus_dm.rolling(period).mean() / (atr_smooth + 1e-9))
    minus_di = 100 * (minus_dm.rolling(period).mean() / (atr_smooth + 1e-9))
    dx = (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9) * 100
    adx = dx.rolling(period).mean()
    return adx.fillna(15)  # Default: low-trend

def _compute_regression_slope(close, window=40):
    """Rolling linear regression slope of log prices (% per day)."""
    from scipy.stats import linregress
    def _slope(arr):
        if len(arr) < window:
            return 0.0
        x = np.arange(len(arr))
        return linregress(x, np.log(arr))[0] * 100
    return close.rolling(window).apply(_slope, raw=True).fillna(0.0)

def _compute_rolling_hurst(close, window=90):
    """Rolling Hurst exponent via simplified R/S analysis."""
    def _hurst_rs(prices):
        if len(prices) < window:
            return 0.50
        log_returns = np.diff(np.log(prices))
        n = len(log_returns)
        if n < 20:
            return 0.50
        mean_ret = np.mean(log_returns)
        deviations = np.cumsum(log_returns - mean_ret)
        R = np.max(deviations) - np.min(deviations)
        S = np.std(log_returns, ddof=1)
        if S < 1e-10:
            return 0.50
        RS = R / S
        H = np.log(RS) / np.log(n)
        return np.clip(H, 0.0, 1.0)
    return close.rolling(window).apply(_hurst_rs, raw=True).fillna(0.50)

def _classify_regime(adx, slope, ema_cross_up, hurst):
    """Classify market regime from indicators."""
    if adx > 40 or hurst > 0.65:
        if slope > 0.10:
            return "EXTREME_UPTREND"
        elif slope < -0.10:
            return "EXTREME_DOWNTREND"
        return "NO_TRADE"
    if adx > 25 and slope > 0.20:
        return "UPTREND"
    if adx > 25 and slope < -0.20:
        return "DOWNTREND"
    return "SIDEWAYS"

def build_regime_base_features(
    close: pd.Series,
    open_price: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    vix: pd.Series,
    spy_close: Optional[pd.Series] = None,
    vix3m: Optional[pd.Series] = None,
    rf: Optional[pd.Series] = None,
    earnings_days_away: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """
    Builds the base HILO features and appends the 6 RegimeBase-specific features.
    """
    # 1. Get base features
    df = build_stock_features(
        close=close,
        high=high,
        low=low,
        volume=volume,
        vix=vix,
        vix3m=vix3m,
        rf=rf,
        earnings_days_away=earnings_days_away
    )
    
    if df.empty:
        return df
        
    # Reindex input series to match the returned base df
    idx = df.index
    c = close.reindex(idx)
    o = open_price.reindex(idx)
    h = high.reindex(idx)
    l = low.reindex(idx)
    
    # 2. Add RegimeBase-specific features
    # a. daily_move_pct (from close to close)
    df["daily_move_pct"] = c.pct_change() * 100
    
    # b. gap_pct (from prev close to open)
    df["gap_pct"] = ((o - c.shift(1)) / c.shift(1)).fillna(0.0)
    
    # c. daily_range_pct
    df["daily_range_pct"] = ((h - l) / c).fillna(0.0)
    
    # d. atr_14
    high_low = h - l
    high_close = (h - c.shift(1)).abs()
    low_close = (l - c.shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr_14"] = tr.rolling(14).mean()
    
    # e. spy_5d_return
    if spy_close is not None:
        spy_aligned = spy_close.reindex(idx).ffill()
        df["spy_5d_return"] = spy_aligned.pct_change(5) * 100
    else:
        df["spy_5d_return"] = 0.0
        
    # f. iv_hv_spread (VRP proxy)
    # df already has 'hv_20' and 'hv_10' from base features
    vix_col = df["vix"]
    hv_col = df["hv_20"]
    move_col = df["daily_move_pct"].abs()
    
    # 1. Base IV from VIX regime
    conditions = [vix_col < 15, vix_col < 25, vix_col < 35, vix_col >= 35]
    choices = [
        hv_col * 1.10 + 0.05,
        hv_col * 1.25 + 0.10,
        hv_col * 1.45 + 0.18,
        hv_col * 1.65 + 0.25,
    ]
    base_iv = pd.Series(np.select(conditions, choices, default=hv_col * 1.25 + 0.10), index=df.index)
    
    # 2. Jump premium: large same-day move adds spike (peak on move day)
    jump_premium = (move_col / 100 * 0.40).clip(lower=0)
    
    # Pass 1: Base iv_est
    df["iv_est"] = (base_iv + jump_premium).clip(0.20, 2.00)
    
    # Calculate IVR (0-100) using 252-day rolling min/max
    iv_rolling_max = df["iv_est"].rolling(252, min_periods=50).max()
    iv_rolling_min = df["iv_est"].rolling(252, min_periods=50).min()
    denom = (iv_rolling_max - iv_rolling_min).replace(0, np.nan)
    df["ivr"] = ((df["iv_est"] - iv_rolling_min) / denom * 100).clip(0, 100).fillna(50)
    
    # Pass 2: Add IVR uplift to iv_est
    ivr_uplift = ((df["ivr"] - 65) / 100 * 0.15).clip(lower=0)
    df["iv_est"] = (df["iv_est"] + ivr_uplift).clip(0.20, 2.00)
    
    df["iv_hv_spread"] = df["iv_est"] - df["hv_10"]
    
    # g. New features for ML upgrade (Phase 4)
    df["days_since_large_move"] = _compute_days_since_large_move(df["daily_move_pct"], threshold=3.0)
    df["vrp_conditional"] = df["iv_est"] - df["hv_20"]
    df["spy_same_day_return"] = spy_aligned.pct_change() * 100 if spy_close is not None else 0.0
    df["regime_base_spy_corr_20d"] = c.pct_change().rolling(20).corr(spy_aligned.pct_change()).fillna(0.5) if spy_close is not None else 0.5
    df["strike_distance_pct"] = 0.0  # Placeholder; set at entry time
    
    # h. Regime detection features
    df["adx_14"] = _compute_adx(h, l, c, period=14)
    df["reg_slope_40d"] = _compute_regression_slope(c, window=40)
    df["ema_20"] = c.ewm(span=20, adjust=False).mean()
    df["ema_50"] = c.ewm(span=50, adjust=False).mean()
    df["ema_cross_up"] = (df["ema_20"] > df["ema_50"] * 1.005).astype(float)
    df["hurst_90d"] = _compute_rolling_hurst(c, window=90)
    
    df["regime"] = df.apply(
        lambda row: _classify_regime(
            row["adx_14"], 
            row["reg_slope_40d"],
            row["ema_cross_up"], 
            row.get("hurst_90d", 0.5)
        ),
        axis=1
    )
    
    return df.dropna(subset=["daily_move_pct", "atr_14"])
