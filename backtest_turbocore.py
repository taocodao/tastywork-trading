#!/usr/bin/env python3
"""
================================================================
TurboCore Standard -- Production-Exact Walk-Forward Backtest
================================================================
Replicates the EXACT daily production pipeline from
run_turbocore_scheduler.py, step-by-step:

  Step 1:  TurboCoreDataPipeline features built once over full history
  Step 2:  BaseStrategy.evaluate()             (SMA200 + 5/30 EMA gate)
  Step 3:  TurboCoreRegimeDetector.predict_regimes()  (HMM)
  Step 4:  TurboCoreSignalScorer.predict_confidence() (XGBoost)
  Step 5:  AllocationOptimizer.get_target_allocation()
  Step 6:  calculate_delta_orders()            (production executor)
  Step 7:  Execute at next-day OPEN (integer shares)
  Step 8:  Mark-to-market at close

Performance note: master_df is built once for the full backtest period.
The signal pipeline runs on the slice [: today] to prevent lookahead.
The HMM + XGBoost fit on the visible slice only.

Assets:  QQQ | QLD (2x) | TQQQ (3x) | SGOV
Capital: $5,000
Period:  2019-01-01 -> 2026-03-20
================================================================
"""

import sys, logging, warnings, math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.tqqq_turbocore.base_strategy import BaseStrategy
from src.tqqq_turbocore.ml.regime_detector import TurboCoreRegimeDetector
from src.tqqq_turbocore.ml.signal_scorer import TurboCoreSignalScorer
from src.tqqq_turbocore.allocation_optimizer import AllocationOptimizer
from src.turbocore_pro.executor import calculate_delta_orders

# ── Config ──────────────────────────────────────────────────────
INITIAL_CAPITAL    = 5_000.0
START_DATE         = "2019-01-01"
END_DATE           = "2026-03-20"
MIN_ORDER_NOTIONAL = 5.0
COMMISSION         = 0.0

EQUITY_TICKERS = ["QQQ", "QLD", "TQQQ", "SGOV"]
ALL_TICKERS    = ["QQQ", "QLD", "TQQQ", "SGOV", "^VIX"]

OUTPUT_CSV = ROOT / "backtest_turbocore_results.csv"
LOG_FILE   = ROOT / "logs" / "backtest_turbocore.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("TC_Backtest")


# ================================================================
# DATA  -- build once
# ================================================================

def download_and_build_master() -> tuple[dict, pd.DataFrame]:
    """
    Downloads all data and builds the full master_df ONCE.
    Returns (price_data_dict, master_df).
    """
    log.info("Downloading market data 2017 -> %s ...", END_DATE)
    raw = yf.download(ALL_TICKERS, start="2017-01-01", end=END_DATE,
                      auto_adjust=True, progress=False)
    data = {}
    for t in ALL_TICKERS:
        try:
            df = raw.xs(t, level=1, axis=1).dropna(how="all")
            data[t] = df
        except Exception:
            log.warning("  %s -- unavailable", t)

    qqq  = data["QQQ"]["Close"]
    tqqq = data["TQQQ"]["Close"].reindex(qqq.index).ffill()
    vix  = data.get("^VIX", pd.DataFrame())
    vix_close = (vix["Close"].reindex(qqq.index).ffill()
                 if not vix.empty else pd.Series(20.0, index=qqq.index))

    master = pd.DataFrame(index=qqq.index)
    master["qqq_close"]  = qqq
    master["tqqq_close"] = tqqq
    master["vix_close"]  = vix_close

    master["tqqq_ema_5"]  = tqqq.ewm(span=5,  adjust=False).mean()
    master["tqqq_ema_30"] = tqqq.ewm(span=30, adjust=False).mean()
    master["tqqq_bull_cross"] = master["tqqq_ema_5"] > master["tqqq_ema_30"]

    master["qqq_sma_200"]          = qqq.rolling(200).mean()
    master["qqq_above_sma200_buy"] = qqq > master["qqq_sma_200"] * 1.05
    master["qqq_below_sma200_sell"]= qqq < master["qqq_sma_200"] * 0.97

    master["qqq_log_return"] = np.log(qqq / qqq.shift(1))
    master["qqq_vol_20d"]    = master["qqq_log_return"].rolling(20).std()

    master = master.dropna(subset=["qqq_sma_200"])
    log.info("Master df: %d rows from %s to %s",
             len(master), master.index[0].date(), master.index[-1].date())
    return data, master


# ================================================================
# SIGNAL PIPELINE  (run on slice)
# ================================================================

def run_turbocore_signal(slice_df: pd.DataFrame) -> dict:
    """
    Steps 2-5 of production scheduler.
    slice_df is master_df sliced up to today (no lookahead).
    """
    df = BaseStrategy(slice_df).evaluate()

    try:
        df     = TurboCoreRegimeDetector().predict_regimes(df)
        regime = str(df.iloc[-1].get("final_regime", "SIDEWAYS"))
    except Exception as e:
        log.debug("RegimeDetector fallback: %s", e)
        last   = df.iloc[-1]
        sr     = int(last.get("sma200_regime", 0))
        bc     = bool(last.get("tqqq_bull_cross", False))
        regime = "BULL" if (sr == 1 and bc) else ("BEAR" if sr == -1 else "SIDEWAYS")

    try:
        df         = TurboCoreSignalScorer().predict_confidence(df)
        confidence = float(df.iloc[-1].get("ml_confidence", 0.55))
    except Exception as e:
        log.debug("SignalScorer fallback: %s", e)
        confidence = 0.55

    last        = df.iloc[-1]
    base_signal = int(last.get("base_signal", 0))
    if bool(last.get("qqq_below_sma200_sell", False)):
        regime = "BEAR_SMA_FORCED"

    target_allocation = AllocationOptimizer().get_target_allocation(
        regime=regime, signal=base_signal, ml_confidence=confidence)

    return dict(regime=regime, base_signal=base_signal,
                confidence=confidence, target_allocation=target_allocation)


# ================================================================
# PORTFOLIO
# ================================================================

class Portfolio:
    def __init__(self, capital):
        self.cash      = capital
        self.shares:   dict[str, int]   = {}
        self.avg_cost: dict[str, float] = {}

    def net_liq(self, prices):
        return self.cash + sum(
            self.shares.get(s, 0) * prices.get(s, 0) for s in self.shares)

    def apply_orders(self, orders, fill_prices):
        for order in sorted(orders, key=lambda o: 0 if o["action"] == "SELL" else 1):
            sym = order["symbol"]
            qty = int(abs(order.get("quantity", 0)))
            px  = fill_prices.get(sym, order.get("estimated_price", 0))
            if px <= 0 or qty == 0 or qty * px < MIN_ORDER_NOTIONAL:
                continue

            if order["action"] == "BUY":
                cost = qty * px + qty * COMMISSION
                if cost > self.cash:
                    qty  = max(0, int((self.cash - 1.0) / (px + COMMISSION)))
                    cost = qty * px
                if qty == 0:
                    continue
                prev  = self.shares.get(sym, 0)
                total = prev + qty
                self.avg_cost[sym] = (prev * self.avg_cost.get(sym, px) + qty * px) / total
                self.shares[sym]   = total
                self.cash         -= cost

            elif order["action"] == "SELL":
                qty = min(qty, self.shares.get(sym, 0))
                if qty == 0:
                    continue
                self.shares[sym] = self.shares.get(sym, 0) - qty
                if self.shares[sym] <= 0:
                    self.shares.pop(sym, None)
                    self.avg_cost.pop(sym, None)
                self.cash += qty * px - qty * COMMISSION


# ================================================================
# MAIN
# ================================================================

def run():
    log.info("=" * 60)
    log.info("TurboCore Standard -- Production Walk-Forward Backtest")
    log.info("  Capital: $%s   Period: %s -> %s", f"{INITIAL_CAPITAL:,.0f}", START_DATE, END_DATE)
    log.info("  Assets : QQQ | QLD | TQQQ | SGOV")
    log.info("=" * 60)

    data, master_df = download_and_build_master()

    close: dict[str, pd.Series] = {s: data[s]["Close"] for s in EQUITY_TICKERS if s in data}
    opn:   dict[str, pd.Series] = {s: data[s]["Open"]  for s in EQUITY_TICKERS if s in data}

    trading_days    = close["QQQ"].loc[START_DATE:END_DATE].index.tolist()
    portfolio       = Portfolio(INITIAL_CAPITAL)
    pending_orders: list = []
    results:        list = []

    log.info("Simulating %d trading days...", len(trading_days))

    for i, today in enumerate(trading_days):

        # Apply yesterday's orders at today's OPEN
        if pending_orders:
            fill_px = {sym: float(opn[sym].loc[today])
                       for sym in EQUITY_TICKERS
                       if sym in opn and today in opn[sym].index}
            portfolio.apply_orders(pending_orders, fill_px)
            pending_orders = []

        # Mark-to-market at close
        close_px = {sym: float(close[sym].loc[today])
                    for sym in EQUITY_TICKERS
                    if sym in close and today in close[sym].index}
        net_liq = portfolio.net_liq(close_px)

        # Run production signal pipeline on slice up to today
        slice_df = master_df.loc[:today]
        if len(slice_df) < 200:
            sig = dict(regime="WARMUP", base_signal=0, confidence=0.0, target_allocation={})
        else:
            try:
                sig = run_turbocore_signal(slice_df)
            except Exception as e:
                log.warning("%s -- signal error: %s", today.date(), e)
                sig = dict(regime="ERROR", base_signal=0, confidence=0.0, target_allocation={})

        target_alloc = sig["target_allocation"]

        # Step 6: Generate orders via production executor
        if target_alloc and net_liq > 0:
            live_px = {sym: close_px.get(sym, 0) for sym in target_alloc
                       if close_px.get(sym, 0) > 0}
            try:
                pending_orders = calculate_delta_orders(
                    target_matrix     = target_alloc,
                    current_net_liq   = net_liq,
                    current_positions = dict(portfolio.shares),
                    live_prices       = live_px,
                )
            except Exception as e:
                log.debug("%s -- executor: %s", today.date(), e)

        row = dict(
            date             = today.date(),
            net_liq          = round(net_liq, 2),
            cash             = round(portfolio.cash, 2),
            total_return_pct = round((net_liq / INITIAL_CAPITAL - 1) * 100, 2),
            regime           = sig["regime"],
            confidence       = round(sig["confidence"], 3),
            base_signal      = sig["base_signal"],
            alloc_QQQ        = round(target_alloc.get("QQQ", 0)  * 100, 1),
            alloc_QLD        = round(target_alloc.get("QLD", 0)  * 100, 1),
            alloc_TQQQ       = round(target_alloc.get("TQQQ", 0) * 100, 1),
            alloc_SGOV       = round(target_alloc.get("SGOV", 0) * 100, 1),
            QQQ_shares       = portfolio.shares.get("QQQ", 0),
            QLD_shares       = portfolio.shares.get("QLD", 0),
            TQQQ_shares      = portfolio.shares.get("TQQQ", 0),
            SGOV_shares      = portfolio.shares.get("SGOV", 0),
            orders_queued    = len(pending_orders),
        )
        results.append(row)

        if i % 50 == 0 or i == len(trading_days) - 1:
            log.info("  %s | net_liq=$%.2f | %s | conf=%.0f%% | ret=%+.1f%%",
                     str(today.date()), net_liq, sig["regime"],
                     sig["confidence"]*100, row["total_return_pct"])

    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_CSV, index=False)

    final   = df["net_liq"].iloc[-1]
    peak    = df["net_liq"].max()
    trough  = df.loc[df["net_liq"].idxmax():, "net_liq"].min()
    max_dd  = (trough - peak) / peak * 100
    years   = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
    cagr    = ((final / INITIAL_CAPITAL) ** (1 / years) - 1) * 100
    total_r = (final / INITIAL_CAPITAL - 1) * 100

    print("\n" + "=" * 60)
    print("  TURBOCORE STANDARD -- RESULTS")
    print("=" * 60)
    print(f"  Start Capital : ${INITIAL_CAPITAL:>12,.2f}")
    print(f"  Final Value   : ${final:>12,.2f}")
    print(f"  Total Return  : {total_r:>12.1f}%")
    print(f"  CAGR          : {cagr:>12.1f}%")
    print(f"  Max Drawdown  : {max_dd:>12.1f}%")
    print(f"  Peak Value    : ${peak:>12,.2f}")
    print(f"  Trading Days  : {len(df):>12,d}")
    print(f"  Output CSV    : {OUTPUT_CSV}")
    print("=" * 60)

    rc = df["regime"].value_counts()
    print("\n  Regime Distribution:")
    for name, count in rc.items():
        print(f"    {name:<22} {count:>4d} days  ({count/len(df)*100:.1f}%)")

    return df


if __name__ == "__main__":
    run()
