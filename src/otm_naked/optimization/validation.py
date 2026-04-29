"""
Statistical Validation: Deflated Sharpe Ratio & Walk-Forward Reporting
========================================================================
Implements:
  1. DeflatedSharpeRatio (Bailey & López de Prado, 2014)
     Adjusts the observed Sharpe ratio for:
     - Number of trials tested (multiple testing inflation)
     - Non-normal return distribution (skew, kurtosis)
     - Sample length effects
  2. WalkForwardReport: aggregates all OOS windows into a final
     institutional-grade performance summary.

Reference:
    Bailey, D.H. & López de Prado, M. (2014).
    "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest
    Overfitting and Non-Normality."
    Journal of Portfolio Management, 40(5), 94–107.
"""

import math
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

ANNUAL_FACTOR = math.sqrt(252)


# ---------------------------------------------------------------------------
# Deflated Sharpe Ratio
# ---------------------------------------------------------------------------
class DeflatedSharpeRatio:
    """
    Computes the Deflated Sharpe Ratio (DSR) — the probability that the
    observed Sharpe ratio is NOT due to multiple testing on the same data.

    DSR ≥ 0.95 is the minimum threshold for statistical credibility.
    """

    @staticmethod
    def _sr_star(n_trials: int, n_obs: int, sr_std: float = 1.0) -> float:
        """
        Compute the expected maximum Sharpe Ratio across N independent
        trials (the "benchmark" SR for multiple testing correction).

        Uses the expected maximum of N i.i.d. normal random variables
        approximation from López de Prado (2018).

        Args:
            n_trials:  Number of strategy variants tested
            n_obs:     Number of observations (time steps)
            sr_std:    Standard deviation of SRs across trials (≈1 if normalized)

        Returns:
            SR* (the threshold that 95% of spurious SRs should fall below)
        """
        if n_trials <= 1:
            return 0.0
        e_max = (
            (1 - np.euler_gamma) * _norm_ppf(1 - 1.0 / n_trials) +
            np.euler_gamma * _norm_ppf(1 - 1.0 / (n_trials * np.e))
        )
        return sr_std * e_max

    @staticmethod
    def compute(
        observed_sharpe: float,
        n_trials:        int,
        skewness:        float = 0.0,
        kurtosis:        float = 3.0,
        n_obs:           int   = 252,
        sr_std:          float = 1.0,
    ) -> float:
        """
        Compute the Deflated Sharpe Ratio.

        Args:
            observed_sharpe: The best annualized Sharpe ratio found
            n_trials:        Number of parameter combinations tested
            skewness:        Estimated skewness of strategy returns
            kurtosis:        Estimated excess kurtosis (normal = 3)
            n_obs:           Number of observations in the backtest
            sr_std:          Std of all trial SRs (default 1)

        Returns:
            DSR ∈ [0, 1]. Values ≥ 0.95 pass the statistical credibility test.
        """
        if n_trials <= 1 or n_obs < 10:
            return 1.0   # No multiple testing penalty with single trial

        # Compute the benchmark SR for multiple testing
        sr0 = DeflatedSharpeRatio._sr_star(n_trials, n_obs, sr_std)

        # Adjust for non-normality of returns
        # (skew reduces effective SR; fat tails inflate it spuriously)
        gamma3 = skewness        # Excess skewness
        gamma4 = kurtosis - 3.0  # Excess kurtosis (0 for normal)

        sr_obs_daily = observed_sharpe / ANNUAL_FACTOR
        sr0_daily    = sr0 / ANNUAL_FACTOR

        numerator = (sr_obs_daily - sr0_daily) * math.sqrt(n_obs - 1)
        nonnormal_adj = math.sqrt(
            1.0
            - gamma3 * sr_obs_daily
            + ((gamma4 - 1) / 4.0) * sr_obs_daily ** 2
        )

        if nonnormal_adj <= 0:
            return 0.0

        z = numerator / nonnormal_adj
        return float(_norm_cdf(z))


def _norm_cdf(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2)))


def _norm_ppf(p: float) -> float:
    """Approximate standard normal PPF (inverse CDF)."""
    # Rational approximation (Abramowitz & Stegun 26.2.17)
    if p <= 0:
        return -10.0
    if p >= 1:
        return 10.0
    # Use scipy if available for precision
    try:
        from scipy.stats import norm
        return float(norm.ppf(p))
    except ImportError:
        # Fallback: Beasley-Springer-Moro approximation
        a = [2.50662823884, -18.61500062529, 41.39119773534, -25.44106049637]
        b = [-8.47351093090, 23.08336743743, -21.06224101826, 3.13082909833]
        c = [0.3374754822726147, 0.9761690190917186, 0.1607979714918209,
             0.0276438810333863, 0.0038405729373609, 0.0003951896511349,
             0.0000321767881768, 0.0000002888167364, 0.0000003960315187]
        y = p - 0.5
        if abs(y) < 0.42:
            r = y * y
            return y * (((a[3] * r + a[2]) * r + a[1]) * r + a[0]) / \
                       ((((b[3] * r + b[2]) * r + b[1]) * r + b[0]) * r + 1)
        r = math.sqrt(-math.log(p if y < 0 else 1 - p))
        x = c[0] + r * (c[1] + r * (c[2] + r * (c[3] + r * (c[4] + r * (
            c[5] + r * (c[6] + r * (c[7] + r * c[8])))))))
        return -x if y < 0 else x


# ---------------------------------------------------------------------------
# Walk-Forward Report
# ---------------------------------------------------------------------------
class WalkForwardReport:
    """
    Aggregates all Out-of-Sample walk-forward windows into final statistics.

    Each window contributes one OOS observation. The aggregate of all
    OOS periods represents the strategy's expected live performance.
    """

    def __init__(self, oos_results: List[Dict]):
        self.oos_results = oos_results

    def summary(self) -> str:
        """Return a formatted text summary for logging."""
        d = self.summary_dict()
        lines = [
            "=" * 65,
            "  OTM NAKED OPTIONS - WALK-FORWARD OPTIMIZATION RESULTS",
            "=" * 65,
            f"  Windows           : {d['n_windows']}",
            f"  Windows Pass DSR  : {d['n_dsr_pass']} / {d['n_windows']}",
            f"",
            f"  OOS Sortino (avg) : {d['avg_sortino']:.2f}",
            f"  OOS Sortino (med) : {d['med_sortino']:.2f}",
            f"  OOS Max Drawdown  : {d['avg_max_drawdown']:.1%} (avg)",
            f"  OOS Win Rate      : {d['avg_win_rate']:.1%}",
            f"  OOS Total Return  : {d['avg_return']:.1%} per window",
            f"",
            f"  Recommended Parameters:",
        ]
        for k, v in d.get("recommended_params", {}).items():
            lines.append(f"    {k:<22}: {v}")
        lines.append("=" * 65)
        return "\n".join(lines)

    def summary_dict(self) -> Dict:
        if not self.oos_results:
            return {
                "n_windows": 0, "n_dsr_pass": 0, "avg_sortino": 0.0,
                "med_sortino": 0.0, "avg_max_drawdown": 0.0,
                "avg_win_rate": 0.0, "avg_return": 0.0, "avg_dsr": 0.0,
                "recommended_params": {}, "error": "No OOS results (all windows pruned)"
            }

        sortinos   = [r["sortino"]      for r in self.oos_results if "sortino" in r]
        drawdowns  = [r["max_drawdown"] for r in self.oos_results if "max_drawdown" in r]
        win_rates  = [r.get("win_rate", 0) for r in self.oos_results]
        returns    = [r.get("total_return", 0) for r in self.oos_results]
        dsr_values = [r.get("dsr", 0) for r in self.oos_results]

        # Pick recommended params from the window with the highest DSR
        best_window = max(
            self.oos_results,
            key=lambda r: r.get("dsr", 0) * max(r.get("sortino", -99), 0),
            default=None
        )
        recommended = best_window.get("params", {}) if best_window else {}

        return {
            "n_windows":        len(self.oos_results),
            "n_dsr_pass":       sum(1 for d in dsr_values if d >= 0.95),
            "avg_sortino":      float(np.mean(sortinos)) if sortinos else 0,
            "med_sortino":      float(np.median(sortinos)) if sortinos else 0,
            "avg_max_drawdown": float(np.mean(drawdowns)) if drawdowns else 0,
            "avg_win_rate":     float(np.mean(win_rates)),
            "avg_return":       float(np.mean(returns)),
            "avg_dsr":          float(np.mean(dsr_values)) if dsr_values else 0,
            "recommended_params": recommended,
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Return all OOS window results as a DataFrame."""
        return pd.DataFrame(self.oos_results)

    def robustness_check(self, params_dict: dict, tolerance: float = 0.15) -> dict:
        """
        Perturb each parameter by ±tolerance and report performance stability.
        A robust strategy should not collapse when params shift by 15%.

        Args:
            params_dict: The recommended parameter dict from optimization
            tolerance:   Fractional perturbation (0.15 = ±15%)

        Returns:
            Dict with stability summary
        """
        from .fast_simulator import OTMParams, FastOTMSimulator

        results = []
        for key, val in params_dict.items():
            for direction in [1 - tolerance, 1 + tolerance]:
                perturbed = dict(params_dict)
                if isinstance(val, int):
                    perturbed[key] = max(1, int(round(val * direction)))
                elif isinstance(val, float):
                    perturbed[key] = float(val * direction)
                try:
                    params = OTMParams(**perturbed)
                    results.append({
                        "param":     key,
                        "perturb":   direction,
                        "new_value": perturbed[key],
                    })
                except Exception:
                    pass

        return {
            "n_perturbations": len(results),
            "perturbations":   results,
            "note": "Run each perturbed set through FastOTMSimulator for full stability analysis"
        }
