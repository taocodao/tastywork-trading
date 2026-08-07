"""
v3.2 Test C -- regression meta-model, drop-in replacement for
TurboCoreSignalScorerV2.

The v2 scorer predicts P(triple-barrier TP hit before SL) with a two-model
recall/precision classifier stack. This one predicts the *magnitude* of the
forward move directly with a single XGBRegressor.

Target: forward 21-trading-day log return of TQQQ divided by the trailing EWMA
bar volatility scaled to that horizon --

    y[i] = log(P[i+H] / P[i]) / (trgt[i] * sqrt(H)),   H = round(21 * bars_per_day)

`trgt` is the identical EWMA series (span 20 trading days, min_periods 10) that
sizes the classifier's TP/SL barriers, so the two targets are measured in the
same volatility units and differ only in classification vs regression. Choosing
the vol-scaled form over a raw log return matters because the target spans
2020 and 2022: raw 21-day TQQQ returns are an order of magnitude more dispersed
in the stressed windows, so a squared-error fit would allocate nearly all its
capacity to a handful of high-vol episodes. Dividing by trailing vol makes the
target roughly homoskedastic and gives it a Sharpe-like interpretation. The
sqrt(H) factor is a constant and therefore does not affect ranking; it is there
so the numbers read as horizon z-scores.

Label embargo is the Phase 0.2 rule, byte-identical to labeling_v2: a bar is
labelled only if its forward window resolves strictly before `label_boundary_pos`.
"""
import os
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from .feature_engineering_v2 import generate_technical_features_v2
from .signal_scorer_v2 import TurboCoreSignalScorerV2


def forward_risk_adjusted_return(
    df: pd.DataFrame,
    forward_days: float = 21,
    bars_per_day: float = 1.0,
    label_boundary_pos: int = None,
    price_col: str = "tqqq_close",
) -> pd.Series:
    """Vol-scaled forward log return, embargoed at `label_boundary_pos`."""
    bpd = bars_per_day
    h = max(1, int(round(forward_days * bpd)))
    span = max(2, int(round(20 * bpd)))
    min_p = max(1, int(round(10 * bpd)))

    px = df[price_col].astype(float)
    trgt = px.pct_change().ewm(span=span, min_periods=min_p).std()

    fwd_log = np.log(px.shift(-h) / px)
    y = fwd_log / (trgt * np.sqrt(h))
    y = y.replace([np.inf, -np.inf], np.nan)

    n = len(df)
    boundary = n if label_boundary_pos is None else min(int(label_boundary_pos), n)
    # Same purge condition as labeling_v2: the window touches index i+h, so it
    # must land strictly inside the train slice.
    pos = np.arange(n)
    y[pos + h >= boundary] = np.nan
    return y.rename("target_fwd_rar")


class TurboCoreSignalScorerRegr:
    """Same interface as TurboCoreSignalScorerV2; regression head."""

    # META_FEATURES minus primary_prob -- there is no primary model to produce it.
    FEATURES = [f for f in TurboCoreSignalScorerV2.META_FEATURES if f != "primary_prob"]

    def __init__(self, bars_per_day: float = 1.0, model_tag: str = "daily",
                 sample_universe: str = "crossover"):
        """
        sample_universe:
          'crossover' -- train only on tqqq_bull_cross bars, the exact sample the
                         classifier is fit on. Isolates the target change.
          'all'       -- train on every bar with a resolved forward window.
                         Regression does not need an event to define an outcome,
                         so this is the variant that exploits the change.
        """
        self.bars_per_day = bars_per_day
        self.model_tag = model_tag
        self.sample_universe = sample_universe
        self.model_file = os.path.join(
            os.path.dirname(__file__), f"turbocore_xgbregr_{model_tag}.joblib")
        self.model: Optional[XGBRegressor] = None
        self.active_features: list = self.FEATURES
        self.is_trained = False

    def load(self):
        if os.path.exists(self.model_file):
            try:
                data = joblib.load(self.model_file)
                self.model = data["model"]
                self.active_features = data["features"]
                self.is_trained = True
            except Exception as e:
                logger.error(f"Failed loading regression scorer: {e}")
        return self

    def save(self):
        if self.model is not None and self.is_trained:
            joblib.dump({"model": self.model, "features": self.active_features},
                        self.model_file)

    def fit(self, df: pd.DataFrame, forward_days: float = 21,
            tp_mult: float = 1.5, sl_mult: float = 0.75,
            train_end_pos: int = None):
        """tp_mult / sl_mult are accepted and ignored -- there are no barriers.
        Kept so this is a drop-in for the classifier in the walk-forward loop."""
        if not XGBOOST_AVAILABLE:
            logger.warning("Cannot train: xgboost missing.")
            return

        fdf = generate_technical_features_v2(df, bars_per_day=self.bars_per_day)
        boundary = len(fdf) if train_end_pos is None else int(train_end_pos)
        fdf["target_fwd_rar"] = forward_risk_adjusted_return(
            fdf, forward_days=forward_days, bars_per_day=self.bars_per_day,
            label_boundary_pos=boundary)

        if self.sample_universe == "crossover":
            if "tqqq_bull_cross" not in fdf.columns:
                logger.warning("tqqq_bull_cross missing; falling back to all bars.")
            else:
                fdf = fdf[fdf["tqqq_bull_cross"] == True]  # noqa: E712

        available = [f for f in self.FEATURES if f in fdf.columns]
        valid = fdf.dropna(subset=available + ["target_fwd_rar"])
        if len(valid) < 30:
            logger.warning(f"Only {len(valid)} regression samples (<30). Skipping training.")
            return

        X = valid[available].values
        y = valid["target_fwd_rar"].values

        # Depth/estimators/subsample mirror the classifier's meta stage so the
        # comparison is between targets, not between capacities.
        self.model = XGBRegressor(
            n_estimators=200, max_depth=3, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.7, reg_alpha=1.0, reg_lambda=2.0,
            random_state=42, objective="reg:squarederror")
        self.model.fit(X, y)
        self.active_features = available
        self.is_trained = True
        self.save()
        logger.info(f"[regr] Trained on {len(X)} samples "
                    f"(universe={self.sample_universe}, y mean={y.mean():+.3f} "
                    f"sd={y.std():.3f}), {len(available)} features.")

    def predict_confidence(self, df: pd.DataFrame) -> pd.DataFrame:
        """Writes the continuous prediction into 'ml_confidence' so the rest of
        the pipeline (percentile transform, allocation tiers) is untouched."""
        out_df = df.copy()
        out_df["ml_confidence"] = 0.0
        if not self.is_trained or not XGBOOST_AVAILABLE:
            return out_df

        fdf = generate_technical_features_v2(out_df, bars_per_day=self.bars_per_day)
        idx = fdf.dropna(subset=self.active_features).index
        if len(idx) == 0:
            return out_df

        pred = self.model.predict(fdf.loc[idx, self.active_features].values)
        out_df.loc[idx, "ml_confidence"] = np.round(pred.astype(float), 4)
        return out_df
