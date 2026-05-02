#!/usr/bin/env python3
"""
Post-Optimization Backtest Runner
===================================
Reads the MC optimization results JSON, extracts the recommended parameters,
and runs a full backtest using backtest_engine.py with those parameters.

Usage:
    python3 run_mc_backtest.py --results mc_results/mc_standard_run.json
"""
import sys
import json
import logging
import argparse
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("MCBacktest")

def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default="mc_results/mc_standard_run.json",
                        help="Path to MC optimization results JSON")
    parser.add_argument("--start",   default="2018-01-01")
    parser.add_argument("--end",     default="2025-12-31")
    parser.add_argument("--capital", type=float, default=50000)
    parser.add_argument("--no-ml",   action="store_true")
    args = parser.parse_args()

    # 1. Load optimized parameters
    results_path = Path(args.results)
    if not results_path.exists():
        logger.error(f"Results file not found: {results_path}")
        logger.error("MC optimization may still be running. Check: tail -f logs/mc_optimization.log")
        sys.exit(1)

    with open(results_path) as f:
        mc_data = json.load(f)

    summary = mc_data.get("summary", {})
    rec_params = summary.get("recommended_params", {})

    if not rec_params:
        logger.warning("No recommended params found. Using strategy defaults.")
    else:
        logger.info("=" * 65)
        logger.info("USING MC-OPTIMIZED PARAMETERS:")
        for k, v in rec_params.items():
            logger.info(f"  {k:<25}: {v}")
        logger.info(f"  OOS Sortino (avg)     : {summary.get('avg_sortino', 'N/A'):.2f}")
        logger.info(f"  OOS Max DD  (avg)     : {summary.get('avg_max_drawdown', 0):.1%}")
        logger.info(f"  DSR windows passing   : {summary.get('n_dsr_pass', 0)}/{summary.get('n_windows', 0)}")
        logger.info("=" * 65)

    # 2. Apply parameters to config
    from src.otm_naked.config import OTMNakedConfig
    cfg = OTMNakedConfig()

    param_map = {
        "dte":                  ("dte_target",              int),
        "put_delta":            ("put_delta_target",        float),
        "min_iv_rank":          ("min_iv_rank",             float),
        "pct_from_52w_high":    ("put_decline_from_high",   float),
        "rsi_oversold":         ("rsi_oversold",            float),
        "profit_take_pct":      ("profit_take_pct",         float),
        "stop_loss_mult":       ("stop_loss_credit_mult",   float),
        "time_exit_dte":        ("time_exit_dte",           int),
        "max_risk_pct":         ("max_risk_per_trade_pct",  float),
        "max_positions":        ("max_concurrent_positions",int),
        "vix_crisis_threshold": ("vix_crisis_threshold",    float),
    }

    for optuna_key, (config_attr, cast) in param_map.items():
        if optuna_key in rec_params:
            setattr(cfg, config_attr, cast(rec_params[optuna_key]))
            logger.info(f"  cfg.{config_attr} = {getattr(cfg, config_attr)}")

    cfg.backtest_start = args.start
    cfg.backtest_end   = args.end
    cfg.initial_capital = args.capital

    # 3. Run full backtest
    logger.info("\nLaunching full backtest with MC-optimized params...")
    from src.otm_naked.backtest_engine import OTMNakedBacktestEngine
    import yfinance as yf
    import pandas as pd
    from datetime import date, timedelta

    start_dt = (date.fromisoformat(args.start) - timedelta(days=730)).isoformat()
    all_tickers = cfg.universe + ["^VIX", "^VIX3M", "^IRX"]

    logger.info(f"Downloading data: {start_dt} -> {args.end}")
    raw = yf.download(all_tickers, start=start_dt, end=args.end,
                      progress=True, auto_adjust=True, group_by="ticker")

    def _extract(ticker):
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

    price_data = {s: _extract(s) for s in cfg.universe}
    price_data  = {s: d for s, d in price_data.items() if d is not None and len(d) > 300}

    def _series(t):
        df = _extract(t)
        return df["Close"] if df is not None and "Close" in df.columns else pd.Series(dtype=float)

    vix   = _series("^VIX")
    vix3m = _series("^VIX3M")
    rf    = _series("^IRX") / 100.0

    engine = OTMNakedBacktestEngine(cfg)
    results = engine.run(
        price_data   = price_data,
        vix          = vix,
        vix3m        = vix3m,
        rf           = rf,
        initial_capital = args.capital,
        use_ml       = not args.no_ml,
    )

    metrics = results["metrics"]
    trades  = results["trades"]

    print("\n" + "=" * 65)
    print("  OTM NAKED OPTIONS — MC-OPTIMIZED BACKTEST RESULTS")
    print("=" * 65)
    print(f"  Parameters Source  : {args.results}")
    print(f"  Initial Capital    : ${args.capital:>12,.2f}")
    print(f"  Final Value        : ${metrics.get('final_value', 0):>12,.2f}")
    print(f"  Total Return       : {metrics.get('total_return_pct', 0):>12.1f}%")
    print(f"  CAGR               : {metrics.get('cagr_pct', 0):>12.1f}%")
    print(f"  Max Drawdown       : {metrics.get('max_drawdown_pct', 0):>12.1f}%")
    print(f"  Sharpe Ratio       : {metrics.get('sharpe_ratio', 0):>12.3f}")
    print(f"  Total Trades       : {metrics.get('n_trades', 0):>12}")
    print(f"  Win Rate           : {metrics.get('win_rate_pct', 0):>12.1f}%")
    print(f"  Profit Factor      : {metrics.get('profit_factor', 0):>12.3f}")
    print("=" * 65)

    if not trades.empty:
        out_path = ROOT / "mc_results" / "mc_backtest_trades.csv"
        out_path.parent.mkdir(exist_ok=True)
        trades.to_csv(out_path, index=False)
        logger.info(f"Trades saved -> {out_path}")

if __name__ == "__main__":
    run()
