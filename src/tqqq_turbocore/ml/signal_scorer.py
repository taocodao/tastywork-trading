import pandas as pd
import numpy as np
import logging
import joblib
import os
from typing import Optional, Dict, Tuple

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from .feature_engineering import (
    SCORER_FEATURES,
    generate_technical_features,
    label_crossover_outcomes_triple_barrier,
)

logger = logging.getLogger(__name__)

# ── Triple-Barrier parameters ─────────────────────────────────────────────────
UPPER_BARRIER_PCT = 0.06   # +6% TQQQ close-to-close → WIN label
LOWER_BARRIER_PCT = 0.04   # -4% TQQQ close-to-close → LOSS label
FORWARD_DAYS = 20          # Vertical barrier (trading days)

# ── Purged K-Fold embargo (must be >= forward label horizon) ─────────────────
EMBARGO_DAYS = 22          # Was 5 — fixed to match 20-day forward horizon + buffer

# ── Confidence thresholds (can be recalibrated annually) ─────────────────────
DEFAULT_HIGH_CONF = 0.737
DEFAULT_MED_CONF = 0.513


class TurboCoreSignalScorer:
    """
    XGBoost classifier — Layer 3 of TurboCore — v2.

    Upgrades vs v1:
      1. Full ternary Triple-Barrier labels (Lopez de Prado 2018):
            class 0 = LOSS (lower barrier hit first)
            class 1 = NEUTRAL (vertical barrier / time expired)
            class 2 = WIN  (upper barrier hit first)
         p_win (class 2 probability) replaces the old binary ml_confidence.
      2. Expanded from 6 to 11 features (cross-asset: VIX term slope, HYG,
         sector rotation, VXN/VIX PCR proxy, IV-RV spread).
      3. Embargo fixed from 5 days → 22 days to match forward label horizon,
         eliminating look-ahead contamination in walk-forward CV.
      4. predict_confidence() returns (p_win, p_loss, p_expire) tuple columns,
         allowing the AllocationOptimizer to apply a p_loss veto gate.
      5. Annual threshold recalibration helper: recalibrate_thresholds().
    """

    MODEL_FILE = os.path.join(os.path.dirname(__file__), 'turbocore_xgboost.joblib')

    FEATURES = SCORER_FEATURES  # 11 features from feature_engineering.py

    def __init__(self):
        self.model: Optional[XGBClassifier] = None
        self.is_trained = False
        self.high_conf_thresh = DEFAULT_HIGH_CONF
        self.med_conf_thresh = DEFAULT_MED_CONF

        if not XGBOOST_AVAILABLE:
            logger.warning("xgboost missing. Signal scorer degraded.")
            return

        self._load_model()

    # ──────────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────────

    def _load_model(self):
        if not os.path.exists(self.MODEL_FILE):
            return
        try:
            data = joblib.load(self.MODEL_FILE)
            # v2 saves a dict; v1 saved the model directly
            if isinstance(data, dict):
                self.model = data['model']
                self.high_conf_thresh = data.get('high_conf_thresh', DEFAULT_HIGH_CONF)
                self.med_conf_thresh = data.get('med_conf_thresh', DEFAULT_MED_CONF)
            else:
                # Legacy v1 model — incompatible with ternary, force rebuild
                logger.warning(
                    "Detected legacy v1 XGBoost model (binary). "
                    "Will rebuild on next fit() call."
                )
                return
            self.is_trained = True
            logger.info(
                f"Loaded XGBoost v2 scorer from {self.MODEL_FILE} "
                f"(thresholds: high={self.high_conf_thresh}, med={self.med_conf_thresh})"
            )
        except Exception as e:
            logger.error(f"Failed loading XGBoost model (will rebuild): {e}")

    def _save_model(self):
        if not (self.model and self.is_trained):
            return
        try:
            joblib.dump({
                'model': self.model,
                'high_conf_thresh': self.high_conf_thresh,
                'med_conf_thresh': self.med_conf_thresh,
                'feature_names': self.FEATURES,
                'label_map': {0: 'LOSS', 1: 'NEUTRAL', 2: 'WIN'},
            }, self.MODEL_FILE)
        except Exception as e:
            logger.error(f"Failed saving XGBoost model: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Purged K-Fold split (with 22-day embargo)
    # ──────────────────────────────────────────────────────────────────────────

    def _time_aware_splits(self, n_samples: int, n_splits: int = 5) -> list:
        """
        Returns (train_idx, test_idx) tuples with EMBARGO_DAYS gap between
        last training index and first test index.

        Embargo must be >= forward label horizon (FORWARD_DAYS=20) to prevent
        look-ahead contamination from overlapping training labels.
        """
        splits = []
        fold_size = n_samples // (n_splits + 1)
        for i in range(n_splits):
            train_end = (i + 1) * fold_size
            test_start = train_end + EMBARGO_DAYS
            test_end = min(test_start + fold_size, n_samples)
            if test_end > test_start + 5:  # Need at least 5 test samples
                splits.append((
                    list(range(train_end)),
                    list(range(test_start, test_end))
                ))
        return splits

    # ──────────────────────────────────────────────────────────────────────────
    # Training
    # ──────────────────────────────────────────────────────────────────────────

    def fit(self, df: pd.DataFrame):
        if not XGBOOST_AVAILABLE:
            logger.warning("xgboost unavailable — skipping fit()")
            return

        logger.info("TurboCoreSignalScorer v2: preparing training data...")

        # 1. Generate 11-feature technical indicators
        fdf = generate_technical_features(df)
        fdf = fdf.dropna(subset=[f for f in self.FEATURES if f in fdf.columns])

        # 2. Triple-Barrier labeling (replaces max-excursion binary)
        fdf = label_crossover_outcomes_triple_barrier(
            fdf,
            forward_days=FORWARD_DAYS,
            upper_pct=UPPER_BARRIER_PCT,
            lower_pct=LOWER_BARRIER_PCT,
        )

        labeled_df = fdf.dropna(subset=['target_label'])

        if len(labeled_df) < 30:
            logger.warning(
                f"Only {len(labeled_df)} labeled signals found "
                f"(need ≥30). Skipping XGBoost fit."
            )
            return

        # Build feature matrix — only include features actually available
        available_features = [f for f in self.FEATURES if f in labeled_df.columns]
        X = labeled_df[available_features].values
        y_raw = labeled_df['target_label'].values.astype(int)

        unique_classes = np.unique(y_raw)
        label_dist = {int(v): int(c) for v, c in zip(*np.unique(y_raw, return_counts=True))}
        logger.info(
            f"Training XGBoost v2 (ternary) on {len(X)} crossover events | "
            f"features={len(available_features)} | "
            f"label distribution: {label_dist} "
            f"(0=LOSS, 1=NEUTRAL, 2=WIN) | unique classes: {unique_classes.tolist()}"
        )

        # 3. Sparse-class guard: XGBoost multi:softprob requires labels 0..num_class-1.
        # When not all 3 labels appear (e.g., warmup window has no NEUTRAL crossovers),
        # remap available class set to dense integers.
        if len(unique_classes) < 2:
            logger.warning(
                f"Only {len(unique_classes)} unique class(es) in training data — "
                f"need at least 2. Skipping XGBoost fit."
            )
            return

        if not np.array_equal(unique_classes, np.array([0, 1, 2])):
            # Remap to dense: e.g., [0, 2] → [0, 1]
            class_to_idx = {cls: idx for idx, cls in enumerate(unique_classes)}
            y = np.array([class_to_idx[v] for v in y_raw])
            actual_num_classes = len(unique_classes)
            logger.info(
                f"Sparse label remap: {dict(zip(unique_classes, range(len(unique_classes))))} "
                f"(num_class={actual_num_classes})"
            )
            # Store mapping for reverse lookup in predict_confidence
            self._class_idx_to_original = {
                idx: cls for idx, cls in enumerate(unique_classes)
            }
        else:
            y = y_raw
            actual_num_classes = 3
            self._class_idx_to_original = {0: 0, 1: 1, 2: 2}

        # 4. Ternary multi-class XGBoost (or binary if sparse)
        objective = 'multi:softprob' if actual_num_classes > 2 else 'binary:logistic'
        self.model = XGBClassifier(
            objective=objective,
            num_class=actual_num_classes if actual_num_classes > 2 else None,
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            gamma=0.1,
            random_state=42,
            eval_metric='mlogloss' if actual_num_classes > 2 else 'logloss',
            verbosity=0,
        )

        # 5. Time-aware walk-forward fit with 22-day embargo
        splits = self._time_aware_splits(len(X), n_splits=min(5, len(X) // 30))

        if splits:
            # Use last split for eval
            train_idx, test_idx = splits[-1]
            X_train, y_train = X[train_idx], y[train_idx]
            X_test, y_test = X[test_idx], y[test_idx]
            self.model.fit(
                X_train, y_train,
                eval_set=[(X_test, y_test)],
                verbose=False,
            )
        else:
            # Not enough data for split validation — fit on all
            self.model.fit(X, y)

        self.is_trained = True
        self._save_model()
        logger.info("XGBoost v2 ternary scorer trained and saved.")

    # ──────────────────────────────────────────────────────────────────────────
    # Inference
    # ──────────────────────────────────────────────────────────────────────────

    def predict_confidence(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Appends three probability columns to the dataframe:
          ml_confidence : P(WIN)    — primary confidence metric (was the only output in v1)
          p_loss        : P(LOSS)   — veto gate for AllocationOptimizer
          p_expire      : P(NEUTRAL) — signal ambiguity indicator

        Columns default to: ml_confidence=0.5, p_loss=0.0, p_expire=0.5

        Handles sparse class remapping: when model was trained with only 2 classes
        (e.g., LOSS=0 + WIN=2 → remapped to 0/1), uses _class_idx_to_original to
        map probabilities back to their semantic meaning.
        """
        out_df = generate_technical_features(df.copy())
        out_df['ml_confidence'] = 0.50   # Default: uncertain
        out_df['p_loss'] = 0.00          # Default: no loss signal
        out_df['p_expire'] = 0.50        # Default: neutral

        if not self.is_trained or not XGBOOST_AVAILABLE or self.model is None:
            return out_df

        available_features = [f for f in self.FEATURES if f in out_df.columns]
        valid_idx = out_df.dropna(subset=available_features).index

        if len(valid_idx) == 0:
            return out_df

        try:
            X = out_df.loc[valid_idx, available_features].values
            probs = self.model.predict_proba(X)  # shape (n_samples, num_classes)

            # Get class mapping (handles sparse label case)
            mapping = getattr(self, '_class_idx_to_original', {0: 0, 1: 1, 2: 2})

            # Initialize result arrays
            n = len(valid_idx)
            p_win = np.zeros(n)
            p_loss = np.zeros(n)
            p_expire = np.full(n, 0.5)

            for model_idx, original_class in mapping.items():
                if model_idx >= probs.shape[1]:
                    continue
                col_probs = probs[:, model_idx]
                if original_class == 2:    # WIN
                    p_win = col_probs
                elif original_class == 0:  # LOSS
                    p_loss = col_probs
                elif original_class == 1:  # NEUTRAL
                    p_expire = col_probs

            # When binary model (no NEUTRAL class), expire = 1 - win - loss
            if 1 not in mapping.values():
                p_expire = np.clip(1.0 - p_win - p_loss, 0, 1)

            out_df.loc[valid_idx, 'ml_confidence'] = np.round(p_win, 3)
            out_df.loc[valid_idx, 'p_loss'] = np.round(p_loss, 3)
            out_df.loc[valid_idx, 'p_expire'] = np.round(p_expire, 3)

        except Exception as e:
            logger.error(f"XGBoost prediction failed: {e}")

        return out_df

    # ──────────────────────────────────────────────────────────────────────────
    # Annual threshold recalibration
    # ──────────────────────────────────────────────────────────────────────────

    def recalibrate_thresholds(
        self,
        df_live: pd.DataFrame,
        min_precision: float = 0.65,
    ) -> Tuple[float, float]:
        """
        Recalibrates confidence thresholds from the most recent 12 months of
        walk-forward predictions.

        Process:
          1. Run predict_confidence() on live data to get ml_confidence (p_win)
          2. Build precision-recall curve against actual outcomes (triple-barrier labels)
          3. Select HIGH threshold at max F1 with minimum 65% precision
          4. Select MED threshold at 50% precision floor (broader entry)

        Returns (new_high_thresh, new_med_thresh) and updates self.high_conf_thresh.
        Does NOT save model — call _save_model() after if accepting values.
        """
        try:
            from sklearn.metrics import precision_recall_curve

            fdf = label_crossover_outcomes_triple_barrier(
                df_live, forward_days=FORWARD_DAYS,
                upper_pct=UPPER_BARRIER_PCT, lower_pct=LOWER_BARRIER_PCT
            )
            labeled = fdf.dropna(subset=['target_label'])
            if len(labeled) < 20:
                logger.warning("Insufficient data for threshold recalibration")
                return self.high_conf_thresh, self.med_conf_thresh

            scored = self.predict_confidence(labeled)
            y_true = (labeled['target_label'] == 2).astype(int)  # 1 = WIN
            y_prob = scored.loc[labeled.index, 'ml_confidence']

            precision, recall, thresholds = precision_recall_curve(y_true, y_prob)

            # High threshold: best F1 at min_precision floor
            f1 = 2 * precision * recall / (precision + recall + 1e-9)
            valid_mask = precision >= min_precision
            if valid_mask.any():
                best_idx = np.argmax(f1[valid_mask])
                new_high = float(thresholds[valid_mask[:-1]][best_idx])
            else:
                new_high = self.high_conf_thresh

            # Med threshold: 50% precision floor
            med_mask = precision >= 0.50
            if med_mask.any():
                best_med_idx = np.argmax(f1[med_mask])
                new_med = float(thresholds[med_mask[:-1]][best_med_idx])
            else:
                new_med = self.med_conf_thresh

            # Ensure high > med
            new_high = max(new_high, new_med + 0.05)

            logger.info(
                f"Threshold recalibration: high {self.high_conf_thresh:.3f}→{new_high:.3f}, "
                f"med {self.med_conf_thresh:.3f}→{new_med:.3f}"
            )

            self.high_conf_thresh = round(new_high, 3)
            self.med_conf_thresh = round(new_med, 3)
            return self.high_conf_thresh, self.med_conf_thresh

        except Exception as e:
            logger.error(f"Recalibration failed: {e}")
            return self.high_conf_thresh, self.med_conf_thresh


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))
    from src.tqqq_turbocore.data_pipeline import TurboCoreDataPipeline
    import logging
    logging.basicConfig(level=logging.INFO)

    pipeline = TurboCoreDataPipeline()
    pipeline.fetch_data("5y")
    df = pipeline.prepare_core_features()

    scorer = TurboCoreSignalScorer()
    scorer.fit(df)
    scored = scorer.predict_confidence(df)

    crosses = scored[
        (scored['tqqq_bull_cross'] == True) &
        (scored['tqqq_bull_cross'].shift(1) == False)
    ]
    print(f"\nScored {len(crosses)} crossovers:")
    print(crosses[['tqqq_close', 'ml_confidence', 'p_loss', 'p_expire']].tail(10))
