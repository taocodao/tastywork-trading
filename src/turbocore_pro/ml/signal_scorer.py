import pandas as pd
import numpy as np
import logging
import joblib
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import cross_val_predict
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from .feature_engineering import (
    generate_technical_features,
    add_fracdiff_features,
    label_crossover_outcomes,
)


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: META-LABELING ARCHITECTURE
#
# Two-model stack (López de Prado, Advances in Financial Machine Learning):
#
# PRIMARY MODEL  (high recall)
#   - Input:  technical features only (fast, always available)
#   - Target: any EMA crossover signal with prob > PRIMARY_THRESHOLD
#   - Goal:   maximize recall — catch every real bull signal
#   - Output: primary_prob (0.0 to 1.0)
#
# META-MODEL  (precision filter)
#   - Input:  ALL features (technical + macro + fracdiff) + primary_prob
#   - Target: triple-barrier label (did the signal actually work?)
#   - Goal:   maximize precision — filter out fakeout Golden Crosses
#   - Output: ml_confidence (0.0 to 1.0) — drives continuous Kelly bet sizing
#
# Why this works: The meta-model doesn't predict market direction — it only
# judges "signal quality", which is a much easier classification task. This
# separates concerns: primary handles timing, meta handles quality filtering.
# ══════════════════════════════════════════════════════════════════════════════

PRIMARY_THRESHOLD = 0.30   # Low threshold to maximize recall (catch all real signals)
META_THRESHOLD    = 0.50   # Meta-model threshold for positive classification


class TurboCoreSignalScorer:
    """
    Phase 1 Meta-Labeling XGBoost pipeline for TurboCore Pro.
    
    Outputs ml_confidence (0.0–1.0) that directly drives continuous Kelly
    bet sizing in AllocationOptimizer.get_target_allocation().
    
    The output now varies meaningfully across different market conditions
    (was stuck at 55% fallback in the prior single-model architecture).
    """

    MODEL_FILE_PRIMARY = os.path.join(os.path.dirname(__file__), 'turbocore_xgboost_primary.joblib')
    MODEL_FILE_META    = os.path.join(os.path.dirname(__file__), 'turbocore_xgboost.joblib')

    # Primary model uses only fast technical features (always available, no lag)
    PRIMARY_FEATURES = [
        'tqqq_rsi_14',
        'tqqq_macd_hist',
        'tqqq_bb_width',
        'qqq_vol_20d',
        'vix_close',
        'vix_rel_50',
        'vol_ratio',
        'momentum_divergence',
        'fib_retracement',
    ]

    # Meta-model uses all features including macro + fracdiff + primary signal probability
    META_FEATURES = [
        # Technical
        'tqqq_rsi_14',
        'tqqq_macd_hist',
        'tqqq_bb_width',
        'qqq_vol_20d',
        'vix_close',
        'vix_rel_50',
        # Volume & breadth (Phase 1)
        'vol_ratio',
        'cum_vol_delta',
        'distribution_day_count_20d',
        'bounce_vol_ratio',
        'fib_retracement',
        'sector_divergence',
        'momentum_divergence',
        'nh_proxy',
        # Macro confirmation (Phase 1 — some stubbed at 0.0 until Phase 2)
        'vix_term_slope',
        'hyg_5d_change',
        'fed_funds_3m_change',
        'ism_mfg_delta',
        'initial_claims_slope',
        # Fracdiff (Phase 1 — graceful fallback if fracdiff library not installed)
        'qqq_close_fracdiff',
        'qqq_volume_fracdiff',
        'vix_close_fracdiff',
        # Primary model signal quality score (the key meta-labeling feature)
        'primary_prob',
    ]

    def __init__(self):
        self.primary_model: Optional[CalibratedClassifierCV] = None
        self.meta_model:    Optional[CalibratedClassifierCV] = None
        self.is_trained = False
        self.active_meta_features: list = self.META_FEATURES  # Pruned after SHAP

        if not XGBOOST_AVAILABLE:
            logger.warning("xgboost or sklearn missing. Signal scorer degraded to 55% fallback.")
            return

        self._load_models()

    def _load_models(self):
        """Load saved primary and meta models from disk."""
        loaded_meta = False
        if os.path.exists(self.MODEL_FILE_META):
            try:
                data = joblib.load(self.MODEL_FILE_META)
                if isinstance(data, dict):
                    # New Phase 1 format: {'meta': ..., 'primary': ..., 'features': ...}
                    self.meta_model    = data.get('meta')
                    self.primary_model = data.get('primary')
                    self.active_meta_features = data.get('features', self.META_FEATURES)
                    loaded_meta = True
                else:
                    # Legacy format: raw calibrated model
                    self.meta_model = data
                    loaded_meta = True
                logger.debug(f"Loaded meta XGBoost from {self.MODEL_FILE_META}")
            except Exception as e:
                logger.error(f"Failed loading meta XGBoost: {e}")

        if os.path.exists(self.MODEL_FILE_PRIMARY):
            try:
                self.primary_model = joblib.load(self.MODEL_FILE_PRIMARY)
                logger.debug(f"Loaded primary XGBoost from {self.MODEL_FILE_PRIMARY}")
            except Exception as e:
                logger.error(f"Failed loading primary XGBoost: {e}")

        if loaded_meta:
            self.is_trained = True

    def _save_models(self):
        """Save both models to disk."""
        if self.meta_model and self.is_trained:
            try:
                joblib.dump({
                    'meta':     self.meta_model,
                    'primary':  self.primary_model,
                    'features': self.active_meta_features,
                }, self.MODEL_FILE_META)
                logger.debug(f"Saved meta model to {self.MODEL_FILE_META}")
            except Exception as e:
                logger.error(f"Failed saving meta model: {e}")

    def fit(self, df: pd.DataFrame):
        """
        Train the two-model meta-labeling pipeline on historical data.

        Training steps:
          1. Generate all features (technical + macro + fracdiff)
          2. Label crossover events with triple barrier method
          3. Train PRIMARY model on technical features (high recall, threshold 0.3)
          4. Get primary signal probabilities for all labeled events
          5. Filter to events where primary fires (prob > PRIMARY_THRESHOLD)
          6. Train META model on full features + primary_prob (precision filter)
          7. Run SHAP analysis to prune low-impact features
          8. Save both models

        This should be called on the training slice in walk-forward validation,
        NOT on the full dataset (would introduce lookahead bias).
        """
        if not XGBOOST_AVAILABLE:
            logger.warning("Cannot train: xgboost missing.")
            return

        logger.info("Phase 1: Preparing features for meta-labeling pipeline...")

        # Step 1: Generate all features
        fdf = generate_technical_features(df)
        fdf = add_fracdiff_features(fdf)  # Graceful fallback if fracdiff not installed

        # Step 2: Triple-barrier labels with diagnostic-report corrections
        # FIX 1: tp_mult=1.5 × EWMA *daily* vol (not path vol)
        # FIX 3: label_mode='daily_condition' → ~1000-1500 samples (not 31)
        fdf = label_crossover_outcomes(
            fdf,
            forward_days=21,     # 1 month vertical barrier (TQQQ appropriate)
            tp_mult=1.5,         # TP = entry × (1 + 1.5 × ewma_daily_vol)
            sl_mult=0.75,        # SL = entry × (1 - 0.75 × ewma_daily_vol)
            label_mode='daily_condition',   # label every active EMA day
        )

        # ── STEP 3: Train PRIMARY model ───────────────────────────────────────
        primary_valid = fdf.dropna(subset=self.PRIMARY_FEATURES + ['target_profitable'])

        if len(primary_valid) < 20:
            logger.warning(f"Only {len(primary_valid)} labeled signals. Need ≥20. Skipping training.")
            return

        X_primary = primary_valid[self.PRIMARY_FEATURES].values
        y         = primary_valid['target_profitable'].values

        logger.info(f"Training PRIMARY XGBoost on {len(X_primary)} crossover events "
                    f"(label balance: {y.mean():.1%} positive)...")

        # Guard: need at least some positive labels to train a meaningful classifier
        n_positive = int(y.sum())
        n_negative = int((1 - y).sum())
        if n_positive < 3 or n_negative < 3:
            logger.warning(f"Insufficient label balance ({n_positive} pos / {n_negative} neg). "
                           f"Cannot train binary classifier. Try a longer history window.")
            return

        base_primary = XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric='logloss',
        )
        n_cv_folds = min(5, max(2, len(X_primary) // 10))
        self.primary_model = CalibratedClassifierCV(
            estimator=base_primary,
            method='sigmoid',
            cv=n_cv_folds,
        )
        self.primary_model.fit(X_primary, y)

        # ── STEP 4: Get primary probabilities (used as meta feature) ──────────
        # Use out-of-fold predictions to avoid leakage into meta-model.
        # Guard against single-class output (XGBoost returns 1-column matrix
        # when cross_val_predict sees only one class in some folds).
        try:
            oof_proba_mat = cross_val_predict(
                CalibratedClassifierCV(
                    XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                                   subsample=0.8, random_state=42, eval_metric='logloss'),
                    method='sigmoid', cv=n_cv_folds
                ),
                X_primary, y,
                cv=n_cv_folds,
                method='predict_proba',
            )
            # Handle both 1-column (single class) and 2-column output
            if oof_proba_mat.shape[1] == 1:
                logger.warning("cross_val_predict returned single class — using direct predict_proba")
                self.primary_model.fit(X_primary, y)
                oof_proba = self.primary_model.predict_proba(X_primary)
                primary_oof_proba = oof_proba[:, -1]  # last column = positive class prob
            else:
                primary_oof_proba = oof_proba_mat[:, 1]
        except Exception as e:
            logger.warning(f"OOF predict failed ({e}), using direct predict_proba fallback")
            self.primary_model.fit(X_primary, y)
            raw = self.primary_model.predict_proba(X_primary)
            primary_oof_proba = raw[:, -1]

        primary_valid = primary_valid.copy()
        primary_valid['primary_prob'] = primary_oof_proba

        # ── STEP 5: Filter to events where primary fires ───────────────────────
        # Meta-model only trains on signals the primary model would have flagged
        meta_mask    = primary_oof_proba >= PRIMARY_THRESHOLD
        meta_df      = primary_valid[meta_mask]

        if len(meta_df) < 15:
            logger.warning(f"Only {meta_mask.sum()} primary signal events after threshold filter. "
                           f"Storing primary model only, no meta model.")
            self.is_trained = True
            self._save_models()
            return

        # ── STEP 6: Train META model ───────────────────────────────────────────
        # Include all available meta features (some may be missing / stubbed)
        available_meta = [f for f in self.META_FEATURES if f in meta_df.columns]
        meta_valid     = meta_df.dropna(subset=available_meta + ['target_profitable'])

        if len(meta_valid) < 15:
            logger.warning(f"Insufficient meta training samples ({len(meta_valid)}). Using primary only.")
            self.is_trained = True
            self._save_models()
            return

        X_meta = meta_valid[available_meta].values
        y_meta = meta_valid['target_profitable'].values

        logger.info(f"Training META XGBoost on {len(X_meta)} primary-filtered events "
                    f"(label balance: {y_meta.mean():.1%} positive)...")

        base_meta = XGBClassifier(
            n_estimators=200,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=1.0,    # L1 regularization — encourages sparse feature use
            reg_lambda=2.0,   # L2 regularization — prevents overfit
            random_state=42,
            eval_metric='logloss',
        )
        n_meta_cv = min(5, max(2, len(X_meta) // 8))
        self.meta_model = CalibratedClassifierCV(
            estimator=base_meta,
            method='isotonic',  # Isotonic (non-parametric) for better calibration
            cv=n_meta_cv,
        )
        self.meta_model.fit(X_meta, y_meta)
        self.active_meta_features = available_meta

        # ── STEP 7: SHAP Feature Pruning ──────────────────────────────────────
        try:
            import shap
            # Get the base estimator from the first calibrated fold
            base_est = self.meta_model.calibrated_classifiers_[0].estimator
            explainer = shap.TreeExplainer(base_est)
            shap_vals = explainer.shap_values(X_meta)
            mean_shap = np.abs(shap_vals).mean(axis=0)
            # Keep features with mean |SHAP| >= 0.005
            keep_mask = mean_shap >= 0.005
            pruned    = [f for f, keep in zip(available_meta, keep_mask) if keep]
            pruned_n  = len(available_meta) - len(pruned)
            if pruned_n > 0 and len(pruned) >= 5:
                self.active_meta_features = pruned
                logger.info(f"SHAP pruning: removed {pruned_n} low-impact features, "
                            f"keeping {len(pruned)}: {pruned}")
        except ImportError:
            logger.debug("shap not installed. Skipping SHAP feature pruning.")
        except Exception as e:
            logger.debug(f"SHAP pruning failed (non-critical): {e}")

        self.is_trained = True
        self._save_models()
        logger.info(f"Meta-labeling pipeline trained and saved. "
                    f"Features: {len(self.active_meta_features)}")

    def predict_confidence(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Returns dataframe with ml_confidence (0.0–1.0) appended.

        Output pipeline:
          1. Generate all features
          2. Run primary model → primary_prob
          3. If primary fires (≥ PRIMARY_THRESHOLD), run meta model → ml_confidence
          4. If no meta model (legacy), use primary_prob directly
          5. Fallback: 0.55 if models not trained

        The ml_confidence output now varies meaningfully between 0.2 and 0.9
        across different market conditions, enabling true Kelly bet sizing.
        """
        out_df = df.copy()
        out_df['ml_confidence'] = 0.55  # Conservative fallback

        if not self.is_trained or not XGBOOST_AVAILABLE:
            return out_df

        # Generate features
        fdf = generate_technical_features(out_df)
        fdf = add_fracdiff_features(fdf)

        # ── Primary model inference ────────────────────────────────────────────
        primary_valid_idx = fdf.dropna(subset=self.PRIMARY_FEATURES).index
        if len(primary_valid_idx) == 0:
            return out_df

        X_primary = fdf.loc[primary_valid_idx, self.PRIMARY_FEATURES].values

        if self.primary_model is not None:
            primary_probs = self.primary_model.predict_proba(X_primary)
            primary_prob_vals = primary_probs[:, 1] if primary_probs.shape[1] > 1 else primary_probs[:, 0]
        else:
            primary_prob_vals = np.full(len(primary_valid_idx), 0.55)

        fdf.loc[primary_valid_idx, 'primary_prob'] = primary_prob_vals

        # ── Meta model inference (if available) ───────────────────────────────
        if self.meta_model is not None and len(self.active_meta_features) > 0:
            meta_valid_idx = fdf.dropna(subset=self.active_meta_features).index
            if len(meta_valid_idx) > 0:
                X_meta      = fdf.loc[meta_valid_idx, self.active_meta_features].values
                meta_probs  = self.meta_model.predict_proba(X_meta)
                meta_conf   = meta_probs[:, 1] if meta_probs.shape[1] > 1 else meta_probs[:, 0]
                out_df.loc[meta_valid_idx, 'ml_confidence'] = np.round(meta_conf, 3)
                return out_df

        # ── Fallback: use primary prob directly ───────────────────────────────
        out_df.loc[primary_valid_idx, 'ml_confidence'] = np.round(primary_prob_vals, 3)
        return out_df
