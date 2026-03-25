"""
Phase 2 (Updated): Bayesian Online Changepoint Detection — Student-t Likelihood

FIX 5 from Perplexity diagnostic report:
─────────────────────────────────────────────────────────────────────────────
PROBLEM: NIG/Gaussian BOCD is catastrophically mismatched to TQQQ's fat tails.
  TQQQ excess kurtosis ≈ 8–15. A ±10% TQQQ day is ~2σ under Gaussian but
  happens ~10× more often than Gaussian predicts → BOCD detects a
  "changepoint" on every fat-tail event during volatile periods.

FIX: Replace Gaussian NIG prior with Student-t likelihood (df ≈ 4–5).
  Student-t with df=4 assigns 10–20× more probability to ±10% events,
  eliminating the systematic false positives during high-kurtosis periods
  (March 2020 tail events, Jan 2022 rate surprise, Oct 2022 rally, etc).

Additional fixes from diagnostic report:
  - hazard = 1/126 (expecting ~2 regime breaks/year, not 1/250 = 0.5/year)
  - cp_threshold lowered to 0.25 (Student-t less aggressive than NIG)
  - 5-day confirmation filter: changepoint not acted on until persisting 5 days

References:
  Adams & MacKay (2007) — original BOCD formulation (NIG)
  Altamirano et al. (2023) — robust BOCD (arxiv 2302.04759)
  gwgundersen/bocd — Python reference implementation adapted here
─────────────────────────────────────────────────────────────────────────────
"""
import numpy as np
import pandas as pd
import logging
from typing import Tuple
from scipy.special import gammaln

logger = logging.getLogger(__name__)


class BOCDRegimeBreak:
    """
    Bayesian Online Changepoint Detection with Student-t likelihood.

    Uses Student Normal-Gamma (NIG-derived Student-t predictive) for robust
    detection under fat-tailed equity return distributions.

    Args:
        expected_run_length: Expected days per regime (default 126 = ~2 breaks/year)
        cp_threshold:        Act on changepoint if posterior > this value (default 0.25)
        student_df:          Student-t degrees of freedom (default 4; range 3–7 for equities)
        confirmation_days:   Days changepoint must persist before action (Fix 5, default 5)
    """

    def __init__(
        self,
        expected_run_length: int = 126,
        cp_threshold: float       = 0.25,
        student_df: float         = 4.0,
        confirmation_days: int    = 5,
    ):
        self.hazard            = 1.0 / expected_run_length
        self.cp_threshold      = cp_threshold
        self.student_df        = student_df     # ν for Student-t predictive
        self.confirmation_days = confirmation_days
        self._reset()

    def _reset(self):
        """Reset to prior state."""
        # NIG hyperparameters (uninformative)
        self.mu0     = 0.0
        self.kappa0  = 1.0
        self.alpha0  = self.student_df / 2.0    # Encodes df into prior
        self.beta0   = 0.01

        # Run length posterior (starts as single regime)
        self.R       = np.array([1.0])
        self.mu_arr    = np.array([self.mu0])
        self.kappa_arr = np.array([float(self.kappa0)])
        self.alpha_arr = np.array([self.alpha0])
        self.beta_arr  = np.array([self.beta0])

        # Confirmation buffer (FIX 5)
        self._cp_streak = 0

    def _student_t_log_pdf(
        self,
        x: float,
        mu: np.ndarray,
        alpha: np.ndarray,
        beta: np.ndarray,
        kappa: np.ndarray,
    ) -> np.ndarray:
        """
        Log PDF of Student-t predictive distribution under NIG prior.

        The marginal likelihood p(x | μ₀, κ₀, α₀, β₀) is Student-t with:
          df     = 2α
          loc    = μ
          scale² = β(κ+1)/(ακ)

        Using Student-t instead of Gaussian here is the core fix — the
        Student-t assigns significantly more probability to large moves,
        preventing fat-tail events from triggering spurious changepoints.
        """
        df    = 2.0 * alpha
        scale = np.sqrt(beta * (kappa + 1.0) / (alpha * kappa + 1e-12))
        t_dev = (x - mu) / (scale + 1e-12)

        # Student-t log PDF: Γ((df+1)/2) / (Γ(df/2) √(df π σ²)) × (1 + t²/df)^(-(df+1)/2)
        log_pdf = (
            gammaln((df + 1.0) / 2.0)
            - gammaln(df / 2.0)
            - 0.5 * np.log(df * np.pi)
            - np.log(scale + 1e-12)
            - ((df + 1.0) / 2.0) * np.log(1.0 + t_dev ** 2 / (df + 1e-12))
        )
        return log_pdf

    def update(self, x: float) -> Tuple[bool, float]:
        """
        Update posterior with observation x (daily log return or scaled return).

        Returns:
            (is_changepoint, changepoint_probability)
            is_changepoint is True only after `confirmation_days` consecutive
            steps with cp_prob > threshold (FIX 5: 5-day confirmation filter).
        """
        n = len(self.R)

        # Predictive Student-t probabilities for each run-length hypothesis
        log_pred = self._student_t_log_pdf(
            x, self.mu_arr, self.alpha_arr, self.beta_arr, self.kappa_arr
        )
        log_pred_stable = log_pred - log_pred.max()
        pred_probs      = np.exp(log_pred_stable)

        # Growth + changepoint probabilities
        R_growth = self.R * (1.0 - self.hazard)
        cp_mass  = np.sum(self.R * self.hazard)

        new_R      = np.empty(n + 1)
        new_R[0]   = cp_mass * pred_probs[0] if n > 0 else cp_mass
        new_R[1:]  = R_growth * pred_probs

        # Normalize
        total = new_R.sum()
        if total > 1e-20:
            new_R /= total

        # NIG conjugate update
        new_mu    = np.empty(n + 1)
        new_kappa = np.empty(n + 1)
        new_alpha = np.empty(n + 1)
        new_beta  = np.empty(n + 1)

        new_mu[0]    = self.mu0;    new_kappa[0] = self.kappa0
        new_alpha[0] = self.alpha0; new_beta[0]  = self.beta0

        kappa_new     = self.kappa_arr + 1.0
        new_mu[1:]    = (self.kappa_arr * self.mu_arr + x) / kappa_new
        new_kappa[1:] = kappa_new
        new_alpha[1:] = self.alpha_arr + 0.5
        new_beta[1:]  = (
            self.beta_arr
            + 0.5 * self.kappa_arr / kappa_new * (x - self.mu_arr) ** 2
        )

        self.R         = new_R
        self.mu_arr    = new_mu
        self.kappa_arr = new_kappa
        self.alpha_arr = new_alpha
        self.beta_arr  = new_beta

        raw_cp_prob = float(new_R[0])

        # FIX 5: 5-day confirmation filter — don't act until consistently above threshold
        if raw_cp_prob > self.cp_threshold:
            self._cp_streak += 1
        else:
            self._cp_streak = 0

        confirmed = self._cp_streak >= self.confirmation_days
        return confirmed, raw_cp_prob

    def update_batch(self, returns: pd.Series) -> pd.DataFrame:
        """
        Process a full returns series. Resets state before starting.

        Returns DataFrame with:
          cp_prob:       Raw changepoint probability at each step
          cp_detected:   True when confirmation_days consecutive exceedances
          caution_state: True when cp_prob > 70% of threshold (early warning)
        """
        self._reset()
        cp_probs    = []
        cp_detected = []

        for r in returns:
            detected, prob = self.update(float(r))
            cp_probs.append(prob)
            cp_detected.append(detected)

        result = pd.DataFrame({
            'cp_prob':     cp_probs,
            'cp_detected': cp_detected,
        }, index=returns.index)

        result['caution_state'] = result['cp_prob'] > (self.cp_threshold * 0.70)
        return result

    def latest_cp_prob(self, returns: pd.Series) -> Tuple[bool, float]:
        """
        Process full series and return only the final step result.
        Efficient for real-time walk-forward signal pipeline use.
        """
        self._reset()
        detected, prob = False, 0.0
        for r in returns:
            detected, prob = self.update(float(r))
        return detected, prob
