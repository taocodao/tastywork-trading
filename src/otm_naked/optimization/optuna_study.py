"""
Bayesian Optimization Study (Optuna) — v2: Multi-Objective NSGA-II
=====================================================================
Finds the optimal OTMParams for the naked put selling strategy.

v2 changes vs v1:
  - Switched from single-objective TPE → multi-objective NSGA-II (NSGAIISampler)
  - Objective 1: Sortino + log-barrier drawdown penalty (smooth gradient, no cliff)
  - Objective 2: Log-scale trade frequency penalty (eliminates degenerate 0-trade solution)
  - Anti-paradox guard: penalizes highly-selective entries paired with tight stop-losses
  - Pareto front selection: picks best Sortino among trials with >= min_trades_per_year
  - Removed MedianPruner (incompatible with NSGA-II)

Architecture:
  1. OUTER loop: Walk-Forward windows (IS train / OOS test)
  2. INNER loop per IS window: Optuna NSGA-II Pareto study over SBB paths
     - Each trial samples OTMParams and returns (sortino_obj, frequency_obj)
     - DSR filter still applied post-hoc to reject curve-fit Pareto solutions
  3. Best Pareto trial → evaluated on OOS window (unseen data)
  4. All OOS metrics aggregated for final parameter reporting

EC2 Usage:
    python -m src.otm_naked.optimization.optuna_study \\
        --start 2018-01-01 --end 2025-12-31 \\
        --n-trials 300 --n-paths 100 --n-jobs 16

Local quick test:
    python -m src.otm_naked.optimization.optuna_study \\
        --start 2022-01-01 --end 2025-12-31 \\
        --n-trials 50 --n-paths 10 --n-jobs 1
"""

import os
import sys
import json
import math
import logging
import argparse
import warnings
from pathlib import Path
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

logger = logging.getLogger("OTMNakedOptimizer")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s"
)

from src.otm_naked.config import OTMNakedConfig
from src.otm_naked.feature_engineering import build_all_features
from src.otm_naked.optimization.sbb_generator import StationaryBlockBootstrap
from src.otm_naked.optimization.fast_simulator import FastOTMSimulator, OTMParams
from src.otm_naked.optimization.validation import DeflatedSharpeRatio, WalkForwardReport


# ---------------------------------------------------------------------------
# Log-barrier drawdown penalty (replaces hard -25% gate)
# ---------------------------------------------------------------------------
def _log_barrier_drawdown(max_dd: float, dd_limit: float = -0.25,
                           mu: float = 5.0) -> float:
    """
    Smooth log-barrier penalty for drawdown constraint.

    Returns a small penalty when max_dd is well within the limit,
    escalating asymptotically as max_dd approaches dd_limit.
    Returns 1000.0 (hard but finite) for constraint violations.

    Why finite (not infinite): allows TPE surrogate to learn a gradient
    near the constraint boundary rather than encountering a discontinuous cliff.

    Args:
        max_dd:   Realized max drawdown (negative number, e.g. -0.15)
        dd_limit: Drawdown limit (negative number, e.g. -0.25)
        mu:       Barrier sharpness (higher = steeper near limit)
    """
    slack = max_dd - dd_limit   # positive when within limit, negative when violated
    if slack <= 0:
        return 1000.0           # Hard violation — catastrophic but finite
    return -(1.0 / mu) * math.log(slack)


# ---------------------------------------------------------------------------
# Optuna multi-objective function (v2: NSGA-II compatible)
# ---------------------------------------------------------------------------
def _make_objective(
    sbb_paths: List[Dict[str, pd.DataFrame]],
    trial_count_ref: list,
    warmup_days: int = 252,
    test_years: float = 3.0,          # IS window size in years (756d / 252 ≈ 3)
    target_trades_per_year: float = 8.0,  # Capital deployment target
    min_trades_threshold: float = 1.0,    # Early exit if median < this after 5 paths
):
    """
    Returns an Optuna multi-objective function for NSGA-II.

    Returns (obj1, obj2):
      obj1 = -(Sortino) + log_barrier_drawdown  → minimize (higher Sortino = lower obj1)
      obj2 = log-frequency-penalty              → minimize (more trades = lower obj2)

    Both objectives are minimized; Optuna finds the Pareto front.
    """
    def objective(trial: optuna.Trial) -> Tuple[float, float]:
        trial_count_ref[0] += 1

        # ── Anti-paradox guard ────────────────────────────────────────────────
        # Highly selective entries (high iv_pct) + tight stops = optimizer avoids
        # all trades and paradoxically achieves 0 drawdown with 0 return.
        iv_pct_threshold = trial.suggest_float("iv_pct_threshold", 0.25, 0.70)
        stop_mult        = trial.suggest_float("stop_loss_mult", 1.5, 4.0)
        if iv_pct_threshold > 0.65 and stop_mult < 2.0:
            return 50.0, 1000.0   # Immediately penalized — signal to NSGA-II

        # ── Sample full parameter space ────────────────────────────────────────
        params = OTMParams(
            dte                  = trial.suggest_int("dte", 21, 60),
            put_delta            = trial.suggest_float("put_delta", 0.08, 0.20),
            pct_from_52w_high    = trial.suggest_float("pct_from_52w_high", 0.05, 0.25),
            iv_pct_threshold     = iv_pct_threshold,
            iv_hv_min            = trial.suggest_float("iv_hv_min", 1.0, 1.5),
            vix_slope_threshold  = trial.suggest_float("vix_slope_threshold", -0.10, 0.05),
            profit_take_pct      = trial.suggest_float("profit_take_pct", 0.40, 0.80),
            stop_loss_mult       = stop_mult,
            time_exit_dte        = trial.suggest_int("time_exit_dte", 3, 14),
            max_risk_pct         = trial.suggest_float("max_risk_pct", 0.005, 0.03),
            max_positions        = trial.suggest_int("max_positions", 2, 8),
        )

        # ── Run simulation on all SBB paths ───────────────────────────────────
        sortinos     = []
        drawdowns    = []
        trade_counts = []

        for path_idx, path_features in enumerate(sbb_paths):
            sim     = FastOTMSimulator(path_features, warmup_days=warmup_days)
            metrics = sim.simulate(params)
            sortinos.append(metrics["sortino"])
            drawdowns.append(metrics["max_drawdown"])
            trade_counts.append(metrics["n_trades"])

            # Early exit: after 5 paths, if median trades < 1, this config never trades
            if path_idx == 4:
                if float(np.median(trade_counts)) < min_trades_threshold:
                    return 50.0, 1000.0   # Ghost strategy — penalize hard

        # Use median (robust to outlier Monte Carlo paths) + p95 drawdown (worst-case path)
        median_sortino = float(np.median(sortinos))
        p95_drawdown   = float(np.percentile(drawdowns, 95))  # Worst 5% path
        median_trades  = float(np.median(trade_counts))

        # ── Objective 1: Risk-adjusted return with log-barrier ────────────────
        # Negated because Optuna minimizes; log-barrier replaces hard -25% gate
        barrier = _log_barrier_drawdown(p95_drawdown, dd_limit=-0.25, mu=5.0)
        obj1 = -median_sortino + barrier

        # ── Objective 2: Trade frequency penalty (log-scale) ──────────────────
        # Log scale: penalizes 0→1 more harshly than 10→11
        # Target: target_trades_per_year × is_window_years
        target_total = target_trades_per_year * test_years
        if median_trades < 1.0:
            obj2 = 1000.0   # Catastrophic: zero trades = degenerate solution
        else:
            obj2 = (math.log(max(target_total, 1)) - math.log(median_trades)) ** 2

        # Store for Pareto selection logic
        trial.set_user_attr("median_sortino", median_sortino)
        trial.set_user_attr("p95_drawdown",   p95_drawdown)
        trial.set_user_attr("median_trades",  median_trades)

        return obj1, obj2

    return objective


import multiprocessing as mp


def _optuna_worker_nsga2(db_path: str, study_name: str, window: int,
                          worker_idx: int, n_trials_chunk: int,
                          sbb_paths: list, warmup_days: int,
                          test_years: float, target_trades_per_year: float):
    """Worker process for parallel NSGA-II trials via SQLite shared storage."""
    local_study = optuna.load_study(
        study_name=study_name,
        storage=db_path,
    )
    local_study.optimize(
        _make_objective(
            sbb_paths, [0],
            warmup_days=warmup_days,
            test_years=test_years,
            target_trades_per_year=target_trades_per_year,
        ),
        n_trials=n_trials_chunk,
        show_progress_bar=False,
    )


# ---------------------------------------------------------------------------
# Walk-Forward Optimization
# ---------------------------------------------------------------------------
def run_walk_forward_optimization(
    features_dict: Dict[str, pd.DataFrame],
    n_trials:    int = 200,
    n_sbb_paths: int = 100,
    block_length: int = 20,
    is_days:     int = 756,    # ~3 years in-sample
    oos_days:    int = 126,    # ~6 months out-of-sample
    step_days:   int = 63,     # Roll forward 3 months at a time
    n_jobs:      int = 1,
    warmup_days: int = 252,
) -> WalkForwardReport:
    """
    Full Monte Carlo Walk-Forward Optimization (v2: NSGA-II multi-objective).

    For each IS window:
      1. Generate SBB paths from IS feature data
      2. Run NSGA-II Pareto study — optimizes (Sortino + barrier, frequency)
      3. Select best Pareto trial with >= 4 trades/year minimum deployment
      4. Apply DSR filter to reject false positives
      5. Evaluate best params on OOS window (unseen)

    Args:
        features_dict:  {symbol: feature_df} from build_all_features()
        n_trials:       Optuna trials per IS window
        n_sbb_paths:    SBB bootstrap paths per trial evaluation
        block_length:   Mean SBB block length (trading days)
        is_days:        In-sample window size (trading days)
        oos_days:       Out-of-sample window size (trading days)
        step_days:      Step size between windows
        n_jobs:         Parallel Optuna workers (-1 = all CPUs)
        warmup_days:    Feature warmup period within each IS window

    Returns:
        WalkForwardReport with all OOS results and the recommended params
    """
    # Population size: scale with n_jobs but maintain minimum genetic diversity
    # NSGA-II requires population_size >= n_jobs for proper parallel evolution
    population_size = max(50, n_jobs * 3)

    # IS window duration in years (for frequency penalty calibration)
    test_years = is_days / 252.0
    # Minimum acceptable trades: 4 per year (conservative capital deployment)
    min_trades_per_window = 4 * test_years
    target_trades_per_year = 8.0

    # Build the common date grid
    all_dates = sorted(set.intersection(
        *[set(df.index) for df in features_dict.values() if not df.empty]
    ))
    all_dates = pd.DatetimeIndex(all_dates)
    n_total   = len(all_dates)

    logger.info("=" * 65)
    logger.info("OTM Naked Options — Monte Carlo Walk-Forward Optimization v2")
    logger.info(f"  Universe: {len(features_dict)} symbols | {n_total} trading days")
    logger.info(f"  IS={is_days}d / OOS={oos_days}d / step={step_days}d")
    logger.info(f"  Trials/window={n_trials} | SBB paths/trial={n_sbb_paths}")
    logger.info(f"  Sampler: NSGA-II | population_size={population_size}")
    logger.info(f"  Objective: (Sortino+barrier, log-freq-penalty)")
    logger.info(f"  Min capital deployment: {min_trades_per_window:.0f} trades/window")
    logger.info("=" * 65)

    oos_results = []
    window = 0

    pos = 0
    while pos + is_days + oos_days <= n_total:
        is_start   = all_dates[pos]
        is_end     = all_dates[min(pos + is_days - 1, n_total - 1)]
        oos_start  = all_dates[min(pos + is_days, n_total - 1)]
        oos_end    = all_dates[min(pos + is_days + oos_days - 1, n_total - 1)]
        window    += 1

        logger.info(
            f"\n[Window {window}] IS: {is_start.date()} → {is_end.date()} | "
            f"OOS: {oos_start.date()} → {oos_end.date()}"
        )

        # ── Slice IS and OOS features ────────────────────────────────────────
        is_features  = {s: df[is_start:is_end] for s, df in features_dict.items()
                        if not df[is_start:is_end].empty}
        oos_features = {s: df[oos_start:oos_end] for s, df in features_dict.items()
                        if not df[oos_start:oos_end].empty}

        if not is_features or not oos_features:
            logger.warning(f"Window {window}: insufficient data, skipping.")
            pos += step_days
            continue

        # ── Generate SBB paths from IS data ─────────────────────────────────
        logger.info(f"  Generating {n_sbb_paths} SBB paths (block_len={block_length})...")
        sbb = StationaryBlockBootstrap(
            is_features, block_length=block_length, n_paths=n_sbb_paths, seed=window
        )
        sbb_paths = sbb.generate()

        # ── Run NSGA-II Pareto study ─────────────────────────────────────────
        db_path = f"sqlite:///mc_window_{window}.db"
        if os.path.exists(f"mc_window_{window}.db"):
            os.remove(f"mc_window_{window}.db")

        study_name = f"mc_window_{window}"
        study = optuna.create_study(
            storage=db_path,
            study_name=study_name,
            directions=["minimize", "minimize"],  # obj1=Sortino+barrier, obj2=frequency
            sampler=optuna.samplers.NSGAIISampler(
                seed=window * 100,
                population_size=population_size,
            ),
        )

        if n_jobs > 1:
            chunk_size = n_trials // n_jobs
            chunks = [chunk_size] * n_jobs
            chunks[-1] += n_trials % n_jobs

            processes = []
            for i, chunk in enumerate(chunks):
                if chunk > 0:
                    p = mp.Process(
                        target=_optuna_worker_nsga2,
                        args=(db_path, study_name, window, i, chunk,
                              sbb_paths, warmup_days, test_years, target_trades_per_year)
                    )
                    p.start()
                    processes.append(p)

            for p in processes:
                p.join()

            # Reload to get aggregated Pareto front
            study = optuna.load_study(study_name=study_name, storage=db_path)
        else:
            study.optimize(
                _make_objective(
                    sbb_paths, [0],
                    warmup_days=warmup_days,
                    test_years=test_years,
                    target_trades_per_year=target_trades_per_year,
                ),
                n_trials=n_trials,
                show_progress_bar=False,
            )

        # ── Select best trial from Pareto front ──────────────────────────────
        pareto_trials = study.best_trials   # All non-dominated (Pareto optimal) trials
        if not pareto_trials:
            logger.warning(f"  Window {window}: empty Pareto front. Using defaults.")
            pos += step_days
            continue

        # Filter: require minimum trade deployment (>= 4 trades/year)
        valid_trials = [
            t for t in pareto_trials
            if t.user_attrs.get("median_trades", 0) >= min_trades_per_window
        ]

        if not valid_trials:
            # Relax: pick least-bad frequency from Pareto front
            logger.warning(
                f"  Window {window}: no Pareto trial meets min_trades={min_trades_per_window:.0f}. "
                f"Selecting least-sparse from front."
            )
            valid_trials = sorted(pareto_trials, key=lambda t: t.values[1])[:5]

        # Among valid trials, pick the one with best Sortino (lowest obj1)
        best_trial       = min(valid_trials, key=lambda t: t.values[0])
        best_params_dict = best_trial.params
        best_median_sortino = best_trial.user_attrs.get("median_sortino", 0.0)
        best_median_trades  = best_trial.user_attrs.get("median_trades", 0)
        best_p95_dd         = best_trial.user_attrs.get("p95_drawdown", -1.0)

        logger.info(
            f"  IS best (Pareto): Sortino={best_median_sortino:.2f} | "
            f"Trades={best_median_trades:.0f} | p95_DD={best_p95_dd:.1%} | "
            f"params={best_params_dict}"
        )

        # ── DSR filter (applied to median Sortino across Pareto front) ──────
        all_sortinos = [
            t.user_attrs.get("median_sortino", -99)
            for t in study.trials
            if t.user_attrs.get("median_sortino", -99) > -99
        ]
        dsr = DeflatedSharpeRatio.compute(
            observed_sharpe=best_median_sortino,
            n_trials=len(all_sortinos),
            skewness=-0.5,       # Short puts have negative skew
            kurtosis=4.0,        # Leptokurtic
            n_obs=is_days,
        )
        logger.info(f"  DSR = {dsr:.3f} (threshold 0.95)")
        if dsr < 0.95:
            logger.warning(
                "  DSR < 0.95: likely curve-fit. Using conservative defaults."
            )
            best_params_dict = _default_params_dict()

        # ── OOS evaluation ───────────────────────────────────────────────────
        best_params = _dict_to_params(best_params_dict)
        oos_sim     = FastOTMSimulator(oos_features, warmup_days=0)
        oos_metrics = oos_sim.simulate(best_params)
        oos_metrics["window"]      = window
        oos_metrics["is_sortino"]  = best_median_sortino
        oos_metrics["dsr"]         = dsr
        oos_metrics["params"]      = best_params_dict
        oos_metrics["is_start"]    = str(is_start.date())
        oos_metrics["oos_start"]   = str(oos_start.date())
        oos_results.append(oos_metrics)

        logger.info(
            f"  OOS: Sortino={oos_metrics['sortino']:.2f} | "
            f"MaxDD={oos_metrics['max_drawdown']:.1%} | "
            f"WinRate={oos_metrics.get('win_rate', 0):.1%} | "
            f"Trades={oos_metrics['n_trades']}"
        )

        pos += step_days

    report = WalkForwardReport(oos_results)
    logger.info("\n" + "=" * 65)
    logger.info("FINAL WALK-FORWARD SUMMARY")
    logger.info(report.summary())
    return report


def _dict_to_params(d: dict) -> OTMParams:
    """Convert Optuna trial dict to OTMParams instance."""
    return OTMParams(**{k: v for k, v in d.items() if k in OTMParams.__dataclass_fields__})


def _default_params_dict() -> dict:
    """Conservative default params when DSR filter rejects the IS best."""
    return {
        "dte": 35,
        "put_delta": 0.12,
        "pct_from_52w_high": 0.12,
        "iv_pct_threshold": 0.40,
        "iv_hv_min": 1.10,
        "vix_slope_threshold": -0.03,
        "profit_take_pct": 0.50,
        "stop_loss_mult": 2.5,
        "time_exit_dte": 7,
        "max_risk_pct": 0.012,
        "max_positions": 4,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import yfinance as yf

    parser = argparse.ArgumentParser(description="OTM Naked Monte Carlo Optimizer v2")
    parser.add_argument("--start",     default="2018-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",       default="2025-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--n-trials",  type=int, default=200, help="Optuna trials per window")
    parser.add_argument("--n-paths",   type=int, default=100, help="SBB paths per trial")
    parser.add_argument("--n-jobs",    type=int, default=1,   help="Parallel workers")
    parser.add_argument("--is-days",   type=int, default=756, help="In-sample window (trading days)")
    parser.add_argument("--oos-days",  type=int, default=126, help="OOS window (trading days)")
    parser.add_argument("--output",    default="mc_results/mc_production_run.json")
    args = parser.parse_args()

    logger.info(f"Downloading data: {args.start} → {args.end}")
    cfg = OTMNakedConfig()
    all_tickers = cfg.universe + ["^VIX", "^VIX3M", "^IRX"]

    raw = yf.download(
        all_tickers,
        start=(date.fromisoformat(args.start) - timedelta(days=730)).isoformat(),
        end=args.end,
        progress=True, auto_adjust=True, group_by="ticker"
    )

    def _extract_sym(ticker, raw):
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if ticker in raw.columns.get_level_values(1):
                    df = raw.xs(ticker, axis=1, level=1)
                elif ticker in raw.columns.get_level_values(0):
                    df = raw[ticker]
                else:
                    return None
            else:
                df = raw
            df.columns = [c.capitalize() if isinstance(c, str) else c for c in df.columns]
            return df.dropna(subset=["Close"]) if "Close" in df.columns else None
        except Exception:
            return None

    price_data = {s: _extract_sym(s, raw) for s in cfg.universe}
    price_data = {s: df for s, df in price_data.items() if df is not None and len(df) > 300}

    def _series(ticker):
        df = _extract_sym(ticker, raw)
        return df["Close"] if df is not None and "Close" in df.columns else pd.Series(dtype=float)

    vix, vix3m, rf = _series("^VIX"), _series("^VIX3M"), _series("^IRX") / 100.0
    logger.info(f"Downloaded {len(price_data)}/{len(cfg.universe)} symbols")

    features_dict = build_all_features(price_data, vix, vix3m, rf)

    # Slice to the requested date range
    start_ts = pd.Timestamp(args.start)
    end_ts   = pd.Timestamp(args.end)
    features_dict = {
        s: df[(df.index >= start_ts) & (df.index <= end_ts)]
        for s, df in features_dict.items()
        if not df[(df.index >= start_ts) & (df.index <= end_ts)].empty
    }

    report = run_walk_forward_optimization(
        features_dict,
        n_trials=args.n_trials,
        n_sbb_paths=args.n_paths,
        n_jobs=args.n_jobs,
        is_days=args.is_days,
        oos_days=args.oos_days,
    )

    out = {"summary": report.summary_dict(), "windows": report.oos_results}
    Path(args.output).parent.mkdir(exist_ok=True, parents=True)
    Path(args.output).write_text(json.dumps(out, indent=2, default=str))
    logger.info(f"Results saved to {args.output}")
