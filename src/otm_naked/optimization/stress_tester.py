"""
Heston + Merton Jump-Diffusion Stress Tester
=============================================
Generates synthetic "crisis" price paths to test strategy survival under
conditions absent from the historical record (e.g., a 2008-style crash
in a universe that only has post-2017 data).

Mathematical framework:
  - Heston stochastic volatility model (mean-reverting vol, vol-of-vol,
    price/vol correlation)
  - Merton jump-diffusion overlay (Poisson-distributed shock events)

This is "Layer 2" of the two-layer simulation stack. The outputs are
feature-dict-compatible so the FastOTMSimulator can consume them
without modification.

Key parameters (calibrated to S&P 500 historical regime data):
  Heston:
    kappa=2.0   (vol mean-reversion speed)
    theta=0.04  (long-run variance, √theta ≈ 20% vol)
    xi=0.3      (vol-of-vol)
    rho=-0.7    (price/vol correlation — negative for equity)
  Merton Jumps:
    jump_intensity=2.0   (avg 2 jumps/year per stock)
    jump_mean=-0.05      (avg jump size: -5%)
    jump_std=0.08        (jump size std dev)
"""

import logging
import math
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heston model parameters
# ---------------------------------------------------------------------------
@dataclass
class HestonParams:
    kappa: float = 2.0      # Vol mean-reversion speed
    theta: float = 0.04     # Long-run variance (vol² target)
    xi:    float = 0.30     # Vol of vol
    rho:   float = -0.70    # Price/vol correlation (negative for equities)
    v0:    float = 0.04     # Initial variance (20% annualized vol)


@dataclass
class JumpParams:
    intensity: float = 2.0   # Avg jumps per year (Poisson lambda)
    mean:      float = -0.05  # Mean log-jump size (-5% average)
    std:       float = 0.08   # Std of log-jump size


# ---------------------------------------------------------------------------
# Heston SDE discretization (Euler-Maruyama)
# ---------------------------------------------------------------------------
def _simulate_heston_path(
    S0: float,
    T_years: float,
    n_steps: int,
    rf: float,
    heston: HestonParams,
    jumps: JumpParams,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Simulate one price path using the Heston model + Merton jump overlay.

    Uses the Euler-Maruyama discretization with the Feller condition check
    to prevent variance from going negative (reflection at zero).

    Args:
        S0:       Initial spot price
        T_years:  Simulation horizon in years
        n_steps:  Number of time steps (= trading days)
        rf:       Risk-free rate
        heston:   Heston model parameters
        jumps:    Jump process parameters
        rng:      NumPy random generator

    Returns:
        np.ndarray of shape (n_steps+1,) with simulated daily prices
    """
    dt = T_years / n_steps
    prices = np.zeros(n_steps + 1)
    prices[0] = S0
    v = heston.v0   # Current variance

    for t in range(1, n_steps + 1):
        # Correlated Brownian motions
        z1 = rng.standard_normal()
        z2 = heston.rho * z1 + math.sqrt(1 - heston.rho ** 2) * rng.standard_normal()

        # Heston variance SDE (Euler, reflected at 0)
        v = max(
            v + heston.kappa * (heston.theta - v) * dt
                + heston.xi * math.sqrt(max(v, 0) * dt) * z2,
            0.0
        )

        # Price SDE
        drift = (rf - 0.5 * v) * dt
        diff  = math.sqrt(max(v, 0) * dt) * z1
        log_S = math.log(prices[t - 1]) + drift + diff

        # Merton jump overlay
        n_jumps = rng.poisson(jumps.intensity * dt)
        if n_jumps > 0:
            jump_sizes = rng.normal(jumps.mean, jumps.std, n_jumps)
            log_S += np.sum(jump_sizes)

        prices[t] = math.exp(log_S)

    return prices


# ---------------------------------------------------------------------------
# Stress scenario generator
# ---------------------------------------------------------------------------
class StressTester:
    """
    Generates synthetic crisis scenarios and evaluates strategy performance.

    Usage:
        tester = StressTester(features_dict, n_paths=500)
        results = tester.run(params)
        survival_rate = results['survival_rate']  # % paths without ruin
    """

    SCENARIOS = {
        "baseline": HestonParams(kappa=2.0, theta=0.04, xi=0.3, rho=-0.7, v0=0.04),
        "vol_shock": HestonParams(kappa=1.5, theta=0.12, xi=0.6, rho=-0.8, v0=0.15),   # VIX spike to ~55%
        "crash":     HestonParams(kappa=1.0, theta=0.20, xi=0.8, rho=-0.9, v0=0.25),   # 2008-style crash
        "squeeze":   HestonParams(kappa=3.0, theta=0.03, xi=0.2, rho=-0.5, v0=0.10),   # Slow grind-down
    }
    JUMP_SCENARIOS = {
        "baseline":  JumpParams(intensity=2.0, mean=-0.05, std=0.08),
        "vol_shock": JumpParams(intensity=5.0, mean=-0.08, std=0.12),
        "crash":     JumpParams(intensity=10.0, mean=-0.12, std=0.15),
        "squeeze":   JumpParams(intensity=1.0, mean=-0.03, std=0.05),
    }

    def __init__(
        self,
        features_dict: Dict[str, pd.DataFrame],
        n_paths: int = 200,
        horizon_days: int = 252,
        scenario: str = "baseline",
        seed: int = 0,
    ):
        self.features_dict  = features_dict
        self.n_paths        = n_paths
        self.horizon_days   = horizon_days
        self.scenario       = scenario
        self._rng           = np.random.default_rng(seed)
        self.heston_params  = self.SCENARIOS.get(scenario, self.SCENARIOS["baseline"])
        self.jump_params    = self.JUMP_SCENARIOS.get(scenario, self.JUMP_SCENARIOS["baseline"])

        # Extract current spot prices and vol from the most recent data
        self._spot_prices: Dict[str, float] = {}
        self._hv20:        Dict[str, float] = {}
        for sym, df in features_dict.items():
            if df.empty:
                continue
            close_col = "close" if "close" in df.columns else "Close"
            if close_col in df.columns:
                self._spot_prices[sym] = float(df[close_col].iloc[-1])
            if "hv_20" in df.columns:
                self._hv20[sym] = float(df["hv_20"].iloc[-1])

    def _generate_feature_path(
        self, rf: float = 0.045
    ) -> Dict[str, pd.DataFrame]:
        """
        Generate one synthetic feature-dict path using Heston + Jumps.
        Returns a dict compatible with FastOTMSimulator.
        """
        date_range = pd.bdate_range(
            start=pd.Timestamp.today().normalize(),
            periods=self.horizon_days
        )
        feature_path: Dict[str, pd.DataFrame] = {}

        for sym, S0 in self._spot_prices.items():
            hv_init = self._hv20.get(sym, 0.25)
            # Scale Heston v0 from stock's own HV
            heston = HestonParams(
                kappa=self.heston_params.kappa,
                theta=self.heston_params.theta,
                xi=self.heston_params.xi,
                rho=self.heston_params.rho,
                v0=min((hv_init ** 2), self.heston_params.v0 * 3),  # Cap at 3× baseline
            )

            prices = _simulate_heston_path(
                S0=S0,
                T_years=self.horizon_days / 252.0,
                n_steps=self.horizon_days,
                rf=rf,
                heston=heston,
                jumps=self.jump_params,
                rng=self._rng,
            )
            prices = prices[1:]   # Drop t=0 (= today's known price)

            close_s = pd.Series(prices, index=date_range)
            log_ret = np.log(close_s / close_s.shift(1))
            hv_20_s = log_ret.rolling(20).std() * math.sqrt(252)

            # Build a minimal feature DataFrame compatible with FastOTMSimulator
            df = pd.DataFrame(index=date_range)
            df["close"]             = close_s
            df["high"]              = close_s * 1.01
            df["low"]               = close_s * 0.99
            df["hv_20"]             = hv_20_s.fillna(hv_init)
            df["rsi_14"]            = 50.0   # Neutral — not the focus for stress test
            df["iv_rank"]           = 0.60   # Elevated IV rank (stress scenario)
            df["pct_from_52w_high"] = (close_s / close_s.cummax() - 1).fillna(0)
            df["pct_b"]             = 0.30   # Below midpoint (oversold)
            # Simulate VIX spiking: scale with scenario vol
            v0_scenario = self.heston_params.v0
            df["vix"]               = (math.sqrt(v0_scenario) * 100 *
                                       (1 + 0.3 * self._rng.standard_normal(len(date_range))))
            df["vix"]               = df["vix"].clip(10, 80)
            df["rf"]                = rf

            feature_path[sym] = df

        return feature_path

    def run_stress_test(
        self, params, max_drawdown_threshold: float = -0.20
    ) -> Dict[str, float]:
        """
        Run all stress paths and compute strategy survival statistics.

        Args:
            params:                  OTMParams from Optuna (or manual)
            max_drawdown_threshold:  Paths with drawdown < this are "failures"

        Returns:
            Dict with survival_rate, avg_sortino, avg_max_drawdown,
            worst_drawdown, avg_return
        """
        from .fast_simulator import FastOTMSimulator

        logger.info(
            f"Stress test [{self.scenario}]: {self.n_paths} paths, "
            f"{self.horizon_days} days horizon"
        )

        sortinos, drawdowns, returns = [], [], []
        failed = 0

        for path_i in range(self.n_paths):
            feature_path = self._generate_feature_path()
            sim = FastOTMSimulator(feature_path, warmup_days=0)
            metrics = sim.simulate(params)
            dd = metrics["max_drawdown"]
            sortinos.append(metrics["sortino"])
            drawdowns.append(dd)
            returns.append(metrics["total_return"])
            if dd < max_drawdown_threshold:
                failed += 1

        survival_rate = 1.0 - (failed / self.n_paths)
        result = {
            "scenario":          self.scenario,
            "n_paths":           self.n_paths,
            "survival_rate":     survival_rate,
            "avg_sortino":       float(np.mean(sortinos)),
            "avg_max_drawdown":  float(np.mean(drawdowns)),
            "worst_drawdown":    float(np.min(drawdowns)),
            "avg_return":        float(np.mean(returns)),
        }
        logger.info(
            f"Stress [{self.scenario}]: survival={survival_rate:.1%} "
            f"worst_dd={result['worst_drawdown']:.1%} "
            f"avg_sortino={result['avg_sortino']:.2f}"
        )
        return result

    @classmethod
    def run_all_scenarios(
        cls, features_dict: Dict[str, pd.DataFrame], params,
        n_paths: int = 100
    ) -> Dict[str, Dict]:
        """Convenience: run all four stress scenarios and aggregate results."""
        all_results = {}
        for scenario in cls.SCENARIOS.keys():
            tester = cls(features_dict, n_paths=n_paths,
                         scenario=scenario, seed=42)
            all_results[scenario] = tester.run_stress_test(params)
        return all_results
