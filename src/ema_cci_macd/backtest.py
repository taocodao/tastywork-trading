"""
EMA-CCI-MACD Backtester
=========================
Historical validation of the signal engine.
Walks through each bar, evaluates the 5-condition filter,
and logs all BUY/SELL signals with entry price and stop loss.

Usage:
    python -m src.ema_cci_macd.backtest
    python -m src.ema_cci_macd.backtest --symbol QQQ --start 2019-01-01 --end 2026-05-01
"""

import sys
import argparse
import logging
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.ema_cci_macd.config import InstrumentConfig
from src.ema_cci_macd.data_fetcher import YFinanceFetcher
from src.ema_cci_macd.indicators import compute_indicators
from src.ema_cci_macd.signal_engine import evaluate_signal

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(message)s")
logger = logging.getLogger("EMA-CCI-MACD-Backtest")


def backtest_instrument(config, start="2019-01-01", end="2026-05-01"):
    fetcher = YFinanceFetcher()
    logger.info(f"Fetching {config.symbol} data: {start} -> {end}")
    df = fetcher.fetch_ohlcv(config.symbol, config.timeframe, start=start, end=end)
    if df.empty:
        logger.error(f"No data for {config.symbol}")
        return pd.DataFrame()
    logger.info(f"  {len(df)} bars downloaded")
    df = compute_indicators(df, ema_layers=config.ema_layers,
                            cci_period=config.cci_period,
                            macd_fast=config.macd_fast,
                            macd_slow=config.macd_slow,
                            macd_signal=config.macd_signal)
    logger.info(f"  {len(df)} bars after indicator warmup")
    warmup = max(config.ema_layers) + config.cci_lookback + 5
    results = []
    for i in range(warmup, len(df)):
        window = df.iloc[:i + 1]
        candidate = evaluate_signal(window, symbol=config.symbol,
                                    timeframe=config.timeframe,
                                    ema_layers=config.ema_layers,
                                    proximity_pct=config.proximity_pct,
                                    cci_lookback=config.cci_lookback)
        if candidate is not None:
            results.append({
                "date": window.index[-1], "signal": candidate.direction,
                "price": candidate.entry_price, "stop_loss": candidate.stop_loss,
                "cci": candidate.cci_value, "macd_hist": candidate.macd_hist,
                "ema1": candidate.ema1_value, "ema2": candidate.ema2_value,
                "conditions_met": candidate.conditions_met, "reason": "All conditions met"
            })
    return pd.DataFrame(results)


def compute_trade_pnl(signals_df, price_df):
    if signals_df.empty:
        return signals_df
    trades = []
    max_hold = 20
    for _, row in signals_df.iterrows():
        entry_date, entry_price = row["date"], row["price"]
        stop_loss, direction = row["stop_loss"], row["signal"]
        if entry_date not in price_df.index:
            continue
        entry_pos = price_df.index.get_loc(entry_date)
        exit_price, exit_date, exit_reason = None, None, "max_hold"
        for j in range(1, min(max_hold + 1, len(price_df) - entry_pos)):
            bar_idx = entry_pos + j
            bar = price_df.iloc[bar_idx]
            if direction == "BUY" and float(bar["low"]) <= stop_loss:
                exit_price, exit_date, exit_reason = stop_loss, price_df.index[bar_idx], "stop_loss"
                break
            elif direction == "SELL" and float(bar["high"]) >= stop_loss:
                exit_price, exit_date, exit_reason = stop_loss, price_df.index[bar_idx], "stop_loss"
                break
        if exit_price is None:
            close_idx = min(entry_pos + max_hold, len(price_df) - 1)
            exit_price = float(price_df.iloc[close_idx]["close"])
            exit_date = price_df.index[close_idx]
        pnl = (exit_price - entry_price) if direction == "BUY" else (entry_price - exit_price)
        pnl_pct = (pnl / entry_price) * 100
        trades.append({**row.to_dict(), "exit_date": exit_date,
                       "exit_price": round(exit_price, 4),
                       "exit_reason": exit_reason,
                       "pnl": round(pnl, 4), "pnl_pct": round(pnl_pct, 2)})
    return pd.DataFrame(trades)


def print_summary(results_df, trades_df, symbol, start, end):
    print("\n" + "=" * 65)
    print(f"  EMA-CCI-MACD BACKTEST RESULTS -- {symbol}")
    print(f"  Period: {start} -> {end}")
    print("=" * 65)
    total = len(results_df)
    buys = len(results_df[results_df["signal"] == "BUY"])
    sells = len(results_df[results_df["signal"] == "SELL"])
    print(f"  Total Signals  : {total}")
    print(f"    BUY signals  : {buys}")
    print(f"    SELL signals : {sells}")
    if not trades_df.empty:
        winners = trades_df[trades_df["pnl"] > 0]
        losers = trades_df[trades_df["pnl"] <= 0]
        win_rate = len(winners) / len(trades_df) * 100
        avg_win = winners["pnl_pct"].mean() if len(winners) > 0 else 0
        avg_loss = losers["pnl_pct"].mean() if len(losers) > 0 else 0
        total_pnl = trades_df["pnl_pct"].sum()
        stops = len(trades_df[trades_df["exit_reason"] == "stop_loss"])
        print(f"\n  Trade Performance:")
        print(f"    Win Rate     : {win_rate:.1f}%")
        print(f"    Avg Win      : +{avg_win:.2f}%")
        print(f"    Avg Loss     : {avg_loss:.2f}%")
        print(f"    Total P&L    : {total_pnl:+.2f}%")
        print(f"    Stopped Out  : {stops}/{len(trades_df)}")
    if not results_df.empty:
        print(f"\n  Signal Timeline:")
        for _, row in results_df.iterrows():
            tag = "[BUY ]" if row["signal"] == "BUY" else "[SELL]"
            dt = row["date"]
            dt_str = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)
            print(f"    {tag} {dt_str} | {row['signal']:4s} @ ${row['price']:.2f}"
                  f" | Stop: ${row['stop_loss']:.2f} | CCI: {row['cci']:.0f}")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EMA-CCI-MACD Backtester")
    parser.add_argument("--symbol", default="QQQ")
    parser.add_argument("--start", default="2019-01-01")
    parser.add_argument("--end", default="2026-05-01")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--ema", nargs=3, type=int, default=[40, 120, 350])
    parser.add_argument("--cci-period", type=int, default=20)
    parser.add_argument("--proximity", type=float, default=0.003)
    parser.add_argument("--cci-lookback", type=int, default=10)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    config = InstrumentConfig(symbol=args.symbol, timeframe=args.timeframe,
                              ema_layers=args.ema, cci_period=args.cci_period,
                              proximity_pct=args.proximity,
                              cci_lookback=args.cci_lookback)

    logger.info(f"Backtesting {config.symbol} with EMA {config.ema_layers}")
    signals_df = backtest_instrument(config, start=args.start, end=args.end)

    fetcher = YFinanceFetcher()
    price_df = fetcher.fetch_ohlcv(config.symbol, args.timeframe, start=args.start, end=args.end)

    trades_df = pd.DataFrame()
    if not signals_df.empty and not price_df.empty:
        trades_df = compute_trade_pnl(signals_df, price_df)

    print_summary(signals_df, trades_df, config.symbol, args.start, args.end)

    out_dir = ROOT / "mc_results"
    out_dir.mkdir(exist_ok=True)
    out_path = args.output or str(out_dir / f"ema_cci_macd_{config.symbol}_backtest.csv")
    if not signals_df.empty:
        save_df = trades_df if not trades_df.empty else signals_df
        save_df.to_csv(out_path, index=False)
        logger.info(f"Results saved to {out_path}")
    else:
        logger.warning("No signals generated during backtest period.")
