
python_code = '''"""
QQQ PMCC Backtester v2
======================
Integrates: TurboBounce QQQ LEAPS Architecture (5-layer) +
            YouTube/BCI/Tastytrade PMCC best practices

Dependencies: yfinance, numpy, pandas, scipy, lightgbm (optional for ML gate)
Install: pip install yfinance numpy pandas scipy lightgbm hmmlearn
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from scipy.stats import norm
from enum import Enum

# ─────────────────────────────────────────
# ENUMS & CONSTANTS
# ─────────────────────────────────────────

class Regime(str, Enum):
    BULL_STRONG     = "BULL_STRONG"
    BULL_MODERATE   = "BULL_MODERATE"
    CHOPPY          = "CHOPPY"
    BEAR            = "BEAR"
    BEAR_SMA_FORCED = "BEAR_SMA_FORCED"

class LeapsStatus(str, Enum):
    NONE = "NONE"
    OPEN = "OPEN"

class PmccStatus(str, Enum):
    NONE       = "NONE"
    ACTIVE     = "ACTIVE"
    DEFENSIVE  = "DEFENSIVE"

class DrawdownTier(str, Enum):
    NONE                  = "NONE"
    TIER1_ROLL_SHORT_DOWN = "TIER1_ROLL_SHORT_DOWN"
    TIER1_MONITOR         = "TIER1_MONITOR"
    TIER2_EXIT            = "TIER2_EXIT"
    TIER3_EMERGENCY_EXIT  = "TIER3_EMERGENCY_EXIT"

# Slippage model: fraction of option price
SLIPPAGE = {
    "low_vix":  0.005,   # VIX < 20
    "mid_vix":  0.010,   # VIX 20-35
    "high_vix": 0.020,   # VIX > 35 (wide bid-ask in panic)
}

# ─────────────────────────────────────────
# BLACK-SCHOLES OPTION PRICER
# ─────────────────────────────────────────

def bs_call_price(S, K, T, r, sigma):
    """Standard Black-Scholes call price. T in years."""
    if T <= 0 or sigma <= 0:
        return max(S - K, 0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

def bs_delta(S, K, T, r, sigma):
    """Black-Scholes call delta."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.cdf(d1)

def find_strike_by_delta(S, T, r, sigma, target_delta, lo_pct=0.5, hi_pct=1.5, tol=1e-4):
    """Binary search for strike giving target_delta."""
    lo, hi = S * lo_pct, S * hi_pct
    for _ in range(50):
        mid = (lo + hi) / 2
        d = bs_delta(S, mid, T, r, sigma)
        if abs(d - target_delta) < tol:
            return mid
        if d < target_delta:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2

def bs_extrinsic(S, K, T, r, sigma):
    """Extrinsic (time) value of a call option."""
    price = bs_call_price(S, K, T, r, sigma)
    intrinsic = max(S - K, 0)
    return price - intrinsic

def slippage_pct(vix):
    if vix < 20:   return SLIPPAGE["low_vix"]
    if vix < 35:   return SLIPPAGE["mid_vix"]
    return SLIPPAGE["high_vix"]

# ─────────────────────────────────────────
# REGIME CLASSIFIER (Layer A)
# ─────────────────────────────────────────

def classify_regime(hmm_p_bull: float, vix: float, qqq: float,
                    sma100: float, sma200: float) -> Regime:
    if qqq < sma200 * 0.97:
        return Regime.BEAR_SMA_FORCED
    if hmm_p_bull < 0.35 or qqq < sma100:
        return Regime.BEAR
    if 0.35 <= hmm_p_bull < 0.55:
        return Regime.CHOPPY
    if 0.55 <= hmm_p_bull < 0.70 and vix < 35:
        return Regime.BULL_MODERATE
    if hmm_p_bull >= 0.70 and vix < 25:
        return Regime.BULL_STRONG
    return Regime.CHOPPY

def smooth_regime(regime_series: pd.Series, window: int = 5) -> pd.Series:
    """Rolling mode to prevent single-day flip-flops (5-day smoothing)."""
    return regime_series.rolling(window, min_periods=1).apply(
        lambda x: pd.Series(x).mode()[0], raw=False
    )

# ─────────────────────────────────────────
# ML CONFIDENCE STUB (Layer B)
# Replace with real LightGBM specialist models in production
# ─────────────────────────────────────────

def ml_confidence_stub(row: pd.Series, regime: Regime) -> float:
    """
    Stub that approximates ML confidence using RSI + VIX + gap.
    Replace with LightGBM bull/neutral specialist inference in production.
    """
    if regime in [Regime.BEAR, Regime.BEAR_SMA_FORCED]:
        return 0.0
    score = 0.0
    # RSI: lower is better for dip-buying
    if "rsi_14" in row:
        score += max(0, (40 - row["rsi_14"]) / 40) * 0.35
    # VIX percentile rank: higher = more fear = better entry
    if "vix_pctile" in row:
        score += row["vix_pctile"] * 0.30
    # Gap down flag: stronger gap = better discount
    if "gap_pct" in row:
        score += min(abs(row["gap_pct"]) / 0.03, 1.0) * 0.20
    # HMM bull probability
    score += row.get("hmm_p_bull", 0.5) * 0.15
    return min(score, 1.0)

def ml_threshold(regime: Regime) -> float:
    return {
        Regime.BULL_STRONG:   0.45,
        Regime.BULL_MODERATE: 0.42,
        Regime.CHOPPY:        0.42,
    }.get(regime, 1.0)

# ─────────────────────────────────────────
# BCI TRADE INITIALIZATION CHECK
# ─────────────────────────────────────────

def bci_initialization_check(S: float, leaps_strike: float, leaps_price: float,
                               short_strike: float, short_credit: float,
                               T_leaps: float, T_short: float, r: float, sigma: float,
                               rally_pct: float = 0.10) -> bool:
    """
    BCI formula: simulate QQQ +rally_pct and verify combined close is still profitable.
    If the test fails, reject the PMCC setup.
    """
    S_rally = S * (1 + rally_pct)
    # LEAPS value at rally price (Black-Scholes, remaining tenor)
    leaps_value_rally = bs_call_price(S_rally, leaps_strike, T_leaps, r, sigma)
    # Short call now deep ITM — approximate exit cost as intrinsic + small extrinsic
    short_cost_rally  = bs_call_price(S_rally, short_strike, T_short, r, sigma)
    pnl = (leaps_value_rally - leaps_price) + (short_credit - short_cost_rally)
    return pnl >= 0

# ─────────────────────────────────────────
# POSITION SIZE
# ─────────────────────────────────────────

def size_position(virtual_nav: float, leaps_price: float, max_contracts: int = 5) -> int:
    allocation = virtual_nav * 0.33
    contracts  = int(allocation / (leaps_price * 100))
    return max(1, min(contracts, max_contracts))

# ─────────────────────────────────────────
# DRAWDOWN GUARD (Layer E)
# ─────────────────────────────────────────

def drawdown_guard(leaps_delta: float, leaps_dte: int,
                   qqq: float, qqq_52w_low: float) -> DrawdownTier:
    if qqq <= qqq_52w_low * 1.02:
        return DrawdownTier.TIER3_EMERGENCY_EXIT
    if leaps_delta < 0.30 and leaps_dte < 60:
        return DrawdownTier.TIER2_EXIT
    if leaps_delta < 0.65:
        return DrawdownTier.TIER1_ROLL_SHORT_DOWN
    return DrawdownTier.NONE

# ─────────────────────────────────────────
# PMCC MANAGEMENT (Layer D — per-day)
# ─────────────────────────────────────────

def manage_pmcc(short_price: float, C0: float, days_elapsed: int,
                short_dte: int, short_delta: float,
                qqq: float, short_strike: float,
                regime: Regime, leaps_delta: float) -> str:
    """Returns management action string."""

    # ── BCI 20%/10% profit-take rule ──
    if days_elapsed < 10 and short_price <= C0 * 0.20:
        return "PROFIT_TAKE_EARLY"
    if days_elapsed >= 10 and short_price <= C0 * 0.10:
        return "PROFIT_TAKE_LATE"

    # ── Tastytrade 21-DTE gamma management ──
    if short_dte <= 21:
        if short_delta > 0.10:
            return "GAMMA_MANAGE"
        return "EXPIRE_WORTHLESS"

    # ── Assignment / rally risk ──
    if qqq >= short_strike * 0.97 or short_delta >= 0.40:
        return "ROLL_UP_OUT"

    # ── Loss limit: 2× credit ──
    if short_price >= C0 * 2.0:
        return "LOSS_LIMIT_CLOSE"

    # ── Regime deterioration ──
    if regime in [Regime.BEAR, Regime.BEAR_SMA_FORCED]:
        return "EMERGENCY_CLOSE"
    if regime == Regime.CHOPPY:
        return "DEFENSIVE_ROLL"

    # ── Layer E Tier 1 integration ──
    if leaps_delta < 0.65:
        return "TIER1_ROLL_DOWN"

    return "HOLD"

# ─────────────────────────────────────────
# POSITION STATE DATACLASS
# ─────────────────────────────────────────

@dataclass
class Position:
    # LEAPS
    leaps_status:       LeapsStatus = LeapsStatus.NONE
    leaps_entry_price:  float = 0.0
    leaps_entry_date:   Optional[pd.Timestamp] = None
    leaps_strike:       float = 0.0
    leaps_expiry_date:  Optional[pd.Timestamp] = None
    leaps_contracts:    int = 0
    leaps_entry_qqq:    float = 0.0
    leaps_delta:        float = 0.0
    leaps_dte:          int = 0

    # PMCC
    pmcc_status:             PmccStatus = PmccStatus.NONE
    short_strike:            float = 0.0
    short_expiry_date:       Optional[pd.Timestamp] = None
    short_call_credit:       float = 0.0
    short_call_entry_date:   Optional[pd.Timestamp] = None
    short_call_delta:        float = 0.0
    short_call_dte:          int = 0
    pmcc_credit_cumulative:  float = 0.0

    def leaps_age(self, today: pd.Timestamp) -> int:
        if self.leaps_entry_date is None:
            return 0
        return (today - self.leaps_entry_date).days

    def pmcc_days_elapsed(self, today: pd.Timestamp) -> int:
        if self.short_call_entry_date is None:
            return 0
        return (today - self.short_call_entry_date).days

    def cost_basis(self) -> float:
        return self.leaps_entry_price - self.pmcc_credit_cumulative

# ─────────────────────────────────────────
# MAIN BACKTEST ENGINE
# ─────────────────────────────────────────

def run_backtest(df: pd.DataFrame,
                 virtual_nav: float = 25_000.0,
                 r: float = 0.045,
                 max_positions: int = 3) -> pd.DataFrame:
    """
    df must contain columns:
      date, qqq_open, qqq_close, vix, vix3m, hmm_p_bull,
      sma50, sma100, sma200, qqq_52w_low,
      rsi_14, vix_pctile, gap_pct
    All implied volatility proxied by VIX/100 for Black-Scholes sigma.

    Returns daily results DataFrame with nav, regime, pmcc_income columns.
    """
    results = []
    pos = Position()
    cash = virtual_nav
    positions_open = 0

    for idx, row in df.iterrows():
        date    = row["date"]
        S       = row["qqq_close"]
        S_open  = row["qqq_open"]
        vix     = row["vix"]
        sigma   = vix / 100.0   # proxy IV from VIX
        q52low  = row["qqq_52w_low"]
        regime  = Regime(row["regime_smooth"])  # pre-computed smoothed regime

        gap_pct = (S_open - row.get("prev_close", S_open)) / row.get("prev_close", S_open) \
                  if "prev_close" in row else 0.0

        slip = slippage_pct(vix)

        # ────── MORNING EXIT SCAN (9:45 AM proxy on open) ──────
        if pos.leaps_status == LeapsStatus.OPEN:
            dg_morning = drawdown_guard(pos.leaps_delta, pos.leaps_dte, S_open, q52low)
            if dg_morning == DrawdownTier.TIER3_EMERGENCY_EXIT:
                # Close both legs at open with 4% slippage
                T_rem = pos.leaps_dte / 365.0
                leaps_val = bs_call_price(S_open, pos.leaps_strike, T_rem, r, sigma)
                leaps_exit = leaps_val * (1 - 0.04) * 100 * pos.leaps_contracts
                cash += leaps_exit
                if pos.pmcc_status != PmccStatus.NONE:
                    T_s = pos.short_call_dte / 365.0
                    short_val = bs_call_price(S_open, pos.short_strike, T_s, r, sigma)
                    short_exit = short_val * (1 + 0.04) * 100 * pos.leaps_contracts
                    cash -= short_exit
                pos = Position()
                positions_open = max(0, positions_open - 1)
                results.append({"date": date, "nav": cash, "regime": regime.value,
                                 "action": "TIER3_EXIT", "pmcc_income": 0})
                continue

        # ────── UPDATE LEAPS MARK-TO-MARKET ──────
        leaps_mark = 0.0
        short_mark = 0.0
        if pos.leaps_status == LeapsStatus.OPEN:
            pos.leaps_dte = max(0, (pos.leaps_expiry_date - date).days)
            T_l = pos.leaps_dte / 365.0
            leaps_mark = bs_call_price(S, pos.leaps_strike, T_l, r, sigma)
            pos.leaps_delta = bs_delta(S, pos.leaps_strike, T_l, r, sigma)

            if pos.pmcc_status != PmccStatus.NONE:
                pos.short_call_dte = max(0, (pos.short_expiry_date - date).days)
                T_s = pos.short_call_dte / 365.0
                short_mark = bs_call_price(S, pos.short_strike, T_s, r, sigma)
                pos.short_call_delta = bs_delta(S, pos.short_strike, T_s, r, sigma)

        # ────── AFTERNOON DRAWDOWN GUARD ──────
        pmcc_income_today = 0.0
        if pos.leaps_status == LeapsStatus.OPEN:
            dg = drawdown_guard(pos.leaps_delta, pos.leaps_dte, S, q52low)

            if dg == DrawdownTier.TIER2_EXIT:
                T_rem = pos.leaps_dte / 365.0
                leaps_exit = bs_call_price(S, pos.leaps_strike, T_rem, r, sigma) * (1 - slip) * 100 * pos.leaps_contracts
                cash += leaps_exit
                if pos.pmcc_status != PmccStatus.NONE:
                    T_s = pos.short_call_dte / 365.0
                    short_exit = bs_call_price(S, pos.short_strike, T_s, r, sigma) * (1 + slip) * 100 * pos.leaps_contracts
                    cash -= short_exit
                pos = Position()
                positions_open = max(0, positions_open - 1)
                results.append({"date": date, "nav": cash + leaps_mark * 100,
                                 "regime": regime.value, "action": "TIER2_EXIT", "pmcc_income": 0})
                continue

            if dg == DrawdownTier.TIER1_ROLL_SHORT_DOWN and pos.pmcc_status == PmccStatus.ACTIVE:
                # Roll short call down to 0.15 delta (same expiry)
                T_s = pos.short_call_dte / 365.0
                new_strike = find_strike_by_delta(S, T_s, r, sigma, 0.15)
                buyback_cost = short_mark * (1 + slip) * 100 * pos.leaps_contracts
                new_credit   = bs_call_price(S, new_strike, T_s, r, sigma) * (1 - slip) * 100 * pos.leaps_contracts
                cash -= (buyback_cost - new_credit)
                pos.short_strike = new_strike
                pos.short_call_credit = bs_call_price(S, new_strike, T_s, r, sigma)
                pos.pmcc_status = PmccStatus.DEFENSIVE

        # ────── PMCC MANAGEMENT ──────
        if pos.leaps_status == LeapsStatus.OPEN and pos.pmcc_status != PmccStatus.NONE:
            T_s = pos.short_call_dte / 365.0
            short_price = bs_call_price(S, pos.short_strike, T_s, r, sigma)
            days_elapsed = pos.pmcc_days_elapsed(date)

            action = manage_pmcc(
                short_price, pos.short_call_credit, days_elapsed,
                pos.short_call_dte, pos.short_call_delta,
                S, pos.short_strike, regime, pos.leaps_delta
            )

            if action in ["PROFIT_TAKE_EARLY", "PROFIT_TAKE_LATE", "EXPIRE_WORTHLESS"]:
                buyback = short_price * (1 + slip) * 100 * pos.leaps_contracts
                gross_credit = pos.short_call_credit * 100 * pos.leaps_contracts
                net_income = gross_credit - buyback
                cash += net_income
                pos.pmcc_credit_cumulative += (pos.short_call_credit - short_price)
                pmcc_income_today = net_income
                pos.pmcc_status = PmccStatus.NONE
                pos.short_strike = 0.0
                # Immediately try re-entry
                qqq_vs_entry = (S - pos.leaps_entry_qqq) / pos.leaps_entry_qqq
                can_reenter = (
                    pos.leaps_status == LeapsStatus.OPEN and
                    regime in [Regime.BULL_STRONG, Regime.BULL_MODERATE] and
                    pos.leaps_age(date) >= 5 and
                    pos.leaps_dte > 60 and
                    qqq_vs_entry >= 0.02 and
                    16 <= vix <= 35
                )
                if can_reenter:
                    dte_target = 30 if vix > 20 else 35
                    delta_tgt  = 0.28 if regime == Regime.BULL_STRONG else 0.23
                    T_new = dte_target / 365.0
                    new_strike  = find_strike_by_delta(S, T_new, r, sigma, delta_tgt)
                    new_premium = bs_call_price(S, new_strike, T_new, r, sigma)
                    if new_premium >= 0.50:
                        credit_received = new_premium * (1 - slip) * 100 * pos.leaps_contracts
                        cash += credit_received
                        pos.short_strike          = new_strike
                        pos.short_call_credit     = new_premium
                        pos.short_call_entry_date = date
                        pos.short_expiry_date     = date + pd.Timedelta(days=dte_target)
                        pos.pmcc_status           = PmccStatus.ACTIVE

            elif action == "GAMMA_MANAGE":
                # Close and re-sell if possible
                buyback = short_price * (1 + slip) * 100 * pos.leaps_contracts
                cash -= buyback
                pos.pmcc_credit_cumulative += (pos.short_call_credit - short_price)
                pos.pmcc_status = PmccStatus.NONE
                # Open fresh 30-35 DTE
                T_new = 32 / 365.0
                delta_tgt = 0.28 if regime == Regime.BULL_STRONG else 0.23
                new_strike  = find_strike_by_delta(S, T_new, r, sigma, delta_tgt)
                new_premium = bs_call_price(S, new_strike, T_new, r, sigma)
                if new_premium >= 0.50:
                    cash += new_premium * (1 - slip) * 100 * pos.leaps_contracts
                    pos.short_strike          = new_strike
                    pos.short_call_credit     = new_premium
                    pos.short_call_entry_date = date
                    pos.short_expiry_date     = date + pd.Timedelta(days=32)
                    pos.pmcc_status           = PmccStatus.ACTIVE

            elif action == "ROLL_UP_OUT":
                buyback = short_price * (1 + slip) * 100 * pos.leaps_contracts
                new_expiry_days = pos.short_call_dte + 21
                T_new   = new_expiry_days / 365.0
                delta_tgt = 0.25
                new_strike  = find_strike_by_delta(S, T_new, r, sigma, delta_tgt)
                new_premium = bs_call_price(S, new_strike, T_new, r, sigma)
                net = (new_premium - short_price) * 100 * pos.leaps_contracts
                if net >= -10.0:   # net credit or ≤$0.10 debit per contract
                    cash += net * (1 - slip)
                    pos.short_strike          = new_strike
                    pos.short_call_credit     = new_premium
                    pos.short_call_entry_date = date
                    pos.short_expiry_date     = date + pd.Timedelta(days=new_expiry_days)
                else:
                    # Cannot roll for credit — close only
                    cash -= buyback
                    pos.pmcc_status = PmccStatus.NONE

            elif action == "LOSS_LIMIT_CLOSE":
                buyback = short_price * (1 + slip) * 100 * pos.leaps_contracts
                cash -= buyback
                pos.pmcc_credit_cumulative -= pos.short_call_credit  # net loss
                pos.pmcc_status = PmccStatus.NONE

            elif action in ["EMERGENCY_CLOSE", "DEFENSIVE_ROLL"]:
                buyback = short_price * (1 + slip) * 100 * pos.leaps_contracts
                cash -= buyback
                if action == "DEFENSIVE_ROLL":
                    T_s2 = pos.short_call_dte / 365.0
                    def_strike  = find_strike_by_delta(S, T_s2, r, sigma, 0.15)
                    def_premium = bs_call_price(S, def_strike, T_s2, r, sigma)
                    if def_premium >= 0.15:
                        cash += def_premium * (1 - slip) * 100 * pos.leaps_contracts
                        pos.short_strike          = def_strike
                        pos.short_call_credit     = def_premium
                        pos.short_expiry_date     = date + pd.Timedelta(days=pos.short_call_dte)
                        pos.pmcc_status           = PmccStatus.DEFENSIVE
                else:
                    pos.pmcc_status = PmccStatus.NONE

        # ────── LEAPS ENTRY CHECK ──────
        if pos.leaps_status == LeapsStatus.NONE and positions_open < max_positions:
            ml_conf   = ml_confidence_stub(row, regime)
            threshold = ml_threshold(regime)
            is_gap    = gap_pct <= -0.005

            if regime in [Regime.BULL_STRONG, Regime.BULL_MODERATE, Regime.CHOPPY] \
               and ml_conf >= threshold and is_gap:

                # Determine LEAPS structure
                if regime == Regime.BULL_STRONG:
                    delta_tgt, dte_tgt = 0.85, 365
                elif regime == Regime.BULL_MODERATE:
                    delta_tgt, dte_tgt = 0.80, 365
                else:
                    delta_tgt, dte_tgt = 0.80, 540

                T_l = dte_tgt / 365.0
                strike_l   = find_strike_by_delta(S, T_l, r, sigma, delta_tgt)
                leaps_price = bs_call_price(S, strike_l, T_l, r, sigma)
                leaps_cost  = leaps_price * (1 + slip)   # buy at ask

                # Extrinsic cap check (≤25% of option price)
                extval = bs_extrinsic(S, strike_l, T_l, r, sigma)
                if extval / leaps_cost > 0.25:
                    pass   # skip — too much time premium for a "deep ITM" LEAPS
                else:
                    contracts = size_position(cash + leaps_mark, leaps_cost)
                    if contracts < 1:
                        pass
                    else:
                        # BCI initialization check (pre-sell short call at 0.25 delta)
                        T_s_test = 32 / 365.0
                        short_test_strike  = find_strike_by_delta(S, T_s_test, r, sigma, 0.25)
                        short_test_premium = bs_call_price(S, short_test_strike, T_s_test, r, sigma)
                        bci_ok = bci_initialization_check(
                            S, strike_l, leaps_cost, short_test_strike, short_test_premium,
                            T_l, T_s_test, r, sigma
                        )
                        if bci_ok:
                            total_cost = leaps_cost * 100 * contracts
                            cash -= total_cost
                            pos.leaps_status      = LeapsStatus.OPEN
                            pos.leaps_entry_price = leaps_cost
                            pos.leaps_entry_date  = date
                            pos.leaps_strike      = strike_l
                            pos.leaps_expiry_date = date + pd.Timedelta(days=dte_tgt)
                            pos.leaps_contracts   = contracts
                            pos.leaps_entry_qqq   = S
                            pos.leaps_delta       = delta_tgt
                            pos.leaps_dte         = dte_tgt
                            positions_open += 1

        # ────── PMCC ENTRY CHECK ──────
        if pos.leaps_status == LeapsStatus.OPEN and pos.pmcc_status == PmccStatus.NONE:
            qqq_vs_entry = (S - pos.leaps_entry_qqq) / pos.leaps_entry_qqq
            can_enter = (
                regime in [Regime.BULL_STRONG, Regime.BULL_MODERATE] and
                pos.leaps_age(date) >= 5 and
                pos.leaps_dte > 60 and
                qqq_vs_entry >= 0.02 and
                16 <= vix <= 35
            )
            if can_enter:
                dte_s   = 30 if vix > 20 else 35
                delta_s = 0.28 if regime == Regime.BULL_STRONG else 0.23
                T_s     = dte_s / 365.0
                short_strike  = find_strike_by_delta(S, T_s, r, sigma, delta_s)
                short_premium = bs_call_price(S, short_strike, T_s, r, sigma)
                if short_premium >= 0.50:
                    credit = short_premium * (1 - slip) * 100 * pos.leaps_contracts
                    cash  += credit
                    pos.short_strike          = short_strike
                    pos.short_call_credit     = short_premium
                    pos.short_call_entry_date = date
                    pos.short_expiry_date     = date + pd.Timedelta(days=dte_s)
                    pos.pmcc_status           = PmccStatus.ACTIVE
                    pmcc_income_today        += credit

        # ────── DAILY NAV ──────
        T_l2 = max(pos.leaps_dte, 0) / 365.0 if pos.leaps_status == LeapsStatus.OPEN else 0
        T_s2 = max(pos.short_call_dte, 0) / 365.0 if pos.pmcc_status != PmccStatus.NONE else 0
        lm = bs_call_price(S, pos.leaps_strike, T_l2, r, sigma) * 100 * pos.leaps_contracts \
             if pos.leaps_status == LeapsStatus.OPEN else 0
        sm = bs_call_price(S, pos.short_strike, T_s2, r, sigma) * 100 * pos.leaps_contracts \
             if pos.pmcc_status != PmccStatus.NONE else 0
        nav = cash + lm - sm

        results.append({
            "date":             date,
            "nav":              nav,
            "cash":             cash,
            "leaps_mark":       lm,
            "short_mark":       sm,
            "regime":           regime.value,
            "leaps_status":     pos.leaps_status.value,
            "pmcc_status":      pos.pmcc_status.value,
            "leaps_delta":      pos.leaps_delta,
            "short_delta":      pos.short_call_delta,
            "cost_basis":       pos.cost_basis(),
            "pmcc_credit_cum":  pos.pmcc_credit_cumulative,
            "pmcc_income_today":pmcc_income_today,
        })

    results_df = pd.DataFrame(results)
    return results_df


# ─────────────────────────────────────────
# PERFORMANCE METRICS
# ─────────────────────────────────────────

def compute_metrics(results: pd.DataFrame, initial_nav: float = 25_000.0) -> dict:
    results = results.set_index("date").sort_index()
    nav = results["nav"]
    returns = nav.pct_change().dropna()

    total_days = (nav.index[-1] - nav.index[0]).days
    years = total_days / 365.25
    cagr  = (nav.iloc[-1] / initial_nav) ** (1 / years) - 1

    sharpe  = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
    running_max = nav.cummax()
    drawdown    = (nav - running_max) / running_max
    max_dd      = drawdown.min()

    pmcc_income_total   = results["pmcc_income_today"].sum()
    pmcc_income_monthly = pmcc_income_total / (total_days / 30.44)

    return {
        "CAGR":                 f"{cagr:.2%}",
        "Sharpe":               f"{sharpe:.2f}",
        "Max Drawdown":         f"{max_dd:.2%}",
        "Final NAV":            f"${nav.iloc[-1]:,.0f}",
        "Total PMCC Income":    f"${pmcc_income_total:,.0f}",
        "Avg Monthly PMCC $":   f"${pmcc_income_monthly:,.0f}",
        "Total Return":         f"{(nav.iloc[-1] / initial_nav - 1):.2%}",
    }


# ─────────────────────────────────────────
# SAMPLE DATA PREP + REGIME PRE-COMPUTATION
# ─────────────────────────────────────────

def prepare_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds technical indicators and pre-smoothed regime column to raw OHLCV+VIX df.
    raw_df must have: date, qqq_open, qqq_close, vix, vix3m, hmm_p_bull
    """
    df = raw_df.copy().sort_values("date").reset_index(drop=True)
    df["sma50"]       = df["qqq_close"].rolling(50).mean()
    df["sma100"]      = df["qqq_close"].rolling(100).mean()
    df["sma200"]      = df["qqq_close"].rolling(200).mean()
    df["qqq_52w_low"] = df["qqq_close"].rolling(252).min()
    df["prev_close"]  = df["qqq_close"].shift(1)
    df["gap_pct"]     = (df["qqq_open"] - df["prev_close"]) / df["prev_close"]

    # RSI 14
    delta = df["qqq_close"].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # VIX percentile rank (252-day rolling)
    df["vix_pctile"] = df["vix"].rolling(252).rank(pct=True)

    # Raw regime classification (vectorized)
    df["regime_raw"] = df.apply(
        lambda r: classify_regime(
            r["hmm_p_bull"], r["vix"],
            r["qqq_close"],
            r.get("sma100", r["qqq_close"]),
            r.get("sma200", r["qqq_close"])
        ).value if not pd.isna(r.get("sma100")) else Regime.CHOPPY.value,
        axis=1
    )

    # Smooth regime (5-day rolling mode)
    df["regime_smooth"] = smooth_regime(df["regime_raw"])
    df = df.dropna(subset=["sma200"]).reset_index(drop=True)
    return df


# ─────────────────────────────────────────
# ENTRY POINT (with synthetic data demo)
# ─────────────────────────────────────────

if __name__ == "__main__":
    # ── Optional: load real data with yfinance ──
    # import yfinance as yf
    # qqq = yf.download("QQQ", start="2019-01-01", end="2026-04-01")[["Open","Close"]]
    # vix = yf.download("^VIX", start="2019-01-01", end="2026-04-01")[["Close"]]
    # vix3m = yf.download("^VIX3M", start="2019-01-01", end="2026-04-01")[["Close"]]
    # ... merge and build df with hmm_p_bull from your HMM module

    # ── Synthetic demo data ──
    np.random.seed(42)
    dates = pd.bdate_range("2019-01-02", "2026-04-01")
    n = len(dates)
    price = 170.0
    prices = [price]
    for _ in range(n - 1):
        price *= np.exp(np.random.normal(0.0003, 0.012))
        prices.append(price)
    prices = np.array(prices)

    vix_sim = np.clip(np.random.normal(18, 6, n), 10, 80)
    hmm_sim = np.clip(np.random.normal(0.65, 0.20, n), 0, 1)

    raw = pd.DataFrame({
        "date":       dates,
        "qqq_open":   prices * (1 + np.random.normal(0, 0.003, n)),
        "qqq_close":  prices,
        "vix":        vix_sim,
        "vix3m":      vix_sim * 1.05,
        "hmm_p_bull": hmm_sim,
    })

    df = prepare_data(raw)
    results = run_backtest(df, virtual_nav=25_000.0)
    metrics = compute_metrics(results)

    print("\\n=== QQQ PMCC Backtest Results ===")
    for k, v in metrics.items():
        print(f"  {k:<25}: {v}")

    results.to_csv("qqq_pmcc_backtest_results.csv", index=False)
    print("\\nResults saved to qqq_pmcc_backtest_results.csv")
'''

with open('/root/qqq_pmcc_backtest_v2.py', 'w') as f:
    f.write(python_code)
print("Python backtest file written.")
