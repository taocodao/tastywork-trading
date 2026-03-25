import logging
import numpy as np
import pandas as pd
from typing import Dict, Optional
import joblib
import os
from sklearn.preprocessing import StandardScaler

try:
    from hmmlearn.hmm import GaussianHMM
    HMMLEARN_AVAILABLE = True
except ImportError:
    HMMLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)


class TurboCoreRegimeDetector:
    """
    Hidden Markov Model for TQQQ TurboCore strategy regime detection.

    PHASE 2 FIXES (from Perplexity diagnostic report):
    ─────────────────────────────────────────────────────────────────────────
    FIX 2a — Feature standardization: z-score all HMM features before fitting.
      Prior fix: VIX (10–80) and qqq_vol_20d (0.005–0.04) were on wildly
      different scales → qqq_vol_20d had near-zero discriminatory power.

    FIX 2b — Diagonal transmat initialization (0.90 self-transition).
      Prior: hmmlearn random init near simplex boundary → pathological 98%
      daily BULL↔SIDEWAYS oscillation. Setting diagonal=0.90 pulls Baum-Welch
      toward persistent regimes (2–8 transitions/year vs 250/year prior).

    FIX 2c — Expanded feature set (4 features → richer state separability):
      Old: [qqq_vol_20d, vix_close]
      New: [qqq_vol_20d, vix_close, qqq_10d_return, vix_term_slope]
      qqq_10d_return separates BULL (positive momentum) from SIDEWAYS (flat).
      vix_term_slope (VIX3M - VIX) is a leading indicator of vol regime shifts.

    FIX 2d — Post-decoding 5-day rolling mode smoothing of Viterbi labels.
      Single-day flip-flops after Viterbi decoding are eliminated.
    ─────────────────────────────────────────────────────────────────────────

    3 states → BULL, SIDEWAYS, BEAR (sorted by ascending vol/VIX score).
    SMA200 (-3% buffer) hard gate overrides always applied post-prediction.
    """

    MODEL_FILE  = os.path.join(os.path.dirname(__file__), 'turbocore_hmm.joblib')
    SCALER_FILE = os.path.join(os.path.dirname(__file__), 'turbocore_hmm_scaler.joblib')

    # FIX 2c: expanded feature set
    FEATURE_COLS = ['qqq_vol_20d', 'vix_close', 'qqq_10d_return', 'vix_term_slope']

    def __init__(self):
        self.model:        Optional[GaussianHMM] = None
        self.scaler:       Optional[StandardScaler] = None
        self.is_trained    = False
        self.state_mapping: Dict[int, str] = {}

        if not HMMLEARN_AVAILABLE:
            logger.warning("hmmlearn not installed. TurboCoreRegimeDetector degraded.")
            return

        self._load_model()

    def _load_model(self):
        if os.path.exists(self.MODEL_FILE):
            try:
                data              = joblib.load(self.MODEL_FILE)
                self.model        = data['model']
                self.state_mapping = data['mapping']
                self.is_trained   = True
                logger.debug(f"Loaded HMM from {self.MODEL_FILE}")
            except Exception as e:
                logger.error(f"Failed loading HMM: {e}")

        if os.path.exists(self.SCALER_FILE):
            try:
                self.scaler = joblib.load(self.SCALER_FILE)
                logger.debug("Loaded HMM feature scaler.")
            except Exception as e:
                logger.warning(f"Failed loading HMM scaler: {e}")

    def _save_model(self):
        if self.model and self.is_trained:
            try:
                joblib.dump({'model': self.model, 'mapping': self.state_mapping},
                            self.MODEL_FILE)
                if self.scaler:
                    joblib.dump(self.scaler, self.SCALER_FILE)
            except Exception as e:
                logger.error(f"Failed saving HMM: {e}")

    def _prepare_features(self, df: pd.DataFrame, fit_scaler: bool = False) -> tuple:
        """
        Extract, compute, and z-score HMM features.

        Returns (X_scaled, valid_index).
        fit_scaler=True: fit scaler on this data (training time only).
        fit_scaler=False: use already-fitted scaler (inference time only).
        """
        fdf = df.copy()

        # Compute qqq_10d_return if not present
        if 'qqq_10d_return' not in fdf.columns:
            if 'qqq_log_return' in fdf.columns:
                fdf['qqq_10d_return'] = fdf['qqq_log_return'].rolling(10).sum()
            elif 'qqq_close' in fdf.columns:
                fdf['qqq_10d_return'] = np.log(
                    fdf['qqq_close'] / fdf['qqq_close'].shift(10)
                )
            else:
                fdf['qqq_10d_return'] = 0.0

        # vix_term_slope defaults to 0 if not available (already in data_pipeline)
        if 'vix_term_slope' not in fdf.columns:
            fdf['vix_term_slope'] = 0.0

        available_features = [f for f in self.FEATURE_COLS if f in fdf.columns]
        feature_df         = fdf[available_features].dropna()

        if len(feature_df) < 50:
            logger.warning("Insufficient feature rows for HMM.")
            return None, None

        # FIX 2a: z-score standardization
        if fit_scaler:
            self.scaler = StandardScaler()
            X_scaled    = self.scaler.fit_transform(feature_df.values)
        elif self.scaler is not None:
            X_scaled = self.scaler.transform(feature_df.values)
        else:
            # Fallback: fit scaler on this data (inference without saved scaler)
            self.scaler = StandardScaler()
            X_scaled    = self.scaler.fit_transform(feature_df.values)

        return X_scaled, feature_df.index

    def fit(self, df: pd.DataFrame):
        """
        Train the stabilized HMM with diagnostic-report fixes applied.
        """
        if not HMMLEARN_AVAILABLE:
            logger.error("Cannot fit: hmmlearn missing.")
            return

        X, valid_idx = self._prepare_features(df, fit_scaler=True)
        if X is None:
            logger.error("Not enough data to train HMM.")
            return

        logger.info(f"Training stabilized HMM on {len(X)} samples with {X.shape[1]} features...")

        # FIX 2b: Initialize transition matrix with strong diagonal (0.90)
        # Forces Baum-Welch to start from a persistent-regime solution
        n = 3
        transmat_init = np.full((n, n), 0.025)   # off-diagonal
        np.fill_diagonal(transmat_init, 0.90)
        # Normalize rows to sum to 1
        transmat_init = transmat_init / transmat_init.sum(axis=1, keepdims=True)

        # covariance_type='full' allows correlated features (better for 4 features)
        self.model = GaussianHMM(
            n_components   = n,
            covariance_type = 'full',
            n_iter          = 200,
            random_state    = 42,
            init_params     = 'mc',   # Only init means/covars randomly, NOT transmat
        )
        self.model.transmat_ = transmat_init

        self.model.fit(X)

        # Map states: sum of normalized mean scores (lowest = BULL, highest = BEAR)
        means      = self.model.means_
        norm_means = (means - means.min(axis=0)) / (np.ptp(means, axis=0) + 1e-9)
        scores     = norm_means.sum(axis=1)
        sorted_idx = np.argsort(scores)

        self.state_mapping = {
            sorted_idx[0]: 'BULL',
            sorted_idx[1]: 'SIDEWAYS',
            sorted_idx[2]: 'BEAR',
        }

        # Log learned transition matrix for diagnostic review
        trans_diag = self.model.transmat_.diagonal()
        logger.info(f"HMM training complete. State mapping: {self.state_mapping}")
        logger.info(f"Learned transmat diagonal: {np.round(trans_diag, 3)} "
                    f"(target: >0.90 for stable regimes)")

        self.is_trained = True
        self._save_model()

    def predict_regimes(self, master_df: pd.DataFrame) -> pd.DataFrame:
        """
        Predict regimes with Viterbi decoding + 5-day rolling mode smoothing.

        Phase 2 changes from diagnostic fixes:
        - FIX 2a: z-scored features before Viterbi decoding
        - FIX 2d: 5-day rolling mode applied to smooth single-day flip-flops
        - SMA200 hard gate applied post-smoothing (always authoritative)
        """
        df = master_df.copy()

        if not self.is_trained or not HMMLEARN_AVAILABLE or len(df) == 0:
            logger.warning("HMM not trained — defaulting to SIDEWAYS")
            df['ml_regime']       = 'SIDEWAYS'
            df['confirmed_regime'] = 'SIDEWAYS'
            df['final_regime']    = 'SIDEWAYS'
            return df

        df['ml_regime'] = 'SIDEWAYS'

        # FIX 2a: standardize features
        X, valid_idx = self._prepare_features(df, fit_scaler=False)

        if X is not None and len(valid_idx) > 0:
            hidden_states = self.model.predict(X)
            state_labels  = [self.state_mapping.get(s, 'SIDEWAYS') for s in hidden_states]
            raw_series    = pd.Series(state_labels, index=valid_idx)

            # FIX 2d: rolling 5-day mode smoothing to eliminate single-day flip-flops
            def rolling_mode(s, window=5):
                return s.rolling(window, min_periods=1).apply(
                    lambda x: pd.Series(x).mode().iloc[0]
                )
            # Encode → mode → decode
            encode  = {'BULL': 0, 'SIDEWAYS': 1, 'BEAR': 2}
            decode  = {0: 'BULL', 1: 'SIDEWAYS', 2: 'BEAR'}
            encoded = raw_series.map(encode).astype(float)
            smoothed_encoded = rolling_mode(encoded)
            smoothed_labels  = smoothed_encoded.map(decode).fillna('SIDEWAYS')

            df.loc[valid_idx, 'ml_regime'] = smoothed_labels.values

        # Keep confirmed_regime as alias for forward compatibility (Phase 3 ensemble)
        df['confirmed_regime'] = df['ml_regime']

        # SMA200 Hard Gate
        final_regimes = []
        for _, row in df.iterrows():
            if row.get('qqq_below_sma200_sell', False):
                final_regimes.append('BEAR_SMA_FORCED')
            else:
                final_regimes.append(row['ml_regime'])

        df['final_regime'] = final_regimes
        return df
