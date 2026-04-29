"""
OTM Naked Options — Entry Classifier
=======================================
XGBoost 2-stage classifier predicting trade win probability.
Mirrors the proven LeapsEntryClassifier architecture:
  Stage 1 (Primary): High-recall XGBoost
  Stage 2 (Meta):    Precision XGBoost on Stage 1 outputs

Target label: trade_won = 1 (closed at profit), 0 (stopped out)
"""
import logging
import numpy as np
import pandas as pd
from typing import Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    import joblib
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logger.warning("xgboost/sklearn not installed — using rule-based fallback.")

ML_DIR = Path(__file__).parent / "ml"
ML_DIR.mkdir(exist_ok=True)
MODEL_FILE = ML_DIR / "otm_naked_entry_xgb.joblib"

PRIMARY_FEATURES: List[str] = [
    "rsi_2", "rsi_5", "rsi_14",
    "pct_b", "bb_width_pct",
    "pct_from_52w_high", "pct_from_52w_low",
    "dist_sma20", "dist_sma50",
    "vix_pct_rank", "vix_rel_50", "vix_term_slope",
    "ret_3d", "ret_5d",
    "iv_rank", "iv_hv_ratio",
    "stoch_14", "volume_ratio",
    "is_gap_up", "is_gap_down",
]

META_FEATURES: List[str] = PRIMARY_FEATURES + [
    "rsi_30", "ret_10d", "ret_21d",
    "ath_drawdown", "dist_sma200",
    "hv_10", "hv_20", "hv_60",
    "vix_5d_change", "primary_prob",
]

PRIMARY_THRESHOLD = 0.30
META_THRESHOLD    = 0.60


class OTMNakedEntryClassifier:
    """Two-stage XGBoost entry classifier for OTM naked options."""

    def __init__(self):
        self.primary_model = None
        self.meta_model    = None
        self.is_trained    = False
        self.training_stats: dict = {}

    def fit(self, train_df: pd.DataFrame, win_col: str = "trade_won"):
        if not ML_AVAILABLE:
            return
        df = train_df.dropna(subset=[win_col])
        if len(df) < 30:
            logger.warning(f"Only {len(df)} labeled samples — need >= 30")
            return

        y = df[win_col].astype(int).values
        prim_features = [c for c in PRIMARY_FEATURES if c in df.columns]
        X_prim = df[prim_features].fillna(0).values

        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        base_xgb = XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            scale_pos_weight=float((y == 0).sum()) / max((y == 1).sum(), 1),
            use_label_encoder=False, eval_metric="logloss",
            random_state=42, verbosity=0,
        )
        self.primary_model = CalibratedClassifierCV(base_xgb, cv=skf, method="isotonic")
        self.primary_model.fit(X_prim, y)

        oof_probs = cross_val_predict(
            CalibratedClassifierCV(base_xgb, cv=skf, method="isotonic"),
            X_prim, y, cv=skf, method="predict_proba"
        )[:, 1]

        meta_mask = oof_probs >= PRIMARY_THRESHOLD
        if meta_mask.sum() >= 20:
            df_meta = df[meta_mask].copy()
            df_meta["primary_prob"] = oof_probs[meta_mask]
            y_meta = y[meta_mask]
            meta_features = [c for c in META_FEATURES if c in df_meta.columns]
            X_meta = df_meta[meta_features].fillna(0).values
            meta_xgb = XGBClassifier(
                n_estimators=150, max_depth=3, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.7,
                use_label_encoder=False, eval_metric="logloss",
                random_state=42, verbosity=0,
            )
            skf_meta = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
            self.meta_model = CalibratedClassifierCV(meta_xgb, cv=skf_meta, method="isotonic")
            self.meta_model.fit(X_meta, y_meta)

        self.is_trained = True
        self.training_stats = {"n_samples": len(df), "win_rate": round(float(y.mean()), 3)}
        logger.info(f"Classifier trained: n={len(df)} win_rate={y.mean():.1%}")

    def predict_confidence(self, row: pd.Series) -> float:
        if not self.is_trained or not ML_AVAILABLE:
            return self._heuristic_confidence(row)
        try:
            prim_features = [c for c in PRIMARY_FEATURES if c in row.index]
            X_prim = np.array([[row.get(c, 0) for c in prim_features]])
            prim_prob = float(self.primary_model.predict_proba(X_prim)[0, 1])
            if prim_prob < PRIMARY_THRESHOLD or self.meta_model is None:
                return prim_prob
            meta_features = [c for c in META_FEATURES if c in row.index]
            row_meta = row.copy()
            row_meta["primary_prob"] = prim_prob
            X_meta = np.array([[row_meta.get(c, 0) for c in meta_features]])
            return float(self.meta_model.predict_proba(X_meta)[0, 1])
        except Exception as e:
            logger.debug(f"predict_confidence error: {e}")
            return self._heuristic_confidence(row)

    def _heuristic_confidence(self, row: pd.Series) -> float:
        score = 0.50
        iv_rank = float(row.get("iv_rank", 0.5))
        score  += min(iv_rank * 0.15, 0.15)
        rsi_14  = float(row.get("rsi_14", 50))
        if rsi_14 <= 30 or rsi_14 >= 70:
            score += 0.08
        pct_b = float(row.get("pct_b", 0.5))
        if pct_b <= 0.05 or pct_b >= 0.95:
            score += 0.05
        return float(np.clip(score, 0.0, 1.0))

    def save(self, path: Optional[Path] = None):
        if not ML_AVAILABLE or not self.is_trained:
            return
        path = path or MODEL_FILE
        joblib.dump({"primary": self.primary_model, "meta": self.meta_model,
                     "stats": self.training_stats}, path)

    def load(self, path: Optional[Path] = None) -> bool:
        if not ML_AVAILABLE:
            return False
        path = path or MODEL_FILE
        if not path.exists():
            return False
        try:
            obj = joblib.load(path)
            self.primary_model = obj["primary"]
            self.meta_model    = obj.get("meta")
            self.training_stats = obj.get("stats", {})
            self.is_trained    = True
            return True
        except Exception:
            return False
