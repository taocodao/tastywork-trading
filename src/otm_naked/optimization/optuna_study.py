"""
Bayesian Optimization Study (Optuna)
=======================================
Finds the optimal OTMParams for the naked put selling strategy using
the Tree-structured Parzen Estimator (TPE) algorithm.

Architecture:
  1. OUTER loop: Walk-Forward windows (IS train / OOS test)
  2. INNER loop per IS window: Optuna study over SBB paths
     - Each Optuna trial samples one OTMParams from the search space
     - Objective = Sortino ratio on the bootstrapped IS paths
     - DSR filter rejects curve-fit solutions
  3. Best IS params → evaluated on the OOS window (unseen data)
  4. All OOS metrics aggregated for final parameter reporting

EC2 Usage:
    python -m src.otm_naked.optimization.optuna_study \
        --start 2018-01-01 --end 2025-12-31 \
        --n-trials 300 --n-paths 200 --n-jobs 4

Local quick test:
    python -m src.otm_naked.optimization.optuna_study \
        --start 2022-01-01 --end 2025-12-31 \
        --n-trials 50 --n-paths 20 --n-jobs 1
"""

import os
import sys
import json
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
# Optuna objective function
# ---------------------------------------------------------------------------
def _make_objective(
    sbb_paths: List[Dict[str, pd.DataFrame]],
    trial_count_ref: list,     # Mutable list[int] to track n_trials for DSR
    warmup_days: int = 252,
):
    """
    Returns an Optuna objective function.
    Each call = one Bayesian trial.
    """
    def objective(trial: optuna.Trial) -> float:
        trial_count_ref[0] += 1

        # ── Sample the parameter space ────────────────────────────────────────
        params = OTMParams(
            dte                  = trial.suggest_int("dte", 21, 60),
            put_delta            = trial.suggest_float("put_delta", 0.05, 0.20),
            min_iv_rank          = trial.suggest_float("min_iv_rank", 0.10, 0.50),
            pct_from_52w_high    = trial.suggest_float("pct_from_52w_high", 0.05, 0.30),
            rsi_oversold         = trial.suggest_float("rsi_oversold", 20.0, 50.0),
            profit_take_pct      = trial.suggest_float("profit_take_pct", 0.25, 0.75),
            stop_loss_mult       = trial.suggest_float("stop_loss_mult", 1.5, 4.0),
            time_exit_dte        = trial.suggest_int("time_exit_dte", 3, 14),
            max_risk_pct         = trial.suggest_float("max_risk_pct", 0.005, 0.03),
            max_positions        = trial.suggest_int("max_positions", 2, 10),
            vix_crisis_threshold = trial.suggest_float("vix_crisis_threshold", 25.0, 50.0),
        )

        # ── Run simulation on all SBB paths ──────────────────────────────────
        sortinos    = []
        drawdowns   = []
        for path_features in sbb_paths:
            sim     = FastOTMSimulator(path_features, warmup_days=warmup_days)
            metrics = sim.simulate(params)
            # Prune unpromising trials early
            if metrics["n_trades"] < 1:
                raise optuna.exceptions.TrialPruned()
            sortinos.append(metrics["sortino"])
            drawdowns.append(metrics["max_drawdown"])

        mean_sortino = float(np.mean(sortinos))
        mean_dd      = float(np.mean(drawdowns))

        # Store all attributes for later DSR filtering
        trial.set_user_attr("sortino",      mean_sortino)
        trial.set_user_attr("max_drawdown", mean_dd)
        trial.set_user_attr("n_paths",      len(sortinos))

        # Penalize extreme drawdown harshly (risk management constraint)
        if mean_dd < -0.25:
            return -99.0

        return mean_sortino

    return objective


import multiprocessing as mp

def _optuna_worker(db_path: str, study_name: str, window: int, worker_idx: int, n_trials_chunk: int, sbb_paths: list, warmup_days: int):
    """Worker process function for parallel Optuna trials via SQLite."""
    # Create an independent study instance per process attached to the same DB
    local_study = optuna.load_study(
        study_name=study_name,
        storage=db_path,
        sampler=optuna.samplers.TPESampler(seed=window * 100 + worker_idx),
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=10),
    )
    
    local_study.optimize(
        _make_objective(sbb_paths, [0], warmup_days=warmup_days),
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
    Full Monte Carlo Walk-Forward Optimization.

    For each IS window:
      1. Generate SBB paths from IS feature data
      2. Run Optuna Bayesian optimization to find best params
      3. Apply DSR filter to reject false positives
      4. Evaluate best params on OOS window (unseen)

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
    # Build the common date grid
    all_dates = sorted(set.intersection(
        *[set(df.index) for df in features_dict.values() if not df.empty]
    ))
    all_dates = pd.DatetimeIndex(all_dates)
    n_total   = len(all_dates)

    logger.info("=" * 65)
    logger.info("OTM Naked Options — Monte Carlo Walk-Forward Optimization")
    logger.info(f"  Universe: {len(features_dict)} symbols | {n_total} trading days")
    logger.info(f"  IS={is_days}d / OOS={oos_days}d / step={step_days}d")
    logger.info(f"  Trials/window={n_trials} | SBB paths/trial={n_sbb_paths}")
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

        # ── Run Optuna study ─────────────────────────────────────────────────
        db_path = f"sqlite:///mc_window_{window}.db"
        if os.path.exists(f"mc_window_{window}.db"):
            os.remove(f"mc_window_{window}.db")
            
        study_name = f"mc_window_{window}"
        study = optuna.create_study(
            storage=db_path,
            study_name=study_name,
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=window * 100),
            pruner=optuna.pruners.MedianPruner(n_warmup_steps=10),
        )

        if n_jobs > 1:
            chunk_size = n_trials // n_jobs
            chunks = [chunk_size] * n_jobs
            chunks[-1] += n_trials % n_jobs
            
            processes = []
            for i, chunk in enumerate(chunks):
                if chunk > 0:
                    p = mp.Process(target=_optuna_worker, args=(db_path, study_name, window, i, chunk, sbb_paths, warmup_days))
                    p.start()
                    processes.append(p)
                    
            for p in processes:
                p.join()
                
            # Reload to get the aggregated results
            study = optuna.load_study(study_name=study_name, storage=db_path)
        else:
            study.optimize(
                _make_objective(sbb_paths, [0], warmup_days=warmup_days),
                n_trials=n_trials,
                show_progress_bar=False,
            )

        # ── Get best trial (guard against all-pruned scenario) ──────────────
        completed = [t for t in study.trials if t.value is not None]
        if not completed:
            logger.warning(f"  Window {window}: all trials pruned. Using defaults.")
            pos += step_days
            continue

        best_trial = study.best_trial
        best_sortino_is = best_trial.value
        best_params_dict = best_trial.params

        logger.info(
            f"  IS best: Sortino={best_sortino_is:.2f} | "
            f"params={best_params_dict}"
        )

        # ── DSR filter ───────────────────────────────────────────────────────
        all_sortinos = [
            t.value for t in study.trials
            if t.value is not None and t.value > -99
        ]
        dsr = DeflatedSharpeRatio.compute(
            observed_sharpe=best_sortino_is,
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
        oos_metrics["is_sortino"]  = best_sortino_is
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
        "dte": 35, "put_delta": 0.10, "min_iv_rank": 0.30,
        "pct_from_52w_high": 0.15, "rsi_oversold": 30.0,
        "profit_take_pct": 0.50, "stop_loss_mult": 2.0,
        "time_exit_dte": 7, "max_risk_pct": 0.01,
        "max_positions": 5, "vix_crisis_threshold": 35.0,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import yfinance as yf

    parser = argparse.ArgumentParser(description="OTM Naked Monte Carlo Optimizer")
    parser.add_argument("--start",     default="2018-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",       default="2025-12-31", help="End date YYYY-MM-DD")
    parser.add_argument("--n-trials",  type=int, default=200, help="Optuna trials per window")
    parser.add_argument("--n-paths",   type=int, default=100, help="SBB paths per trial")
    parser.add_argument("--n-jobs",    type=int, default=1,   help="Parallel workers")
    parser.add_argument("--is-days",   type=int, default=756, help="In-sample window (trading days)")
    parser.add_argument("--oos-days",  type=int, default=126, help="OOS window (trading days)")
    parser.add_argument("--output",    default="mc_optimization_results.json")
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
    Path(args.output).write_text(json.dumps(out, indent=2, default=str))
    logger.info(f"Results saved to {args.output}")
