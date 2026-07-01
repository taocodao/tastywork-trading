"""
Earnings Iron Condor Overlay — Phase 3b
=========================================
A separate, defined-risk sub-strategy that sells tight iron condors
on stocks 1 day BEFORE their earnings announcement, then closes the
next trading day to capture IV crush.

Design rules (from ORATS 5,217-event backtest + academic literature):
  - Only trade when IV/RV ratio > 1.25 (meaningful VRP over realized vol)
  - IV Rank >= 80th percentile (options expensive pre-earnings)
  - Max 1% of NAV per trade (strict tail-risk limit)
  - Max 3 concurrent earnings IC positions
  - Entry: 1 day before earnings close
  - Exit: next trading day open/close (IV crush realized)
  - Structure: OTM call spread + OTM put spread (defined-risk)
  - Wing width: ~5-delta wings on each side

IMPORTANT: This runs as a SEPARATE capital pool from the HILO-IV core.
Max allocation: 5% of NAV to earnings plays at any time.
P&L is tracked independently so HILO-IV edge is not contaminated.

References:
  - ORATS: "Long Straddle Backtest: 5,217 earnings events" (apexvol.com)
  - TastyTrade: "IV Crush" concept guide
  - Perplexity research: earnings IV crush overlay, Phase 3 plan
"""
import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import OTMNakedConfig
from .strike_selector import bs_put_price, bs_call_price

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Position tracking for earnings IC
# ---------------------------------------------------------------------------
@dataclass
class EarningsICPosition:
    symbol:           str
    entry_date:       pd.Timestamp
    exit_date:        Optional[pd.Timestamp]
    expiry_date:      pd.Timestamp
    # Call spread (short lower call + long higher call)
    short_call_strike: float
    long_call_strike:  float
    # Put spread (short higher put + long lower put)
    short_put_strike:  float
    long_put_strike:   float
    # Premium
    net_credit:        float          # Total net credit per share (all 4 legs)
    contracts:         int
    max_profit:        float          # = net_credit * contracts * 100
    max_loss:          float          # = (wing_width - net_credit) * contracts * 100
    # Outcomes
    exit_debit:        float = 0.0    # Cost to close (IV crush benefit = net_credit - exit_debit)
    pnl:               float = 0.0
    trade_won:         bool  = False
    exit_reason:       str   = ""
    entry_spot:        float = 0.0
    iv_rank:           float = 0.0
    iv_rv_ratio:       float = 0.0


# ---------------------------------------------------------------------------
# Earnings IC Overlay Engine
# ---------------------------------------------------------------------------
class EarningsICOverlay:
    """
    Earnings iron condor overlay for Phase 3.
    Runs independently from the HILO-IV core strategy.

    Usage (inside backtest loop):
        overlay = EarningsICOverlay(config)
        # Each day:
        new_ic = overlay.scan_entries(today, features, nav)
        for ic in new_ic:
            cash += ic.net_credit * ic.contracts * 100
        closed_ic = overlay.check_exits(today, features, cash)
        for ic in closed_ic:
            cash -= ic.exit_debit * ic.contracts * 100
    """

    def __init__(self, config: Optional[OTMNakedConfig] = None):
        self.config       = config or OTMNakedConfig()
        self.open_ics:    List[EarningsICPosition] = []
        self.closed_ics:  List[EarningsICPosition] = []

    @property
    def total_allocation(self) -> float:
        """Current total notional allocated to open earnings ICs."""
        return sum(ic.max_loss for ic in self.open_ics)

    def scan_entries(
        self,
        today:    pd.Timestamp,
        features: Dict[str, pd.DataFrame],
        nav:      float,
    ) -> List[EarningsICPosition]:
        """
        Scan for earnings IC entry opportunities today.
        Enters 1 day before earnings if filters pass.

        Returns list of new EarningsICPosition objects (cash not yet updated).
        """
        cfg   = self.config
        new_positions: List[EarningsICPosition] = []

        # Cap: max 5% of NAV in earnings plays total
        max_earnings_alloc = nav * 0.05
        current_alloc      = self.total_allocation

        # Max 3 concurrent earnings IC positions
        if len(self.open_ics) >= cfg.earnings_ic_max_positions:
            return new_positions

        existing_symbols = {ic.symbol for ic in self.open_ics}

        for symbol, feat_df in features.items():
            if symbol in existing_symbols:
                continue
            if today not in feat_df.index:
                continue

            row = feat_df.loc[today]

            # ── Earnings proximity check ─────────────────────────────────────
            # Must be exactly 1 day before earnings (or earnings_days_away == 1)
            earn_days = int(row.get("earnings_days_away", 999))
            if earn_days != 1:
                continue

            # ── IV filters ───────────────────────────────────────────────────
            iv_rank    = float(row.get("iv_rank", 0.0))
            iv_hv_ratio = float(row.get("iv_hv_ratio", 1.0))
            hv_20      = float(row.get("hv_20", 0.20))

            # Require elevated IV Rank (options expensive pre-earnings)
            if iv_rank < cfg.earnings_ic_min_iv_rank:
                logger.debug(f"  EARNINGS IC {symbol}: IV rank {iv_rank:.2f} < {cfg.earnings_ic_min_iv_rank}")
                continue

            # Require meaningful VRP (IV meaningfully exceeds realized vol)
            if iv_hv_ratio < cfg.earnings_ic_min_iv_rv_ratio:
                logger.debug(f"  EARNINGS IC {symbol}: IV/RV {iv_hv_ratio:.2f} < {cfg.earnings_ic_min_iv_rv_ratio}")
                continue

            # ── Build IC structure ───────────────────────────────────────────
            spot = float(row.get("close", 0.0))
            if spot <= 0:
                continue

            # Use 1-week expiry (5 trading days) to capture earnings IV crush
            # In backtest: synthetic expiry, 5 DTE
            dte         = 5
            T_years     = dte / 365.0
            rf          = 0.045
            sigma       = max(hv_20 * 1.5, 0.30)  # Pre-earnings IV typically 1.5x HV

            # Wing width: ~5% OTM on each side (tight, captures most premium)
            wing_pct    = 0.05
            short_put   = round(spot * (1 - wing_pct), 0)
            long_put    = round(spot * (1 - wing_pct * 2), 0)
            short_call  = round(spot * (1 + wing_pct), 0)
            long_call   = round(spot * (1 + wing_pct * 2), 0)
            wing_width  = short_call - spot   # Approx wing width (call side)

            # Synthetic BS pricing for IC legs (mid-price)
            try:
                short_put_pr  = bs_put_price(spot, short_put,  T_years, rf, sigma)
                long_put_pr   = bs_put_price(spot, long_put,   T_years, rf, sigma)
                short_call_pr = bs_call_price(spot, short_call, T_years, rf, sigma)
                long_call_pr  = bs_call_price(spot, long_call,  T_years, rf, sigma)
            except Exception as e:
                logger.debug(f"  EARNINGS IC {symbol}: pricing error {e}")
                continue

            net_credit = (short_put_pr - long_put_pr) + (short_call_pr - long_call_pr)
            if net_credit < cfg.earnings_ic_min_credit:
                logger.debug(f"  EARNINGS IC {symbol}: credit ${net_credit:.2f} < min ${cfg.earnings_ic_min_credit}")
                continue

            # ── Sizing: max 1% of NAV per trade ─────────────────────────────
            max_per_trade   = nav * cfg.earnings_ic_max_risk_pct
            max_loss_per_c  = (wing_width - net_credit) * 100   # per contract
            contracts       = max(1, int(max_per_trade / max(max_loss_per_c, 1)))
            contracts       = min(contracts, 5)  # hard cap at 5 contracts

            trade_max_loss  = max_loss_per_c * contracts
            trade_max_profit = net_credit * contracts * 100

            # Total earnings alloc check
            if current_alloc + trade_max_loss > max_earnings_alloc:
                logger.debug(f"  EARNINGS IC {symbol}: allocation full")
                continue

            # ── Build position ───────────────────────────────────────────────
            expiry = today + pd.Timedelta(days=dte)
            ic = EarningsICPosition(
                symbol=symbol,
                entry_date=today,
                exit_date=None,
                expiry_date=expiry,
                short_call_strike=short_call,
                long_call_strike=long_call,
                short_put_strike=short_put,
                long_put_strike=long_put,
                net_credit=net_credit,
                contracts=contracts,
                max_profit=trade_max_profit,
                max_loss=trade_max_loss,
                entry_spot=spot,
                iv_rank=iv_rank,
                iv_rv_ratio=iv_hv_ratio,
            )
            new_positions.append(ic)
            current_alloc += trade_max_loss
            logger.info(f"  EARNINGS IC ENTER {symbol} | spot={spot:.1f} | "
                        f"IC={short_put:.0f}/{short_call:.0f} | credit=${net_credit:.2f} | "
                        f"x{contracts} | IV rank={iv_rank:.2f}")

        self.open_ics.extend(new_positions)
        return new_positions

    def check_exits(
        self,
        today:    pd.Timestamp,
        features: Dict[str, pd.DataFrame],
        vix:      float,
    ) -> List[EarningsICPosition]:
        """
        Check for exits. Primary rule: close the day AFTER earnings (1-day hold).
        Also force-close at expiry.

        Returns list of positions that were closed (cash update done by caller).
        """
        exits = []
        for ic in self.open_ics:
            # Primary exit: 1 trading day after entry (IV crush captured)
            days_held = (today - ic.entry_date).days
            dte_left  = (ic.expiry_date - today).days
            should_exit = (days_held >= 1) or (dte_left <= 0)

            if not should_exit:
                continue

            # Price the IC at exit (reduced IV = IV crush benefit)
            spot    = self._get_spot(ic.symbol, today, features)
            sigma_exit = self._get_exit_sigma(ic.symbol, today, features, vix, ic.iv_rv_ratio)
            T_exit     = max(dte_left / 365.0, 0.001)

            try:
                exit_short_put  = bs_put_price(spot, ic.short_put_strike,  T_exit, 0.045, sigma_exit)
                exit_long_put   = bs_put_price(spot, ic.long_put_strike,   T_exit, 0.045, sigma_exit)
                exit_short_call = bs_call_price(spot, ic.short_call_strike, T_exit, 0.045, sigma_exit)
                exit_long_call  = bs_call_price(spot, ic.long_call_strike,  T_exit, 0.045, sigma_exit)
                exit_debit = (exit_short_put - exit_long_put) + (exit_short_call - exit_long_call)
                # Exit debit is what we pay to close the short legs (net of long legs)
                exit_debit = max(0.0, exit_debit)   # Cannot be negative (can't receive debit to close)
            except Exception:
                # Fallback: assume 30% IV crush reduces premium to 70%
                exit_debit = ic.net_credit * 0.70

            pnl = (ic.net_credit - exit_debit) * ic.contracts * 100
            pnl -= 0.65 * ic.contracts * 4   # 4 legs * $0.65 commission each way

            ic.exit_date   = today
            ic.exit_debit  = exit_debit
            ic.pnl         = pnl
            ic.trade_won   = pnl > 0
            ic.exit_reason = f"iv_crush_day{days_held}" if days_held >= 1 else "expiry"
            exits.append(ic)

            logger.info(f"  EARNINGS IC EXIT {ic.symbol} | credit={ic.net_credit:.2f} | "
                        f"debit={exit_debit:.2f} | pnl=${pnl:+.0f} [{ic.exit_reason}]")

        # Move exits to closed
        self.open_ics   = [ic for ic in self.open_ics if ic not in exits]
        self.closed_ics.extend(exits)
        return exits

    def get_metrics(self) -> dict:
        """Compute earnings IC overlay performance metrics."""
        if not self.closed_ics:
            return {"n_trades": 0, "win_rate_pct": 0, "total_pnl": 0, "avg_pnl": 0}
        pnls     = [ic.pnl for ic in self.closed_ics]
        won      = [ic.trade_won for ic in self.closed_ics]
        return {
            "n_trades":    len(self.closed_ics),
            "win_rate_pct": sum(won) / len(won) * 100,
            "total_pnl":   sum(pnls),
            "avg_pnl":     sum(pnls) / len(pnls),
            "profit_factor": (
                sum(p for p in pnls if p > 0) /
                max(abs(sum(p for p in pnls if p < 0)), 1)
            ),
        }

    def to_dataframe(self) -> pd.DataFrame:
        """Export closed IC trades to DataFrame."""
        records = []
        for ic in self.closed_ics:
            records.append({
                "symbol":           ic.symbol,
                "entry_date":       ic.entry_date,
                "exit_date":        ic.exit_date,
                "short_put":        ic.short_put_strike,
                "short_call":       ic.short_call_strike,
                "net_credit":       ic.net_credit,
                "exit_debit":       ic.exit_debit,
                "contracts":        ic.contracts,
                "max_profit":       ic.max_profit,
                "max_loss":         ic.max_loss,
                "pnl":              ic.pnl,
                "trade_won":        ic.trade_won,
                "exit_reason":      ic.exit_reason,
                "iv_rank":          ic.iv_rank,
                "iv_rv_ratio":      ic.iv_rv_ratio,
                "entry_spot":       ic.entry_spot,
            })
        return pd.DataFrame(records)

    # ── Private helpers ───────────────────────────────────────────────────────
    def _get_spot(self, symbol: str, today: pd.Timestamp,
                  features: Dict[str, pd.DataFrame]) -> float:
        feat_df = features.get(symbol)
        if feat_df is not None and today in feat_df.index:
            return float(feat_df.loc[today].get("close", 100.0))
        return 100.0

    def _get_exit_sigma(self, symbol: str, today: pd.Timestamp,
                        features: Dict[str, pd.DataFrame],
                        vix: float, entry_iv_rv_ratio: float) -> float:
        """Estimate post-earnings IV. Typically drops 40-60% from pre-earnings level."""
        feat_df = features.get(symbol)
        if feat_df is not None and today in feat_df.index:
            hv_20 = float(feat_df.loc[today].get("hv_20", 0.20))
            # Post-earnings: IV reverts toward historical vol (crush)
            # Conservative estimate: IV drops to 1.1x HV (from ~1.5x at entry)
            return max(hv_20 * 1.1, 0.15)
        return max(vix / 100 * 1.5, 0.20)
