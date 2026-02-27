"""
TQQQ Risk Manager
=================
Extends the base RiskManager with TQQQ-specific rules:
  - Capital pool budgeting (Theta 70% / Swing 30%)
  - Pool-aware position limits
  - Leg-out validation (long put/call must be worth holding)
  - Leverage-adjusted position sizing for a 3× leveraged ETF
  - Circuit breakers for drawdown and consecutive losses
"""

import logging
from typing import Optional
from dataclasses import dataclass
from enum import Enum, auto

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

class CircuitBreakerPhase(Enum):
    NORMAL = auto()
    HALT = auto()
    OBSERVE = auto()
    PROBE = auto()
    SCALE = auto()


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
    MAX_RISK_PCT            = 0.15   # 15% of portfolio at risk across positions
    MIN_BUYING_POWER_RESERVE= 0.30   # 30% buying power always reserved
    MAX_LONG_PUT_EXPOSURE   = 0.05   # 5% max account exposure per retained long

    # ── Capital Pool Allocation ────────────────────────────────────────────
    THETA_POOL_PCT          = 0.70   # 70% of capital for theta (credit spread) positions
    SWING_POOL_PCT          = 0.30   # 30% of capital for swing (diagonal) positions
    MAX_THETA_POSITIONS     = 3      # Max simultaneous theta positions
    MAX_SWING_POSITIONS     = 3      # Max simultaneous swing positions

    def __init__(self, account_value: float):
        self.account_value      = account_value
        self._peak_value        = account_value
        self._current_value     = account_value
        self._circuit_broken    = False
        self._cb_phase          = CircuitBreakerPhase.NORMAL
        self._probe_trades_won  = 0
        self._open_positions    = 0
        self._total_at_risk     = 0.0     # sum of max_loss across open spreads
        # Pool-specific tracking
        self._theta_positions   = 0
        self._theta_at_risk     = 0.0
        self._swing_positions   = 0
        self._swing_at_risk     = 0.0

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
        if self._cb_phase in (CircuitBreakerPhase.HALT, CircuitBreakerPhase.OBSERVE):
            return TQQQRiskCheck(False, f"CIRCUIT_BREAKER_ACTIVE: Currently in {self._cb_phase.name} phase.")

        # Max concurrent positions
        if self._open_positions >= TQQQ_MAX_CONCURRENT_SPREADS:
            return TQQQRiskCheck(
                False,
                f"MAX_POSITIONS: Already at {self._open_positions} concurrent spreads."
            )

        # Total risk budget
        new_total_risk = self._total_at_risk + new_max_loss
        risk_pct = new_total_risk / max(self._current_value, 1.0)
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

    def can_enter_theta_position(
        self,
        new_max_loss: float,
        current_buying_power: float,
    ) -> TQQQRiskCheck:
        """
        Check whether the THETA pool has budget for a new credit spread.
        """
        if self._theta_positions >= self.MAX_THETA_POSITIONS:
            return TQQQRiskCheck(
                False,
                f"THETA_MAX_POSITIONS: {self._theta_positions} theta positions active."
            )

        theta_budget = self._current_value * self.THETA_POOL_PCT
        if self._theta_at_risk + new_max_loss > theta_budget:
            return TQQQRiskCheck(
                False,
                f"THETA_BUDGET: Would use ${self._theta_at_risk + new_max_loss:.0f} "
                f"of ${theta_budget:.0f} theta budget."
            )

        return self.can_open_new_spread(new_max_loss, current_buying_power)

    def can_enter_swing_position(
        self,
        new_max_loss: float,
        current_buying_power: float,
    ) -> TQQQRiskCheck:
        """
        Check whether the SWING pool has budget for a new diagonal trade.
        """
        if self._swing_positions >= self.MAX_SWING_POSITIONS:
            return TQQQRiskCheck(
                False,
                f"SWING_MAX_POSITIONS: {self._swing_positions} swing positions active."
            )

        swing_budget = self._current_value * self.SWING_POOL_PCT
        if self._swing_at_risk + new_max_loss > swing_budget:
            return TQQQRiskCheck(
                False,
                f"SWING_BUDGET: Would use ${self._swing_at_risk + new_max_loss:.0f} "
                f"of ${swing_budget:.0f} swing budget."
            )

        return self.can_open_new_spread(new_max_loss, current_buying_power)

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

    def get_sizing_multiplier(self) -> float:
        """Returns the capital sizing multiplier based on the current CB phase."""
        if self._cb_phase == CircuitBreakerPhase.NORMAL: return 1.0
        if self._cb_phase == CircuitBreakerPhase.PROBE: return 0.25
        if self._cb_phase == CircuitBreakerPhase.SCALE: return 0.50
        return 0.0

    def calculate_contracts(
        self,
        max_loss_per_spread: float,
        credit_per_spread: float,
    ) -> int:
        """
        TQQQ-specific contract sizing:
        Risk ≤ 5% of current account value per position.
        Returns number of spread contracts.
        """
        dollar_risk_allowed = self._current_value * 0.05 * self.get_sizing_multiplier()
        contracts           = int(dollar_risk_allowed / max(max_loss_per_spread * 100, 1))
        return max(0, min(contracts, 100))   # hard cap at 100 contracts per spread

    def update_pnl(self, pnl_delta: float) -> None:
        """Call after each closed trade to update running P&L."""
        self._current_value += pnl_delta
        if self._current_value > self._peak_value:
            self._peak_value = self._current_value

        drawdown = (self._peak_value - self._current_value) / self._peak_value
        if drawdown >= self.MAX_DRAWDOWN_PCT and self._cb_phase == CircuitBreakerPhase.NORMAL:
            self._circuit_broken = True
            self._cb_phase = CircuitBreakerPhase.HALT
            logger.warning(
                f"CIRCUIT BREAKER TRIPPED: {drawdown:.1%} drawdown "
                f"(limit {self.MAX_DRAWDOWN_PCT:.0%}). Halting new entries."
            )
            
        # Update tiered recovery mechanics
        if pnl_delta > 0 and self._cb_phase in (CircuitBreakerPhase.PROBE, CircuitBreakerPhase.SCALE):
            self._probe_trades_won += 1
            if self._probe_trades_won >= 3:
                if self._cb_phase == CircuitBreakerPhase.PROBE:
                    logger.info("Probe successful (3 wins). Upgrading to SCALE phase.")
                    self._cb_phase = CircuitBreakerPhase.SCALE
                    self._probe_trades_won = 0
                elif self._cb_phase == CircuitBreakerPhase.SCALE:
                    logger.info("Scale successful (3 wins). Recovered to NORMAL phase.")
                    self._cb_phase = CircuitBreakerPhase.NORMAL
                    self._circuit_broken = False
                    self._probe_trades_won = 0
        elif pnl_delta < 0 and self._cb_phase in (CircuitBreakerPhase.PROBE, CircuitBreakerPhase.SCALE):
            logger.warning(f"{self._cb_phase.name} trade failed. Demoting back to OBSERVE phase.")
            self._cb_phase = CircuitBreakerPhase.OBSERVE
            self._probe_trades_won = 0

    def evaluate_reentry_conditions(self, vix: float, vix_sma: float, tqqq_price: float, tqqq_sma20: float, regime_score: int) -> bool:
        """Called daily to evaluate transitioning from HALT/OBSERVE to PROBE."""
        if self._cb_phase not in (CircuitBreakerPhase.HALT, CircuitBreakerPhase.OBSERVE):
            return False
            
        if vix < vix_sma and tqqq_price > tqqq_sma20 and regime_score >= 50:
            logger.info("Re-entry conditions met. Transitioning to PROBE phase.")
            self._cb_phase = CircuitBreakerPhase.PROBE
            self._probe_trades_won = 0
            return True
            
        self._cb_phase = CircuitBreakerPhase.OBSERVE
        return False

    def on_position_opened(self, max_loss: float, pool: str = "THETA") -> None:
        self._open_positions  += 1
        self._total_at_risk   += max_loss
        if pool == "THETA":
            self._theta_positions += 1
            self._theta_at_risk += max_loss
        elif pool == "SWING":
            self._swing_positions += 1
            self._swing_at_risk += max_loss

    def on_position_closed(self, max_loss: float, pool: str = "THETA") -> None:
        self._open_positions  = max(0, self._open_positions - 1)
        self._total_at_risk   = max(0.0, self._total_at_risk - max_loss)
        if pool == "THETA":
            self._theta_positions = max(0, self._theta_positions - 1)
            self._theta_at_risk = max(0.0, self._theta_at_risk - max_loss)
        elif pool == "SWING":
            self._swing_positions = max(0, self._swing_positions - 1)
            self._swing_at_risk = max(0.0, self._swing_at_risk - max_loss)

    def reset_circuit_breaker(self) -> None:
        """Manual override (e.g., after end-of-day review)."""
        self._circuit_broken = False
        self._cb_phase = CircuitBreakerPhase.NORMAL
        self._probe_trades_won = 0
        logger.info("Circuit breaker manually reset.")

    def get_status(self) -> dict:
        return {
            "account_value":        self._current_value,
            "peak_value":           self._peak_value,
            "drawdown_pct":         1 - self._current_value / self._peak_value,
            "circuit_broken":       self._circuit_broken,
            "cb_phase":             self._cb_phase.name,
            "probe_wins":           self._probe_trades_won,
            "open_positions":       self._open_positions,
            "total_at_risk":        self._total_at_risk,
            "risk_pct_of_account":  self._total_at_risk / max(self.account_value, 1),
            "sizing_multiplier":    self.get_sizing_multiplier(),
            # Pool-specific stats
            "theta_positions":      self._theta_positions,
            "theta_at_risk":        self._theta_at_risk,
            "theta_budget":         self._current_value * self.THETA_POOL_PCT,
            "swing_positions":      self._swing_positions,
            "swing_at_risk":        self._swing_at_risk,
            "swing_budget":         self._current_value * self.SWING_POOL_PCT,
        }
