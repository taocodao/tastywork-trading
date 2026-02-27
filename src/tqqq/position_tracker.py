"""
TQQQ Position Tracker
=====================
Tracks the state of active TQQQ positions across all three strategy layers:
  - Theta: Put credit spreads, bear call credit spreads
  - Swing: Put diagonal spreads (RSI mean-reversion)
"""

from dataclasses import dataclass, field
from typing import Optional
from src.tqqq import TQQQStrategyState


@dataclass
class TQQQPosition:
    """
    State container for an active TQQQ strategy position.
    Supports put spreads, call spreads, and diagonal swing trades.
    """
    id: str
    symbol: str
    state: TQQQStrategyState = TQQQStrategyState.IDLE

    # ── Position Classification ───────────────────────────────────────────
    spread_type: str = "PUT"       # "PUT", "CALL", or "DIAGONAL"
    pool: str = "THETA"            # "THETA" or "SWING" — capital pool assignment

    # ── Put Spread Fields ─────────────────────────────────────────────────
    short_strike: float = 0.0
    long_strike: float = 0.0
    expiration_date: str = ""
    quantity: int = 1

    # ── Call Spread Fields ────────────────────────────────────────────────
    short_call_strike: float = 0.0
    long_call_strike: float = 0.0
    tqqq_entry_price: float = 0.0        # TQQQ price at entry (for rally circuit breaker)

    # ── Diagonal Swing Fields ─────────────────────────────────────────────
    anchor_strike: float = 0.0
    anchor_expiration: str = ""
    hedge_strike: float = 0.0
    hedge_expiration: str = ""
    crash_guard_score: int = 0            # CrashGuard score at entry (for Layer 3 sizing)
    entry_price: float = 0.0             # TQQQ price at diagonal entry
    roll_count: int = 0                  # Number of hedge rolls (theta kicker)
    tranche: str = ""                    # Swing tranche (Deep, Mod, Light)

    # ── Entry Metrics ─────────────────────────────────────────────────────
    original_credit: float = 0.0
    max_loss: float = 0.0

    # ── Leg-Out Tracking ──────────────────────────────────────────────────
    short_put_close_price: Optional[float] = None
    long_put_legout_value: Optional[float] = None
    short_call_close_price: Optional[float] = None
    long_call_legout_value: Optional[float] = None

    # ── Exit Tracking ─────────────────────────────────────────────────────
    final_exit_price: float = 0.0

    @property
    def is_active(self) -> bool:
        return self.state in [
            TQQQStrategyState.FULL_SPREAD,
            TQQQStrategyState.LONG_PUT_ONLY,
            TQQQStrategyState.FULL_CALL_SPREAD,
            TQQQStrategyState.LONG_CALL_ONLY,
        ]

    @property
    def legout_cost(self) -> float:
        """If we legged out, the cost paid to close the short leg."""
        if self.spread_type == "CALL":
            return self.short_call_close_price if self.short_call_close_price is not None else 0.0
        return self.short_put_close_price if self.short_put_close_price is not None else 0.0

    def get_unrealized_pnl(self, current_spread_value: float) -> float:
        """
        Calculates unrealized PNL based on position state and type.

        For full spreads: PNL = credit received - current spread value
        For legged-out:  PNL = credit - legout cost + retained leg value
        """
        if self.state == TQQQStrategyState.FULL_SPREAD:
            return self.original_credit - current_spread_value

        elif self.state == TQQQStrategyState.FULL_CALL_SPREAD:
            return self.original_credit - current_spread_value

        elif self.state == TQQQStrategyState.LONG_PUT_ONLY:
            return self.original_credit - self.legout_cost + current_spread_value

        elif self.state == TQQQStrategyState.LONG_CALL_ONLY:
            return self.original_credit - self.legout_cost + current_spread_value

        return 0.0
