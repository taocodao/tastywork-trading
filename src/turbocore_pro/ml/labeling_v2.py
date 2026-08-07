"""
Bar-cadence-aware triple-barrier meta-labeling. Generalizes
feature_engineering.py's label_crossover_outcomes() so the vertical
barrier (forward_days) and the EWMA vol span used for TP/SL sizing are
expressed in TRADING DAYS and internally rescaled to bar counts via
bars_per_day -- avoiding the bug where feeding hourly bars directly into
the daily-tuned function would make forward_days=21 mean "21 HOURLY BARS"
(~3 trading days) instead of the intended 1-month horizon.
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def label_crossover_outcomes_v2(
    df: pd.DataFrame,
    forward_days: float = 21,
    tp_mult: float = 1.5,
    sl_mult: float = 0.75,
    label_mode: str = 'daily_condition',
    bars_per_day: float = 1.0,
    label_boundary_pos: int = None,
) -> pd.DataFrame:
    """
    Same semantics as the original (López de Prado triple-barrier), but
    forward_days and the 20-day EWMA vol span are both expressed in
    TRADING DAYS and converted to bar counts internally via bars_per_day.
    Pass bars_per_day=1.0 for daily data (exact reproduction of the
    original function).

    label_boundary_pos (Phase 0.2 correctness fix): positional index that the
    forward-looking barrier window must resolve strictly before. Any candidate
    bar i whose window [i+1, i+forward_bars] would reach at or past this
    position is left unlabelled. Defaults to len(df) — i.e. the barrier may
    only use bars present in the frame that was passed in. Callers fitting on
    a walk-forward train slice should pass the train-end position explicitly so
    the invariant is enforced rather than merely implied by the slice bounds.
    """
    bpd = bars_per_day
    forward_bars = max(1, int(round(forward_days * bpd)))
    ewma_span_bars = max(2, int(round(20 * bpd)))
    min_periods_bars = max(1, int(round(10 * bpd)))

    fdf = df.copy()
    fdf['target_profitable'] = np.nan
    fdf['label_trgt'] = np.nan

    if 'tqqq_close' not in fdf.columns or 'tqqq_bull_cross' not in fdf.columns:
        logger.warning("label_crossover_outcomes_v2: missing tqqq_close or tqqq_bull_cross")
        return fdf

    # Bar-over-bar returns, EWMA'd over a bar-scaled 20-trading-day span.
    # This still measures BAR-level vol (not daily-close-to-close vol) --
    # at hourly cadence this yields a lower per-bar vol number, which is
    # dimensionally correct for setting hourly-bar-appropriate barriers.
    bar_ret = fdf['tqqq_close'].pct_change()
    ewma_vol = bar_ret.ewm(span=ewma_span_bars, min_periods=min_periods_bars).std()
    fdf['label_trgt'] = ewma_vol

    if label_mode == 'crossover_only':
        label_mask = (fdf['tqqq_bull_cross'] == True) & (fdf['tqqq_bull_cross'].shift(1) == False)  # noqa: E712
    else:
        label_mask = fdf['tqqq_bull_cross'] == True  # noqa: E712

    labeled_idx = fdf.index[label_mask]
    logger.info(f"[v2] Labeling {len(labeled_idx)} bars (mode='{label_mode}', "
                f"tp_mult={tp_mult}, sl_mult={sl_mult}, forward={forward_days}d="
                f"{forward_bars}bars, bars_per_day={bpd})")

    prices = fdf['tqqq_close'].values
    n = len(fdf)
    boundary = n if label_boundary_pos is None else min(int(label_boundary_pos), n)
    idx_pos = {ts: i for i, ts in enumerate(fdf.index)}
    n_pos, n_neg, n_purged = 0, 0, 0

    trgt_vals = ewma_vol.values
    for ts in labeled_idx:
        i = idx_pos[ts]
        if i + forward_bars >= boundary:
            n_purged += 1
            continue
        trgt = trgt_vals[i]
        if not np.isfinite(trgt) or trgt <= 0:
            continue

        entry = prices[i]
        tp_price = entry * (1 + tp_mult * trgt)
        sl_price = entry * (1 - sl_mult * trgt)

        future = prices[i + 1: i + 1 + forward_bars]
        hit_tp = False
        for fp in future:
            if fp >= tp_price:
                hit_tp = True
                break
            if fp <= sl_price:
                break

        label = 1 if hit_tp else 0
        fdf.iloc[i, fdf.columns.get_loc('target_profitable')] = label
        if label == 1:
            n_pos += 1
        else:
            n_neg += 1

    total = n_pos + n_neg
    bal = n_pos / total if total > 0 else 0.0
    logger.info(f"[v2] Labels: {n_pos} pos / {n_neg} neg = {bal:.1%} positive "
                f"({n_purged} candidates purged: barrier window crossed bar {boundary})")

    return fdf
