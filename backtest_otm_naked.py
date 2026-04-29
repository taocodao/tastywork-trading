#!/usr/bin/env python3
"""
================================================================
OTM Naked Options Selling Strategy -- Walk-Forward Backtest
================================================================
Runs the full ML-optimized backtest using Black-Scholes synthetic
option pricing over the pre-selected 35-stock universe.

Usage:
    python backtest_otm_naked.py
    python backtest_otm_naked.py --start 2020-01-01 --end 2025-12-31
    python backtest_otm_naked.py --no-ml --capital 100000

Outputs:
    backtest_otm_naked_results.csv  â€” daily equity curve
    backtest_otm_naked_trades.csv   â€” all closed trades
    logs/backtest_otm_naked.log     â€” detailed execution log
================================================================
"""

import sys
import logging
import warnings
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.otm_naked.config import OTMNakedConfig, OTM_NAKED_UNIVERSE
from src.otm_naked.backtest_engine import OTMNakedBacktestEngine

# â”€â”€ Output files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
EQUITY_CSV = ROOT / "backtest_otm_naked_results.csv"
TRADES_CSV = ROOT / "backtest_otm_naked_trades.csv"
LOG_FILE   = ROOT / "logs" / "backtest_otm_naked.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("OTM_Backtest")


# â”€â”€ CLI args â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def parse_args():
    parser = argparse.ArgumentParser(description="OTM Naked Options Backtest")
    parser.add_argument("--start",   default="2018-01-01", help="Backtest start date")
    parser.add_argument("--end",     default="2025-12-31", help="Backtest end date")
    parser.add_argument("--capital", type=float, default=50_000.0, help="Initial capital")
    parser.add_argument("--no-ml",   action="store_true", help="Disable XGBoost gate (rule-only baseline)")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Subset of symbols (default: all 35)")
    return parser.parse_args()


# â”€â”€ Data download â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def download_data(symbols: list, start: str, end: str) -> dict:
    """
    Download OHLCV data for all symbols + VIX/VIX3M/IRX.
    Uses yfinance with extra warmup period for feature computation.
    """
    # Add 2 years of warmup for 200-day SMA and 252-day IV rank
    warmup_start = str(int(start[:4]) - 2) + start[4:]

    all_tickers = symbols + ["^VIX", "^VIX3M", "^IRX"]
    log.info(f"Downloading data for {len(all_tickers)} tickers: {warmup_start} â†’ {end}")

    raw = yf.download(all_tickers, start=warmup_start, end=end,
                      progress=True, auto_adjust=True, group_by="ticker")

    def _extract(ticker: str, col: str = "Close") -> pd.Series:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                lvl1_vals = raw.columns.get_level_values(1)
                lvl0_vals = raw.columns.get_level_values(0)
                if ticker in lvl1_vals:
                    s = raw.xs(ticker, axis=1, level=1)
                elif ticker in lvl0_vals:
                    s = raw[ticker]
                else:
                    return pd.Series(dtype=float)
                s.columns = [c.capitalize() if isinstance(c, str) else c for c in s.columns]
                return s[col].dropna() if col in s.columns else pd.Series(dtype=float)
            else:
                return raw[col].dropna() if col in raw.columns else pd.Series(dtype=float)
        except Exception:
            return pd.Series(dtype=float)

    price_data = {}
    for sym in symbols:
        try:
            if isinstance(raw.columns, pd.MultiIndex):
                if sym in raw.columns.get_level_values(1):
                    df = raw.xs(sym, axis=1, level=1).copy()
                elif sym in raw.columns.get_level_values(0):
                    df = raw[sym].copy()
                else:
                    log.warning(f"  {sym}: not in downloaded data, skipping")
                    continue
            else:
                df = raw.copy()
            # Normalize column names
            df.columns = [c.capitalize() if isinstance(c, str) else c for c in df.columns]
            needed = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            if "Close" not in needed:
                log.warning(f"  {sym}: no Close column, skipping")
                continue
            df = df[needed].dropna(subset=["Close"])
            if len(df) >= 300:
                price_data[sym] = df
                log.debug(f"  {sym}: {len(df)} rows")
            else:
                log.warning(f"  {sym}: only {len(df)} rows, skipping")
        except Exception as e:
            log.warning(f"  {sym}: download failed ({e})")

    # Extract VIX series (using the _extract closure defined above)
    vix   = _extract("^VIX")
    vix3m = _extract("^VIX3M")
    rf    = _extract("^IRX") / 100.0   # Convert % to decimal

    log.info(f"Downloaded {len(price_data)}/{len(symbols)} symbols | "
             f"VIX: {len(vix)} rows | VIX3M: {len(vix3m)} rows")
    return price_data, vix, vix3m, rf


# â”€â”€ Main â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def run(args=None):
    if args is None:
        args = parse_args()

    symbols = args.symbols or OTM_NAKED_UNIVERSE
    use_ml  = not args.no_ml

    log.info("=" * 62)
    log.info("  OTM NAKED OPTIONS â€” BACKTEST RUNNER")
    log.info(f"  Period  : {args.start} â†’ {args.end}")
    log.info(f"  Capital : ${args.capital:,.0f}")
    log.info(f"  Symbols : {len(symbols)} | ML gate: {use_ml}")
    log.info("=" * 62)

    # â”€â”€ Download â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    price_data, vix, vix3m, rf = download_data(symbols, args.start, args.end)
    if not price_data:
        log.error("No price data downloaded. Check internet connection / symbols.")
        sys.exit(1)

    # â”€â”€ Configure â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    config = OTMNakedConfig(
        backtest_start=args.start,
        backtest_end=args.end,
        initial_capital=args.capital,
    )

    # â”€â”€ Run backtest â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    engine  = OTMNakedBacktestEngine(config)
    results = engine.run(
        price_data=price_data,
        vix=vix,
        vix3m=vix3m if len(vix3m) > 0 else None,
        rf=rf if len(rf) > 0 else None,
        initial_capital=args.capital,
        use_ml=use_ml,
    )

    # â”€â”€ Save outputs â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    equity_df = results["equity_curve"]
    trades_df = results["trades"]

    equity_df.to_csv(EQUITY_CSV)
    log.info(f"Equity curve â†’ {EQUITY_CSV}")

    if not trades_df.empty:
        trades_df.to_csv(TRADES_CSV, index=False)
        log.info(f"Trades       â†’ {TRADES_CSV}")

    # â”€â”€ Print summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    engine.print_summary(results)

    # â”€â”€ Print trade breakdown by symbol â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not trades_df.empty and "symbol" in trades_df.columns:
        print("\n  Trades by Symbol (top 10):")
        by_sym = (trades_df.groupby("symbol")
                  .agg(trades=("pnl", "count"),
                       win_rate=("trade_won", "mean"),
                       total_pnl=("pnl", "sum"))
                  .sort_values("total_pnl", ascending=False)
                  .head(10))
        by_sym["win_rate"] = by_sym["win_rate"].map("{:.1%}".format)
        by_sym["total_pnl"] = by_sym["total_pnl"].map("${:,.0f}".format)
        print(by_sym.to_string())

    # â”€â”€ Comparison: ML vs rule-only â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if use_ml:
        print("\n  Tip: Run with --no-ml to compare rule-only baseline.")

    m = results["metrics"]
    return results


if __name__ == "__main__":
    run()
