import pandas as pd
import numpy as np

# ──────────────────────────────────────────────────────────────────────────────
# Feature set v2 — expanded from 6 to 11 features
# Research basis: Perplexity Q3 findings on cross-asset XGBoost features
# ──────────────────────────────────────────────────────────────────────────────
SCORER_FEATURES = [
    # ── Existing 6 ───────────────────────────────────────────────────────────
    'tqqq_rsi_14',     # RSI(14) on TQQQ — momentum anchor
    'tqqq_macd_hist',  # MACD(12,26,9) histogram — trend momentum
    'tqqq_bb_width',   # Bollinger Band width (20,2) — volatility state
    'qqq_vol_20d',     # QQQ 20-day realized vol — regime volatility
    'vix_close',       # VIX level — fear / implied vol
    'vix_rel_50',      # VIX / VIX-50d-SMA — relative fear level

    # ── New 5 (cross-asset regime signals) ───────────────────────────────────
    'vix_term_slope',      # VIX/VIX3M ratio — term structure stress indicator
    'hyg_20d_slope',       # HYG 20d ROC — credit spread trend (cross-asset)
    'qqq_pcr_proxy',       # VXN/VIX ratio — QQQ-specific vol premium vs SPX
    'xlk_xlv_ratio_20d',   # XLK/XLV 20d momentum — tech vs defensive rotation
    'iv_rv_spread',        # VXN - QQQ realized vol (annualized) — variance risk premium
]


def generate_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Appends all 11 XGBoost scorer features to the master dataframe.

    Original features (6):
      tqqq_rsi_14, tqqq_macd_hist, tqqq_bb_width, qqq_vol_20d, vix_close, vix_rel_50

    New cross-asset features (5):
      vix_term_slope, hyg_20d_slope, qqq_pcr_proxy, xlk_xlv_ratio_20d, iv_rv_spread

    Cross-asset features are passed through from data_pipeline v2 columns.
    If missing they are computed with fallback proxies.
    """
    if 'tqqq_close' not in df.columns:
        return df

    fdf = df.copy()
    close_s = fdf['tqqq_close']

    # ── 1. RSI(14) on TQQQ ───────────────────────────────────────────────────
    delta = close_s.diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    fdf['tqqq_rsi_14'] = (100 - (100 / (1 + rs))).clip(0, 100)

    # ── 2. MACD(12, 26, 9) histogram ─────────────────────────────────────────
    ema12 = close_s.ewm(span=12, adjust=False).mean()
    ema26 = close_s.ewm(span=26, adjust=False).mean()
    fdf['tqqq_macd'] = ema12 - ema26
    fdf['tqqq_macd_signal'] = fdf['tqqq_macd'].ewm(span=9, adjust=False).mean()
    fdf['tqqq_macd_hist'] = fdf['tqqq_macd'] - fdf['tqqq_macd_signal']

    # ── 3. Bollinger Band Width (20, 2) ─────────────────────────────────────
    sma20 = close_s.rolling(window=20).mean()
    std20 = close_s.rolling(window=20).std()
    upper_band = sma20 + (std20 * 2)
    lower_band = sma20 - (std20 * 2)
    fdf['tqqq_bb_width'] = (upper_band - lower_band) / sma20.replace(0, np.nan)

    # ── 4. Relative VIX (VIX / VIX-50d-SMA) ─────────────────────────────────
    if 'vix_close' in fdf.columns:
        vix_sma50 = fdf['vix_close'].rolling(50).mean()
        fdf['vix_rel_50'] = (fdf['vix_close'] / vix_sma50.replace(0, np.nan)).clip(0.3, 4.0)

    # ── 5. VIX term structure slope (NEW) ────────────────────────────────────
    # Carry-through from data_pipeline v2; compute fallback if missing
    if 'vix_term_slope' not in fdf.columns:
        if 'vix_close' in fdf.columns:
            # Proxy: no VIX3M data → assume normal contango (slope ~0.9)
            fdf['vix_term_slope'] = 0.9
        else:
            fdf['vix_term_slope'] = 0.9

    # ── 6. HYG 20d slope (NEW — credit spread proxy) ─────────────────────────
    if 'hyg_20d_slope' not in fdf.columns:
        fdf['hyg_20d_slope'] = 0.0  # Neutral default (no credit data)

    # ── 7. QQQ put-call ratio proxy (NEW) ────────────────────────────────────
    # Proxy: VXN/VIX ratio captures QQQ-specific fear premium relative to SPX
    if 'qqq_pcr_proxy' not in fdf.columns:
        if 'vxn_close' in fdf.columns and 'vix_close' in fdf.columns:
            fdf['qqq_pcr_proxy'] = (
                fdf['vxn_close'] / fdf['vix_close'].replace(0, np.nan)
            ).clip(0.5, 3.0)
        else:
            fdf['qqq_pcr_proxy'] = 1.15  # Historical VXN/VIX average

    # ── 8. XLK/XLV sector rotation momentum (NEW) ────────────────────────────
    if 'xlk_xlv_ratio_20d' not in fdf.columns:
        fdf['xlk_xlv_ratio_20d'] = 0.0  # Neutral default

    # ── 9. IV-RV spread / variance risk premium (NEW) ────────────────────────
    if 'iv_rv_spread' not in fdf.columns:
        if 'vxn_close' in fdf.columns and 'qqq_vol_20d' in fdf.columns:
            vxn_ann = fdf['vxn_close'] / 100.0
            qqq_rv_ann = fdf['qqq_vol_20d'] * np.sqrt(252)
            fdf['iv_rv_spread'] = (vxn_ann - qqq_rv_ann).clip(-0.3, 0.5)
        elif 'vix_close' in fdf.columns and 'qqq_vol_20d' in fdf.columns:
            # Proxy using VIX instead of VXN
            vix_ann = fdf['vix_close'] / 100.0
            qqq_rv_ann = fdf['qqq_vol_20d'] * np.sqrt(252)
            fdf['iv_rv_spread'] = (vix_ann - qqq_rv_ann).clip(-0.3, 0.5)
        else:
            fdf['iv_rv_spread'] = 0.05  # Small positive VRP as default

    return fdf


def label_crossover_outcomes_triple_barrier(
    df: pd.DataFrame,
    forward_days: int = 20,
    upper_pct: float = 0.06,
    lower_pct: float = 0.04,
) -> pd.DataFrame:
    """
    Full ternary Triple-Barrier labeling (Lopez de Prado, 2018 — AFML Ch. 3).

    For each bull crossover event (TQQQ 5/30 EMA first fires):
      Upper barrier: +6% from entry (close-to-close) → label = +1 (WIN)
      Lower barrier: -4% from entry (close-to-close) → label = -1 (LOSS)
      Vertical barrier: 20 trading days, whichever comes first → label = 0 (NEUTRAL)

    This replaces the previous max-excursion label which overfitted to lucky
    price touches that immediately reversed (Lopez de Prado 2018, §3.4).

    Class mapping for XGBoost num_class=3:
      -1 (LOSS)    → class 0
       0 (NEUTRAL) → class 1
      +1 (WIN)     → class 2
    """
    fdf = df.copy()
    fdf['target_class'] = np.nan    # raw ternary label: -1, 0, +1
    fdf['target_label'] = np.nan    # encoded: 0, 1, 2 for XGBoost

    # Detect crossover trigger: first day the golden cross fires
    fdf['bull_cross_trigger'] = (
        (fdf['tqqq_bull_cross'] == True) &
        (fdf['tqqq_bull_cross'].shift(1) == False)
    )

    for idx_loc in range(len(fdf)):
        idx = fdf.index[idx_loc]
        if not fdf.loc[idx, 'bull_cross_trigger']:
            continue

        end_loc = min(idx_loc + forward_days, len(fdf) - 1)
        future_slice = fdf.iloc[idx_loc + 1: end_loc + 1]

        if len(future_slice) < 5:
            continue  # Insufficient forward data for reliable label

        entry_price = fdf.loc[idx, 'tqqq_close']
        upper_barrier = entry_price * (1.0 + upper_pct)
        lower_barrier = entry_price * (1.0 - lower_pct)

        label = 0  # default: vertical barrier (time expired)

        for _, row in future_slice.iterrows():
            # Use high/low if available for more accurate barrier detection
            day_high = row.get('tqqq_high', row['tqqq_close'])
            day_low = row.get('tqqq_low', row['tqqq_close'])

            if day_high >= upper_barrier:
                label = 1    # Upper barrier hit first → WIN
                break
            elif day_low <= lower_barrier:
                label = -1   # Lower barrier hit first → LOSS
                break

        fdf.loc[idx, 'target_class'] = label

        # Encode for XGBoost: {-1→0, 0→1, +1→2}
        fdf.loc[idx, 'target_label'] = {-1: 0, 0: 1, 1: 2}[label]

    return fdf


# ── Legacy alias for backward compatibility with existing callers ─────────────
def label_crossover_outcomes(
    df: pd.DataFrame,
    forward_days: int = 20,
    threshold_pct: float = 0.06,
) -> pd.DataFrame:
    """
    Deprecated: calls triple-barrier and maps to binary target_profitable.
    Kept for backward compatibility. New code should use label_crossover_outcomes_triple_barrier.
    """
    fdf = label_crossover_outcomes_triple_barrier(
        df, forward_days=forward_days, upper_pct=threshold_pct, lower_pct=0.04
    )
    # Map ternary → binary: WIN(+1)→1, everything else→0
    fdf['target_profitable'] = (fdf['target_class'] == 1).astype(float)
    # Preserve NaN for unlabeled rows
    fdf.loc[fdf['target_class'].isna(), 'target_profitable'] = np.nan
    return fdf
