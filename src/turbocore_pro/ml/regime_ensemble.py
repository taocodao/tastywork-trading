"""
Phase 3: 2-of-3 Regime Voting Ensemble

Combines three complementary regime detectors through a majority-vote mechanism:

  Detector 1: TurboCoreRegimeDetector (Gaussian HMM)
    - Strengths: Robust to noise, produces smooth transitions
    - Weakness:  5–10 day detection lag, daily BULL↔SIDEWAYS oscillation

  Detector 2: MSGARCHRegimeDetector
    - Strengths: Models volatility clustering, distinguishes "bull market turbulence"
                 from genuine bear onset via regime-specific GARCH dynamics
    - Weakness:  Requires fitting time, less precise for short-window slices

  Detector 3: BOCDRegimeBreak (fast crash signal)
    - Strengths: 1–2 day detection latency for genuine regime breaks
    - Weakness:  Higher false positive rate, requires 2-of-3 confirmation
    - Role:      CAUTION signal only when fired alone; BEAR trigger when confirmed

Voting logic:
  BULL:                 HMM=BULL AND MSGARCH=BULL (2-of-2 structural agreement)
  BEAR:                 (HMM=BEAR OR MSGARCH=BEAR) AND 2-of-3 total BEAR votes
  CAUTION (→50% LEAPS): BOCD fires alone (no structural BEAR consensus)
  EMERGENCY_DELEVERAGE: BOCD fires + (HMM=BEAR OR MSGARCH=BEAR)
  SIDEWAYS:             Default when no consensus

References:
  Ensemble HMM + XGBoost voting: AIMS Press DSFE 2025
  BOCD: Adams & MacKay 2007
  MSGARCH: Ardia et al. 2019
"""
import numpy as np
import pandas as pd
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

from .regime_detector  import TurboCoreRegimeDetector
from .msgarch_detector import MSGARCHRegimeDetector
from .bocd_detector    import BOCDRegimeBreak


class RegimeEnsemble:
    """
    Phase 3 three-detector voting ensemble for TurboCore Pro regime detection.

    Usage in walk-forward backtest:
        ensemble = RegimeEnsemble()
        result   = ensemble.predict(slice_df)
        regime   = result['regime']       # 'BULL'|'SIDEWAYS'|'BEAR'|...
        caution  = result['caution']      # True → halve LEAPS allocation

    Usage in production scheduler:
        ensemble = RegimeEnsemble()
        result   = ensemble.predict(master_df)
    """

    def __init__(self,
                 cp_threshold: float = 0.35,
                 expected_run_length: int = 250):
        self.hmm     = TurboCoreRegimeDetector()
        self.msgarch = MSGARCHRegimeDetector()
        self.bocd    = BOCDRegimeBreak(
            expected_run_length=expected_run_length,
            cp_threshold=cp_threshold,
        )

    # ─── Core prediction ──────────────────────────────────────────────────────

    def predict(self, df: pd.DataFrame) -> Dict:
        """
        Predict current regime from the full slice dataframe.

        Returns dict:
          regime:           Final voted regime string
          caution:          True = BOCD fired alone → halve LEAPS
          hmm_regime:       Raw HMM prediction
          msgarch_regime:   Raw MS-GARCH prediction
          bocd_cp_prob:     BOCD changepoint probability
          votes:            Vote tally dict
        """
        # ── SMA200 Hard Gate (always authoritative) ────────────────────────────
        last_row = df.iloc[-1]
        if last_row.get('qqq_below_sma200_sell', False):
            return self._result('BEAR_SMA_FORCED', caution=False,
                                hmm='BEAR_SMA_FORCED', msgarch='N/A', bocd_prob=0.0)

        # ── Detector 1: HMM ───────────────────────────────────────────────────
        try:
            hmm_df     = self.hmm.predict_regimes(df)
            hmm_regime = str(hmm_df.iloc[-1].get('ml_regime', 'SIDEWAYS'))
        except Exception as e:
            logger.debug(f"HMM prediction error: {e}")
            hmm_regime = 'SIDEWAYS'

        # ── Detector 2: MS-GARCH ──────────────────────────────────────────────
        try:
            if 'qqq_log_return' in df.columns and self.msgarch.is_trained:
                msgarch_regime = self.msgarch.predict_regime(
                    df['qqq_log_return'].dropna().values
                )
            else:
                msgarch_regime = hmm_regime   # Fallback alignment with HMM
        except Exception as e:
            logger.debug(f"MS-GARCH prediction error: {e}")
            msgarch_regime = hmm_regime

        # ── Detector 3: BOCD ──────────────────────────────────────────────────
        try:
            if 'qqq_log_return' in df.columns:
                returns = df['qqq_log_return'].dropna()
                bocd_detected, bocd_prob = self.bocd.latest_cp_prob(returns)
            else:
                bocd_detected, bocd_prob = False, 0.0
        except Exception as e:
            logger.debug(f"BOCD prediction error: {e}")
            bocd_detected, bocd_prob = False, 0.0

        # ── Voting Logic ──────────────────────────────────────────────────────
        structural_votes = [hmm_regime, msgarch_regime]
        bear_votes  = structural_votes.count('BEAR')
        bull_votes  = structural_votes.count('BULL')

        # EMERGENCY DELEVERAGE: BOCD fires + at least one structural detector agrees BEAR
        if bocd_detected and bear_votes >= 1:
            return self._result('BEAR', caution=False,
                                hmm=hmm_regime, msgarch=msgarch_regime,
                                bocd_prob=bocd_prob,
                                note='EMERGENCY_DELEVERAGE (BOCD+structural)')

        # CAUTION: BOCD fires alone (no structural BEAR consensus)
        caution = bocd_detected and bear_votes == 0

        # 2-of-2 structural consensus (HMM + MSGARCH agree)
        if bear_votes >= 2:
            return self._result('BEAR', caution=False,
                                hmm=hmm_regime, msgarch=msgarch_regime, bocd_prob=bocd_prob)

        if bull_votes >= 2:
            return self._result('BULL', caution=caution,
                                hmm=hmm_regime, msgarch=msgarch_regime, bocd_prob=bocd_prob)

        # Mixed signal: default SIDEWAYS (conservative)
        return self._result('SIDEWAYS', caution=caution,
                            hmm=hmm_regime, msgarch=msgarch_regime, bocd_prob=bocd_prob)

    @staticmethod
    def _result(regime: str, caution: bool,
                hmm: str, msgarch: str, bocd_prob: float,
                note: str = '') -> Dict:
        return {
            'regime':         regime,
            'caution':        caution,
            'hmm_regime':     hmm,
            'msgarch_regime': msgarch,
            'bocd_cp_prob':   round(bocd_prob, 4),
            'note':           note,
        }

    # ─── Training support ─────────────────────────────────────────────────────

    def fit_msgarch(self, df: pd.DataFrame):
        """
        Fit the MS-GARCH model using HMM-assigned regime labels as initial segmentation.
        
        Call once after the HMM is trained, on the full 7-year historical dataset.
        The HMM regime labels are used to segment returns into regime-specific slices,
        then GARCH(1,1) is fit per slice to learn volatility dynamics.
        """
        if 'qqq_log_return' not in df.columns:
            logger.warning("qqq_log_return not in df — cannot fit MS-GARCH.")
            return

        try:
            # Step 1: Get HMM labels for segmentation
            hmm_df = self.hmm.predict_regimes(df)
            ml_regime_numeric = hmm_df['ml_regime'].map({
                'BULL': 0, 'SIDEWAYS': 1, 'BEAR': 2
            }).fillna(1).values.astype(int)

            # Step 2: Fit GARCH per regime
            returns = df['qqq_log_return'].dropna().values
            # Align lengths
            n_align = min(len(returns), len(ml_regime_numeric))
            self.msgarch.fit(returns[:n_align], ml_regime_numeric[:n_align])
            logger.info("MS-GARCH fitting complete via ensemble.")
        except Exception as e:
            logger.error(f"MS-GARCH ensemble fitting failed: {e}")

    # ─── Batch prediction for backtesting ─────────────────────────────────────

    def predict_series(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Predict regime for every day in the dataframe (batch mode for backtesting).
        
        Unlike the walk-forward predict() which processes one day at a time,
        this uses rolling-window logic internally: each day's regime is determined
        from the last N rows. Useful for analysing the full ensemble output across
        different time periods without the walk-forward re-fitting cost.

        Returns: df with columns added:
          ensemble_regime, ensemble_caution, hmm_regime, msgarch_regime, bocd_cp_prob
        """
        result_df = df.copy()
        result_df['ensemble_regime']   = 'SIDEWAYS'
        result_df['ensemble_caution']  = False
        result_df['hmm_regime']        = 'SIDEWAYS'
        result_df['msgarch_regime']    = 'SIDEWAYS'
        result_df['bocd_cp_prob']      = 0.0

        # HMM: compute once on full df (cheaper than row-by-row)
        try:
            hmm_df = self.hmm.predict_regimes(df)
            result_df['hmm_regime'] = hmm_df['ml_regime'].values
        except Exception as e:
            logger.warning(f"HMM batch predict failed: {e}")

        # MSGARCH: rolling 20-day window
        if 'qqq_log_return' in df.columns and self.msgarch.is_trained:
            msgarch_series = self.msgarch.predict_series(df['qqq_log_return'])
            result_df['msgarch_regime'] = msgarch_series.values

        # BOCD: batch update
        if 'qqq_log_return' in df.columns:
            bocd_result = self.bocd.update_batch(df['qqq_log_return'].dropna())
            result_df.loc[bocd_result.index, 'bocd_cp_prob'] = bocd_result['cp_prob'].values

        # Apply SMA200 gate and voting per row
        final_regimes = []
        final_caution = []

        for idx, row in result_df.iterrows():
            if row.get('qqq_below_sma200_sell', False):
                final_regimes.append('BEAR_SMA_FORCED')
                final_caution.append(False)
                continue

            hmm_r     = row['hmm_regime']
            msgarch_r = row['msgarch_regime']
            bocd_p    = row['bocd_cp_prob']

            bocd_det  = bocd_p > self.bocd.cp_threshold
            bear_votes = [hmm_r, msgarch_r].count('BEAR')
            bull_votes = [hmm_r, msgarch_r].count('BULL')
            caution    = bocd_det and bear_votes == 0

            if bocd_det and bear_votes >= 1:
                final_regimes.append('BEAR')
            elif bear_votes >= 2:
                final_regimes.append('BEAR')
            elif bull_votes >= 2:
                final_regimes.append('BULL')
            else:
                final_regimes.append('SIDEWAYS')
            final_caution.append(caution)

        result_df['ensemble_regime']  = final_regimes
        result_df['ensemble_caution'] = final_caution
        return result_df
