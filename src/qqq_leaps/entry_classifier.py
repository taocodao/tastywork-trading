"""
QQQ LEAPS — Layer B: Entry Classifier
========================================
XGBoost binary classifier that replaces the static "RSI < 30 + gap-down" rule
with a probabilistic ML gate.

Target: "Did QQQ close >= target_gain% above entry within forward_days trading days?"
Architecture: Primary XGBoost (high recall) + Meta XGBoost (precision filter),
              mirroring the proven TurboCore Pro meta-labeling approach.

Walk-forward training is managed externally by the backtest engine.
This module handles: fit(), predict_confidence(), save/load.
"""
import os
import logging
import numpy as np
import pandas as pd
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.preprocessing import StandardScaler
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("xgboost/sklearn not installed — entry classifier will use rule-based fallback.")

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False

ML_DIR = Path(__file__).parent / "ml"
ML_DIR.mkdir(exist_ok=True)

MODEL_FILE = ML_DIR / "qqq_leaps_entry_xgb.joblib"


# ─── Feature sets ────────────────────────────────────────────────────────────
# Primary: fast technical features only (no macro lag)
PRIMARY_FEATURES = [
    "rsi_2",
    "rsi_5",
    "rsi_14",
    "pct_b",                # Bollinger %B
    "vix_pct_rank",         # VIX percentile
    "vix_rel_50",           # VIX relative to 50-DMA
    "vix_term_slope",       # Contango/backwardation
    "ret_3d",               # 3-day return
    "ret_5d",               # 5-day return
    "dist_sma100",          # Distance from 100-SMA
    "hmm_p_bull",           # TurboCore HMM bull probability
    "is_gap_down",          # Binary gap-down flag
]

# Meta: all features + primary model output
META_FEATURES = PRIMARY_FEATURES + [
    "rsi_30",
    "ret_21d",
    "ath_drawdown",         # Drawdown from all-time high
    "bb_width_pct",         # Bollinger Band width
    "vix_5d_change",        # VIX acceleration
    "put_call_proxy",       # Fear sentiment proxy
    "dist_sma200",          # Distance from 200-SMA
    "iv_rank",              # Historical volatility rank
    "is_gap_down2",         # Strong gap-down (>= 2%)
    "hv_20",                # 20-day HV
    "primary_prob",         # Primary model output (meta-labeling key feature)
]

PRIMARY_THRESHOLD = 0.30   # Low threshold to maximize recall
META_THRESHOLD    = 0.55   # Meta confidence > 0.55 = positive signal


class LeapsEntryClassifier:
    """
    Layer B: ML-driven entry confidence scorer for QQQ LEAPS.

    Usage in backtest:
        clf = LeapsEntryClassifier()
        clf.fit(train_df)                    # Walk-forward training slice
        conf = clf.predict_confidence(row)   # 0.0-1.0 per day
        if conf >= config.entry_ml_confidence_min:
            # ENTER POSITION
    """

    def __init__(self):
        self.primary_model: Optional[object] = None
        self.meta_model: Optional[object]    = None
        self.is_trained: bool = False
        self.training_stats: dict = {}

    def fit(self, train_df: pd.DataFrame, target_gain: float = 0.04, forward_days: int = 30):
        """
        Train primary + meta XGBoost models on a historical slice.

        Args:
            train_df:     Master features DataFrame (from build_leaps_features + add_forward_labels)
                          Must contain 'label_bounce' column (1 = bounce, 0 = no bounce).
            target_gain:  Not used here (label already computed externally), kept for logging.
            forward_days: Not used here, kept for logging.
        """
        if not XGBOOST_AVAILABLE:
            logger.warning("XGBoost not available — skipping ML training.")
            return

        if "label_bounce" not in train_df.columns:
            logger.error("'label_bounce' column missing. Call add_forward_labels() first.")
            return

        # Drop rows where we don't have a label (last forward_days rows)
        df = train_df.dropna(subset=["label_bounce"] + PRIMARY_FEATURES)
        if len(df) < 50:
            logger.warning(f"Only {len(df)} labeled rows — too few to train reliably.")
            return

        X_primary = df[PRIMARY_FEATURES].fillna(0).values
        y         = df["label_bounce"].values.astype(int)

        n_pos = int(y.sum())
        n_neg = int((1 - y).sum())
        if n_pos < 5 or n_neg < 5:
            logger.warning(f"Imbalanced labels: {n_pos} pos / {n_neg} neg — skipping training.")
            return

        logger.info(f"Training PRIMARY XGBoost: {len(df)} samples, {n_pos} pos / {n_neg} neg "
                    f"({n_pos/len(y)*100:.1f}% positive).")

        # ── PRIMARY MODEL ─────────────────────────────────────────────────────
        scale_pos = max(1.0, n_neg / n_pos)   # Class weight for imbalance
        base_primary = XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=scale_pos,
            random_state=42,
            eval_metric="logloss",
            verbosity=0,
        )
        n_folds = min(5, max(2, len(df) // 30))
        self.primary_model = CalibratedClassifierCV(
            estimator=base_primary, method="sigmoid", cv=n_folds
        )
        self.primary_model.fit(X_primary, y)

        # Out-of-fold probabilities for meta feature (avoids leakage)
        try:
            oof_proba = cross_val_predict(
                CalibratedClassifierCV(
                    XGBClassifier(
                        n_estimators=300, max_depth=4, learning_rate=0.05,
                        subsample=0.8, scale_pos_weight=scale_pos,
                        random_state=42, eval_metric="logloss", verbosity=0
                    ),
                    method="sigmoid", cv=n_folds
                ),
                X_primary, y, cv=n_folds, method="predict_proba"
            )
            primary_oof = oof_proba[:, 1] if oof_proba.shape[1] > 1 else oof_proba[:, 0]
        except Exception as e:
            logger.warning(f"OOF prediction failed ({e}), using direct predict_proba.")
            proba_mat = self.primary_model.predict_proba(X_primary)
            primary_oof = proba_mat[:, 1] if proba_mat.shape[1] > 1 else proba_mat[:, 0]

        # ── META MODEL ────────────────────────────────────────────────────────
        # Add primary_prob column to the training slice
        df2 = df.copy()
        df2["primary_prob"] = primary_oof

        meta_available = [f for f in META_FEATURES if f in df2.columns]
        meta_df = df2.dropna(subset=meta_available + ["label_bounce"])
        meta_df = meta_df[meta_df["primary_prob"] >= PRIMARY_THRESHOLD]

        if len(meta_df) < 20:
            logger.warning(f"Only {len(meta_df)} meta-training rows — using primary model only.")
            self.is_trained = True
            self._save()
            return

        X_meta = meta_df[meta_available].fillna(0).values
        y_meta = meta_df["label_bounce"].values.astype(int)

        logger.info(f"Training META XGBoost: {len(meta_df)} rows "
                    f"({int(y_meta.sum())} pos / {int((1-y_meta).sum())} neg).")

        base_meta = XGBClassifier(
            n_estimators=200,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=1.0,
            reg_lambda=2.0,
            random_state=42,
            eval_metric="logloss",
            verbosity=0,
        )
        n_meta_folds = min(5, max(2, len(meta_df) // 15))
        self.meta_model = CalibratedClassifierCV(
            estimator=base_meta, method="isotonic", cv=n_meta_folds
        )
        self.meta_model.fit(X_meta, y_meta)
        self.active_meta_features = meta_available

        self.training_stats = {
            "n_primary": len(df),
            "n_meta": len(meta_df),
            "pos_rate": round(n_pos / len(y), 3),
        }
        self.is_trained = True
        self._save()
        logger.info(f"Entry classifier trained and saved. Stats: {self.training_stats}")

    def predict_confidence(self, row: pd.Series) -> float:
        """
        Returns ML entry confidence for a single day (0.0–1.0).
        Falls back to a heuristic score if models not trained.
        """
        if not self.is_trained or not XGBOOST_AVAILABLE:
            return self._heuristic_confidence(row)

        # Primary model
        try:
            x_primary = np.array([[row.get(f, 0.0) for f in PRIMARY_FEATURES]])
            primary_proba = self.primary_model.predict_proba(x_primary)
            primary_conf  = float(primary_proba[0, 1] if primary_proba.shape[1] > 1 else primary_proba[0, 0])
        except Exception:
            return self._heuristic_confidence(row)

        if primary_conf < PRIMARY_THRESHOLD:
            return primary_conf  # Below even primary threshold — return raw low prob

        # Meta model (if available)
        if self.meta_model is not None:
            try:
                meta_feats = getattr(self, "active_meta_features", META_FEATURES)
                row2 = row.copy()
                row2["primary_prob"] = primary_conf
                x_meta = np.array([[row2.get(f, 0.0) for f in meta_feats]])
                meta_proba = self.meta_model.predict_proba(x_meta)
                meta_conf  = float(meta_proba[0, 1] if meta_proba.shape[1] > 1 else meta_proba[0, 0])
                return round(meta_conf, 4)
            except Exception:
                pass

        return round(primary_conf, 4)

    def _heuristic_confidence(self, row: pd.Series) -> float:
        """
        Rule-based fallback when ML not trained.
        Approximates the XGBoost output using the same features we'd use to train.
        """
        score = 0.40  # Base

        rsi_2  = float(row.get("rsi_2", 50))
        pct_b  = float(row.get("pct_b", 0.5))
        vix_pct= float(row.get("vix_pct_rank", 0.5))
        ret_3d = float(row.get("ret_3d", 0))
        hmm_pb = float(row.get("hmm_p_bull", 0.5))
        above_100 = bool(row.get("above_sma100", True))

        # RSI-2 extremity
        if rsi_2 < 5:   score += 0.20
        elif rsi_2 < 10: score += 0.15
        elif rsi_2 < 20: score += 0.10
        elif rsi_2 < 30: score += 0.05

        # Bollinger %B below lower band
        if pct_b < 0:  score += 0.10
        elif pct_b < 0.2: score += 0.05

        # VIX fear (high VIX = near capitulation = better bounce odds)
        if vix_pct > 0.85: score += 0.08
        elif vix_pct > 0.70: score += 0.04

        # Recent sharp decline
        if ret_3d < -0.07: score += 0.08
        elif ret_3d < -0.04: score += 0.04

        # HMM regime
        score += (hmm_pb - 0.5) * 0.10   # +5% at 100% bull, -5% at 0% bull

        # SMA gate
        if not above_100: score -= 0.20

        return round(min(max(score, 0.0), 1.0), 4)

    def _save(self):
        if JOBLIB_AVAILABLE and self.is_trained:
            try:
                joblib.dump({
                    "primary": self.primary_model,
                    "meta":    self.meta_model,
                    "features": getattr(self, "active_meta_features", META_FEATURES),
                    "stats":   self.training_stats,
                }, MODEL_FILE)
            except Exception as e:
                logger.warning(f"Could not save entry classifier: {e}")

    def load(self) -> bool:
        """Load saved model from disk. Returns True if successful."""
        if not (JOBLIB_AVAILABLE and MODEL_FILE.exists()):
            return False
        try:
            data = joblib.load(MODEL_FILE)
            self.primary_model = data.get("primary")
            self.meta_model    = data.get("meta")
            self.active_meta_features = data.get("features", META_FEATURES)
            self.training_stats = data.get("stats", {})
            self.is_trained = self.primary_model is not None
            return self.is_trained
        except Exception as e:
            logger.warning(f"Could not load entry classifier: {e}")
            return False
