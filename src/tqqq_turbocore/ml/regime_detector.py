import logging
import numpy as np
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, Optional
import joblib
import os

try:
    from hmmlearn.hmm import GaussianHMM
    HMMLEARN_AVAILABLE = True
except ImportError:
    HMMLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)

# Features used by the upgraded 6-feature HMM (v2)
# Research basis: SSRN 2026, Imperial College McIndoe paper, Perplexity Q2 findings
HMM_FEATURES = [
    'qqq_vol_20d',       # QQQ 20d realized volatility — existing core feature
    'vix_close',          # VIX level — existing core feature
    'vix_term_slope',     # VIX/VIX3M ratio (>1 = backwardation = stress) — NEW
    'hyg_20d_slope',      # HYG 20d slope (credit spread proxy) — NEW: 3-6wk early lead
    'qqq_sma200_zscore',  # Signed distance from SMA200 as Z-score — NEW
    'tnx_irx_slope',      # 10Y-3M yield curve slope — NEW: macro regime anchor
]

# How many days between mandatory HMM retraining runs (quarterly)
RETRAIN_INTERVAL_DAYS = 90


class TurboCoreRegimeDetector:
    """
    Hidden Markov Model (HMM) — Layer 2 of TurboCore — v2.

    Upgraded from 2 features (vol + VIX) to 6 features (adds VIX term structure,
    credit spread, SMA200 Z-score, yield curve slope) based on SSRN 2026 research.

    Critical fixes vs v1:
      - State anchoring: after every fit(), states sorted by qqq_vol_20d mean so
        BULL label is always assigned to the lowest-vol state. Eliminates the
        HMM label-swapping problem between quarterly retraining runs.
      - Warm-start initialization: new model initialized from prior emission means
        when prior model exists, reducing random initialization divergence.
      - Quarterly auto-retrain: if last_trained_date > 90 days ago, retrain
        automatically on next scheduler startup.

    Outputs ml_regime ∈ {BULL, SIDEWAYS, BEAR, BEAR_SMA_FORCED}.
    """

    MODEL_FILE = os.path.join(os.path.dirname(__file__), 'turbocore_hmm.joblib')

    def __init__(self):
        self.model: Optional[GaussianHMM] = None
        self.is_trained = False
        self.state_mapping: Dict[int, str] = {}
        self.last_trained_date: Optional[date] = None

        if not HMMLEARN_AVAILABLE:
            logger.warning("hmmlearn not installed. TurboCoreRegimeDetector degraded.")
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
            self.model = data['model']
            self.state_mapping = data['mapping']
            self.last_trained_date = data.get('last_trained_date')
            self.is_trained = True
            logger.info(
                f"Loaded HMM v2 from {self.MODEL_FILE} "
                f"(trained: {self.last_trained_date}, mapping: {self.state_mapping})"
            )
        except Exception as e:
            logger.error(f"Failed to load HMM model: {e}")

    def _save_model(self):
        if not (self.model and self.is_trained):
            return
        try:
            joblib.dump({
                'model': self.model,
                'mapping': self.state_mapping,
                'last_trained_date': self.last_trained_date,
                'feature_names': HMM_FEATURES,
            }, self.MODEL_FILE)
            logger.info(f"HMM model saved to {self.MODEL_FILE}")
        except Exception as e:
            logger.error(f"Failed to save HMM model: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # Feature extraction
    # ──────────────────────────────────────────────────────────────────────────

    def _extract_features(self, df: pd.DataFrame) -> tuple:
        """
        Returns (X, valid_index) — the feature matrix and the matching DatetimeIndex.
        Falls back gracefully when new features are missing (supports legacy pipeline).
        """
        available = [f for f in HMM_FEATURES if f in df.columns]
        missing = [f for f in HMM_FEATURES if f not in df.columns]

        if missing:
            logger.warning(
                f"HMM: {len(missing)} features missing from dataframe, "
                f"using {len(available)} available: {available}. "
                f"Missing: {missing}. Run data_pipeline v2 to add them."
            )

        if not available:
            raise ValueError("No HMM features available in dataframe")

        feat_df = df[available].replace([np.inf, -np.inf], np.nan).dropna()
        return feat_df.values, feat_df.index, available

    # ──────────────────────────────────────────────────────────────────────────
    # State anchoring (Critical Fix)
    # ──────────────────────────────────────────────────────────────────────────

    def _anchor_state_labels(self, feature_names: list):
        """
        Sort HMM states by mean of the first feature (qqq_vol_20d).
        Lowest vol → BULL, mid → SIDEWAYS, highest vol → BEAR.

        This is the key fix for label stability across retraining runs.
        Called immediately after every fit().
        """
        if self.model is None:
            return

        # Use qqq_vol_20d (index 0) for anchoring; fall back to feature 0
        sort_feature_idx = 0  # always first feature in HMM_FEATURES
        means = self.model.means_[:, sort_feature_idx]  # scalar per state
        sorted_indices = np.argsort(means)  # ascending: low vol first

        self.state_mapping = {
            int(sorted_indices[0]): "BULL",
            int(sorted_indices[1]): "SIDEWAYS",
            int(sorted_indices[2]): "BEAR",
        }
        logger.info(
            f"HMM state anchoring: state_mapping={self.state_mapping} "
            f"(vol means: {means[sorted_indices].round(6).tolist()})"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Training
    # ──────────────────────────────────────────────────────────────────────────

    def needs_retrain(self) -> bool:
        """Returns True if model is untrained or older than RETRAIN_INTERVAL_DAYS."""
        if not self.is_trained or self.last_trained_date is None:
            return True
        days_since = (date.today() - self.last_trained_date).days
        if days_since >= RETRAIN_INTERVAL_DAYS:
            logger.info(
                f"HMM retrain triggered: {days_since} days since last training "
                f"(threshold={RETRAIN_INTERVAL_DAYS}d)"
            )
            return True
        return False

    def fit(self, df: pd.DataFrame):
        if not HMMLEARN_AVAILABLE:
            logger.error("Cannot fit: hmmlearn missing.")
            return

        X, valid_idx, feature_names = self._extract_features(df)
        if len(X) < 100:
            logger.error(f"Not enough data to train HMM ({len(X)} samples, need ≥100).")
            return

        logger.info(
            f"Training TurboCore HMM v2 on {len(X)} samples, "
            f"{len(feature_names)} features: {feature_names}"
        )

        # Warm-start: initialize means from prior model if available and
        # the feature count matches (avoids divergent random initialization)
        init_params = 'stmc'
        params = 'stmc'
        init_means = None
        if (self.model is not None and
                hasattr(self.model, 'means_') and
                self.model.means_.shape == (3, len(feature_names))):
            init_means = self.model.means_.copy()
            init_params = 'stc'   # skip means (m) from random init
            logger.info("HMM warm-starting from prior model means")

        self.model = GaussianHMM(
            n_components=3,
            covariance_type="diag",
            n_iter=1000,
            random_state=42,
            init_params=init_params,
            params=params,
        )

        if init_means is not None:
            self.model.means_ = init_means

        self.model.fit(X)

        # ── CRITICAL: anchor state labels by vol (prevents label swapping) ──
        self._anchor_state_labels(feature_names)

        self.is_trained = True
        self.last_trained_date = date.today()
        self._save_model()
        logger.info(f"HMM v2 training complete. State mapping: {self.state_mapping}")

    # ──────────────────────────────────────────────────────────────────────────
    # Inference
    # ──────────────────────────────────────────────────────────────────────────

    def predict_regimes(self, master_df: pd.DataFrame) -> pd.DataFrame:
        """
        Appends ml_regime and final_regime to the dataframe.
        Also applies the Layer 1 SMA200 hard-exit override.
        """
        df = master_df.copy()

        if not self.is_trained or not HMMLEARN_AVAILABLE or len(df) == 0:
            logger.warning("HMM not trained or unavailable — defaulting to SIDEWAYS")
            df['ml_regime'] = "SIDEWAYS"
            df['final_regime'] = "SIDEWAYS"
            return df

        df['ml_regime'] = "SIDEWAYS"  # Safe default

        try:
            X, valid_idx, _ = self._extract_features(df)
            if len(valid_idx) > 0:
                hidden_states = self.model.predict(X)
                state_labels = [
                    self.state_mapping.get(int(s), "SIDEWAYS") for s in hidden_states
                ]
                df.loc[valid_idx, 'ml_regime'] = state_labels
        except Exception as e:
            logger.error(f"HMM prediction failed: {e}. Defaulting to SIDEWAYS.")

        # ── Layer 1 override: SMA200 hard exit trumps HMM ────────────────────
        final_regimes = []
        for _, row in df.iterrows():
            if row.get('qqq_below_sma200_sell', False):
                final_regimes.append("BEAR_SMA_FORCED")
            else:
                final_regimes.append(row['ml_regime'])
        df['final_regime'] = final_regimes

        return df


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))
    from src.tqqq_turbocore.data_pipeline import TurboCoreDataPipeline
    logging.basicConfig(level=logging.INFO)

    pipeline = TurboCoreDataPipeline()
    pipeline.fetch_data("5y")
    df = pipeline.prepare_core_features()

    detector = TurboCoreRegimeDetector()
    detector.fit(df)
    df_r = detector.predict_regimes(df)
    print("\nRecent regimes:")
    print(df_r[['qqq_close', 'vix_close', 'vix_term_slope', 'ml_regime', 'final_regime']].tail(10))
    print("\nRegime distribution:")
    print(df_r['final_regime'].value_counts())
