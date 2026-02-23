"""
VIX Regime Detector
===================
Gaussian Hidden Markov Model (HMM) that classifies the market into
four VIX regimes: LOW_VOL, NORMAL, HIGH_VOL, CRISIS.

Inputs: VIX time-series features + TQQQ realized volatility
Output: regime label + transition probability matrix + confidence score
"""

import logging
import numpy as np
import pandas as pd
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Optional heavy import guard
try:
    from hmmlearn.hmm import GaussianHMM
    HMM_AVAILABLE = True
except ImportError:
    logger.warning("hmmlearn not installed. VIXRegimeDetector will run in FALLBACK mode.")
    GaussianHMM = None
    HMM_AVAILABLE = False

import joblib
import os

# ── Regime labels ordered by volatility level ──────────────────────────────
REGIME_LABELS = ["LOW_VOL", "NORMAL", "HIGH_VOL", "CRISIS"]


@dataclass
class RegimeResult:
    """Result returned by the regime detector."""
    regime: str
    confidence: float                         # max probability from forward algorithm
    regime_probs: Dict[str, float] = field(default_factory=dict)
    transition_matrix: Optional[np.ndarray] = None  # (n_states × n_states)


class VIXRegimeDetector:
    """
    Gaussian HMM with N=4 states for VIX regime classification.

    Training uses an expanding walk-forward window.
    Weekly retraining is triggered when prediction confidence drops
    below ``min_confidence``.

    Features (7):
        1. VIX close
        2. VIX 5-day MA
        3. VIX 10-day MA
        4. VIX 20-day MA
        5. VIX 5-day rate-of-change  (momentum)
        6. VIX / VIX3M term slope    (proxy for term structure steepness)
        7. TQQQ realized volatility  (HV-10)
    """

    N_STATES        = 4
    MIN_TRAIN_ROWS  = 250   # ~1 year of daily bars
    MODEL_PATH      = "src/tqqq/ml/models/vix_hmm.pkl"

    def __init__(self, n_states: int = N_STATES, min_confidence: float = 0.55):
        self.n_states       = n_states
        self.min_confidence = min_confidence
        self.model: Optional["GaussianHMM"] = None
        self._label_map: Dict[int, str] = {}   # state_id → regime label

        # Load pre-trained model if it exists
        if os.path.exists(self.MODEL_PATH):
            self._load()

    # ─────────────────────────── Public API ──────────────────────────────

    def fit(self, df: pd.DataFrame) -> None:
        """
        Train the HMM on a DataFrame containing VIX and TQQQ columns.

        Required columns:
            vix_close, vix_ma5, vix_ma10, vix_ma20, vix_roc5,
            term_slope, tqqq_hv10
        """
        if not HMM_AVAILABLE:
            logger.error("Cannot train: hmmlearn not available.")
            return

        X = self._build_feature_matrix(df)
        if len(X) < self.MIN_TRAIN_ROWS:
            logger.warning(f"Only {len(X)} rows — need {self.MIN_TRAIN_ROWS} to train.")
            return

        self.model = GaussianHMM(
            n_components=self.n_states,
            covariance_type="full",
            n_iter=200,
            tol=1e-4,
            random_state=42,
        )
        self.model.fit(X)
        self._label_map = self._auto_label_states()
        self._save()
        logger.info(f"HMM trained. State→Regime map: {self._label_map}")

    def predict(self, df: pd.DataFrame) -> RegimeResult:
        """
        Classifies the most recent regime from the provided feature DataFrame.
        Uses the fallback rule-based detector when HMM is unavailable.
        """
        if self.model is None or not HMM_AVAILABLE:
            logger.warning("HMM unavailable — using rule-based fallback.")
            return self._rule_based_fallback(df)

        X = self._build_feature_matrix(df)
        _, state_seq = self.model.decode(X, algorithm="viterbi")
        current_state = int(state_seq[-1])

        # Forward-algorithm posteriors for confidence
        log_posteriors = self.model.predict_proba(X)
        probs          = log_posteriors[-1]        # last bar probabilities
        confidence     = float(probs.max())

        regime_probs = {
            self._label_map.get(i, f"STATE_{i}"): float(probs[i])
            for i in range(self.n_states)
        }

        return RegimeResult(
            regime=self._label_map.get(current_state, "NORMAL"),
            confidence=confidence,
            regime_probs=regime_probs,
            transition_matrix=self.model.transmat_,
        )

    def needs_retraining(self, result: RegimeResult) -> bool:
        """Returns True when the model should be retrained (low confidence)."""
        return result.confidence < self.min_confidence

    # ─────────────────────── Feature Engineering ──────────────────────────

    @staticmethod
    def build_features(df_raw: pd.DataFrame) -> pd.DataFrame:
        """
        Computes the seven HMM features from a raw VIX / TQQQ DataFrame.

        Required raw columns: ``vix``, ``vix3m`` (optional), ``tqqq_close``
        """
        df = df_raw.copy()

        df["vix_close"] = df["vix"]
        df["vix_ma5"]   = df["vix"].rolling(5).mean()
        df["vix_ma10"]  = df["vix"].rolling(10).mean()
        df["vix_ma20"]  = df["vix"].rolling(20).mean()
        df["vix_roc5"]  = df["vix"].pct_change(5)

        # Term slope: VIX / VIX3M  (if vix3m missing use 1.0)
        if "vix3m" in df.columns:
            df["term_slope"] = df["vix"] / df["vix3m"].replace(0, np.nan)
        else:
            df["term_slope"] = 1.0

        # TQQQ 10-day historical volatility (annualized)
        tqqq_ret        = df["tqqq_close"].pct_change()
        df["tqqq_hv10"] = tqqq_ret.rolling(10).std() * np.sqrt(252)

        feature_cols = [
            "vix_close", "vix_ma5", "vix_ma10", "vix_ma20",
            "vix_roc5", "term_slope", "tqqq_hv10"
        ]
        return df[feature_cols].dropna()

    # ─────────────────────────── Internals ────────────────────────────────

    def _build_feature_matrix(self, df: pd.DataFrame) -> np.ndarray:
        feature_cols = [
            "vix_close", "vix_ma5", "vix_ma10", "vix_ma20",
            "vix_roc5", "term_slope", "tqqq_hv10"
        ]
        missing = [c for c in feature_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing feature columns: {missing}")
        return df[feature_cols].dropna().values

    def _auto_label_states(self) -> Dict[int, str]:
        """
        Label HMM states by their mean VIX value (feature index 0).
        Sorted ascending: lowest VIX → LOW_VOL, highest → CRISIS.
        """
        means       = self.model.means_[:, 0]   # VIX close mean per state
        sorted_ids  = np.argsort(means)
        return {int(state_id): REGIME_LABELS[i] for i, state_id in enumerate(sorted_ids)}

    def _rule_based_fallback(self, df: pd.DataFrame) -> RegimeResult:
        """Simple VIX-level rule when HMM is unavailable."""
        vix = float(df["vix_close"].iloc[-1]) if "vix_close" in df.columns else 20.0
        if vix >= 40:
            regime = "CRISIS"
        elif vix >= 25:
            regime = "HIGH_VOL"
        elif vix >= 15:
            regime = "NORMAL"
        else:
            regime = "LOW_VOL"
        return RegimeResult(regime=regime, confidence=0.75)

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.MODEL_PATH), exist_ok=True)
        joblib.dump({"model": self.model, "label_map": self._label_map}, self.MODEL_PATH)
        logger.info(f"HMM model saved → {self.MODEL_PATH}")

    def _load(self) -> None:
        try:
            data            = joblib.load(self.MODEL_PATH)
            self.model      = data["model"]
            self._label_map = data["label_map"]
            logger.info(f"HMM model loaded ← {self.MODEL_PATH}")
        except Exception as exc:
            logger.warning(f"Could not load HMM model: {exc}")
