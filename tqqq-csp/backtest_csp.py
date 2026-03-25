#!/usr/bin/env python3
"""
================================================================
TQQQ Weekly Cash-Secured Put Strategy — Backtest
================================================================
Simulates selling weekly cash-secured puts on TQQQ with:

  Strategy Rules (from viability analysis doc):
  ─────────────────────────────────────────────
  1. Entry: Monday open, sell 1-week put at ~8-12 delta OTM
  2. Strike: ~8-10% below current TQQQ price (90% PoP target)
  3. Collateral: 100% cash-secured (strike × 100 per contract)
  4. Profit target: Close at 50% of premium (GTC order)
  5. Stop-loss: Close if put price > 3x original premium
  6. Regime filters:
       - SKIP if TQQQ < 200-day SMA (SMA200 circuit breaker)
       - SKIP if VIX > 35 (extreme fear circuit breaker)
       - REDUCED size if VIX > 25 (sell half-normal contracts)
  7. Friday: let expire worthless if OTM, or assign if ITM
  8. If assigned: hold shares + sell covered call (Wheel Phase 2)
     CC strike: ~25-30 delta above current price, same week tenor
  9. Max position: ≤ 25% of account NAV at risk per trade

  Premium estimation:
  ─────────────────────────────────────────────
  Since we don't have historical TQQQ option chains,
  premium is estimated using Black-Scholes with:
    - Strike at put_otm_pct below spot
    - IV = TQQQ 20-day historical vol × iv_multiplier (1.3x)
      (market IV is always higher than realized — the V-R premium)
    - Risk-free rate from ^IRX

Capital: $25,000
Period:  2019-01-01 → 2026-03-20
================================================================
"""

import sys, math, warnings, logging
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

warnings.filterwarnings("ignore")
ROOT = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[
        logging.FileHandler(ROOT / "backtest_csp.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("CSP_Backtest")

# ── Config ────────────────────────────────────────────────────────────────────
INITIAL_CAPITAL   = 25_000.0
START_DATE        = "2019-01-01"
END_DATE          = "2026-03-20"

PUT_OTM_PCT       = 0.09     # Strike = spot × (1 - 0.09) → ~10% OTM
# ── Perplexity-calibrated IV (2026-03-22) ──────────────────────────────────
# Perplexity: TQQQ ATM_IV = max(1.2×HV20, VIX×3/100); OTM put skew ×1.30
# Previously: IV = HV20 × 1.30 → ~$0.20/share (3.6× too low)
# Corrected:  ATM from leverage floor, then skew → ~$0.50-0.80/share
IV_ATM_HV_MULT    = 1.20     # ATM IV minimum = HV20 × 1.2
IV_LEVERAGE_FLOOR = 3.00     # TQQQ: VIX×3 sets the IV floor (3x leverage)
IV_OTM_SKEW       = 1.30     # 10-delta OTM put skew premium (1.2-1.4 per Perplexity)
PROFIT_TARGET_PCT = 0.75     # 75% profit target (closer to hold-to-expiry; was 50%)
STOP_LOSS_MULT    = 3.0      # Close if put price > 3x original premium
MAX_POSITION_PCT  = 0.80     # 80% NAV as collateral (near-full deployment; was 25%)
VIX_SUSPEND       = 35.0     # Suspend new puts above this VIX
VIX_REDUCE        = 25.0     # Half-size puts above this VIX
COMMISSION        = 1.00     # $1 per contract (tastytrade rate)
OUTPUT_CSV        = ROOT / "backtest_csp_results.csv"


# ── Black-Scholes put pricing ─────────────────────────────────────────────────
def bs_put_price(S, K, T, r, sigma):
    """Black-Scholes put price."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return max(K - S, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_put_delta(S, K, T, r, sigma):
    """Black-Scholes put delta (negative for puts)."""
    if T <= 0 or sigma <= 0:
        return -1.0 if S < K else 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return norm.cdf(d1) - 1.0


def find_delta_strike(S, T, r, sigma, target_delta=-0.10):
    """Find strike that produces the target delta via binary search."""
    lo, hi = S * 0.30, S * 0.99
    for _ in range(50):
        mid = (lo + hi) / 2
        d   = bs_put_delta(S, mid, T, r, sigma)
        if abs(d - target_delta) < 1e-4:
            return mid
        if d > target_delta:
            hi = mid
        else:
            lo = mid
    return S * (1 - PUT_OTM_PCT)  # fallback


# ── Data Download ─────────────────────────────────────────────────────────────
log.info("Downloading market data (2017 → %s)...", END_DATE)
tqqq_raw = yf.download("TQQQ", start="2017-01-01", end=END_DATE,
                       auto_adjust=True, progress=False)
qqq_raw  = yf.download("QQQ",  start="2017-01-01", end=END_DATE,
                       auto_adjust=True, progress=False)
vix_raw  = yf.download("^VIX", start="2017-01-01", end=END_DATE,
                       progress=False)
irx_raw  = yf.download("^IRX", start="2017-01-01", end=END_DATE,
                       progress=False)

def squeeze(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df

tqqq_raw = squeeze(tqqq_raw)
qqq_raw  = squeeze(qqq_raw)
vix_raw  = squeeze(vix_raw)
irx_raw  = squeeze(irx_raw)

tqqq_close = tqqq_raw["Close"]
tqqq_open  = tqqq_raw["Open"]
qqq_close  = qqq_raw["Close"].reindex(tqqq_close.index).ffill()
vix_close  = vix_raw["Close"].reindex(tqqq_close.index).ffill().fillna(20.0).squeeze()
rf_rate    = (irx_raw["Close"] / 100.0).reindex(tqqq_close.index).ffill().fillna(0.045).squeeze()

# ── Build master features ─────────────────────────────────────────────────────
log.info("Building features...")
master = pd.DataFrame(index=tqqq_close.index)
master["tqqq_close"]  = tqqq_close
master["tqqq_open"]   = tqqq_open
master["qqq_close"]   = qqq_close
master["vix"]         = vix_close
master["rf"]          = rf_rate

# SMA filters
master["tqqq_sma200"] = tqqq_close.rolling(200).mean()
master["tqqq_sma50"]  = tqqq_close.rolling(50).mean()
master["above_sma200"]= tqqq_close > master["tqqq_sma200"]
master["above_sma50"] = tqqq_close > master["tqqq_sma50"]

# Historical vol (20-day) for IV estimation
log_ret                = np.log(tqqq_close / tqqq_close.shift(1))
master["tqqq_hv20"]   = log_ret.rolling(20).std() * math.sqrt(252)
master["tqqq_hv5"]    = log_ret.rolling(5).std()  * math.sqrt(252)

# Perplexity-calibrated IV columns
# ATM IV = max(HV20 * 1.2, VIX * 3 / 100)  [leverage floor]
# OTM 10-delta put IV = ATM_IV * 1.30       [downside skew]
master["iv_atm"]  = master[["tqqq_hv20"]].assign(
    lev_floor=master["vix"] * IV_LEVERAGE_FLOOR / 100
).apply(lambda r: max(r["tqqq_hv20"] * IV_ATM_HV_MULT,
                       r["lev_floor"]), axis=1)
master["iv_put10d"] = master["iv_atm"] * IV_OTM_SKEW
master["iv_put10d"] = master["iv_put10d"].clip(upper=3.0, lower=0.10)

master = master.dropna()

# ── Identify weekly expiration Fridays ────────────────────────────────────────
trading_days = master.loc[START_DATE:END_DATE].index
fridays = [d for d in trading_days if d.weekday() == 4]  # Friday = 4
mondays = [d for d in trading_days if d.weekday() == 0]  # Monday = 0

# Map each Monday to its nearest following Friday
def next_friday_after(date, friday_list):
    for f in friday_list:
        if f >= date:
            return f
    return None

log.info("Identified %d Mondays and %d Fridays in backtest window.", len(mondays), len(fridays))

# ── Portfolio State ───────────────────────────────────────────────────────────
class Portfolio:
    def __init__(self, capital):
        self.cash         = capital
        self.open_puts    = []    # list of dicts (active CSP trades)
        self.tqqq_shares  = 0     # shares from assignment
        self.open_calls   = []    # covered calls written against assigned shares
        self.trade_log    = []

    def net_liq(self, tqqq_px, put_prices, call_prices):
        equity = self.tqqq_shares * tqqq_px
        put_liability = sum(
            p["contracts"] * 100 * pp
            for p, pp in zip(self.open_puts, put_prices)
        )
        call_liability = sum(
            c["contracts"] * 100 * cp
            for c, cp in zip(self.open_calls, call_prices)
        )
        return self.cash + equity - put_liability - call_liability

# ── Main backtest loop ────────────────────────────────────────────────────────
log.info("Starting backtest (%s → %s)...", START_DATE, END_DATE)

portfolio  = Portfolio(INITIAL_CAPITAL)
daily_rows = []

weekday_states = {
    "open_puts":   [],  # active CSP trades
    "open_calls":  [],  # covered call trades
    "tqqq_shares": 0,
}

def mark_puts(row, puts):
    """Mark-to-market open puts."""
    prices = []
    for p in puts:
        days_left = (p["expiry"] - row.name).days
        T = max(days_left / 365.0, 1/365.0)
        px = bs_put_price(row["tqqq_close"], p["strike"], T, row["rf"], p["iv"])
        prices.append(px)
    return prices

def mark_calls(row, calls, tqqq_shares):
    """Mark-to-market open covered calls."""
    prices = []
    for c in calls:
        days_left = (c["expiry"] - row.name).days
        T = max(days_left / 365.0, 1/365.0)
        px = bs_put_price(row["tqqq_close"], c["strike"], T, row["rf"], c["iv"])
        # Actually use call price
        S, K = row["tqqq_close"], c["strike"]
        if T <= 0 or c["iv"] <= 0:
            px_call = max(S - K, 0.0)
        else:
            d1 = (math.log(S / K) + (row["rf"] + 0.5 * c["iv"]**2) * T) / (c["iv"] * math.sqrt(T))
            d2 = d1 - c["iv"] * math.sqrt(T)
            px_call = S * norm.cdf(d1) - K * math.exp(-row["rf"] * T) * norm.cdf(d2)
        prices.append(px_call)
    return prices

total_puts_opened   = 0
total_puts_expired  = 0
total_puts_closed   = 0
total_puts_assigned = 0
total_calls_opened  = 0
total_weeks_skipped = 0
total_weeks_reduced = 0

for i, date in enumerate(trading_days):
    if date not in master.index:
        continue
    row = master.loc[date]

    # ── 1. Process expirations (Friday) ───────────────────────────────────────
    if date.weekday() == 4:  # Friday
        new_puts = []
        for put in portfolio.open_puts:
            if put["expiry"] == date:
                tqqq_px = row["tqqq_close"]
                if tqqq_px >= put["strike"]:
                    # Expired worthless — keep premium ✅
                    freed_collateral = put["contracts"] * 100 * put["strike"]
                    portfolio.cash += freed_collateral
                    total_puts_expired += 1
                    put["result"] = "EXPIRED"
                    portfolio.trade_log.append({**put, "result": "EXPIRED",
                        "pnl": put["premium_collected"]})
                else:
                    # Assigned — forced to buy shares at strike ❌
                    shares_received = put["contracts"] * 100
                    cost_basis      = put["strike"] * shares_received
                    freed_cash      = put["contracts"] * 100 * put["strike"]
                    portfolio.cash  += freed_cash - cost_basis  # net 0 (already reserved)
                    portfolio.tqqq_shares += shares_received
                    total_puts_assigned += 1
                    loss = (put["strike"] - tqqq_px) * shares_received - put["premium_collected"]
                    portfolio.trade_log.append({**put, "result": "ASSIGNED",
                        "pnl": -loss})
                    log.debug("  %s ASSIGNED: strike=%.2f spot=%.2f loss=$%.0f",
                             date.date(), put["strike"], tqqq_px, loss)
            else:
                new_puts.append(put)
        portfolio.open_puts = new_puts

        # Covered call expirations
        new_calls = []
        for call in portfolio.open_calls:
            if call["expiry"] == date:
                tqqq_px = row["tqqq_close"]
                if tqqq_px <= call["strike"]:
                    # CC expired worthless — keep premium
                    portfolio.cash += call["premium_collected"]
                    total_calls_opened += 1
                    portfolio.trade_log.append({**call, "result": "CC_EXPIRED",
                        "pnl": call["premium_collected"]})
                else:
                    # Shares called away at strike
                    proceeds = call["contracts"] * 100 * call["strike"]
                    portfolio.cash += proceeds + call["premium_collected"]
                    portfolio.tqqq_shares -= call["contracts"] * 100
                    portfolio.tqqq_shares = max(0, portfolio.tqqq_shares)
                    portfolio.trade_log.append({**call, "result": "CC_EXERCISED",
                        "pnl": call["premium_collected"] + (call["strike"] - call["cost_basis"]) * call["contracts"] * 100})
            else:
                new_calls.append(call)
        portfolio.open_calls = new_calls

    # ── 2. Daily mark-to-market and stop-loss / profit-target ─────────────────
    put_prices  = mark_puts(row, portfolio.open_puts)
    call_prices = mark_calls(row, portfolio.open_calls, portfolio.tqqq_shares)

    surviving_puts = []
    for put, px in zip(portfolio.open_puts, put_prices):
        orig = put["premium_per_share"]
        # Profit target: current value ≤ 50% of original premium
        if px <= orig * PROFIT_TARGET_PCT:
            # Close at 50% profit
            profit = put["contracts"] * 100 * (orig - px) - COMMISSION * put["contracts"]
            freed  = put["contracts"] * 100 * put["strike"]
            portfolio.cash += freed + profit
            portfolio.cash -= put["contracts"] * 100 * px  # buy back cost
            total_puts_closed += 1
            portfolio.trade_log.append({**put, "result": "PROFIT_TARGET",
                "pnl": profit})
        elif px >= orig * STOP_LOSS_MULT:
            # Stop-loss: close immediately
            loss  = put["contracts"] * 100 * (px - orig) + COMMISSION * put["contracts"]
            freed = put["contracts"] * 100 * put["strike"]
            portfolio.cash += freed - put["contracts"] * 100 * px
            total_puts_closed += 1
            portfolio.trade_log.append({**put, "result": "STOP_LOSS",
                "pnl": -loss})
            log.debug("  %s STOP_LOSS: strike=%.2f px=%.2f orig=%.2f",
                     date.date(), put["strike"], px, orig)
        else:
            surviving_puts.append(put)
    portfolio.open_puts = surviving_puts

    # ── 3. Monday: open new CSP if conditions pass ────────────────────────────
    if date.weekday() == 0 and not portfolio.open_puts:
        tqqq_px  = row["tqqq_close"]
        vix      = row["vix"]
        above200 = bool(row["above_sma200"])
        # Perplexity calibration: use ATM IV with OTM skew
        iv       = float(row["iv_put10d"])
        iv       = max(min(iv, 3.0), 0.10)
        rf       = float(row["rf"])
        expiry   = next_friday_after(date, fridays)

        # Regime filters
        if not above200:
            total_weeks_skipped += 1
            log.debug("  %s SKIP (below SMA200: tqqq=%.2f sma=%.2f)", date.date(), tqqq_px, row["tqqq_sma200"])
        elif vix > VIX_SUSPEND:
            total_weeks_skipped += 1
            log.debug("  %s SKIP (VIX circuit breaker: %.1f)", date.date(), vix)
        elif expiry is None:
            total_weeks_skipped += 1
        else:
            T_days = (expiry - date).days
            T = T_days / 365.0

            # Find 10-delta strike (target ~90% PoP)
            strike = find_delta_strike(tqqq_px, T, rf, iv, target_delta=-0.10)
            premium_per_share = bs_put_price(tqqq_px, strike, T, rf, iv)
            premium_per_share = max(premium_per_share, 0.01)

            # Position sizing: max 25% of NAV as collateral
            nl  = portfolio.cash + portfolio.tqqq_shares * tqqq_px
            max_notional  = nl * MAX_POSITION_PCT
            max_contracts = int(max_notional / (strike * 100))

            # Reduce size in elevated VIX
            if vix > VIX_REDUCE:
                max_contracts = max(1, max_contracts // 2)
                total_weeks_reduced += 1

            contracts = max(0, max_contracts)

            if contracts > 0 and portfolio.cash >= contracts * strike * 100:
                # Reserve collateral
                collateral = contracts * 100 * strike
                portfolio.cash -= collateral
                premium_total = contracts * 100 * premium_per_share - COMMISSION * contracts

                put_trade = {
                    "open_date":         date,
                    "expiry":            expiry,
                    "strike":            strike,
                    "spot_at_open":      tqqq_px,
                    "iv":                iv,
                    "premium_per_share": premium_per_share,
                    "premium_collected": premium_total,
                    "contracts":         contracts,
                    "collateral":        collateral,
                    "type":              "CSP",
                }
                portfolio.open_puts.append(put_trade)
                portfolio.cash += premium_total  # Premium received immediately
                total_puts_opened += 1

    # ── 4. After assignment: sell covered call if we have shares (Monday) ──────
    if date.weekday() == 0 and portfolio.tqqq_shares > 0 and not portfolio.open_calls:
        tqqq_px = row["tqqq_close"]
        iv      = float(row["iv_put10d"])  # same calibrated IV for CC phase
        iv      = max(min(iv, 3.0), 0.10)
        rf      = float(row["rf"])
        expiry  = next_friday_after(date, fridays)

        if expiry:
            T       = max((expiry - date).days / 365.0, 1/365.0)
            # ~25-delta call: slightly OTM
            cc_strike = tqqq_px * 1.04  # ~4% OTM call
            S, K = tqqq_px, cc_strike
            d1 = (math.log(S / K) + (rf + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
            d2 = d1 - iv * math.sqrt(T)
            cc_premium = S * norm.cdf(d1) - K * math.exp(-rf * T) * norm.cdf(d2)
            cc_premium = max(cc_premium, 0.01)

            cc_contracts = portfolio.tqqq_shares // 100
            if cc_contracts > 0:
                cc_total = cc_contracts * 100 * cc_premium - COMMISSION * cc_contracts
                portfolio.cash += cc_total
                portfolio.open_calls.append({
                    "open_date":         date,
                    "expiry":            expiry,
                    "strike":            cc_strike,
                    "iv":                iv,
                    "premium_per_share": cc_premium,
                    "premium_collected": cc_total,
                    "contracts":         cc_contracts,
                    "cost_basis":        tqqq_px,
                    "type":              "CC",
                })
                total_calls_opened += 1

    # ── 5. Record daily NAV ───────────────────────────────────────────────────
    put_px_now  = mark_puts(row, portfolio.open_puts)
    call_px_now = mark_calls(row, portfolio.open_calls, portfolio.tqqq_shares)
    nl = portfolio.net_liq(row["tqqq_close"], put_px_now, call_px_now)

    daily_rows.append({
        "date":            date.date(),
        "net_liq":         round(nl, 2),
        "cash":            round(portfolio.cash, 2),
        "tqqq_shares":     portfolio.tqqq_shares,
        "open_puts":       len(portfolio.open_puts),
        "open_calls":      len(portfolio.open_calls),
        "tqqq_price":      round(row["tqqq_close"], 2),
        "vix":             round(row["vix"], 1),
        "above_sma200":    int(row["above_sma200"]),
        "total_return_pct":round((nl / INITIAL_CAPITAL - 1) * 100, 2),
    })

    if i % 100 == 0 or i == len(trading_days) - 1:
        log.info("  %s | NAV=$%.0f | puts=%d | shares=%d | ret=%+.1f%%",
                 str(date.date()), nl, len(portfolio.open_puts),
                 portfolio.tqqq_shares, (nl/INITIAL_CAPITAL-1)*100)

# ── Results ───────────────────────────────────────────────────────────────────
df = pd.DataFrame(daily_rows)
df.to_csv(OUTPUT_CSV, index=False)

final   = df["net_liq"].iloc[-1]
peak    = df["net_liq"].max()
# Max drawdown calculation
roll_max = df["net_liq"].cummax()
drawdown = (df["net_liq"] - roll_max) / roll_max * 100
max_dd   = drawdown.min()
years    = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
cagr     = ((final / INITIAL_CAPITAL) ** (1 / years) - 1) * 100
total_r  = (final / INITIAL_CAPITAL - 1) * 100

# Trade log analysis
tlog = pd.DataFrame(portfolio.trade_log) if portfolio.trade_log else pd.DataFrame()
csp_log  = tlog[tlog.get("type","") == "CSP"] if len(tlog) > 0 else pd.DataFrame()
win_rate = 0.0
avg_win  = 0.0
avg_loss = 0.0
if len(csp_log) > 0 and "pnl" in csp_log.columns:
    win_rate = (csp_log["pnl"] > 0).mean() * 100
    wins     = csp_log[csp_log["pnl"] > 0]["pnl"]
    losses   = csp_log[csp_log["pnl"] <= 0]["pnl"]
    avg_win  = wins.mean() if len(wins) > 0 else 0
    avg_loss = losses.mean() if len(losses) > 0 else 0

print("\n" + "=" * 60)
print("  TQQQ CASH-SECURED PUT STRATEGY — RESULTS")
print("=" * 60)
print(f"  Start Capital : ${INITIAL_CAPITAL:>12,.2f}")
print(f"  Final Value   : ${final:>12,.2f}")
print(f"  Total Return  : {total_r:>12.1f}%")
print(f"  CAGR          : {cagr:>12.1f}%")
print(f"  Max Drawdown  : {max_dd:>12.1f}%")
print(f"  Peak Value    : ${peak:>12,.2f}")
print(f"  Output CSV    : {OUTPUT_CSV}")
print("=" * 60)
print(f"\n  Trade Summary:")
print(f"    CSPs Opened   : {total_puts_opened:>5d}")
print(f"    Expired OTM   : {total_puts_expired:>5d}  (premium kept)")
print(f"    Closed early  : {total_puts_closed:>5d}  (profit target / stop-loss)")
print(f"    Assigned ITM  : {total_puts_assigned:>5d}  (forced to buy shares)")
print(f"    Weeks skipped : {total_weeks_skipped:>5d}  (regime filter)")
print(f"    Weeks reduced : {total_weeks_reduced:>5d}  (VIX > 25, half-size)")
print(f"    Covered Calls : {total_calls_opened:>5d}  (wheel phase 2)")
if len(csp_log) > 0:
    print(f"\n  CSP Win Rate  : {win_rate:>5.1f}%")
    print(f"  Avg Win       : ${avg_win:>8.0f}")
    print(f"  Avg Loss      : ${avg_loss:>8.0f}")
print("=" * 60)
