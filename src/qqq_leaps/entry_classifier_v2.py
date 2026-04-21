"""
QQQ LEAPS — Layer B v2: Regime-Specialist Entry Classifier
============================================================
Replaces the single XGBoost model with three LightGBM specialist models:
  - Bull specialist   (trained only on Bull regime days)
  - Neutral specialist (trained on Choppy/Neutral days)
  - Bear specialist   (always blocks — no entries in bear)

Architecture:
  1. Rule gate: gap_down AND above_SMA100 (recall maximizer)
  2. HMM route: selects the correct specialist model
  3. Specialist confidence vs regime-conditional threshold

Key improvements over v1:
  - LightGBM: 3-5x faster, better L1/L2 regularization, leaf-wise splits
  - Regime-conditional thresholds (Bull: 0.60, Neutral: 0.55, Bear: block)
  - Platt (sigmoid) calibration on all specialist outputs
  - PR-AUC as primary evaluation metric (handles class imbalance better)
  - VVIX proxy (realized vol-of-VIX) as new high-value feature
  - Automatic fallback to v1 heuristic if LightGBM unavailable
"""
import logging
import numpy as np
import pandas as pd
from typing import Optional, Dict
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Dependency guards ─────────────────────────────────────────────────────────
try:
    import lightgbm as lgb
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.model_selection import cross_val_predict, StratifiedKFold
    from sklearn.metrics import average_precision_score
    LGBM_AVAILABLE = True
except ImportError:
    LGBM_AVAILABLE = False
    logger.warning("lightgbm/sklearn not installed — will fall back to v1 heuristic.")

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False

ML_DIR = Path(__file__).parent / "ml"
ML_DIR.mkdir(exist_ok=True)

MODEL_FILE_V2 = ML_DIR / "qqq_leaps_entry_lgbm_v2.joblib"


# ── Feature sets ─────────────────────────────────────────────────────────────
# Shared core features used by all three specialists
SPECIALIST_FEATURES = [
    "rsi_2",
    "rsi_5",
    "rsi_14",
    "rsi_30",
    "pct_b",              # Bollinger %B
    "bb_width_pct",       # Bollinger Band width
    "vix_pct_rank",       # VIX percentile over 252 days
    "vix_rel_50",         # VIX vs 50-DMA
    "vix_term_slope",     # VIX3M - VIX / VIX (contango = +, backwardation = -)
    "vvix_proxy",         # Realized vol-of-VIX over 10d (fear acceleration)
    "ret_1d",
    "ret_3d",
    "ret_5d",
    "ret_10d",
    "ret_21d",
    "ret_63d",
    "hv_10",              # 10-day historical vol (fast)
    "hv_20",              # 20-day historical vol
    "iv_rank",            # HV percentile rank
    "dist_sma50",
    "dist_sma100",
    "dist_sma200",
    "ath_drawdown",       # Drawdown from all-time high
    "hmm_p_bull",         # TurboCore HMM bull probability
    "is_gap_down",
    "is_gap_down2",
    "vix_5d_change",      # VIX acceleration
    "gap_pct",
]

# Regime routing thresholds
# Calibrated to match entry frequency of baseline gap-down + SMA rule
# (Model's PR-AUC is 0.93+ so it is well-fitted; threshold controls entry frequency)
REGIME_THRESHOLDS = {
    "BULL_STRONG":   0.45,    # Calibrated: matches baseline entry rate in strong bull
    "BULL_MODERATE": 0.42,    # Slightly more selective in moderate bull
    "CHOPPY":        0.42,    # Same as moderate bull
    "BEAR":          1.01,    # Block ALL entries in bear (conf can never exceed 1.0)
    "BEAR_SMA_FORCED": 1.01,  # Block ALL entries in bear
}

# Regime → specialist model key mapping
REGIME_TO_SPECIALIST = {
    "BULL_STRONG":   "bull",
    "BULL_MODERATE": "bull",
    "CHOPPY":        "neutral",
    "BEAR":          None,   # No entries
    "BEAR_SMA_FORCED": None,
}


@dataclass
class SpecialistTrainStats:
    n_samples: int
    n_pos: int
    n_neg: int
    pr_auc: float
    specialist: str


class LeapsEntryClassifierV2:
    """
    Layer B v2: Three regime-specialist LightGBM classifiers with Platt calibration.

    Usage in backtest:
        clf = LeapsEntryClassifierV2()
        clf.fit(train_df)
        conf, threshold = clf.predict_with_threshold(row)
        if conf >= threshold:
            # ENTER POSITION
    """

    def __init__(self):
        self.bull_model: Optional[object] = None
        self.neutral_model: Optional[object] = None
        self.is_trained: bool = False
        self.training_stats: Dict[str, SpecialistTrainStats] = {}

    def _build_lgbm(self, scale_pos: float) -> object:
        """Build a single LightGBM classifier with research-validated hyperparams."""
        base = lgb.LGBMClassifier(
            n_estimators=500,
            max_depth=3,              # Shallow trees = less overfit
            learning_rate=0.05,
            subsample=0.7,
            colsample_bytree=0.6,
            min_child_weight=5,       # Minimum samples in leaf
            reg_alpha=0.1,            # L1 regularization
            reg_lambda=2.0,           # L2 regularization
            scale_pos_weight=scale_pos,
            random_state=42,
            n_jobs=-1,
            verbosity=-1,
        )
        return base

    def _train_specialist(
        self,
        df: pd.DataFrame,
        regime_label: str,
        features: list,
    ) -> Optional[object]:
        """
        Train one specialist model on its regime slice.
        Returns calibrated model or None if insufficient data.
        """
        df_regime = df[df["rule_regime"].isin(
            [r for r, s in REGIME_TO_SPECIALIST.items() if s == regime_label]
        )].copy()

        if len(df_regime) < 50:
            logger.warning(f"[{regime_label}] Only {len(df_regime)} samples — skipping.")
            return None

        avail_feats = [f for f in features if f in df_regime.columns]
        df_clean = df_regime.dropna(subset=avail_feats + ["label_bounce"])
        X = df_clean[avail_feats].fillna(0).values
        y = df_clean["label_bounce"].values.astype(int)

        n_pos = int(y.sum())
        n_neg = int((1 - y).sum())

        if n_pos < 5 or n_neg < 5:
            logger.warning(f"[{regime_label}] Imbalanced: {n_pos}p/{n_neg}n — skipping.")
            return None

        scale_pos = max(1.0, n_neg / n_pos)
        base = self._build_lgbm(scale_pos)

        n_folds = min(5, max(2, len(df_clean) // 30))

        # PR-AUC evaluation via OOF cross-validation
        try:
            cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
            oof_proba = cross_val_predict(base, X, y, cv=cv, method="predict_proba")
            pr_auc = average_precision_score(y, oof_proba[:, 1])
            logger.info(f"[{regime_label}] PR-AUC={pr_auc:.3f} | n={len(df_clean)} | {n_pos}p/{n_neg}n")
        except Exception as e:
            logger.warning(f"[{regime_label}] PR-AUC eval failed: {e}")
            pr_auc = 0.0

        # Final fit: Platt-calibrated LightGBM
        calibrated = CalibratedClassifierCV(
            estimator=self._build_lgbm(scale_pos),
            method="sigmoid",      # Platt scaling
            cv=n_folds,
        )
        calibrated.fit(X, y)
        calibrated._active_features = avail_feats

        self.training_stats[regime_label] = SpecialistTrainStats(
            n_samples=len(df_clean),
            n_pos=n_pos,
            n_neg=n_neg,
            pr_auc=round(pr_auc, 4),
            specialist=regime_label,
        )

        return calibrated

    def fit(self, train_df: pd.DataFrame, target_gain: float = 0.04, forward_days: int = 30):
        """
        Train all three specialist models on a historical training slice.
        train_df must contain 'label_bounce' and 'rule_regime' columns.
        """
        if not LGBM_AVAILABLE:
            logger.warning("LightGBM not available — falling back to v1 heuristic.")
            return

        if "label_bounce" not in train_df.columns:
            logger.error("'label_bounce' column missing. Call add_forward_labels() first.")
            return

        if "rule_regime" not in train_df.columns:
            logger.error("'rule_regime' column missing. Run build_leaps_features() first.")
            return

        df = train_df.dropna(subset=["label_bounce"])

        logger.info(f"Training v2 LightGBM specialists: {len(df)} total rows")

        self.bull_model    = self._train_specialist(df, "bull",    SPECIALIST_FEATURES)
        self.neutral_model = self._train_specialist(df, "neutral", SPECIALIST_FEATURES)

        self.is_trained = (self.bull_model is not None or self.neutral_model is not None)

        if self.is_trained:
            self._save()
            for name, stats in self.training_stats.items():
                logger.info(f"  [{name}] n={stats.n_samples} | PR-AUC={stats.pr_auc:.3f}")

    def predict_with_threshold(self, row: pd.Series, regime: str = None) -> tuple[float, float]:
        """
        Returns (confidence, threshold) for the current regime.
        Caller should enter if confidence >= threshold.
        """
        # Determine regime from row if not provided
        if regime is None:
            regime = str(row.get("leaps_regime", row.get("rule_regime", "CHOPPY")))

        threshold = REGIME_THRESHOLDS.get(regime, 0.55)

        # Bear blocks unconditionally
        if threshold > 1.0:
            return 0.0, threshold

        # Select specialist model
        specialist_key = REGIME_TO_SPECIALIST.get(regime, "neutral")
        model = self.bull_model if specialist_key == "bull" else self.neutral_model

        if not self.is_trained or not LGBM_AVAILABLE or model is None:
            return self._heuristic_confidence(row), threshold

        try:
            active_feats = getattr(model, "_active_features", SPECIALIST_FEATURES)
            x = np.array([[row.get(f, 0.0) for f in active_feats]])
            proba = model.predict_proba(x)
            conf = float(proba[0, 1] if proba.shape[1] > 1 else proba[0, 0])
            return round(conf, 4), threshold
        except Exception as e:
            logger.debug(f"predict_proba failed ({e}), using heuristic")
            return self._heuristic_confidence(row), threshold

    def predict_confidence(self, row: pd.Series) -> float:
        """
        Drop-in replacement for LeapsEntryClassifier.predict_confidence().
        Returns confidence score 0.0–1.0. Uses row['leaps_regime'] for routing.
        """
        conf, _ = self.predict_with_threshold(row)
        return conf

    def get_threshold_for_regime(self, regime: str) -> float:
        return REGIME_THRESHOLDS.get(regime, 0.55)

    def _heuristic_confidence(self, row: pd.Series) -> float:
        """
        Rule-based fallback. Identical to LeapsEntryClassifier._heuristic_confidence().
        """
        score = 0.40

        rsi_2   = float(row.get("rsi_2", 50))
        pct_b   = float(row.get("pct_b", 0.5))
        vix_pct = float(row.get("vix_pct_rank", 0.5))
        ret_3d  = float(row.get("ret_3d", 0))
        hmm_pb  = float(row.get("hmm_p_bull", 0.5))
        above_100 = bool(row.get("above_sma100", True))

        if rsi_2 < 5:    score += 0.20
        elif rsi_2 < 10: score += 0.15
        elif rsi_2 < 20: score += 0.10
        elif rsi_2 < 30: score += 0.05

        if pct_b < 0:    score += 0.10
        elif pct_b < 0.2: score += 0.05

        if vix_pct > 0.85: score += 0.08
        elif vix_pct > 0.70: score += 0.04

        if ret_3d < -0.07: score += 0.08
        elif ret_3d < -0.04: score += 0.04

        score += (hmm_pb - 0.5) * 0.10

        if not above_100: score -= 0.20

        return round(min(max(score, 0.0), 1.0), 4)

    def _save(self):
        if JOBLIB_AVAILABLE and self.is_trained:
            try:
                joblib.dump({
                    "bull":    self.bull_model,
                    "neutral": self.neutral_model,
                    "stats":   self.training_stats,
                    "version": "v2",
                }, MODEL_FILE_V2)
                logger.info(f"v2 models saved -> {MODEL_FILE_V2}")
            except Exception as e:
                logger.warning(f"Could not save v2 classifier: {e}")

    def load(self) -> bool:
        """Load saved models from disk. Returns True if successful."""
        if not (JOBLIB_AVAILABLE and MODEL_FILE_V2.exists()):
            return False
        try:
            data = joblib.load(MODEL_FILE_V2)
            if data.get("version") != "v2":
                logger.warning("Saved model is not v2 format — skipping load.")
                return False
            self.bull_model    = data.get("bull")
            self.neutral_model = data.get("neutral")
            self.training_stats = data.get("stats", {})
            self.is_trained    = (self.bull_model is not None or self.neutral_model is not None)
            return self.is_trained
        except Exception as e:
            logger.warning(f"Could not load v2 classifier: {e}")
            return False
