"""
TurboCore Pro v2 — 2-State Regime Detector (HMM primary + MS-GARCH/BOCD ensemble)
===================================================================================
Rebuild driven by deep-research findings (Aug 2026):

  1. The production 3-state Gaussian HMM is pathologically degenerate:
     SIDEWAYS absorbed 48.7% of days (expected 5-10%) and confidence was
     compressed to mean 0.476 / std 0.059 / max 0.655, rarely reaching the
     0.60 "high-conviction" Kelly threshold.
  2. Academic consensus (Hamilton 1989 and successors) favors a 2-state
     regime specification for equities -- intermediate "sideways" states
     lack a clean economic analog and the meta-model's continuous XGBoost
     confidence score is a better-suited mechanism for graded conviction
     within a BULL regime than a third discrete HMM state.
  3. A 2018 academic paper on 2-state HMMs for expensive/cheap volatility
     regimes found positive alpha net of a Carhart four-factor model; a
     2026 MS-GARCH-with-TVTP paper found strong regime separation
     (KS test p ~= 1.35e-153) versus single-regime GARCH.
  4. This codebase ALREADY contains fully-built (but never wired in or
     trained) MS-GARCH (msgarch_detector.py) and BOCD (bocd_detector.py)
     modules plus a 3-detector voting ensemble (regime_ensemble.py). The
     highest-leverage fix is training and activating that existing stack
     with a 2-state HMM as its structural backbone, not re-inventing it.

This module is bar-cadence agnostic: pass `bars_per_day` (default 1 for
daily bars, ~6.5 for US-equity hourly RTH bars) and all lookback windows
below are expressed in *trading days* internally, then converted to bar
counts. This lets the exact same code train/predict on daily OR hourly
data consistently.

Feature set (4 features, matches the original well-validated design):
  qqq_vol_20d      - 20-trading-day realized vol of QQQ log returns (annualized)
  vix_close        - VIX level (or hourly-cadence proxy, see data_pipeline)
  qqq_10d_return   - 10-trading-day QQQ log return (momentum)
  vix_term_slope   - VIX3M - VIX (contango/backwardation; falls back to 0)

Semantic anchoring (2-state):
  State 0 = BULL: low vol/VIX, positive momentum, contango term structure
  State 1 = BEAR: high vol/VIX, negative momentum, backwardation

Persistent transmat prior: BULL self-transition 0.97 (~4-12mo avg regime,
scaled to bar cadence), BEAR self-transition 0.95 (~2-4mo avg regime,
bears are shorter and faster). At hourly cadence with ~6.5 bars/day these
self-transition probabilities are re-derived from the same *day-scale*
average regime length so persistence is comparable across cadences.
"""
import logging
import os
from typing import Dict, Optional

import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler

try:
    from hmmlearn.hmm import GaussianHMM
    HMMLEARN_AVAILABLE = True
except ImportError:
    HMMLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)


def _day_persistence_to_bar_transmat(bull_days: float, bear_days: float,
                                      bars_per_day: float) -> np.ndarray:
    """
    Convert target average regime length (in TRADING DAYS) to a bar-cadence
    self-transition probability, so a "4-week bull regime" means the same
    thing whether bars are daily or hourly.

    Average regime length in bars L_bars = L_days * bars_per_day.
    For a geometric distribution, self-transition p satisfies
    E[run length] = 1 / (1 - p)  =>  p = 1 - 1 / L_bars.
    """
    bull_bars = max(2.0, bull_days * bars_per_day)
    bear_bars = max(2.0, bear_days * bars_per_day)
    p_bull = 1.0 - 1.0 / bull_bars
    p_bear = 1.0 - 1.0 / bear_bars
    return np.array([
        [p_bull,        1.0 - p_bull],
        [1.0 - p_bear,  p_bear],
    ])


class TurboCoreRegimeDetectorV2:
    """
    2-state Gaussian HMM regime detector, bar-cadence agnostic.

    Args:
        bars_per_day: number of bars per trading day (1 for daily, ~6.5 for
                      hourly RTH bars -- 6.5h session / 1h bars).
        model_tag:    suffix for the persisted model file, so daily and
                      hourly-trained models don't collide on disk
                      (e.g. 'daily', 'hourly').
    """

    FEATURE_COLS = ['qqq_vol_20d', 'vix_close', 'qqq_10d_return', 'vix_term_slope']

    # Target average regime length in TRADING DAYS (bar-cadence independent)
    BULL_AVG_REGIME_DAYS = 90.0   # ~4-12mo per research; use mid-point-ish
    BEAR_AVG_REGIME_DAYS = 45.0   # bears are shorter (~2-4mo)

    def __init__(self, bars_per_day: float = 1.0, model_tag: str = "daily"):
        self.bars_per_day = bars_per_day
        self.model_tag = model_tag
        self.model: Optional[GaussianHMM] = None
        self.scaler: Optional[StandardScaler] = None
        self.is_trained = False
        self.state_mapping: Dict[int, str] = {}

        self.MODEL_FILE = os.path.join(
            os.path.dirname(__file__), f'turbocore_hmm_v2_{model_tag}.joblib')
        self.SCALER_FILE = os.path.join(
            os.path.dirname(__file__), f'turbocore_hmm_v2_{model_tag}_scaler.joblib')

        if not HMMLEARN_AVAILABLE:
            logger.warning("hmmlearn not installed. TurboCoreRegimeDetectorV2 degraded.")
            return

    # ─── Persistence ────────────────────────────────────────────────────────

    def load(self) -> bool:
        if os.path.exists(self.MODEL_FILE) and os.path.exists(self.SCALER_FILE):
            try:
                data = joblib.load(self.MODEL_FILE)
                self.model = data['model']
                self.state_mapping = data['mapping']
                self.scaler = joblib.load(self.SCALER_FILE)
                self.is_trained = True
                logger.info(f"Loaded 2-state HMM ({self.model_tag}) from disk.")
                return True
            except Exception as e:
                logger.error(f"Failed loading 2-state HMM: {e}")
        return False

    def save(self):
        if self.model is not None and self.is_trained:
            joblib.dump({'model': self.model, 'mapping': self.state_mapping,
                         'n_states': 2, 'bars_per_day': self.bars_per_day},
                        self.MODEL_FILE)
            joblib.dump(self.scaler, self.SCALER_FILE)

    # ─── Feature prep ───────────────────────────────────────────────────────

    def _prepare_features(self, df: pd.DataFrame, fit_scaler: bool) -> tuple:
        fdf = df.copy()
        bpd = self.bars_per_day
        win20 = max(2, int(round(20 * bpd)))
        win10 = max(1, int(round(10 * bpd)))

        if 'qqq_vol_20d' not in fdf.columns:
            if 'qqq_log_return' in fdf.columns:
                ann_factor = np.sqrt(252 * bpd)
                fdf['qqq_vol_20d'] = fdf['qqq_log_return'].rolling(win20).std() * ann_factor
            else:
                fdf['qqq_vol_20d'] = 0.20

        if 'qqq_10d_return' not in fdf.columns:
            if 'qqq_log_return' in fdf.columns:
                fdf['qqq_10d_return'] = fdf['qqq_log_return'].rolling(win10).sum()
            elif 'qqq_close' in fdf.columns:
                fdf['qqq_10d_return'] = np.log(fdf['qqq_close'] / fdf['qqq_close'].shift(win10))
            else:
                fdf['qqq_10d_return'] = 0.0

        if 'vix_term_slope' not in fdf.columns:
            fdf['vix_term_slope'] = 0.0
        if 'vix_close' not in fdf.columns:
            fdf['vix_close'] = 20.0

        available = [f for f in self.FEATURE_COLS if f in fdf.columns]
        feature_df = fdf[available].replace([np.inf, -np.inf], np.nan).dropna()

        if len(feature_df) < max(50, win20 * 2):
            logger.warning("Insufficient feature rows for 2-state HMM.")
            return None, None

        if fit_scaler or self.scaler is None:
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(feature_df.values)
        else:
            X_scaled = self.scaler.transform(feature_df.values)

        return X_scaled, feature_df.index

    # ─── Train ──────────────────────────────────────────────────────────────

    def fit(self, df: pd.DataFrame):
        if not HMMLEARN_AVAILABLE:
            logger.error("Cannot fit: hmmlearn missing.")
            return

        X, valid_idx = self._prepare_features(df, fit_scaler=True)
        if X is None:
            logger.error("Not enough data to train 2-state HMM.")
            return

        logger.info(f"Training 2-state HMM ({self.model_tag}, bars_per_day="
                    f"{self.bars_per_day}) on {len(X)} samples...")

        transmat_init = _day_persistence_to_bar_transmat(
            self.BULL_AVG_REGIME_DAYS, self.BEAR_AVG_REGIME_DAYS, self.bars_per_day)

        n_features = X.shape[1]
        self.model = GaussianHMM(
            n_components=2,
            covariance_type='full',
            n_iter=300,
            tol=1e-5,
            init_params='c',    # only randomly init covariances; means+transmat set manually below
            params='stmc',
            random_state=42,
        )
        self.model.transmat_ = transmat_init
        self.model.startprob_ = np.array([0.5, 0.5])

        # Semantic mean initialization (z-score space), same design as the
        # original train_hmm_2state.py: state0=BULL (low vol/VIX, positive
        # momentum, contango), state1=BEAR (high vol/VIX, negative momentum,
        # backwardation). Feature order: [vol, vix, 10d_ret, term_slope]
        semantic_means = np.array([
            [-0.70, -0.70,  0.60,  0.30],
            [ 0.80,  0.80, -0.60, -0.40],
        ])
        self.model.means_ = semantic_means[:, :n_features]

        self.model.fit(X)

        momentum_means = self.model.means_[:, 2]  # qqq_10d_return column
        bull_state = int(np.argmax(momentum_means))
        bear_state = int(np.argmin(momentum_means))
        self.state_mapping = {bull_state: 'BULL', bear_state: 'BEAR'}

        trans_diag = self.model.transmat_.diagonal()
        logger.info(f"2-state HMM trained. Mapping: {self.state_mapping}. "
                    f"Transmat diagonal: {np.round(trans_diag, 4)}")

        self.is_trained = True
        self.save()

    # ─── Causal decoding ────────────────────────────────────────────────────

    def _causal_filter_states(self, X: np.ndarray) -> np.ndarray:
        """
        Causal forward filtering (Phase 0.1 correctness fix).

        hmmlearn's `.predict()` runs Viterbi, a full-sequence MAP decode: the
        label assigned to bar t depends on observations at t+1..T. In a
        backtest that is lookahead — a bar can be relabelled BEAR because of
        a crash that has not happened yet.

        This replaces it with the forward algorithm: at each bar t we compute
        the filtered posterior P(state_t | obs_1..obs_t) using ONLY past and
        present observations, then take argmax. Implemented as a scaled
        (normalize-at-each-step) recursion in probability space to avoid
        underflow, which is O(T * K^2) with K=2 — trivially fast.
        """
        framelogprob = self.model._compute_log_likelihood(X)
        # Per-bar max-subtraction keeps emissions in a safe numeric range; the
        # per-step renormalization below cancels the constant out exactly.
        b = np.exp(framelogprob - framelogprob.max(axis=1, keepdims=True))
        b = np.nan_to_num(b, nan=0.0, posinf=0.0, neginf=0.0)

        transmat = np.asarray(self.model.transmat_)
        startprob = np.asarray(self.model.startprob_)
        n_samples, n_states = b.shape
        filtered = np.empty((n_samples, n_states))

        alpha = startprob * b[0]
        s = alpha.sum()
        alpha = alpha / s if s > 0 else np.full(n_states, 1.0 / n_states)
        filtered[0] = alpha

        for t in range(1, n_samples):
            alpha = (alpha @ transmat) * b[t]
            s = alpha.sum()
            alpha = alpha / s if s > 0 else np.full(n_states, 1.0 / n_states)
            filtered[t] = alpha

        return filtered.argmax(axis=1)

    # ─── Predict ────────────────────────────────────────────────────────────

    def predict_regimes(self, master_df: pd.DataFrame,
                         smooth_days: float = 5.0,
                         causal: bool = True) -> pd.DataFrame:
        """
        Predict regimes with causal forward filtering + trailing rolling-mode
        smoothing. smooth_days is expressed in trading days, converted to bars.

        causal=False restores the legacy Viterbi decode; retained only so the
        two can be compared bar-by-bar in the Phase 0.1 validation harness.
        """
        df = master_df.copy()

        if not self.is_trained or not HMMLEARN_AVAILABLE or len(df) == 0:
            logger.warning("2-state HMM not trained -- defaulting to BULL (conservative).")
            df['ml_regime'] = 'BULL'
            df['confirmed_regime'] = 'BULL'
            df['final_regime'] = 'BULL'
            return df

        df['ml_regime'] = 'BULL'

        X, valid_idx = self._prepare_features(df, fit_scaler=False)

        if X is not None and len(valid_idx) > 0:
            if causal:
                hidden_states = self._causal_filter_states(X)
            else:
                hidden_states = self.model.predict(X)
            state_labels = [self.state_mapping.get(s, 'BULL') for s in hidden_states]
            raw_series = pd.Series(state_labels, index=valid_idx)

            smooth_window = max(1, int(round(smooth_days * self.bars_per_day)))
            encode = {'BULL': 0, 'BEAR': 1}
            decode = {0: 'BULL', 1: 'BEAR'}
            encoded = raw_series.map(encode).astype(float)
            smoothed_encoded = encoded.rolling(smooth_window, min_periods=1).apply(
                lambda x: pd.Series(x).mode().iloc[0])
            smoothed_labels = smoothed_encoded.map(decode).fillna('BULL')

            df.loc[valid_idx, 'ml_regime'] = smoothed_labels.values

        df['confirmed_regime'] = df['ml_regime']

        # SMA200 hard gate (always authoritative), and demote to SIDEWAYS-like
        # treatment is NOT reintroduced here -- the 2-state design intentionally
        # routes "uncertain bull" through the meta-model's continuous confidence
        # score in allocation_optimizer.py rather than a discrete third state.
        final_regimes = []
        for _, row in df.iterrows():
            if row.get('qqq_below_sma200_sell', False):
                final_regimes.append('BEAR_SMA_FORCED')
            else:
                final_regimes.append(row['ml_regime'])
        df['final_regime'] = final_regimes
        return df
