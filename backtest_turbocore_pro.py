#!/usr/bin/env python3
"""
================================================================
TurboCore Pro -- Production-Exact Walk-Forward Backtest
================================================================
Replicates the EXACT daily production pipeline from
run_turbocore_pro_scheduler.py, step-by-step:

  Step 1:  Full master_df built ONCE upfront (2017->END), then sliced
  Step 2:  BaseStrategy.evaluate()              (SMA200 + 5/30 EMA gate)
  Step 3:  TurboCoreRegimeDetector.predict_regimes()  (HMM)
  Step 4:  TurboCoreSignalScorer.predict_confidence() (XGBoost)
  Step 5:  AllocationOptimizer.get_target_allocation() (Kelly + drawdown)
  Step 6:  calculate_delta_orders()             (production executor)
  Step 7:  Execute orders at next-day OPEN (integer shares for equities)
  Step 8:  LEAPS: Black-Scholes deep-ITM (80% strike, 1yr tenor).
           Priced daily using QQQ HV-30 + ^IRX risk-free rate.
  Step 9:  Mark-to-market at close

Assets:  QQQ | QLD (2x) | QQQ_LEAPS (~0.85 delta) | SGOV
Capital: $5,000
Period:  2019-01-01 -> 2026-03-20
================================================================
"""

import sys, logging, warnings, math
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.turbocore_pro.base_strategy import BaseStrategy
from src.turbocore_pro.ml.regime_detector import TurboCoreRegimeDetector
from src.turbocore_pro.ml.signal_scorer import TurboCoreSignalScorer
from src.turbocore_pro.allocation_optimizer import AllocationOptimizer
from src.turbocore_pro.executor import calculate_delta_orders

# ── Config ──────────────────────────────────────────────────────
INITIAL_CAPITAL      = 5_000.0
START_DATE           = "2019-01-01"
END_DATE             = "2026-03-20"
MIN_ORDER_NOTIONAL   = 5.0
COMMISSION           = 0.0

LEAPS_DAYS_TO_EXPIRY = 365
LEAPS_STRIKE_PCT     = 0.80      # 20% deep ITM -> delta ~0.85
LEAPS_RISK_FREE_RATE = 0.045

EQUITY_TICKERS = ["QQQ", "QLD", "SGOV"]
ALL_TICKERS    = ["QQQ", "QLD", "SGOV", "^VIX", "^IRX"]

OUTPUT_CSV = ROOT / "backtest_turbocore_pro_results.csv"
LOG_FILE   = ROOT / "logs" / "backtest_turbocore_pro.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("TCPro_Backtest")


# ================================================================
# LEAPS PRICING
# ================================================================

def bs_call_price(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def build_leaps_price_series(qqq_prices, rf_series, hv30):
    """
    Returns the price PER CONTRACT (= B-S per-share price × 100 shares/contract).
    Standard options: 1 contract = 100 underlying shares.
    With QQQ at ~$460 and 80% strike (~$370), this is roughly:
      B-S per share ≈ $40-90  →  contract cost ≈ $4,000-9,000
    """
    T = LEAPS_DAYS_TO_EXPIRY / 365.0
    return pd.Series(
        [bs_call_price(
            float(qqq_prices.loc[dt]),
            float(qqq_prices.loc[dt]) * LEAPS_STRIKE_PCT,
            T,
            float(rf_series.get(dt, LEAPS_RISK_FREE_RATE)),
            max(0.05, min(float(hv30.get(dt, 0.20)), 2.0)),
         ) * 100  # contract = 100 underlying shares
         for dt in qqq_prices.index],
        index=qqq_prices.index,
        name="QQQ_LEAPS",
    )


# ================================================================
# DATA -- build once
# ================================================================

def download_and_build_master():
    log.info("Downloading market data (2017 -> %s)...", END_DATE)
    raw = yf.download(ALL_TICKERS, start="2017-01-01", end=END_DATE,
                      auto_adjust=True, progress=False)
    data = {}
    for t in ALL_TICKERS:
        try:
            df = raw.xs(t, level=1, axis=1).dropna(how="all")
            data[t] = df
        except Exception:
            log.warning("  %s -- unavailable", t)

    log.info("Downloading TQQQ history...")
    tqqq_raw = yf.download("TQQQ", start="2017-01-01", end=END_DATE,
                            auto_adjust=True, progress=False)
    if isinstance(tqqq_raw.columns, pd.MultiIndex):
        tqqq_raw.columns = tqqq_raw.columns.droplevel(1)
    data["TQQQ"] = tqqq_raw

    qqq   = data["QQQ"]["Close"]
    tqqq  = data["TQQQ"]["Close"].reindex(qqq.index).ffill() if not tqqq_raw.empty else qqq * 3
    vix_raw   = data.get("^VIX", pd.DataFrame())
    vix_close = (vix_raw["Close"].reindex(qqq.index).ffill()
                 if not vix_raw.empty else pd.Series(20.0, index=qqq.index))

    master = pd.DataFrame(index=qqq.index)
    master["qqq_close"]  = qqq
    master["tqqq_close"] = tqqq
    master["vix_close"]  = vix_close

    master["qqq_sma_200"]          = qqq.rolling(200).mean()
    master["qqq_above_sma200_buy"] = qqq > master["qqq_sma_200"] * 1.05
    master["qqq_below_sma200_sell"]= qqq < master["qqq_sma_200"] * 0.97

    master["tqqq_ema_5"]      = tqqq.ewm(span=5,  adjust=False).mean()
    master["tqqq_ema_30"]     = tqqq.ewm(span=30, adjust=False).mean()
    master["tqqq_bull_cross"] = master["tqqq_ema_5"] > master["tqqq_ema_30"]

    master["qqq_ath"]          = qqq.cummax()
    master["qqq_drawdown_ath"] = (qqq - master["qqq_ath"]) / master["qqq_ath"]

    delta = tqqq.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    master["tqqq_rsi_14"] = 100 - (100 / (1 + rs))

    ema12 = tqqq.ewm(span=12, adjust=False).mean()
    ema26 = tqqq.ewm(span=26, adjust=False).mean()
    master["tqqq_macd"]        = ema12 - ema26
    master["tqqq_macd_signal"] = master["tqqq_macd"].ewm(span=9, adjust=False).mean()
    master["tqqq_macd_hist"]   = master["tqqq_macd"] - master["tqqq_macd_signal"]

    sma20 = tqqq.rolling(20).mean()
    std20 = tqqq.rolling(20).std()
    master["tqqq_bb_width"] = ((sma20 + 2*std20) - (sma20 - 2*std20)) / sma20

    master["vix_30d_avg"] = vix_close.rolling(30).mean()
    master["vix_ratio"]   = vix_close / master["vix_30d_avg"]

    master["qqq_log_return"] = np.log(qqq / qqq.shift(1))
    master["qqq_vol_20d"]    = master["qqq_log_return"].rolling(20).std()

    master["bull_cross_trigger"] = (
        (master["tqqq_bull_cross"] == True) &
        (master["tqqq_bull_cross"].shift(1) == False)
    )

    master = master.dropna(subset=["qqq_sma_200"])

    # LEAPS price series (close + open)
    log.info("Computing LEAPS Black-Scholes price series...")
    rf_series = (data["^IRX"]["Close"] / 100.0).reindex(qqq.index).ffill().fillna(LEAPS_RISK_FREE_RATE) \
                if "^IRX" in data else pd.Series(LEAPS_RISK_FREE_RATE, index=qqq.index)
    hv30 = np.log(qqq / qqq.shift(1)).rolling(30).std() * math.sqrt(252)

    # Simpler: just pass the series directly
    leaps_close = build_leaps_price_series(data["QQQ"]["Close"], rf_series, hv30)
    leaps_open  = build_leaps_price_series(data["QQQ"]["Open"],  rf_series, hv30)

    log.info("Master df: %d rows from %s to %s",
             len(master), master.index[0].date(), master.index[-1].date())
    return data, master, leaps_close, leaps_open


# ================================================================
# SIGNAL PIPELINE
# ================================================================

def run_turbocore_pro_signal(slice_df):
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

    last         = df.iloc[-1]
    base_signal  = int(last.get("base_signal", 0))
    qqq_drawdown = float(last.get("qqq_drawdown_ath", 0.0))
    if bool(last.get("qqq_below_sma200_sell", False)):
        regime = "BEAR_SMA_FORCED"

    target_allocation = AllocationOptimizer().get_target_allocation(
        regime=regime, signal=base_signal,
        ml_confidence=confidence, qqq_drawdown=qqq_drawdown)

    return dict(regime=regime, base_signal=base_signal, confidence=confidence,
                qqq_drawdown=qqq_drawdown, target_allocation=target_allocation)


# ================================================================
# PORTFOLIO
# ================================================================

class Portfolio:
    def __init__(self, capital):
        self.cash             = capital
        self.shares:   dict   = {}
        self.avg_cost: dict   = {}
        self.leaps_contracts  = 0
        self.leaps_avg_cost   = 0.0

    def net_liq(self, prices, leaps_px):
        eq_val = sum(self.shares.get(s, 0) * prices.get(s, 0) for s in self.shares)
        return self.cash + eq_val + self.leaps_contracts * leaps_px

    def apply_orders(self, orders, fill_prices, leaps_fill_px):
        for order in sorted(orders, key=lambda o: 0 if o["action"] == "SELL" else 1):
            sym = order["symbol"]
            qty = int(abs(order.get("quantity", 0)))
            if qty == 0:
                continue

            if sym == "QQQ_LEAPS":
                px = leaps_fill_px
                if px <= 0 or qty * px < MIN_ORDER_NOTIONAL:
                    continue
                if order["action"] == "BUY":
                    cost = qty * px
                    if cost > self.cash:
                        qty  = max(0, int((self.cash - 1.0) / px))
                        cost = qty * px
                    if qty == 0:
                        continue
                    prev_c = self.leaps_contracts
                    total_c = prev_c + qty
                    self.leaps_avg_cost = (
                        (prev_c * self.leaps_avg_cost + qty * px) / total_c if total_c else px)
                    self.leaps_contracts = total_c
                    self.cash -= cost
                elif order["action"] == "SELL":
                    qty = min(qty, self.leaps_contracts)
                    if qty == 0:
                        continue
                    self.leaps_contracts -= qty
                    if self.leaps_contracts == 0:
                        self.leaps_avg_cost = 0.0
                    self.cash += qty * px
                continue

            px = fill_prices.get(sym, order.get("estimated_price", 0))
            if px <= 0 or qty * px < MIN_ORDER_NOTIONAL:
                continue

            if order["action"] == "BUY":
                cost = qty * px
                if cost > self.cash:
                    qty  = max(0, int((self.cash - 1.0) / px))
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
                self.cash += qty * px


# ================================================================
# MAIN
# ================================================================

def run():
    log.info("=" * 60)
    log.info("TurboCore Pro -- Production Walk-Forward Backtest")
    log.info("  Capital: $%s   Period: %s -> %s", f"{INITIAL_CAPITAL:,.0f}", START_DATE, END_DATE)
    log.info("  Assets : QQQ | QLD | QQQ_LEAPS (B-S 80%% strike) | SGOV")
    log.info("=" * 60)

    data, master_df, leaps_close, leaps_open = download_and_build_master()

    close: dict = {s: data[s]["Close"] for s in EQUITY_TICKERS if s in data}
    opn:   dict = {s: data[s]["Open"]  for s in EQUITY_TICKERS if s in data}

    trading_days    = close["QQQ"].loc[START_DATE:END_DATE].index.tolist()
    portfolio       = Portfolio(INITIAL_CAPITAL)
    pending_orders: list = []
    results:        list = []

    log.info("Simulating %d trading days...", len(trading_days))

    for i, today in enumerate(trading_days):

        # Apply yesterday's orders at today's OPEN
        if pending_orders:
            eq_fill    = {sym: float(opn[sym].loc[today])
                          for sym in EQUITY_TICKERS
                          if sym in opn and today in opn[sym].index}
            leaps_fill = float(leaps_open.loc[today]) if today in leaps_open.index else 0.0
            portfolio.apply_orders(pending_orders, eq_fill, leaps_fill)
            pending_orders = []

        # Mark-to-market at close
        eq_close    = {sym: float(close[sym].loc[today])
                       for sym in EQUITY_TICKERS
                       if sym in close and today in close[sym].index}
        leaps_today = float(leaps_close.loc[today]) if today in leaps_close.index else 0.0
        net_liq     = portfolio.net_liq(eq_close, leaps_today)

        # Signal pipeline -- slice master_df to today (no lookahead)
        slice_df = master_df.loc[:today]
        if len(slice_df) < 200:
            sig = dict(regime="WARMUP", base_signal=0, confidence=0.0,
                       qqq_drawdown=0.0, target_allocation={})
        else:
            try:
                sig = run_turbocore_pro_signal(slice_df)
            except Exception as e:
                log.warning("%s -- signal error: %s", today.date(), e)
                sig = dict(regime="ERROR", base_signal=0, confidence=0.0,
                           qqq_drawdown=0.0, target_allocation={})

        target_alloc = sig["target_allocation"]
        leaps_alloc  = target_alloc.get("QQQ_LEAPS", 0.0)
        eq_alloc     = {k: v for k, v in target_alloc.items() if k != "QQQ_LEAPS"}

        if target_alloc and net_liq > 0:
            eq_net_liq = net_liq * (1.0 - leaps_alloc)
            live_eq_px = {sym: eq_close.get(sym, 0) for sym in eq_alloc
                          if eq_close.get(sym, 0) > 0}
            try:
                eq_orders = calculate_delta_orders(
                    target_matrix     = eq_alloc,
                    current_net_liq   = eq_net_liq,
                    current_positions = dict(portfolio.shares),
                    live_prices       = live_eq_px,
                )
            except Exception as e:
                log.debug("%s -- executor: %s", today.date(), e)
                eq_orders = []

            leaps_target  = net_liq * leaps_alloc
            leaps_current = portfolio.leaps_contracts * leaps_today
            leaps_delta   = leaps_target - leaps_current
            leaps_orders: list = []
            if abs(leaps_delta) >= MIN_ORDER_NOTIONAL and leaps_today > 0:
                qty = int(abs(leaps_delta) / leaps_today)
                if qty > 0:
                    leaps_orders = [{"symbol": "QQQ_LEAPS",
                                     "action": "BUY" if leaps_delta > 0 else "SELL",
                                     "quantity": qty,
                                     "estimated_price": leaps_today}]

            all_orders = eq_orders + leaps_orders
            pending_orders = (
                [o for o in all_orders if o["action"] == "SELL"] +
                [o for o in all_orders if o["action"] == "BUY"]
            )

        row = dict(
            date             = today.date(),
            net_liq          = round(net_liq, 2),
            cash             = round(portfolio.cash, 2),
            total_return_pct = round((net_liq / INITIAL_CAPITAL - 1) * 100, 2),
            regime           = sig["regime"],
            confidence       = round(sig["confidence"], 3),
            base_signal      = sig["base_signal"],
            qqq_drawdown     = round(sig.get("qqq_drawdown", 0.0) * 100, 2),
            alloc_QQQ        = round(target_alloc.get("QQQ", 0)       * 100, 1),
            alloc_QLD        = round(target_alloc.get("QLD", 0)       * 100, 1),
            alloc_LEAPS      = round(target_alloc.get("QQQ_LEAPS", 0) * 100, 1),
            alloc_SGOV       = round(target_alloc.get("SGOV", 0)      * 100, 1),
            QQQ_shares       = portfolio.shares.get("QQQ", 0),
            QLD_shares       = portfolio.shares.get("QLD", 0),
            SGOV_shares      = portfolio.shares.get("SGOV", 0),
            LEAPS_contracts  = portfolio.leaps_contracts,
            leaps_price      = round(leaps_today, 2),
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
    print("  TURBOCORE PRO -- RESULTS")
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

    leaps_days = df[df["LEAPS_contracts"] > 0]
    print(f"\n  LEAPS Active Days : {len(leaps_days):,d} ({len(leaps_days)/len(df)*100:.1f}%)")
    if len(leaps_days):
        print(f"  Avg LEAPS price   : ${df['leaps_price'].mean():.2f}")

    return df


if __name__ == "__main__":
    run()
