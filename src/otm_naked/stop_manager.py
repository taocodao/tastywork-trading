"""
stop_manager.py — Spread-Aware GTC Stop-Loss & Trailing Logic
==============================================================
Replaces the simple "2x credit" static stop with:

  1. IV-adjusted stop multiplier   : scales stop width by the stock's own IV rank
                                     (high IV rank → wider stop, less noise-triggered)
  2. Spread-aware effective stop   : compares bid price (not mid) to stop level
  3. Trailing high-water mark      : locks in profits — stop only moves favorably
  4. Regime-conditional base mult  : LOW_VOL=1.8x, NORMAL=2.0x, HIGH_VOL=2.5x
  5. Check frequency optimization  : skips evaluation on calm days to save compute
                                     → checks every 5 days normally
                                     → checks daily when DTE ≤ 14 or move > 20%

Usage inside backtest_engine._check_exits():
    stop_mgr = SpreadAwareStopManager(cfg)
    should_check = stop_mgr.should_check(pos, today, last_check, prev_premium, current_mid)
    if should_check:
        triggered, exit_px, reason = stop_mgr.check(...)
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spread simulator  (production: replace with real L2 bid/ask from TT API)
# ---------------------------------------------------------------------------
def _simulated_spread(mid_price: float, regime: str) -> float:
    """
    Simulate bid/ask half-spread as % of mid price.

    Empirical estimates for TastyTrade liquid equities options:
      LOW_VOL  → ±4%  of mid
      NORMAL   → ±6%  of mid
      HIGH_VOL → ±10% of mid
      CRISIS   → ±15% of mid
    """
    spreads = {"LOW_VOL": 0.04, "NORMAL": 0.06, "HIGH_VOL": 0.10, "CRISIS": 0.15}
    half_pct = spreads.get(regime, 0.07)
    return mid_price * half_pct


def bid_price(mid: float, regime: str) -> float:
    """Simulated bid = mid − half_spread."""
    return max(mid - _simulated_spread(mid, regime), 0.01)


def ask_price(mid: float, regime: str) -> float:
    """Simulated ask = mid + half_spread."""
    return mid + _simulated_spread(mid, regime)


# ---------------------------------------------------------------------------
# Per-position stop state
# ---------------------------------------------------------------------------
@dataclass
class StopState:
    """Mutable stop-loss state that updates daily as the position is monitored."""
    initial_stop_px:   float       # Stop price at entry
    current_stop_px:   float       # Current stop level (ratchets tighter)
    best_premium_seen: float       # Lowest mid seen post-entry (decay = profit)
    trailing_activated: bool = False
    stop_tightened_count: int = 0
    stop_mult_used: float = 2.0
    last_check_day_idx: int = 0    # Day index of last stop check (for frequency gating)
    last_known_premium: float = 0.0  # Last mid price we recorded


# ---------------------------------------------------------------------------
# Main stop manager
# ---------------------------------------------------------------------------
@dataclass
class SpreadAwareStopManager:
    """
    IV-adjusted, spread-aware GTC stop-loss with trailing logic.

    Parameters
    ----------
    base_stop_mult      : float — NORMAL regime base multiplier (2.0)
    high_vol_mult       : float — HIGH_VOL regime multiplier (2.5)
    low_vol_mult        : float — LOW_VOL regime multiplier (1.8)
    iv_rank_scale       : float — Per-stock IV rank scaling factor.
                          Effective stop = base_mult * (1 + iv_rank * iv_rank_scale)
                          e.g. iv_rank=0.80, scale=1.0 → 1.8x boost on top of base_mult
    trail_trigger_pct   : float — start trailing after this % profit
    trail_step_pct      : float — tighten stop by this % of entry credit per step
    spread_buffer_mult  : float — extra buffer = N × half_spread
    check_interval      : int   — only evaluate stop every N simulation days
    check_dte_urgent    : int   — switch to daily check when DTE ≤ this value
    check_move_pct      : float — also check daily if premium moved > this fraction
    """
    base_stop_mult:    float = 2.0
    high_vol_mult:     float = 2.5
    low_vol_mult:      float = 1.8
    iv_rank_scale:     float = 1.0
    trail_trigger_pct: float = 0.25
    trail_step_pct:    float = 0.20
    spread_buffer_mult:float = 1.5
    check_interval:    int   = 5
    check_dte_urgent:  int   = 14
    check_move_pct:    float = 0.20

    # ── Entry initialization ──────────────────────────────────────────────────
    def init_stop(
        self,
        entry_premium: float,
        regime: str,
        iv_rank: float = 0.30,
        day_idx: int = 0,
    ) -> StopState:
        """
        Create the initial StopState for a newly entered position.

        iv_rank   : stock's own IV rank at entry (0–1). Higher → wider stop.
        """
        mult = self._iv_adjusted_mult(regime, iv_rank)
        raw_stop = entry_premium * mult
        half_spread = _simulated_spread(raw_stop, regime)
        buffered_stop = raw_stop + self.spread_buffer_mult * half_spread

        return StopState(
            initial_stop_px=buffered_stop,
            current_stop_px=buffered_stop,
            best_premium_seen=entry_premium,
            trailing_activated=False,
            stop_mult_used=mult,
            last_check_day_idx=day_idx,
            last_known_premium=entry_premium,
        )

    # ── Check frequency gate ──────────────────────────────────────────────────
    def should_check(
        self,
        stop_state: StopState,
        current_day_idx: int,
        dte_remaining: int,
        current_mid: float,
    ) -> bool:
        """
        Return True if we should evaluate the stop today.

        Always True when:
          - DTE is urgent (≤ check_dte_urgent)
          - Premium moved significantly since last check
          - Enough days elapsed since last check
        """
        # Urgent: approaching expiry
        if dte_remaining <= self.check_dte_urgent:
            return True

        # Urgent: premium has moved more than threshold since last check
        last_px = stop_state.last_known_premium
        if last_px > 0:
            move = abs(current_mid - last_px) / last_px
            if move >= self.check_move_pct:
                return True

        # Regular cadence: check every N days
        days_since_check = current_day_idx - stop_state.last_check_day_idx
        return days_since_check >= self.check_interval

    # ── Daily check ──────────────────────────────────────────────────────────
    def check(
        self,
        entry_premium: float,
        current_mid: float,
        stop_state: StopState,
        regime: str,
        current_day_idx: int = 0,
        underlying_daily_move: float = 0.0,
        underlying_avg_move: float = 0.01,
    ) -> tuple[bool, float, str]:
        """
        Evaluate stop logic for an open position.

        Returns
        -------
        (should_stop: bool, effective_stop_px: float, reason: str)
        """
        # Record last check state
        stop_state.last_check_day_idx = current_day_idx
        stop_state.last_known_premium = current_mid

        # ── 0. Crisis → immediate exit ────────────────────────────────────────
        if regime == "CRISIS":
            return True, current_mid, "stop_crisis_regime"

        # ── 1. Update trailing best ───────────────────────────────────────────
        if current_mid < stop_state.best_premium_seen:
            stop_state.best_premium_seen = current_mid

        # ── 2. Volatility-scaled buffer ───────────────────────────────────────
        move_ratio = underlying_daily_move / max(underlying_avg_move, 0.001)
        vol_buffer = (
            _simulated_spread(current_mid, regime)
            * self.spread_buffer_mult
            * max(1.0, move_ratio * 0.5)
        )

        # ── 3. Trailing stop ratchet ──────────────────────────────────────────
        profit_pct = 1.0 - (current_mid / max(entry_premium, 0.001))

        if profit_pct >= self.trail_trigger_pct and not stop_state.trailing_activated:
            stop_state.trailing_activated = True

        if stop_state.trailing_activated:
            # New trail stop: best seen + small bounce allowance
            trail_stop = stop_state.best_premium_seen + self.trail_step_pct * entry_premium
            if trail_stop < stop_state.current_stop_px:
                stop_state.current_stop_px = trail_stop + vol_buffer
                stop_state.stop_tightened_count += 1

        # ── 4. Spread-aware bid comparison ───────────────────────────────────
        # Compare the BID we'd receive (not mid) to avoid false triggers on wide spreads
        effective_bid = bid_price(current_mid, regime)
        stop_level    = stop_state.current_stop_px

        if effective_bid >= stop_level:
            return True, effective_bid, "stop_loss_spread_aware"

        return False, effective_bid, "no_stop"

    # ── Private ───────────────────────────────────────────────────────────────
    def _iv_adjusted_mult(self, regime: str, iv_rank: float) -> float:
        """
        Compute IV-adjusted stop multiplier.

        Base mult comes from regime, then scaled up by the stock's own IV rank.
        Formula: mult = base_regime_mult * (1 + iv_rank * iv_rank_scale)

        Examples with iv_rank_scale=0.5:
          NORMAL + iv_rank=0.10 → 2.0 * 1.05 = 2.10  (calm stock, small boost)
          NORMAL + iv_rank=0.50 → 2.0 * 1.25 = 2.50  (moderate IV, wider stop)
          NORMAL + iv_rank=0.90 → 2.0 * 1.45 = 2.90  (high IV, much wider stop)
          HIGH_VOL + iv_rank=0.80 → 2.5 * 1.40 = 3.50 (stressed, very wide stop)
        """
        base = {
            "LOW_VOL":  self.low_vol_mult,
            "NORMAL":   self.base_stop_mult,
            "HIGH_VOL": self.high_vol_mult,
            "CRISIS":   self.base_stop_mult,
        }.get(regime, self.base_stop_mult)

        # Cap iv_rank_scale at 0.5 to prevent stop being too wide to ever trigger
        effective_scale = min(self.iv_rank_scale, 0.5)
        return base * (1.0 + iv_rank * effective_scale)


# ---------------------------------------------------------------------------
# Convenience wrapper for backtest integration
# ---------------------------------------------------------------------------
def compute_stop_from_row(
    stop_mgr: SpreadAwareStopManager,
    entry_premium: float,
    current_mid: float,
    stop_state: StopState,
    regime: str,
    feat_row,
    current_day_idx: int = 0,
) -> tuple[bool, float, str]:
    """
    Wrapper that extracts vol/move info from a feature row and calls stop_mgr.check().
    Also handles should_check() frequency gate.
    """
    try:
        dte_remaining = stop_state.last_check_day_idx  # proxy; caller passes correctly
        if not stop_mgr.should_check(stop_state, current_day_idx, 999, current_mid):
            return False, current_mid, "no_check"

        close_today = float(feat_row.get("close", 1.0))
        close_prev  = float(feat_row.get("prev_close", close_today))
        daily_move  = abs(close_today - close_prev) / max(close_prev, 0.01)
        hv20        = float(feat_row.get("hv_20", 0.20))
        avg_move    = hv20 / math.sqrt(252)
    except Exception:
        daily_move, avg_move = 0.01, 0.01

    return stop_mgr.check(
        entry_premium=entry_premium,
        current_mid=current_mid,
        stop_state=stop_state,
        regime=regime,
        current_day_idx=current_day_idx,
        underlying_daily_move=daily_move,
        underlying_avg_move=avg_move,
    )
