"""
Diagonal Risk Manager
=====================
Circuit breakers and margin/portfolio risk checks specific to the standalone Active Diagonal.
"""

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class DiagonalRiskCheck:
    passed: bool
    reason: str = ""
    
    def __bool__(self):
        return self.passed

class DiagonalRiskManager:
    """
    Portfolio-level risk controls for the Active Diagonal Strategy.
    """
    MAX_DRAWDOWN_PCT = 0.10
    MAX_RISK_PCT = 0.15
    MIN_BUYING_POWER_RESERVE = 0.30

    def __init__(self, account_value: float):
        self.account_value = account_value
        self._peak_value = account_value
        self._current_value = account_value
        self._circuit_broken = False
        self._open_positions = 0
        self._total_at_risk = 0.0

    def _get_tier(self) -> dict:
        from diagonal_strategy.config import PRINCIPAL_TIERS
        tier = PRINCIPAL_TIERS[0]
        for t in PRINCIPAL_TIERS:
            if self.account_value >= t['min']:
                tier = t
        return tier

    def can_open_new_diagonal(self, new_max_loss: float, current_buying_power: float) -> DiagonalRiskCheck:
        if self._circuit_broken:
            return DiagonalRiskCheck(False, "CIRCUIT_BREAKER")

        tier = self._get_tier()
        if self._open_positions >= tier['max_positions']: 
            return DiagonalRiskCheck(False, "MAX_POSITIONS")

        risk_pct = (self._total_at_risk + new_max_loss) / self.account_value
        if risk_pct > self.MAX_RISK_PCT:
            return DiagonalRiskCheck(False, "RISK_BUDGET")

        bp_used_pct = 1.0 - (current_buying_power / self.account_value)
        if bp_used_pct > (1.0 - self.MIN_BUYING_POWER_RESERVE):
            return DiagonalRiskCheck(False, "BP_RESERVE")

        return DiagonalRiskCheck(True)

    def calculate_contracts(self, max_loss_per_spread: float) -> int:
        tier = self._get_tier()
        dollar_risk_allowed = self.account_value * tier['risk_pct']
        contracts = int(dollar_risk_allowed / max(max_loss_per_spread * 100, 1))
        return max(1, min(contracts, tier['max_contracts']))

    def update_pnl(self, pnl_delta: float):
        self._current_value += pnl_delta
        if self._current_value > self._peak_value:
            self._peak_value = self._current_value

        drawdown = (self._peak_value - self._current_value) / self._peak_value
        if drawdown >= self.MAX_DRAWDOWN_PCT:
            self._circuit_broken = True
            logger.warning(f"CIRCUIT BREAKER: {drawdown:.1%} drawdown.")

    def on_position_opened(self, max_loss: float):
        self._open_positions += 1
        self._total_at_risk += max_loss

    def on_position_closed(self, max_loss: float):
        self._open_positions = max(0, self._open_positions - 1)
        self._total_at_risk = max(0.0, self._total_at_risk - max_loss)

    def get_status(self) -> dict:
        return {
            "account_value": self._current_value,
            "peak_value": self._peak_value,
            "drawdown_pct": 1 - self._current_value / self._peak_value if self._peak_value else 0,
            "circuit_broken": self._circuit_broken,
            "open_positions": self._open_positions,
            "total_at_risk": self._total_at_risk,
        }
