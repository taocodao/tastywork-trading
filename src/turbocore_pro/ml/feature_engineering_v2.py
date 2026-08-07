"""
TurboCore Pro v2 — Bar-Cadence-Aware Feature Engineering
==========================================================
Generalizes feature_engineering.py's `generate_technical_features` to work
correctly at hourly cadence (or any bars_per_day) by scaling every rolling
window from trading-day units to bar counts, and REPLACES the two
permanently-stubbed daily macro features that are meaningless at any
cadence with real hourly-native breadth/cross-asset features.

Dropped (were hard-stubbed at 0.0 in the original, contributed zero signal
at daily cadence and are even less meaningful sampled hourly):
  - ism_mfg_delta          (never wired to FRED API)
  - initial_claims_slope   (never wired to FRED API)

Added (hourly-native, no daily analog needed -- these are the actual
breadth/cross-asset signals appropriate for intraday cadence):
  - vix_intraday_momentum_6b : VIX change over last ~1 trading day (6 bars)
  - hyg_intraday_momentum_6b : HYG log-return momentum over last ~1 day
  - hyg_mom_20b              : HYG log-return momentum over ~3 trading days
  - qqq_intraday_vol_6b      : rolling std of last 6 bars' returns (~1 day
                               realized vol -- captures within-day vol
                               clustering that's invisible at daily bars)
  - volume_zscore_20d        : QQQ bar volume z-scored against the trailing
                               20-trading-day distribution for the SAME
                               time-of-day bucket (accounts for the strong
                               U-shaped intraday volume pattern -- open/
                               close bars are always higher volume than
                               midday, so a raw cross-bar z-score would be
                               dominated by time-of-day rather than genuine
                               volume anomalies)

All other features (RSI, MACD, Bollinger Band width, volume ratios,
distribution days, Fibonacci retracement, momentum divergence, new-highs
proxy, fracdiff proxies) are retained with their rolling windows rescaled
by `bars_per_day`.
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def generate_technical_features_v2(df: pd.DataFrame, bars_per_day: float = 1.0) -> pd.DataFrame:
    """
    Bar-cadence-aware feature generation. Pass bars_per_day=1.0 for daily
    data (reproduces the original feature_engineering.py windows exactly)
    or bars_per_day=6.5 for hourly RTH bars.
    """
    if 'tqqq_close' not in df.columns:
        return df

    bpd = bars_per_day
    w = lambda days: max(1, int(round(days * bpd)))  # noqa: E731

    fdf = df.copy()
    tqqq = fdf['tqqq_close']
    qqq = fdf.get('qqq_close', tqqq)

    # ─── Core Technical ──────────────────────────────────────────────────────
    delta = tqqq.diff()
    gain = delta.clip(lower=0).rolling(w(14)).mean()
    loss = (-delta.clip(upper=0)).rolling(w(14)).mean()
    rs = gain / loss.replace(0, np.nan)
    fdf['tqqq_rsi_14'] = 100 - (100 / (1 + rs))

    ema_span_12 = w(12)
    ema_span_26 = w(26)
    ema_span_9 = w(9)
    ema12 = tqqq.ewm(span=ema_span_12, adjust=False).mean()
    ema26 = tqqq.ewm(span=ema_span_26, adjust=False).mean()
    fdf['tqqq_macd'] = ema12 - ema26
    fdf['tqqq_macd_signal'] = fdf['tqqq_macd'].ewm(span=ema_span_9, adjust=False).mean()
    fdf['tqqq_macd_hist'] = fdf['tqqq_macd'] - fdf['tqqq_macd_signal']

    sma20 = tqqq.rolling(w(20)).mean()
    std20 = tqqq.rolling(w(20)).std()
    fdf['tqqq_bb_width'] = ((sma20 + 2 * std20) - (sma20 - 2 * std20)) / sma20

    if 'vix_close' in fdf.columns:
        vix_sma50 = fdf['vix_close'].rolling(w(50)).mean()
        fdf['vix_rel_50'] = fdf['vix_close'] / vix_sma50

    # ─── Category 1: Volume & Breadth ────────────────────────────────────────
    if 'qqq_volume' in fdf.columns:
        vol = fdf['qqq_volume']
        vol_5d = vol.rolling(w(5)).mean()
        vol_20d = vol.rolling(w(20)).mean()

        raw_ratio = np.log(vol_5d / vol_20d.replace(0, np.nan))
        fdf['vol_ratio'] = raw_ratio.rolling(w(252)).rank(pct=True).fillna(0.5)

        price_direction = np.sign(qqq - qqq.shift(1))
        cum_vol_delta = (vol * price_direction).rolling(w(20)).sum()
        fdf['cum_vol_delta'] = (cum_vol_delta / vol.rolling(w(20)).sum()).fillna(0.0)

        is_dist_day = ((vol > vol.shift(1)) & (qqq.pct_change() < -0.004)).astype(float)
        fdf['distribution_day_count_20d'] = is_dist_day.rolling(w(20)).sum().fillna(0.0)

        qqq_ret = qqq.pct_change()
        declining_vol_20d = (vol * (qqq_ret < 0).astype(float)).rolling(w(20)).sum()
        bounce_vol_5d = vol_5d
        raw_bounce_ratio = bounce_vol_5d / (declining_vol_20d / w(20)).replace(0, np.nan)
        fdf['bounce_vol_ratio'] = raw_bounce_ratio.clip(0, 5).fillna(1.0)
    else:
        fdf['vol_ratio'] = 0.5
        fdf['cum_vol_delta'] = 0.0
        fdf['distribution_day_count_20d'] = 0.0
        fdf['bounce_vol_ratio'] = 1.0

    rolling_high = qqq.rolling(w(20)).max()
    rolling_low = qqq.rolling(w(20)).min()
    price_range = (rolling_high - rolling_low).replace(0, np.nan)
    fdf['fib_retracement'] = ((qqq - rolling_low) / price_range).fillna(0.5)

    tqqq_5d_ret = tqqq.pct_change(w(5))
    qqq_5d_ret = qqq.pct_change(w(5))
    fdf['sector_divergence'] = (tqqq_5d_ret - (3 * qqq_5d_ret)).abs().rolling(w(10)).mean().fillna(0.0)

    ret_5d = qqq.pct_change(w(5))
    ret_20d = qqq.pct_change(w(20))
    fdf['momentum_divergence'] = (ret_5d / ret_20d.replace(0, np.nan)).clip(-3, 3).fillna(0.0)

    qqq_52w_max = qqq.rolling(w(252)).max()
    fdf['nh_proxy'] = (qqq / qqq_52w_max).rolling(w(20)).mean().fillna(0.5)

    # ─── Category 2: Macro / Cross-Asset Confirmation ───────────────────────
    # VIX term structure slope: use proxy if provided by data_pipeline
    # (intraday-momentum-based at hourly cadence), else 0.0.
    if 'vix_term_slope' in fdf.columns:
        fdf['vix_term_slope'] = fdf['vix_term_slope'].fillna(0.0)
    else:
        fdf['vix_term_slope'] = 0.0

    if 'hyg_5d_change' in fdf.columns:
        fdf['hyg_5d_change'] = fdf['hyg_5d_change'].fillna(0.0)
    elif 'hyg_close' in fdf.columns:
        fdf['hyg_5d_change'] = fdf['hyg_close'].pct_change(w(5)).fillna(0.0)
    else:
        fdf['hyg_5d_change'] = 0.0

    if 'hy_oas_zscore' in fdf.columns:
        fdf['hy_oas_zscore'] = fdf['hy_oas_zscore'].fillna(0.0)
    else:
        fdf['hy_oas_zscore'] = -fdf.get('hyg_5d_change', pd.Series(0.0, index=fdf.index))

    if 'hy_oas_5d_change' in fdf.columns:
        fdf['hy_oas_5d_change'] = fdf['hy_oas_5d_change'].fillna(0.0)
    else:
        fdf['hy_oas_5d_change'] = fdf['hy_oas_zscore'].diff(w(5)).fillna(0.0)

    if 'fed_funds_3m_change' in fdf.columns:
        fdf['fed_funds_3m_change'] = fdf['fed_funds_3m_change'].fillna(0.0)
    elif 'tlt_close' in fdf.columns:
        fdf['fed_funds_3m_change'] = fdf['tlt_close'].pct_change(w(63)).fillna(0.0)
    else:
        fdf['fed_funds_3m_change'] = 0.0

    # ── REMOVED: ism_mfg_delta, initial_claims_slope ──────────────────────
    # Permanently stubbed at 0.0 in the original (never wired to FRED API);
    # contribute zero signal at daily cadence and are structurally
    # meaningless at hourly cadence (macro releases are daily/monthly at
    # best) -- replaced below with real hourly-native breadth features.

    # ── NEW: hourly-native breadth / cross-asset momentum features ─────────
    if 'vix_close' in fdf.columns:
        fdf['vix_intraday_momentum_6b'] = fdf['vix_close'].diff(w(1)) if bpd <= 1 else fdf['vix_close'].diff(6)
    else:
        fdf['vix_intraday_momentum_6b'] = 0.0

    if 'hyg_close' in fdf.columns:
        hyg_log_ret = np.log(fdf['hyg_close'] / fdf['hyg_close'].shift(1))
        intraday_win = 6 if bpd > 1 else w(1)
        fdf['hyg_intraday_momentum_6b'] = hyg_log_ret.rolling(intraday_win).sum().fillna(0.0)
        fdf['hyg_mom_20b'] = hyg_log_ret.rolling(20 if bpd > 1 else w(3)).sum().fillna(0.0)
    else:
        fdf['hyg_intraday_momentum_6b'] = 0.0
        fdf['hyg_mom_20b'] = 0.0

    qqq_log_ret = np.log(qqq / qqq.shift(1))
    intraday_vol_win = 6 if bpd > 1 else w(1)
    fdf['qqq_intraday_vol_6b'] = qqq_log_ret.rolling(intraday_vol_win).std().fillna(0.0)

    if 'qqq_volume' in fdf.columns and bpd > 1:
        # Time-of-day-aware volume z-score (see module docstring)
        bar_of_day = fdf.index.hour * 60 + fdf.index.minute
        vol_by_bar_mean = fdf.groupby(bar_of_day)['qqq_volume'].transform(
            lambda s: s.rolling(20, min_periods=5).mean())
        vol_by_bar_std = fdf.groupby(bar_of_day)['qqq_volume'].transform(
            lambda s: s.rolling(20, min_periods=5).std())
        fdf['volume_zscore_20d'] = ((fdf['qqq_volume'] - vol_by_bar_mean) /
                                     vol_by_bar_std.replace(0, np.nan)).fillna(0.0)
    elif 'qqq_volume' in fdf.columns:
        vol_mean = fdf['qqq_volume'].rolling(w(20)).mean()
        vol_std = fdf['qqq_volume'].rolling(w(20)).std()
        fdf['volume_zscore_20d'] = ((fdf['qqq_volume'] - vol_mean) / vol_std.replace(0, np.nan)).fillna(0.0)
    else:
        fdf['volume_zscore_20d'] = 0.0

    # ─── Category 3: Fractionally Differentiated Series (proxy) ────────────
    for col in ['qqq_close', 'qqq_volume', 'vix_close']:
        fracdiff_col = f'{col}_fracdiff'
        if fracdiff_col not in fdf.columns:
            src = fdf.get(col, None)
            if src is not None:
                fdf[fracdiff_col] = src.pct_change(w(10)).fillna(0.0)
            else:
                fdf[fracdiff_col] = 0.0

    return fdf
