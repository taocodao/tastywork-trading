"""
Phase 3 v2: 2-of-2 Regime Voting Ensemble (2-state HMM + MS-GARCH + BOCD)
===========================================================================
Rebuild of regime_ensemble.py for the 2-state (BULL/BEAR) HMM design, and
generalized to run at ANY bar cadence (daily or hourly) via `bars_per_day`.

Key differences from the original 3-detector ensemble:
  - HMM component is TurboCoreRegimeDetectorV2 (2-state: BULL/BEAR only,
    no SIDEWAYS -- see regime_detector_v2.py docstring for rationale).
  - MSGARCHRegimeDetector is instantiated with n_regimes=2 to match.
  - BOCD's expected_run_length and confirmation_days are scaled by
    bars_per_day so a "6-month expected regime length" and "5-day
    confirmation" mean the same thing at daily or hourly cadence.
  - Voting logic simplifies from 2-of-3 to a 2-detector structural vote
    (HMM + MSGARCH) plus BOCD as a fast overlay -- with only two possible
    structural regimes (BULL/BEAR) there is no "mixed signal -> SIDEWAYS"
    fallback path; ties are broken by trusting the HMM (smoother, more
    robust detector) when MSGARCH disagrees, with BOCD able to force
    caution/deleverage on top of either outcome.

Voting logic (2-detector + fast overlay):
  BEAR:                 HMM=BEAR AND MSGARCH=BEAR (structural agreement)
  EMERGENCY_DELEVERAGE: BOCD fires + at least one of {HMM, MSGARCH}=BEAR
                         (returned as 'BEAR' regime, noted for logging)
  CAUTION:              BOCD fires alone (no structural BEAR agreement). The
                         ensemble only reports the flag; acting on it is the
                         allocator's job -- v3 halves the highest-leverage
                         sleeve held (TQQQ, else QLD) and moves the freed
                         weight to QQQ. See AllocationOptimizer.apply_caution.
  BULL:                  Default when no BEAR consensus and no BOCD-alone
                          fire (matches original ensemble's bias toward
                          staying invested; meta-model's continuous
                          confidence score handles graded conviction)
"""
import logging
from typing import Dict, Optional

import pandas as pd

from .regime_detector_v2 import TurboCoreRegimeDetectorV2
from .msgarch_detector import MSGARCHRegimeDetector
from .bocd_detector import BOCDRegimeBreak

logger = logging.getLogger(__name__)


class RegimeEnsembleV2:
    """
    Phase 3 v2 two-detector structural voting ensemble + BOCD fast overlay.

    Args:
        bars_per_day: 1.0 for daily bars, ~6.5 for hourly RTH bars. Scales
                      BOCD's expected_run_length/confirmation_days and is
                      passed through to the HMM component.
        model_tag:    disk-persistence suffix for the HMM component
                      ('daily' or 'hourly'), keeps daily/hourly-trained
                      models from colliding.
    """

    def __init__(self,
                 bars_per_day: float = 1.0,
                 model_tag: str = "daily",
                 cp_threshold: float = 0.25,
                 expected_run_length_days: float = 126.0,
                 confirmation_days: float = 5.0,
                 causal_hmm: bool = True):
        self.bars_per_day = bars_per_day
        # Phase 0.1: causal forward filtering instead of full-sequence Viterbi.
        # Only the ablation harness sets this False, to measure the fix's effect.
        self.causal_hmm = causal_hmm
        self.hmm = TurboCoreRegimeDetectorV2(bars_per_day=bars_per_day, model_tag=model_tag)
        self.hmm.load()

        self.msgarch = MSGARCHRegimeDetector(n_regimes=2)

        # NOTE on confirmation_days scaling: BOCD's changepoint posterior is
        # inherently spiky -- once a changepoint fires, the run-length resets
        # and next-bar probability naturally declines again measuring a fresh
        # short run. A literal day-count-scaled *consecutive* bar-hold
        # requirement (e.g. 5 days -> 33 hourly bars) is empirically almost
        # never satisfied (validated: max consecutive streak was 1 bar on
        # 7yrs of hourly QQQ data), silencing the detector entirely. At bar
        # cadence, single-bar threshold crossing already IS the fast/local
        # signal BOCD is meant to provide (paralleling the original daily
        # design's stated 1-2 day detection latency) -- so we use
        # confirmation_days=1 (immediate action on crossing) at any cadence
        # by default when bars_per_day > 1, unless explicitly overridden.
        if bars_per_day > 1.0 and confirmation_days >= 5.0:
            effective_confirmation_bars = 1
        else:
            effective_confirmation_bars = max(1, int(round(confirmation_days * bars_per_day)))

        self.bocd = BOCDRegimeBreak(
            expected_run_length=max(2, int(round(expected_run_length_days * bars_per_day))),
            cp_threshold=cp_threshold,
            confirmation_days=effective_confirmation_bars,
        )

    # ─── Training support ───────────────────────────────────────────────────

    def fit_msgarch(self, df: pd.DataFrame):
        """
        Fit MS-GARCH per regime using the (already-trained) 2-state HMM's
        labels for segmentation. `qqq_log_return` scale note: MS-GARCH's
        `avg_cv = conditional_volatility.mean()/100 * sqrt(252)` annualizes
        assuming ~252 obs/year; for hourly bars this needs bars_per_day
        scaling inside msgarch_detector.py OR we can compensate by scaling
        returns before fit. We compensate here: pass raw per-bar returns
        (not rescaled) -- msgarch_detector's annualization constant is only
        used for regime *labeling* (lowest vol = BULL, highest = BEAR),
        which is a relative ranking and is invariant to the annualization
        constant's absolute value. So no change needed to msgarch_detector
        itself; documented here for auditability.
        """
        if 'qqq_log_return' not in df.columns:
            logger.warning("qqq_log_return not in df -- cannot fit MS-GARCH.")
            return
        if not self.hmm.is_trained:
            logger.warning("HMM not trained -- cannot segment for MS-GARCH fit.")
            return

        hmm_df = self.hmm.predict_regimes(df, causal=self.causal_hmm)
        ml_regime_numeric = hmm_df['ml_regime'].map({'BULL': 0, 'BEAR': 1}).fillna(0).values.astype(int)

        returns = df['qqq_log_return'].dropna().values
        n_align = min(len(returns), len(ml_regime_numeric))
        self.msgarch.fit(returns[:n_align], ml_regime_numeric[:n_align])
        logger.info(f"MS-GARCH (2-regime) fit complete. Regime vol mapping: {self.msgarch.regime_vols}, "
                    f"names: {self.msgarch.regime_names}")

    # ─── Live/walk-forward single-step prediction ───────────────────────────

    def predict(self, df: pd.DataFrame) -> Dict:
        last_row = df.iloc[-1]
        if last_row.get('qqq_below_sma200_sell', False):
            return self._result('BEAR_SMA_FORCED', caution=False,
                                 hmm='BEAR_SMA_FORCED', msgarch='N/A', bocd_prob=0.0)

        try:
            hmm_df = self.hmm.predict_regimes(df, causal=self.causal_hmm)
            hmm_regime = str(hmm_df.iloc[-1].get('ml_regime', 'BULL'))
        except Exception as e:
            logger.debug(f"HMM prediction error: {e}")
            hmm_regime = 'BULL'

        try:
            if 'qqq_log_return' in df.columns and self.msgarch.is_trained:
                msgarch_regime = self.msgarch.predict_regime(df['qqq_log_return'].dropna().values)
            else:
                msgarch_regime = hmm_regime
        except Exception as e:
            logger.debug(f"MS-GARCH prediction error: {e}")
            msgarch_regime = hmm_regime

        try:
            if 'qqq_log_return' in df.columns:
                bocd_detected, bocd_prob = self.bocd.latest_cp_prob(df['qqq_log_return'].dropna())
            else:
                bocd_detected, bocd_prob = False, 0.0
        except Exception as e:
            logger.debug(f"BOCD prediction error: {e}")
            bocd_detected, bocd_prob = False, 0.0

        bear_votes = [hmm_regime, msgarch_regime].count('BEAR')

        if bocd_detected and bear_votes >= 1:
            return self._result('BEAR', caution=False, hmm=hmm_regime, msgarch=msgarch_regime,
                                 bocd_prob=bocd_prob, note='EMERGENCY_DELEVERAGE (BOCD+structural)')

        caution = bocd_detected and bear_votes == 0

        if bear_votes >= 2:
            return self._result('BEAR', caution=False, hmm=hmm_regime, msgarch=msgarch_regime, bocd_prob=bocd_prob)

        return self._result('BULL', caution=caution, hmm=hmm_regime, msgarch=msgarch_regime, bocd_prob=bocd_prob)

    @staticmethod
    def _result(regime: str, caution: bool, hmm: str, msgarch: str, bocd_prob: float, note: str = '') -> Dict:
        return {
            'regime': regime,
            'caution': caution,
            'hmm_regime': hmm,
            'msgarch_regime': msgarch,
            'bocd_cp_prob': round(bocd_prob, 4),
            'note': note,
        }

    # ─── Batch prediction for backtesting ───────────────────────────────────

    def predict_series(self, df: pd.DataFrame) -> pd.DataFrame:
        result_df = df.copy()
        result_df['ensemble_regime'] = 'BULL'
        result_df['ensemble_caution'] = False
        result_df['hmm_regime'] = 'BULL'
        result_df['msgarch_regime'] = 'BULL'
        result_df['bocd_cp_prob'] = 0.0

        try:
            hmm_df = self.hmm.predict_regimes(df, causal=self.causal_hmm)
            result_df['hmm_regime'] = hmm_df['ml_regime'].values
        except Exception as e:
            logger.warning(f"HMM batch predict failed: {e}")

        if 'qqq_log_return' in df.columns and self.msgarch.is_trained:
            msgarch_series = self.msgarch.predict_series(df['qqq_log_return'], window=int(round(20 * self.bars_per_day)))
            result_df['msgarch_regime'] = msgarch_series.reindex(result_df.index).fillna('BULL').values

        if 'qqq_log_return' in df.columns:
            bocd_result = self.bocd.update_batch(df['qqq_log_return'].dropna())
            result_df.loc[bocd_result.index, 'bocd_cp_prob'] = bocd_result['cp_prob'].values

        final_regimes = []
        final_caution = []
        hmm_col = result_df['hmm_regime'].values
        msgarch_col = result_df['msgarch_regime'].values
        bocd_col = result_df['bocd_cp_prob'].values
        sma_col = result_df['qqq_below_sma200_sell'].values if 'qqq_below_sma200_sell' in result_df.columns else [False] * len(result_df)

        for i in range(len(result_df)):
            if sma_col[i]:
                final_regimes.append('BEAR_SMA_FORCED')
                final_caution.append(False)
                continue

            hmm_r = hmm_col[i]
            msgarch_r = msgarch_col[i]
            bocd_p = bocd_col[i]
            bocd_det = bocd_p > self.bocd.cp_threshold
            bear_votes = [hmm_r, msgarch_r].count('BEAR')
            caution = bocd_det and bear_votes == 0

            if bocd_det and bear_votes >= 1:
                final_regimes.append('BEAR')
            elif bear_votes >= 2:
                final_regimes.append('BEAR')
            else:
                final_regimes.append('BULL')
            final_caution.append(caution)

        result_df['ensemble_regime'] = final_regimes
        result_df['ensemble_caution'] = final_caution
        return result_df
