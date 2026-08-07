"""
TurboCore Pro v2 -- Live Calibration Drift Monitor
====================================================
Monitors whether the live feature distribution and model calibration have
drifted away from the training distribution, using two complementary
statistics:

  - PSI (Population Stability Index): standard industry metric for
    detecting distributional shift in a scored population. Buckets a
    reference (training) distribution into deciles, then compares the
    live distribution's bucket proportions against them.
        PSI < 0.10  -> no significant shift
        0.10-0.25   -> moderate shift, investigate
        > 0.25      -> major shift, retrain/review recommended

  - KS (Kolmogorov-Smirnov) two-sample test: nonparametric test of whether
    two samples are drawn from the same distribution. Used here per
    feature and on the model's predicted-confidence distribution, with a
    p-value threshold (default 0.01) for flagging drift.

Usage pattern (intended for live/paper deployment, not backtest-internal):
    monitor = DriftMonitor(reference_df=train_features_df,
                            reference_confidence=train_ml_confidence_array)
    report = monitor.check(live_window_df, live_confidence_array)
    if report['overall_flag']:
        # page/alert: feature or calibration drift detected
        ...

This module is intentionally decoupled from the walk-forward harness --
it is meant to run in the live/paper-trading loop (e.g. called once per
trading day or once per N hourly bars) to flag when a fold-style model
refresh is warranted before the next scheduled rolling-refit date.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

# Features tracked for input-distribution drift (subset of the v2 meta
# feature set most likely to shift regime-to-regime; deliberately excludes
# one-hot/boolean flags which PSI/KS are not well-suited for).
DEFAULT_DRIFT_FEATURES = [
    "qqq_log_return",
    "vix_intraday_momentum_6b",
    "hyg_intraday_momentum_6b",
    "hyg_mom_20b",
    "qqq_intraday_vol_6b",
    "volume_zscore_20d",
    "qqq_drawdown_ath",
    "vix_ratio",
]

PSI_MODERATE_THRESHOLD = 0.10
PSI_MAJOR_THRESHOLD = 0.25
KS_PVALUE_THRESHOLD = 0.01
N_BUCKETS = 10


def _psi_for_series(reference: np.ndarray, live: np.ndarray, n_buckets: int = N_BUCKETS) -> float:
    """Population Stability Index between a reference and live 1-D sample."""
    reference = reference[~np.isnan(reference)]
    live = live[~np.isnan(live)]
    if len(reference) < n_buckets or len(live) < 5:
        return float("nan")

    quantiles = np.linspace(0, 100, n_buckets + 1)
    edges = np.unique(np.percentile(reference, quantiles))
    if len(edges) < 3:
        return 0.0  # degenerate reference distribution (near-constant)

    ref_counts, _ = np.histogram(reference, bins=edges)
    live_counts, _ = np.histogram(live, bins=edges)

    ref_pct = np.clip(ref_counts / max(ref_counts.sum(), 1), 1e-6, None)
    live_pct = np.clip(live_counts / max(live_counts.sum(), 1), 1e-6, None)

    psi = np.sum((live_pct - ref_pct) * np.log(live_pct / ref_pct))
    return float(psi)


def _ks_for_series(reference: np.ndarray, live: np.ndarray) -> tuple[float, float]:
    reference = reference[~np.isnan(reference)]
    live = live[~np.isnan(live)]
    if len(reference) < 10 or len(live) < 10:
        return float("nan"), float("nan")
    stat, pvalue = stats.ks_2samp(reference, live)
    return float(stat), float(pvalue)


@dataclass
class DriftMonitor:
    reference_df: pd.DataFrame
    reference_confidence: np.ndarray | None = None
    features: list = field(default_factory=lambda: list(DEFAULT_DRIFT_FEATURES))
    psi_moderate: float = PSI_MODERATE_THRESHOLD
    psi_major: float = PSI_MAJOR_THRESHOLD
    ks_pvalue_threshold: float = KS_PVALUE_THRESHOLD

    def check(self, live_df: pd.DataFrame, live_confidence: np.ndarray | None = None) -> dict:
        """
        Compare a live window against the stored reference distribution.

        Returns a dict:
          {
            'feature_report': {feat: {'psi':..., 'ks_stat':..., 'ks_pvalue':..., 'flag': 'ok'|'moderate'|'major'}},
            'confidence_report': {'psi':..., 'ks_stat':..., 'ks_pvalue':..., 'flag': ...} or None,
            'overall_flag': bool,   # True if ANY major-level drift detected
            'summary': str,
          }
        """
        feature_report = {}
        any_major = False
        any_moderate = False

        for feat in self.features:
            if feat not in self.reference_df.columns or feat not in live_df.columns:
                continue
            ref_vals = self.reference_df[feat].astype(float).values
            live_vals = live_df[feat].astype(float).values

            psi = _psi_for_series(ref_vals, live_vals)
            ks_stat, ks_p = _ks_for_series(ref_vals, live_vals)

            flag = "ok"
            if (not np.isnan(psi) and psi >= self.psi_major) or (not np.isnan(ks_p) and ks_p < self.ks_pvalue_threshold):
                flag = "major"
                any_major = True
            elif not np.isnan(psi) and psi >= self.psi_moderate:
                flag = "moderate"
                any_moderate = True

            feature_report[feat] = {
                "psi": round(psi, 4) if not np.isnan(psi) else None,
                "ks_stat": round(ks_stat, 4) if not np.isnan(ks_stat) else None,
                "ks_pvalue": round(ks_p, 4) if not np.isnan(ks_p) else None,
                "flag": flag,
            }

        confidence_report = None
        if self.reference_confidence is not None and live_confidence is not None:
            ref_c = np.asarray(self.reference_confidence, dtype=float)
            live_c = np.asarray(live_confidence, dtype=float)
            psi_c = _psi_for_series(ref_c, live_c)
            ks_stat_c, ks_p_c = _ks_for_series(ref_c, live_c)
            flag_c = "ok"
            if (not np.isnan(psi_c) and psi_c >= self.psi_major) or (not np.isnan(ks_p_c) and ks_p_c < self.ks_pvalue_threshold):
                flag_c = "major"
                any_major = True
            elif not np.isnan(psi_c) and psi_c >= self.psi_moderate:
                flag_c = "moderate"
                any_moderate = True
            confidence_report = {
                "psi": round(psi_c, 4) if not np.isnan(psi_c) else None,
                "ks_stat": round(ks_stat_c, 4) if not np.isnan(ks_stat_c) else None,
                "ks_pvalue": round(ks_p_c, 4) if not np.isnan(ks_p_c) else None,
                "flag": flag_c,
            }

        if any_major:
            summary = "MAJOR drift detected -- recommend triggering an out-of-cycle model refit/review."
        elif any_moderate:
            summary = "Moderate drift detected -- monitor closely; consider refit at next scheduled window."
        else:
            summary = "No significant drift detected."

        return {
            "feature_report": feature_report,
            "confidence_report": confidence_report,
            "overall_flag": any_major,
            "any_moderate": any_moderate,
            "summary": summary,
        }

    @staticmethod
    def format_report(report: dict) -> str:
        lines = [f"Drift Monitor Report -- {report['summary']}", ""]
        lines.append(f"{'Feature':<28} {'PSI':>8} {'KS stat':>10} {'KS p-val':>10} {'Flag':>10}")
        for feat, r in report["feature_report"].items():
            lines.append(f"{feat:<28} {str(r['psi']):>8} {str(r['ks_stat']):>10} "
                          f"{str(r['ks_pvalue']):>10} {r['flag']:>10}")
        if report["confidence_report"]:
            r = report["confidence_report"]
            lines.append("")
            lines.append(f"{'ml_confidence':<28} {str(r['psi']):>8} {str(r['ks_stat']):>10} "
                          f"{str(r['ks_pvalue']):>10} {r['flag']:>10}")
        return "\n".join(lines)
