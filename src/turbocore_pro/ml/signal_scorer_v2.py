"""
TurboCore Pro v2 -- Bar-Cadence-Aware Meta-Labeling Signal Scorer.

Same two-model (primary recall / meta precision) XGBoost architecture as
signal_scorer.py, with three changes:
  1. Uses feature_engineering_v2.generate_technical_features_v2 (bar-scaled
     windows) instead of the daily-only feature_engineering module.
  2. Uses labeling_v2.label_crossover_outcomes_v2 (bar-scaled forward
     window and EWMA vol span) instead of the daily-only labeler.
  3. META_FEATURES drops the permanently-stubbed ism_mfg_delta /
     initial_claims_slope (hardcoded 0.0, zero signal at any cadence) and
     adds the new hourly-native breadth features (vix_intraday_momentum_6b,
     hyg_intraday_momentum_6b, hyg_mom_20b, qqq_intraday_vol_6b,
     volume_zscore_20d).
  4. Already uses Platt/sigmoid calibration (method='sigmoid'), matching
     the fix applied to the v1 signal_scorer.py in this rebuild.

Persists to its own model files (turbocore_xgboost_v2*.joblib) so it never
collides with the legacy v1 daily models.
"""
import os
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import cross_val_predict
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from .feature_engineering_v2 import generate_technical_features_v2
from .labeling_v2 import label_crossover_outcomes_v2

PRIMARY_THRESHOLD = 0.30
META_THRESHOLD = 0.50


class TurboCoreSignalScorerV2:
    MODEL_FILE_META = os.path.join(os.path.dirname(__file__), 'turbocore_xgboost_v2.joblib')

    PRIMARY_FEATURES = [
        'tqqq_rsi_14', 'tqqq_macd_hist', 'tqqq_bb_width', 'qqq_vol_20d',
        'vix_close', 'vix_rel_50', 'vol_ratio', 'momentum_divergence', 'fib_retracement',
    ]

    META_FEATURES = [
        'tqqq_rsi_14', 'tqqq_macd_hist', 'tqqq_bb_width', 'qqq_vol_20d',
        'vix_close', 'vix_rel_50',
        'vol_ratio', 'cum_vol_delta', 'distribution_day_count_20d', 'bounce_vol_ratio',
        'fib_retracement', 'sector_divergence', 'momentum_divergence', 'nh_proxy',
        'vix_term_slope', 'hyg_5d_change', 'fed_funds_3m_change',
        # NEW hourly-native breadth features replacing dead ism_mfg_delta /
        # initial_claims_slope stubs:
        'vix_intraday_momentum_6b', 'hyg_intraday_momentum_6b', 'hyg_mom_20b',
        'qqq_intraday_vol_6b', 'volume_zscore_20d',
        'qqq_close_fracdiff', 'qqq_volume_fracdiff', 'vix_close_fracdiff',
        'primary_prob',
    ]

    def __init__(self, bars_per_day: float = 1.0, model_tag: str = 'daily'):
        self.bars_per_day = bars_per_day
        self.model_tag = model_tag
        self.model_file = os.path.join(
            os.path.dirname(__file__), f'turbocore_xgboost_v2_{model_tag}.joblib')
        self.primary_model: Optional[CalibratedClassifierCV] = None
        self.meta_model: Optional[CalibratedClassifierCV] = None
        self.is_trained = False
        self.active_meta_features: list = self.META_FEATURES
        if not XGBOOST_AVAILABLE:
            logger.warning("xgboost/sklearn missing -- signal scorer degraded to 55%% fallback.")

    def load(self):
        if os.path.exists(self.model_file):
            try:
                data = joblib.load(self.model_file)
                self.meta_model = data.get('meta')
                self.primary_model = data.get('primary')
                self.active_meta_features = data.get('features', self.META_FEATURES)
                self.is_trained = True
                logger.debug(f"Loaded v2 signal scorer from {self.model_file}")
            except Exception as e:
                logger.error(f"Failed loading v2 signal scorer: {e}")
        return self

    def save(self):
        if self.meta_model and self.is_trained:
            joblib.dump({'meta': self.meta_model, 'primary': self.primary_model,
                         'features': self.active_meta_features}, self.model_file)
            logger.debug(f"Saved v2 signal scorer to {self.model_file}")

    def _prep_features(self, df: pd.DataFrame) -> pd.DataFrame:
        return generate_technical_features_v2(df, bars_per_day=self.bars_per_day)

    def fit(self, df: pd.DataFrame, forward_days: float = 21,
            tp_mult: float = 1.5, sl_mult: float = 0.75,
            train_end_pos: int = None):
        """
        train_end_pos (Phase 0.2): positional index in `df` marking the end of
        the training window. Triple-barrier labels forward-look `forward_days`
        trading days, so any bar within that horizon of train_end would have
        its outcome decided by price action inside the test window. Those bars
        are excluded as labelled training examples (they remain available as
        feature/rolling-window context). Defaults to len(df), which is correct
        whenever `df` is already exactly the train slice.
        """
        if not XGBOOST_AVAILABLE:
            logger.warning("Cannot train: xgboost missing.")
            return

        fdf = self._prep_features(df)
        boundary = len(fdf) if train_end_pos is None else int(train_end_pos)
        fdf = label_crossover_outcomes_v2(
            fdf, forward_days=forward_days, tp_mult=tp_mult, sl_mult=sl_mult,
            label_mode='daily_condition', bars_per_day=self.bars_per_day,
            label_boundary_pos=boundary,
        )

        primary_valid = fdf.dropna(subset=self.PRIMARY_FEATURES + ['target_profitable'])
        if len(primary_valid) < 20:
            logger.warning(f"Only {len(primary_valid)} labeled signals (<20). Skipping training.")
            return

        X_primary = primary_valid[self.PRIMARY_FEATURES].values
        y = primary_valid['target_profitable'].values
        n_positive, n_negative = int(y.sum()), int((1 - y).sum())
        if n_positive < 3 or n_negative < 3:
            logger.warning(f"Insufficient label balance ({n_positive} pos / {n_negative} neg). Skipping.")
            return

        base_primary = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                                      subsample=0.8, colsample_bytree=0.8, random_state=42,
                                      eval_metric='logloss')
        n_cv = min(5, max(2, len(X_primary) // 10))
        self.primary_model = CalibratedClassifierCV(estimator=base_primary, method='sigmoid', cv=n_cv)
        self.primary_model.fit(X_primary, y)

        try:
            oof = cross_val_predict(
                CalibratedClassifierCV(
                    XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                                  subsample=0.8, random_state=42, eval_metric='logloss'),
                    method='sigmoid', cv=n_cv),
                X_primary, y, cv=n_cv, method='predict_proba')
            primary_oof = oof[:, 1] if oof.shape[1] > 1 else oof[:, 0]
        except Exception as e:
            logger.warning(f"OOF predict failed ({e}), using direct predict_proba")
            raw = self.primary_model.predict_proba(X_primary)
            primary_oof = raw[:, -1]

        primary_valid = primary_valid.copy()
        primary_valid['primary_prob'] = primary_oof

        meta_mask = primary_oof >= PRIMARY_THRESHOLD
        meta_df = primary_valid[meta_mask]
        if len(meta_df) < 15:
            logger.warning(f"Only {meta_mask.sum()} primary events after threshold. Primary-only model.")
            self.is_trained = True
            self.save()
            return

        available_meta = [f for f in self.META_FEATURES if f in meta_df.columns]
        meta_valid = meta_df.dropna(subset=available_meta + ['target_profitable'])
        if len(meta_valid) < 15:
            logger.warning(f"Insufficient meta samples ({len(meta_valid)}). Primary-only model.")
            self.is_trained = True
            self.save()
            return

        X_meta = meta_valid[available_meta].values
        y_meta = meta_valid['target_profitable'].values

        base_meta = XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.05,
                                   subsample=0.8, colsample_bytree=0.7, reg_alpha=1.0,
                                   reg_lambda=2.0, random_state=42, eval_metric='logloss')
        n_meta_cv = min(5, max(2, len(X_meta) // 8))
        self.meta_model = CalibratedClassifierCV(estimator=base_meta, method='sigmoid', cv=n_meta_cv)
        self.meta_model.fit(X_meta, y_meta)
        self.active_meta_features = available_meta

        # NOTE (v2 fix): SHAP pruning is diagnostic-only here. The original
        # v1 signal_scorer.py had a latent bug where pruning shrank
        # active_meta_features (used at INFERENCE time) without retraining
        # the already-fitted booster, causing a train/predict feature-count
        # mismatch ("Feature shape mismatch, expected: 26, got 25") the
        # first time a pruned feature set was used for prediction. Fixed by
        # always keeping active_meta_features == available_meta (the exact
        # columns the booster was fit on); SHAP importances are still
        # logged for visibility but no longer silently break inference.
        try:
            import shap
            base_est = self.meta_model.calibrated_classifiers_[0].estimator
            explainer = shap.TreeExplainer(base_est)
            shap_vals = explainer.shap_values(X_meta)
            mean_shap = np.abs(shap_vals).mean(axis=0)
            low_impact = [f for f, m in zip(available_meta, mean_shap) if m < 0.005]
            if low_impact:
                logger.info(f"[v2] SHAP: {len(low_impact)} low-impact features "
                            f"(kept for train/predict consistency): {low_impact}")
        except Exception as e:
            logger.debug(f"SHAP diagnostic skipped: {e}")

        self.is_trained = True
        self.save()
        logger.info(f"[v2] Trained on {len(X_meta)} meta samples "
                    f"({y_meta.mean():.1%} positive), {len(self.active_meta_features)} features kept.")

    def predict_confidence(self, df: pd.DataFrame) -> pd.DataFrame:
        out_df = df.copy()
        out_df['ml_confidence'] = 0.55
        if not self.is_trained or not XGBOOST_AVAILABLE:
            return out_df

        fdf = self._prep_features(out_df)
        primary_valid_idx = fdf.dropna(subset=self.PRIMARY_FEATURES).index
        if len(primary_valid_idx) == 0:
            return out_df

        X_primary = fdf.loc[primary_valid_idx, self.PRIMARY_FEATURES].values
        if self.primary_model is not None:
            pp = self.primary_model.predict_proba(X_primary)
            primary_prob = pp[:, 1] if pp.shape[1] > 1 else pp[:, 0]
        else:
            primary_prob = np.full(len(primary_valid_idx), 0.55)
        fdf.loc[primary_valid_idx, 'primary_prob'] = primary_prob

        if self.meta_model is not None and len(self.active_meta_features) > 0:
            meta_valid_idx = fdf.dropna(subset=self.active_meta_features).index
            if len(meta_valid_idx) > 0:
                X_meta = fdf.loc[meta_valid_idx, self.active_meta_features].values
                mp = self.meta_model.predict_proba(X_meta)
                meta_conf = mp[:, 1] if mp.shape[1] > 1 else mp[:, 0]
                out_df.loc[meta_valid_idx, 'ml_confidence'] = np.round(meta_conf, 3)
                return out_df

        out_df.loc[primary_valid_idx, 'ml_confidence'] = np.round(primary_prob, 3)
        return out_df
