"""
Fast Vectorized Simulator for Optuna Optimization
===================================================
A stripped-down, NumPy-native backtesting engine designed for high
throughput: ~1,000+ simulations/minute on EC2, compared to ~10/minute
for the pandas-based backtest_engine.py.

Key design:
- Operates on pre-built feature arrays (no per-step yfinance calls)
- No pandas overhead in the inner loop — pure NumPy array operations
- Parameterized by a single OTMParams dataclass (the Optuna search space)
- Returns only scalar performance metrics (Sortino, max drawdown, etc.)
  to minimize memory overhead when running thousands of trials

Entry Filter Architecture (Perplexity-validated, v2):
- VIX Term Structure Slope replaces flat VIX threshold (orthogonal to pullback)
- IV/HV Ratio replaces RSI (direct measure of premium edge)
- IV Percentile replaces IV Rank (robust to outlier spikes)
- Pullback depth retained (relaxed bounds)

This simulator is NOT a replacement for backtest_engine.py (which has
full logging, trade records, and position detail). It is specifically
for Bayesian optimization search.
"""

import math
import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..strike_selector import bs_put_price, bs_put_delta, find_put_strike
from ..config import OTM_NAKED_UNIVERSE

logger = logging.getLogger(__name__)

ANNUAL_FACTOR = math.sqrt(252)


# ---------------------------------------------------------------------------
# Optuna Search Space — all tunable parameters (v2: regime-aware filters)
# ---------------------------------------------------------------------------
@dataclass
class OTMParams:
    """
    The complete Bayesian optimization search space (v2).
    One instance = one trial in Optuna.

    Key changes from v1:
    - Removed: rsi_oversold, vix_crisis_threshold, min_iv_rank
    - Added:   vix_slope_threshold, iv_hv_min, iv_pct_threshold
    """
    # ── DTE ──────────────────────────────────────────────────────────────────
    dte: int = 35                       # Target days-to-expiry (21–60)

    # ── Strike selection ─────────────────────────────────────────────────────
    put_delta: float = 0.12             # Target delta for put selling (0.08–0.20)

    # ── Entry filters ─────────────────────────────────────────────────────────
    pct_from_52w_high: float = 0.12     # Required drawdown from 52W high (0.05–0.25)
    iv_pct_threshold: float = 0.40      # IV Percentile threshold (0.25–0.70)
    iv_hv_min: float = 1.10             # Min IV/HV ratio — premium quality gate (1.0–1.5)
    vix_slope_threshold: float = -0.03  # Min VIX term structure slope (VIX3M-VIX)/VIX
                                        # Positive = contango (favorable), negative = backwardation

    # ── Exit rules ─────────────────────────────────────────────────────────────
    profit_take_pct: float = 0.50       # Close at X% of max credit (0.40–0.80)
    stop_loss_mult: float = 2.5         # Close at X× credit received (1.5–4.0)
    time_exit_dte: int = 7              # Force close at X DTE remaining (3–14)

    # ── Risk management ────────────────────────────────────────────────────────
    max_risk_pct: float = 0.012         # Max risk per trade as % of NAV (0.005–0.03)
    max_positions: int = 4              # Max concurrent positions (2–8)

    # ── Portfolio ──────────────────────────────────────────────────────────────
    initial_capital: float = 50_000.0


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------
def compute_metrics(nav_series: np.ndarray, trades: list,
                    initial_capital: float) -> Dict[str, float]:
    """
    Compute risk-adjusted performance metrics from a NAV time series.

    Args:
        nav_series:      Daily NAV array (length = simulation days)
        trades:          List of (entry_credit, exit_cost) tuples
        initial_capital: Starting capital

    Returns:
        Dict with Sortino, Sharpe, max_drawdown, total_return, CAGR,
        win_rate, profit_factor, n_trades
    """
    if len(nav_series) < 2:
        return _empty_metrics()

    # Daily returns
    returns = np.diff(nav_series) / nav_series[:-1]
    returns = returns[np.isfinite(returns)]

    if len(returns) < 10:
        return _empty_metrics()

    # Sortino ratio (downside deviation only)
    mean_ret = np.mean(returns)
    neg_ret  = returns[returns < 0]
    downside_std = np.std(neg_ret) if len(neg_ret) > 1 else 1e-8
    sortino = (mean_ret / downside_std) * ANNUAL_FACTOR if downside_std > 0 else 0.0

    # Sharpe ratio
    std_ret = np.std(returns)
    sharpe  = (mean_ret / std_ret) * ANNUAL_FACTOR if std_ret > 1e-10 else 0.0

    # Max drawdown
    peak = np.maximum.accumulate(nav_series)
    drawdowns = (nav_series - peak) / np.where(peak > 0, peak, 1)
    max_dd = float(np.min(drawdowns))

    # Return metrics
    total_return = float((nav_series[-1] / nav_series[0]) - 1)
    n_years = len(nav_series) / 252.0
    cagr = float((nav_series[-1] / nav_series[0]) ** (1.0 / max(n_years, 0.1)) - 1)

    # Trade-level metrics
    n_trades  = len(trades)
    if n_trades > 0:
        pnls     = [t["pnl"] for t in trades]
        winners  = [p for p in pnls if p > 0]
        losers   = [p for p in pnls if p <= 0]
        win_rate = len(winners) / n_trades
        gross_win  = sum(winners) if winners else 0
        gross_loss = abs(sum(losers)) if losers else 1e-8
        profit_factor = gross_win / gross_loss
    else:
        win_rate = profit_factor = 0.0

    return {
        "sortino":       sortino,
        "sharpe":        sharpe,
        "max_drawdown":  max_dd,
        "total_return":  total_return,
        "cagr":          cagr,
        "win_rate":      win_rate,
        "profit_factor": profit_factor,
        "n_trades":      n_trades,
    }


def _empty_metrics() -> Dict[str, float]:
    return {
        "sortino": -99.0, "sharpe": -99.0, "max_drawdown": -1.0,
        "total_return": -1.0, "cagr": -1.0, "win_rate": 0.0,
        "profit_factor": 0.0, "n_trades": 0,
    }


# ---------------------------------------------------------------------------
# Fast simulation engine
# ---------------------------------------------------------------------------
class FastOTMSimulator:
    """
    High-throughput OTM naked put simulator (v2 — regime-aware filters).

    Designed to be called thousands of times by Optuna with different
    OTMParams. Each call runs a complete backtest over the provided
    feature dictionary and returns scalar performance metrics.

    Entry filter stack (v2):
      Layer 1 (Regime): VIX term structure slope — (VIX3M - VIX) / VIX
                        Positive = contango (harvest vol premium)
                        Negative = backwardation (tail-risk, avoid new entries)
      Layer 2 (Signal): IV Percentile >= threshold (options expensive vs history)
      Layer 3 (Signal): IV/HV ratio >= threshold (IV overpriced vs realized vol)
      Layer 4 (Signal): Pullback depth from 52W high (stock oversold)
    """

    def __init__(self, features_dict: Dict[str, pd.DataFrame],
                 warmup_days: int = 252):
        """
        Args:
            features_dict: Pre-built {symbol: feature_df} from build_all_features()
                           (or from StationaryBlockBootstrap.generate_single())
            warmup_days:   Days to skip before entering any trades (feature warmup)
        """
        self.warmup = warmup_days
        # Pre-cache all feature arrays in memory as NumPy arrays for speed
        self._cache: Dict[str, Dict[str, np.ndarray]] = {}
        self._dates: Optional[np.ndarray] = None
        self._build_cache(features_dict)

    def _build_cache(self, features_dict: Dict[str, pd.DataFrame]):
        """Convert feature DataFrames to NumPy arrays for fast access."""
        all_indices = []
        for symbol, df in features_dict.items():
            if df.empty:
                continue
            cols = {
                "close":             df.get("close",              df.get("Close",    np.nan)),
                "hv_20":             df.get("hv_20",              pd.Series(0.2, index=df.index)),
                "vix":               df.get("vix",                pd.Series(18, index=df.index)),
                "pct_from_52w_high": df.get("pct_from_52w_high",  pd.Series(0, index=df.index)),
                "rf":                df.get("rf",                  pd.Series(0.045, index=df.index)),
                # v2 feature filters (already computed by feature_engineering.py)
                "vix_term_slope":    df.get("vix_term_slope",      pd.Series(0.05, index=df.index)),
                "iv_hv_ratio":       df.get("iv_hv_ratio",         pd.Series(1.1,  index=df.index)),
                "iv_rank":           df.get("iv_rank",             pd.Series(0.4,  index=df.index)),
                # iv_rank is used as IV Percentile proxy (same 0–1 scale)
            }
            idx = df.index
            all_indices.append(idx)
            self._cache[symbol] = {k: v.reindex(idx).ffill().bfill().values
                                   for k, v in cols.items()}
            self._cache[symbol]["__index__"] = np.array(idx, dtype="datetime64[D]")

        # Build common date grid (intersection of all symbols)
        if all_indices:
            common = all_indices[0]
            for idx in all_indices[1:]:
                common = common.intersection(idx)
            self._dates = np.array(common.sort_values(), dtype="datetime64[D]")
            # Build per-symbol index map: common_position → symbol_position
            for symbol in list(self._cache.keys()):
                sym_idx = pd.DatetimeIndex(self._cache[symbol]["__index__"])
                common_idx = pd.DatetimeIndex(common)
                mask = common_idx.isin(sym_idx)
                pos_map = np.searchsorted(sym_idx, common_idx[mask])
                self._cache[symbol]["__pos_map__"] = pos_map
                self._cache[symbol]["__common_mask__"] = mask

    def simulate(self, params: OTMParams) -> Dict[str, float]:
        """
        Run a single backtest simulation with the given parameter set.

        Args:
            params: OTMParams instance (one Optuna trial)

        Returns:
            Dict of performance metrics (see compute_metrics)
        """
        if self._dates is None or len(self._dates) < self.warmup + 30:
            return _empty_metrics()

        n_days       = len(self._dates)
        cash         = params.initial_capital
        nav_series   = np.zeros(n_days)
        open_pos     = []   # List of dicts: {symbol, strike, entry_px, dte_entry, contracts}
        closed_trades = []

        for i, today in enumerate(self._dates):
            # Skip warmup period
            if i < self.warmup:
                nav_series[i] = cash
                continue

            # ── 1. Check exits ────────────────────────────────────────────────
            still_open = []
            for pos in open_pos:
                days_held = i - pos["entry_day"]
                dte_remaining = pos["dte_entry"] - days_held
                sym = pos["symbol"]

                # Get current price for this symbol/day
                sym_i = self._get_sym_idx(sym, i)
                if sym_i is None:
                    still_open.append(pos)
                    continue

                spot   = float(self._cache[sym]["close"][sym_i])
                hv_20  = float(self._cache[sym]["hv_20"][sym_i])
                vix_   = float(self._cache[sym]["vix"][sym_i])
                rf_    = float(self._cache[sym]["rf"][sym_i])
                sigma  = self._estimate_iv(hv_20, vix_)
                T      = max(dte_remaining, 0) / 365.0
                cur_px = bs_put_price(spot, pos["strike"], T, rf_, sigma)

                exit_reason = None
                # Profit take
                if cur_px <= pos["entry_px"] * (1 - params.profit_take_pct):
                    exit_reason = "profit_take"
                # Stop loss
                elif cur_px >= pos["entry_px"] * params.stop_loss_mult:
                    exit_reason = "stop_loss"
                # Time exit
                elif dte_remaining <= params.time_exit_dte:
                    exit_reason = "time_exit"
                # Expired worthless
                elif dte_remaining <= 0:
                    cur_px = max(spot - pos["strike"], 0.0)
                    exit_reason = "expiry"

                if exit_reason:
                    cost = cur_px * pos["contracts"] * 100
                    pnl  = (pos["entry_px"] * pos["contracts"] * 100) - cost
                    cash += pnl
                    closed_trades.append({
                        "pnl":    pnl,
                        "reason": exit_reason,
                        "symbol": sym,
                    })
                else:
                    still_open.append(pos)

            open_pos = still_open

            # ── 2. MTM NAV ────────────────────────────────────────────────────
            liability = 0.0
            for pos in open_pos:
                sym_i = self._get_sym_idx(pos["symbol"], i)
                if sym_i is None:
                    continue
                spot   = float(self._cache[pos["symbol"]]["close"][sym_i])
                hv_20  = float(self._cache[pos["symbol"]]["hv_20"][sym_i])
                vix_   = float(self._cache[pos["symbol"]]["vix"][sym_i])
                rf_    = float(self._cache[pos["symbol"]]["rf"][sym_i])
                days_held     = i - pos["entry_day"]
                dte_remaining = max(pos["dte_entry"] - days_held, 0)
                T      = dte_remaining / 365.0
                sigma  = self._estimate_iv(hv_20, vix_)
                liability += bs_put_price(spot, pos["strike"], T, rf_, sigma) * pos["contracts"] * 100

            nav_series[i] = cash - liability

            # ── 3. Entry scan (regime-aware v2 filter stack) ──────────────────
            if len(open_pos) >= params.max_positions:
                continue

            # Layer 1 (Regime): VIX Term Structure Slope
            # Positive slope = contango = favorable for short-vol premium harvesting
            # Negative slope = backwardation = panic/crisis, skip new entries
            vix_slope = self._get_vix_slope(i)
            if vix_slope < params.vix_slope_threshold:
                continue   # Market in backwardation — avoid new naked puts

            candidates = []
            existing_syms = {p["symbol"] for p in open_pos}

            for sym, cache in self._cache.items():
                if sym.startswith("__") or sym in existing_syms:
                    continue
                sym_i = self._get_sym_idx(sym, i)
                if sym_i is None:
                    continue

                iv_pct    = float(cache["iv_rank"][sym_i])       # 0–1 IV percentile proxy
                iv_hv     = float(cache["iv_hv_ratio"][sym_i])   # IV / HV ratio
                pct_52w   = float(cache["pct_from_52w_high"][sym_i])  # ≤ 0
                spot      = float(cache["close"][sym_i])
                hv_20     = float(cache["hv_20"][sym_i])
                rf_       = float(cache["rf"][sym_i])
                vix_      = float(cache["vix"][sym_i])

                # Layer 2 (Signal): IV Percentile — options must be historically expensive
                if iv_pct < params.iv_pct_threshold:
                    continue

                # Layer 3 (Signal): IV/HV ratio — premium must exceed realized vol
                if iv_hv < params.iv_hv_min:
                    continue

                # Layer 4 (Signal): Required pullback from 52-week high
                if pct_52w > -params.pct_from_52w_high:
                    continue   # Not enough pullback — stock not oversold enough

                # Strike selection via Black-Scholes binary search
                sigma    = self._estimate_iv(hv_20, vix_)
                T_years  = params.dte / 365.0
                try:
                    strike  = find_put_strike(spot, T_years, rf_, sigma, params.put_delta)
                    premium = bs_put_price(spot, strike, T_years, rf_, sigma)
                except Exception:
                    continue

                if premium < 0.20:   # Minimum credit filter ($0.20/share = $20/contract)
                    continue

                candidates.append({
                    "symbol":    sym,
                    "spot":      spot,
                    "strike":    strike,
                    "entry_px":  premium,
                    "sigma":     sigma,
                    "rf":        rf_,
                    "pct_52w":   pct_52w,   # Sort key
                })

            # Sort by most extreme pullback (most negative = deepest dip = best entry)
            candidates.sort(key=lambda x: x["pct_52w"])

            nav_now = nav_series[i] if nav_series[i] > 0 else params.initial_capital
            for cand in candidates:
                if len(open_pos) >= params.max_positions:
                    break
                # Size position by risk budget: max_risk_pct% of NAV
                risk_budget = nav_now * params.max_risk_pct
                contracts   = max(1, int(risk_budget / (cand["strike"] * 100)))
                credit       = cand["entry_px"] * contracts * 100
                cash        += credit  # Credit received upfront

                open_pos.append({
                    "symbol":    cand["symbol"],
                    "strike":    cand["strike"],
                    "entry_px":  cand["entry_px"],
                    "entry_day": i,
                    "dte_entry": params.dte,
                    "contracts": contracts,
                })

        return compute_metrics(nav_series[self.warmup:], closed_trades,
                               params.initial_capital)

    def _get_sym_idx(self, sym: str, common_i: int) -> Optional[int]:
        """Map common date index → symbol-specific array index."""
        cache = self._cache.get(sym)
        if cache is None:
            return None
        mask = cache["__common_mask__"]
        if common_i >= len(mask) or not mask[common_i]:
            return None
        # Count True values up to and including common_i
        return int(np.sum(mask[:common_i + 1]) - 1)

    def _get_vix(self, common_i: int) -> float:
        """Get VIX level for a common date index from the first available symbol."""
        for sym, cache in self._cache.items():
            if sym.startswith("__"):
                continue
            sym_i = self._get_sym_idx(sym, common_i)
            if sym_i is not None:
                return float(cache["vix"][sym_i])
        return 18.0

    def _get_vix_slope(self, common_i: int) -> float:
        """
        Get VIX term structure slope: (VIX3M - VIX) / VIX.
        Positive = contango (normal, premium-selling favorable).
        Negative = backwardation (crisis/panic, avoid new short-vol positions).
        Default 0.05 = slight contango (historically average ~84% of the time).
        """
        for sym, cache in self._cache.items():
            if sym.startswith("__"):
                continue
            sym_i = self._get_sym_idx(sym, common_i)
            if sym_i is not None and "vix_term_slope" in cache:
                return float(cache["vix_term_slope"][sym_i])
        return 0.05   # Default: slight contango

    @staticmethod
    def _estimate_iv(hv_20: float, vix: float) -> float:
        """Estimate single-stock IV using HV20 scaled by VIX/mean."""
        vix_scale = vix / 18.0
        iv_est    = hv_20 * vix_scale
        return float(np.clip(iv_est, 0.05, 2.0))
