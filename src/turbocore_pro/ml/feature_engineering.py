import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: FULL FAKEOUT-AVOIDANCE FEATURE SET
# 16 features across 3 categories:
#   Category 1: Volume & Breadth (8 features)
#   Category 2: Macro Confirmation (5 features — some from data_pipeline)
#   Category 3: Fractionally Differentiated Price Series (3 features)
# ══════════════════════════════════════════════════════════════════════════════

def generate_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Appends all momentum, volatility, trend, fakeout-avoidance, and macro
    features to the master dataframe for the meta-labeling XGBoost pipeline.

    Expects columns: qqq_close, tqqq_close, vix_close
    Optional:        qqq_volume, vix_term_slope, hyg_5d_change, 
                     fed_funds_3m_change, ism_mfg_delta, initial_claims_slope,
                     qqq_close_fracdiff, qqq_volume_fracdiff, vix_close_fracdiff
    """
    if 'tqqq_close' not in df.columns:
        return df

    fdf = df.copy()
    tqqq = fdf['tqqq_close']
    qqq  = fdf.get('qqq_close', tqqq)

    # ─── Core Technical (legacy, kept for compatibility) ─────────────────────
    delta = tqqq.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    fdf['tqqq_rsi_14'] = 100 - (100 / (1 + rs))

    ema12 = tqqq.ewm(span=12, adjust=False).mean()
    ema26 = tqqq.ewm(span=26, adjust=False).mean()
    fdf['tqqq_macd']        = ema12 - ema26
    fdf['tqqq_macd_signal'] = fdf['tqqq_macd'].ewm(span=9, adjust=False).mean()
    fdf['tqqq_macd_hist']   = fdf['tqqq_macd'] - fdf['tqqq_macd_signal']

    sma20 = tqqq.rolling(20).mean()
    std20 = tqqq.rolling(20).std()
    fdf['tqqq_bb_width'] = ((sma20 + 2 * std20) - (sma20 - 2 * std20)) / sma20

    if 'vix_close' in fdf.columns:
        vix_sma50       = fdf['vix_close'].rolling(50).mean()
        fdf['vix_rel_50'] = fdf['vix_close'] / vix_sma50

    # ─── Category 1: Volume & Breadth Features ───────────────────────────────

    if 'qqq_volume' in fdf.columns:
        vol = fdf['qqq_volume']
        vol_5d  = vol.rolling(5).mean()
        vol_20d = vol.rolling(20).mean()

        # 1a. Volume ratio (5-day avg vs 20-day avg, percentile-ranked)
        raw_ratio = np.log(vol_5d / vol_20d.replace(0, np.nan))
        fdf['vol_ratio'] = raw_ratio.rolling(252).rank(pct=True).fillna(0.5)

        # 1b. Cumulative volume delta (buy vs sell pressure, 20-day window)
        price_direction   = np.sign(qqq - qqq.shift(1))
        cum_vol_delta     = (vol * price_direction).rolling(20).sum()
        fdf['cum_vol_delta'] = (cum_vol_delta / vol.rolling(20).sum()).fillna(0.0)

        # 1c. Distribution day count (high-vol down days in 20-day window)
        is_dist_day = ((vol > vol.shift(1)) & (qqq.pct_change() < -0.004)).astype(float)
        fdf['distribution_day_count_20d'] = is_dist_day.rolling(20).sum().fillna(0.0)

        # 1d. Bounce volume vs prior decline volume
        qqq_ret          = qqq.pct_change()
        declining_vol_20d = (vol * (qqq_ret < 0).astype(float)).rolling(20).sum()
        bounce_vol_5d     = vol_5d
        raw_bounce_ratio  = bounce_vol_5d / (declining_vol_20d / 20).replace(0, np.nan)
        fdf['bounce_vol_ratio'] = raw_bounce_ratio.clip(0, 5).fillna(1.0)
    else:
        fdf['vol_ratio']                  = 0.5
        fdf['cum_vol_delta']              = 0.0
        fdf['distribution_day_count_20d'] = 0.0
        fdf['bounce_vol_ratio']           = 1.0

    # 1e. Fibonacci retracement level (bounce vs. prior 20-day range)
    rolling_high  = qqq.rolling(20).max()
    rolling_low   = qqq.rolling(20).min()
    price_range   = (rolling_high - rolling_low).replace(0, np.nan)
    fdf['fib_retracement'] = ((qqq - rolling_low) / price_range).fillna(0.5)

    # 1f. Sector breadth uniformity (variance of 5d returns across TQQQ/QLD proxies)
    # Use TQQQ vs QQQ return divergence as breadth proxy (true sector data needs ETF feed)
    tqqq_5d_ret = tqqq.pct_change(5)
    qqq_5d_ret  = qqq.pct_change(5)
    fdf['sector_divergence'] = (tqqq_5d_ret - (3 * qqq_5d_ret)).abs().rolling(10).mean().fillna(0.0)

    # 1g. Short-term momentum divergence (5d vs 20d return ratio)
    ret_5d  = qqq.pct_change(5)
    ret_20d = qqq.pct_change(20)
    fdf['momentum_divergence'] = (ret_5d / ret_20d.replace(0, np.nan)).clip(-3, 3).fillna(0.0)

    # 1h. New highs minus new lows proxy (rolling 52-week % of days at highs)
    qqq_52w_max    = qqq.rolling(252).max()
    fdf['nh_proxy'] = (qqq / qqq_52w_max).rolling(20).mean().fillna(0.5)

    # ─── Category 2: Macro Confirmation Features ─────────────────────────────

    # 2a. VIX term structure slope (VIX3M - VIX spread, normalized)
    if 'vix_term_slope' in fdf.columns:
        fdf['vix_term_slope'] = fdf['vix_term_slope'].fillna(0.0)
    else:
        fdf['vix_term_slope'] = 0.0

    # 2b. HY credit spread proxy (HYG z-score change over 5 days)
    if 'hyg_5d_change' in fdf.columns:
        fdf['hyg_5d_change'] = fdf['hyg_5d_change'].fillna(0.0)
    else:
        fdf['hyg_5d_change'] = 0.0

    # 2b2. HY OAS z-score — ICE BofA BAMLH0A0HYM2 (preferred over HYG proxy)
    # Positive z = spreads wider than 60-day mean = risk-off signal (fakeout detector).
    # Negative z = spreads tightening = risk-on confirmation of genuine bull move.
    # Perplexity 2026-03-21: "Single best macro leading indicator for NASDAQ-100
    # regime deterioration — 15–30 day lead time on price decline."
    if 'hy_oas_zscore' in fdf.columns:
        fdf['hy_oas_zscore'] = fdf['hy_oas_zscore'].fillna(0.0)
    else:
        # If data_pipeline didn't provide it, synthesise from HYG proxy (inverted)
        fdf['hy_oas_zscore'] = -fdf.get('hyg_5d_change', pd.Series(0.0, index=fdf.index))

    if 'hy_oas_5d_change' in fdf.columns:
        fdf['hy_oas_5d_change'] = fdf['hy_oas_5d_change'].fillna(0.0)
    else:
        fdf['hy_oas_5d_change'] = fdf['hy_oas_zscore'].diff(5).fillna(0.0)

    # 2c. Fed funds rate trajectory (3-month change)
    if 'fed_funds_3m_change' in fdf.columns:
        fdf['fed_funds_3m_change'] = fdf['fed_funds_3m_change'].fillna(0.0)
    else:
        # Approximate via TLT proxy (Treasury ETF 20-day momentum)
        if 'tlt_close' in fdf.columns:
            fdf['fed_funds_3m_change'] = fdf['tlt_close'].pct_change(63).fillna(0.0)
        else:
            fdf['fed_funds_3m_change'] = 0.0

    # 2d. ISM Manufacturing delta (proxied via industrial sector momentum)
    if 'ism_mfg_delta' in fdf.columns:
        fdf['ism_mfg_delta'] = fdf['ism_mfg_delta'].fillna(0.0)
    else:
        fdf['ism_mfg_delta'] = 0.0  # Set to 0 until FRED API wired in Phase 2

    # 2e. Initial claims slope (proxied via inverted TLT momentum as risk-off signal)
    if 'initial_claims_slope' in fdf.columns:
        fdf['initial_claims_slope'] = fdf['initial_claims_slope'].fillna(0.0)
    else:
        fdf['initial_claims_slope'] = 0.0  # Set to 0 until FRED API wired in Phase 2

    # ─── Category 3: Fractionally Differentiated Series ──────────────────────

    # 3a-3c: Use pre-computed fracdiff columns if available (from data_pipeline)
    # If not, fall back to standard 10-day returns as proxy
    for col in ['qqq_close', 'qqq_volume', 'vix_close']:
        fracdiff_col = f'{col}_fracdiff'
        if fracdiff_col not in fdf.columns:
            # Proxy: pct_change(10) approximates fractional differentiation when d≈0.4
            src = fdf.get(col, None)
            if src is not None:
                fdf[fracdiff_col] = src.pct_change(10).fillna(0.0)
            else:
                fdf[fracdiff_col] = 0.0

    return fdf


def add_fracdiff_features(df: pd.DataFrame, cols: list = None) -> pd.DataFrame:
    """
    Adds truly fractionally differentiated price series using the fracdiff library.
    Finds minimum d that achieves ADF stationarity (p < 0.05) for each column.

    These features preserve long-memory in price series while achieving stationarity,
    which standard returns (d=1.0) destroy. Optimal d for QQQ daily closes is
    typically in [0.3, 0.5], preserving >85% correlation with the original series.

    Pure-numpy implementation — no external fracdiff package required.
    """
    if cols is None:
        cols = ['qqq_close', 'qqq_volume', 'vix_close']

    # ADF test requires statsmodels (usually pre-installed with pandas)
    try:
        from statsmodels.tsa.stattools import adfuller
        adf_available = True
    except ImportError:
        adf_available = False
        logger.debug("statsmodels not available. fracdiff will use d=0.4 fixed.")

    fdf = df.copy()

    for col in cols:
        fracdiff_col = f'{col}_fracdiff'
        if col not in fdf.columns:
            fdf[fracdiff_col] = 0.0
            continue

        series = fdf[col].ffill().dropna()
        if len(series) < 100:
            fdf[fracdiff_col] = fdf[col].pct_change(10).fillna(0.0)
            continue

        best_d      = 0.4   # Sensible default if ADF sweep fails
        best_result = None

        # Sweep d values to find minimum d achieving stationarity
        d_range = np.arange(0.1, 1.0, 0.05) if adf_available else [0.4]

        for d in d_range:
            try:
                diffed = _fracdiff_numpy(series.values, d=round(float(d), 2), window=100)
                clean  = diffed[~np.isnan(diffed)]
                if len(clean) < 50:
                    continue
                if adf_available:
                    _, p_val, *_ = adfuller(clean, maxlag=10, autolag='AIC')
                    if p_val < 0.05:
                        best_d      = d
                        best_result = diffed
                        break
                else:
                    best_result = diffed
                    break
            except Exception:
                continue

        if best_result is not None:
            aligned = np.full(len(series), np.nan)
            aligned[:len(best_result)] = best_result
            fdf.loc[series.index, fracdiff_col] = aligned
            logger.debug(f"Fracdiff {col}: d={best_d:.2f}")
        else:
            fdf[fracdiff_col] = fdf[col].pct_change(10).fillna(0.0)

    return fdf


def _fracdiff_numpy(x: np.ndarray, d: float, window: int = 100) -> np.ndarray:
    """
    Pure-numpy fractional differentiation using binomial series expansion.

    Computes weights: w_k = prod_{j=0}^{k-1} (d - j) / (j + 1)
    Then applies rolling dot-product: fracdiff[t] = sum_{k=0}^{w} w_k * x[t-k]

    Args:
        x:      Price series (1D numpy array)
        d:      Fractional order [0.0, 1.0]
        window: Number of weights to use (higher = more accurate, slower)

    Returns:
        Fractionally differentiated series (same length as x, NaN for first `window` rows)
    """
    # Compute binomial series weights
    weights    = np.zeros(window)
    weights[0] = 1.0
    for k in range(1, window):
        weights[k] = weights[k - 1] * (d - k + 1) / k
    weights = weights[::-1]   # Flip so oldest weight is first in dot product

    n      = len(x)
    result = np.full(n, np.nan)

    for t in range(window - 1, n):
        result[t] = np.dot(weights, x[t - window + 1: t + 1])

    return result



def label_crossover_outcomes(
    df: pd.DataFrame,
    forward_days: int = 21,
    tp_mult: float = 1.5,
    sl_mult: float = 0.75,
    label_mode: str = 'daily_condition',
) -> pd.DataFrame:
    """
    Triple-Barrier Meta-Labeling (López de Prado methodology, corrected for TQQQ).

    KEY FIXES vs prior implementation:
    ─────────────────────────────────────────────────────────────────────────────
    FIX 1 — Barrier scaler: Use 20-day EWMA *daily* volatility, NOT path vol.
      Prior: trgt = rolling(60).std() * sqrt(63) ≈ 60–80% → TP required 180%+
      Fixed: trgt = 20-day EWMA daily std ≈ 4–5% → TP requires ~6–7.5%
      Source: López de Prado (2018) Ch.3; Quantreo newsletter

    FIX 3 — Labeling granularity: Label every day EMA condition is TRUE,
      not only the first crossover day.
      Prior:  31 labeled events (7 years) → too sparse for XGBoost
      Fixed:  ~1,000–1,500 labeled days → sufficient for reliable meta-labeling
      Source: Meta-Labeling Reddit (r/algotrading); Hudson & Thames research

    Parameters:
        forward_days: Vertical barrier (default 21 = 1 month; short enough for TQQQ)
        tp_mult:      TP = entry_price × (1 + tp_mult × ewma_daily_vol)
        sl_mult:      SL = entry_price × (1 - sl_mult × ewma_daily_vol)
        label_mode:   'daily_condition' (all active EMA days, ~1000+ samples)
                      'crossover_only'  (only first day of crossover, 31 events)
    ─────────────────────────────────────────────────────────────────────────────

    Output column: target_profitable
        1  = TQQQ hit TP before SL or vertical barrier
        0  = TQQQ hit SL or timed out without TP
       NaN = no signal active on this day (label_mode='crossover_only')
    """
    fdf = df.copy()
    fdf['target_profitable'] = np.nan
    fdf['label_trgt']        = np.nan   # Target barrier width (for diagnostics)

    if 'tqqq_close' not in fdf.columns or 'tqqq_bull_cross' not in fdf.columns:
        logger.warning("label_crossover_outcomes: missing tqqq_close or tqqq_bull_cross")
        return fdf

    # ── FIX 1: 20-day EWMA daily volatility as barrier scaler ────────────────
    # ewma_daily_vol ≈ 4–5% for TQQQ, giving realistic TP/SL barriers
    daily_ret     = fdf['tqqq_close'].pct_change()
    ewma_daily_vol = daily_ret.ewm(span=20, min_periods=10).std()
    fdf['label_trgt'] = ewma_daily_vol

    # ── FIX 3: Determine which days to label ─────────────────────────────────
    if label_mode == 'crossover_only':
        # Original behaviour: only the first day of a new EMA crossover
        label_mask = (
            (fdf['tqqq_bull_cross'] == True) &
            (fdf['tqqq_bull_cross'].shift(1) == False)
        )
    else:
        # FIX: label every day the 5/30 EMA bull condition is active
        # The meta-model predicts "will this active bull window succeed?"
        label_mask = fdf['tqqq_bull_cross'] == True

    labeled_days = fdf.index[label_mask]
    logger.info(f"Labeling {len(labeled_days)} days (mode='{label_mode}', "
                f"tp_mult={tp_mult}, sl_mult={sl_mult}, forward={forward_days}d)")

    prices = fdf['tqqq_close']
    n_pos, n_neg = 0, 0

    for idx_loc, idx in enumerate(fdf.index):
        if idx not in labeled_days:
            continue
        if idx_loc + forward_days >= len(fdf):
            continue  # Not enough future data for vertical barrier

        trgt        = ewma_daily_vol.loc[idx]
        if pd.isna(trgt) or trgt <= 0:
            continue

        entry_price  = prices.loc[idx]
        tp_price     = entry_price * (1 + tp_mult * trgt)
        sl_price     = entry_price * (1 - sl_mult * trgt)

        # Scan forward until one barrier is hit or vertical barrier reached
        future_prices = prices.iloc[idx_loc + 1: idx_loc + 1 + forward_days]
        hit_tp        = False
        hit_sl        = False

        for fp in future_prices:
            if fp >= tp_price:
                hit_tp = True
                break
            if fp <= sl_price:
                hit_sl = True
                break

        label = 1 if hit_tp else 0
        fdf.loc[idx, 'target_profitable'] = label

        if label == 1:
            n_pos += 1
        else:
            n_neg += 1

    total = n_pos + n_neg
    bal   = n_pos / total if total > 0 else 0.0
    logger.info(f"Labels: {n_pos} pos / {n_neg} neg = {bal:.1%} positive "
                f"(target: 25–35% for reliable XGBoost meta-model)")

    return fdf

