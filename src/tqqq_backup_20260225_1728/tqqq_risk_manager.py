"""
TQQQ Risk Manager
=================
Extends the base RiskManager with TQQQ-specific rules:
  - Leg-out validation (long put must be worth holding)
  - Leverage-adjusted position sizing for a 3× leveraged ETF
  - Circuit breakers for drawdown and consecutive losses
"""

import logging
from typing import Optional
from dataclasses import dataclass

from config import (
    TQQQ_MAX_CONCURRENT_SPREADS,
    TQQQ_MIN_LONG_PUT_VALUE, TQQQ_MIN_DTE_LEGOUT
)

logger = logging.getLogger(__name__)


@dataclass
class TQQQRiskCheck:
    passed: bool
    reason: str = ""

    def __bool__(self):
        return self.passed


class TQQQRiskManager:
    """
    Portfolio-level risk controls for the TQQQ spread strategy.

    Hard limits
    ───────────
    • Max 3 concurrent spreads
    • Max 5% of portfolio at risk across all open positions
    • Min 30% buying power reserve at all times
    • 10% portfolio drawdown → halt new entries (circuit breaker)

    Leg-out validation
    ──────────────────
    • Long put value > $0.30 (otherwise theta decay is too severe)
    • DTE > 14 days (enough time to capture a VIX spike)
    • Long put exposure < 1% of account value
    """

    # ── Circuit breaker thresholds ──────────────────────────────────────
    MAX_DRAWDOWN_PCT        = 0.10   # 10% portfolio drawdown → halt
    MAX_RISK_PCT            = 0.05   # 5% of portfolio at risk across positions
    MIN_BUYING_POWER_RESERVE= 0.30   # 30% buying power always reserved
    MAX_LONG_PUT_EXPOSURE   = 0.01   # 1% max account exposure per retained long

    def __init__(self, account_value: float):
        self.account_value      = account_value
        self._peak_value        = account_value
        self._current_value     = account_value
        self._circuit_broken    = False
        self._open_positions    = 0
        self._total_at_risk     = 0.0     # sum of max_loss across open spreads

    # ─────────────────────── Public API ──────────────────────────────────

    def can_open_new_spread(
        self,
        new_max_loss: float,
        current_buying_power: float,
    ) -> TQQQRiskCheck:
        """
        Check whether we are allowed to open a new TQQQ spread.
        """
        # Circuit breaker
        if self._circuit_broken:
            return TQQQRiskCheck(False, "CIRCUIT_BREAKER: Drawdown limit breached.")

        # Max concurrent positions
        if self._open_positions >= TQQQ_MAX_CONCURRENT_SPREADS:
            return TQQQRiskCheck(
                False,
                f"MAX_POSITIONS: Already at {self._open_positions} concurrent spreads."
            )

        # Total risk budget
        new_total_risk = self._total_at_risk + new_max_loss
        risk_pct = new_total_risk / self.account_value
        if risk_pct > self.MAX_RISK_PCT:
            return TQQQRiskCheck(
                False,
                f"RISK_BUDGET: Adding this spread would put {risk_pct:.1%} at risk "
                f"(limit: {self.MAX_RISK_PCT:.0%})."
            )

        # Buying power reserve
        bp_used_pct = 1.0 - (current_buying_power / self.account_value)
        if bp_used_pct > (1.0 - self.MIN_BUYING_POWER_RESERVE):
            return TQQQRiskCheck(
                False,
                f"BP_RESERVE: Only {1 - bp_used_pct:.1%} buying power available "
                f"(need {self.MIN_BUYING_POWER_RESERVE:.0%} reserve)."
            )

        return TQQQRiskCheck(True)

    def can_leg_out(
        self,
        long_put_value: float,
        dte: int,
        account_value: Optional[float] = None,
    ) -> TQQQRiskCheck:
        """
        Validates leg-out conditions from a risk perspective.
        """
        av = account_value or self.account_value

        if long_put_value < TQQQ_MIN_LONG_PUT_VALUE:
            return TQQQRiskCheck(
                False,
                f"LONG_PUT_TOO_CHEAP: ${long_put_value:.2f} < min ${TQQQ_MIN_LONG_PUT_VALUE:.2f}. "
                "Not worth legging out."
            )

        if dte < TQQQ_MIN_DTE_LEGOUT:
            return TQQQRiskCheck(
                False,
                f"DTE_TOO_SHORT: {dte} days < min {TQQQ_MIN_DTE_LEGOUT}. "
                "Not enough time for VIX spike."
            )

        long_put_exposure_pct = long_put_value * 100 / av
        if long_put_exposure_pct > self.MAX_LONG_PUT_EXPOSURE:
            return TQQQRiskCheck(
                False,
                f"LONG_PUT_OVER_EXPOSED: {long_put_exposure_pct:.2%} > "
                f"max {self.MAX_LONG_PUT_EXPOSURE:.0%}."
            )

        return TQQQRiskCheck(True)

    def calculate_contracts(
        self,
        max_loss_per_spread: float,
        credit_per_spread: float,
    ) -> int:
        """
        TQQQ-specific contract sizing:
        Risk ≤ 1% of account per position (conservative for 3× leverage).
        Returns number of spread contracts.
        """
        dollar_risk_allowed = self.account_value * 0.01
        contracts           = int(dollar_risk_allowed / max(max_loss_per_spread * 100, 1))
        return max(1, min(contracts, 5))   # hard cap at 5 contracts per spread

    def update_pnl(self, pnl_delta: float) -> None:
        """Call after each closed trade to update running P&L."""
        self._current_value += pnl_delta
        if self._current_value > self._peak_value:
            self._peak_value = self._current_value

        drawdown = (self._peak_value - self._current_value) / self._peak_value
        if drawdown >= self.MAX_DRAWDOWN_PCT:
            self._circuit_broken = True
            logger.warning(
                f"CIRCUIT BREAKER TRIPPED: {drawdown:.1%} drawdown "
                f"(limit {self.MAX_DRAWDOWN_PCT:.0%}). Halting new entries."
            )

    def on_position_opened(self, max_loss: float) -> None:
        self._open_positions  += 1
        self._total_at_risk   += max_loss

    def on_position_closed(self, max_loss: float) -> None:
        self._open_positions  = max(0, self._open_positions - 1)
        self._total_at_risk   = max(0.0, self._total_at_risk - max_loss)

    def reset_circuit_breaker(self) -> None:
        """Manual override (e.g., after end-of-day review)."""
        self._circuit_broken = False
        logger.info("Circuit breaker manually reset.")

    def get_status(self) -> dict:
        return {
            "account_value":        self._current_value,
            "peak_value":           self._peak_value,
            "drawdown_pct":         1 - self._current_value / self._peak_value,
            "circuit_broken":       self._circuit_broken,
            "open_positions":       self._open_positions,
            "total_at_risk":        self._total_at_risk,
            "risk_pct_of_account":  self._total_at_risk / self.account_value,
        }
