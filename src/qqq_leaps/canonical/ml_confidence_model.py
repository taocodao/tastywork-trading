"""
ml_confidence_model.py — Trained, walk-forward ml_confidence replacement.

Item 1 of the CAGR Improvement Plan: replaces the hand-weighted ml_confidence
formula in build_enhanced_features() with a gradient-boosted classifier,
trained and applied via a fully causal (no lookahead) walk-forward scheme.

WHY WALK-FORWARD INFERENCE, NOT A SINGLE STATIC MODEL:
Every one of the 5 QQQ hourly engines backtests a different, overlapping
date range (1Y: 2025-07 to 2026-07; ..., 5Y: 2021-08 to 2026-07). A single
model trained once on, say, the first 60% of history and then applied to
the rest (mirroring how the HMM regime classifier already works in this
codebase) would still be "causal" in the narrow sense of not training on
future data -- but it would leave the model stale for years of live-relevant
history without ever refitting on newer regimes. Instead, this module
retrains an expanding-window model periodically (default: every ~63 trading
days, roughly quarterly) so that every prediction for date t only ever uses
a model trained on data available strictly before t (respecting a purge gap
equal to the label horizon, so training labels near the cutoff don't leak
future information either).

TARGET: y = 1 if QQQ forward 40-trading-day return > 0, else 0.
  Chosen (with user approval) as a short-horizon proxy for "is this a good
  time to open a bullish LEAPS position" -- the literal 365-730 day LEAPS
  holding-period target was checked and rejected: it yields only 2-5
  independent non-overlapping training examples even using the full 2016+
  daily history, far too few to train or validate any model reliably.

FEATURES: the same causal inputs the current hand-weighted formula uses
(above_sma100, above_sma200, p_bull_hmm, p_bear_hmm, rsi_14, vix,
iv_rv_ratio, vix_term_slope, put_demand_proxy) plus a handful of extras
already computed causally elsewhere in this same pipeline (adx_14,
vix_5d_chg, realized_vol_20d, gap_down_pct, vix_curve_inverted, ret_20d,
ret_60d) -- chosen deliberately to make this a direct, comparable upgrade of
the existing formula's inputs, not an unrelated black box.

VALIDATION SUMMARY (see /home/user/workspace/item1_*.py smoke tests and
item1_ml_confidence_results.md report for full detail): a 7-fold expanding
walk-forward, purged (40-day gap), causal evaluation found the new model
beats the old formula's per-fold AUC-ROC in 6/7 folds (mean per-fold AUC
0.623 vs 0.344) -- the old formula is often WORSE than random ranking
(AUC<0.5) across most of the tested history. Restricting to only the days
the engine's own regime gate would actually allow a trade (excluding
BEAR/BEAR_SMA_FORCED), the new model shows a lower negative-outcome rate
(22.1% vs 30.4%) and higher mean forward return (4.30% vs 2.75%) than the
old formula at the current entry_ml_min=0.45 threshold.

SAFEGUARD (added per user request): the highest-stakes usage of
ml_confidence is the BULL_STRONG bonus-sizing rule (doubles LEAPS contract
count when ml_confidence>=0.80). Smoke-tested a 3-bar confidence-persistence
requirement (must stay >=0.80 for 3 consecutive bars, not just spike once)
as an independent-of-ml_confidence check on signal stability: this improved
both mean forward return (6.36% vs 6.01%) and lowered the negative-outcome
rate (12.9% vs 15.3%) for bonus-sizing days versus no safeguard. Implemented
as `ml_confidence_stable` alongside `ml_confidence` so engines can gate
sizing decisions on persistence, not just the instantaneous score.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.utils.class_weight import compute_sample_weight

logger = logging.getLogger(__name__)

HORIZON_DAYS = 40          # forward-return label horizon
PURGE_DAYS = HORIZON_DAYS  # must equal horizon: purge gap prevents label leakage
MIN_TRAIN_DAYS = 500       # ~2 years, minimum history before the first prediction
REFIT_EVERY_DAYS = 63      # ~1 trading quarter between model refits
PERSISTENCE_BARS = 3       # consecutive bars ml_confidence must hold >=0.80 for ml_confidence_stable

CORE_FEATURES = [
    "above_sma100", "above_sma200", "p_bull_hmm", "p_bear_hmm",
    "rsi_14", "vix", "iv_rv_ratio", "vix_term_slope", "put_demand_proxy",
]
EXTRA_FEATURES = [
    "adx_14", "vix_5d_chg", "realized_vol_20d", "gap_down_pct",
    "vix_curve_inverted", "ret_20d", "ret_60d",
]
ALL_FEATURES = CORE_FEATURES + EXTRA_FEATURES


def _make_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=150, max_depth=4, learning_rate=0.05,
        l2_regularization=1.0, random_state=42,
    )


def compute_ml_confidence_walkforward(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given a features dataframe (as produced by build_enhanced_features, with
    Close and all ALL_FEATURES columns already present and causal), returns
    the same dataframe with two new/replaced columns:
      - ml_confidence: walk-forward, causal model P(y=1) score, same [0,1]
        scale and same semantic meaning ("higher = more bullish confidence")
        as the old hand-weighted formula it replaces.
      - ml_confidence_stable: 1.0 if ml_confidence has been >=0.80 for the
        trailing PERSISTENCE_BARS consecutive bars (including the current
        one), else 0.0. Intended for gating high-stakes bonus-sizing
        decisions on sustained conviction rather than a single-bar spike.

    Rows before MIN_TRAIN_DAYS + PURGE_DAYS (i.e. before the first model can
    be causally trained and applied) get ml_confidence = NaN, matching the
    existing pattern of other rolling-window features (e.g. sma_200) being
    NaN during their own warmup period. Callers (build_enhanced_features)
    should fill or handle NaN consistently with how they already handle
    other NaN warmup features.
    """
    n = len(df)
    for col in ALL_FEATURES + ["Close"]:
        if col not in df.columns:
            raise ValueError(f"compute_ml_confidence_walkforward: missing required column '{col}'")

    X_all = df[ALL_FEATURES].astype(float).values
    close = df["Close"].values

    # Forward-return target, computed once for training purposes only. NaN in
    # the last HORIZON_DAYS rows (no future price yet) -- those rows are never
    # used as training labels since the purge gap always excludes them from
    # any model's training window before its prediction date.
    fwd_ret = np.full(n, np.nan)
    fwd_ret[: n - HORIZON_DAYS] = close[HORIZON_DAYS:] / close[: n - HORIZON_DAYS] - 1
    y_all = (fwd_ret > 0).astype(float)
    y_all[np.isnan(fwd_ret)] = np.nan

    ml_confidence = np.full(n, np.nan)

    first_test_idx = MIN_TRAIN_DAYS + PURGE_DAYS
    if first_test_idx >= n:
        logger.warning(
            f"compute_ml_confidence_walkforward: not enough history ({n} rows) "
            f"to train even one walk-forward fold (need >= {first_test_idx}); "
            f"returning all-NaN ml_confidence."
        )
        df = df.copy()
        df["ml_confidence"] = ml_confidence
        df["ml_confidence_stable"] = 0.0
        return df

    model: Optional[HistGradientBoostingClassifier] = None
    next_refit_idx = first_test_idx

    for t in range(first_test_idx, n):
        if model is None or t >= next_refit_idx:
            train_end = t - PURGE_DAYS  # exclusive; strictly causal
            X_train = X_all[:train_end]
            y_train = y_all[:train_end]
            valid = ~np.isnan(y_train)
            X_train, y_train = X_train[valid], y_train[valid]

            if len(np.unique(y_train)) < 2:
                # Degenerate training window (single class) -- skip refit, keep
                # using the previous model if one exists, else leave NaN.
                if model is None:
                    continue
            else:
                sw = compute_sample_weight(class_weight="balanced", y=y_train)
                model = _make_model()
                model.fit(X_train, y_train, sample_weight=sw)
            next_refit_idx = t + REFIT_EVERY_DAYS

        if model is not None:
            ml_confidence[t] = model.predict_proba(X_all[t : t + 1])[:, 1][0]

    df = df.copy()
    df["ml_confidence"] = ml_confidence

    # Persistence flag: current AND trailing (PERSISTENCE_BARS-1) prior bars
    # all >= 0.80. NaN-safe (NaN propagates to False via the comparison).
    conf_series = pd.Series(ml_confidence, index=df.index)
    rolling_min = conf_series.rolling(PERSISTENCE_BARS, min_periods=PERSISTENCE_BARS).min()
    df["ml_confidence_stable"] = (rolling_min >= 0.80).astype(float).fillna(0.0)

    n_trained = n - first_test_idx
    n_refits = max(1, n_trained // REFIT_EVERY_DAYS + 1)
    logger.info(
        f"ml_confidence walk-forward: {n_trained} predicted rows, ~{n_refits} model refits "
        f"(refit every {REFIT_EVERY_DAYS}d, purge={PURGE_DAYS}d, min_train={MIN_TRAIN_DAYS}d)"
    )
    return df
