"""
OTM Naked Options — Risk Manager
===================================
Naked-specific risk rules extending the base RiskManager pattern.
Handles 1% per-position sizing, 2x credit stop-loss, margin checks,
VIX crisis gate, and portfolio heat limits.
"""
import logging
from dataclasses import dataclass
from typing import Optional
from .config import OTMNakedConfig

logger = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    passed: bool
    reason: str = ""
    def __bool__(self): return self.passed


class OTMNakedRiskManager:
    """
    Risk gate for new naked option entries.

    Hard rules (no ML override):
    - Max 1% capital at risk per position
    - Max 5% total portfolio heat (all naked positions)
    - No trades when VIX >= 35 (crisis gate)
    - IV rank must be >= min_iv_rank to enter
    - Stop-loss at 2x credit received
    - No more than max_concurrent_positions open
    - No earnings within 21 days
    """

    def __init__(self, config: Optional[OTMNakedConfig] = None,
                 account_size: float = 50_000.0):
        self.config       = config or OTMNakedConfig()
        self.account_size = account_size
        self.open_positions: list = []       # List of open position dicts
        self.today_pnl:    float = 0.0
        self.realized_pnl: float = 0.0

    @property
    def max_risk_per_trade(self) -> float:
        return self.account_size * self.config.max_risk_per_trade_pct

    @property
    def max_portfolio_heat(self) -> float:
        return self.account_size * self.config.max_portfolio_heat_pct

    @property
    def current_heat(self) -> float:
        """Total open risk (strike * contracts * 100 for naked puts/calls)."""
        return sum(p.get("notional_risk", 0) for p in self.open_positions)

    def check_entry(
        self,
        symbol:         str,
        strike:         float,
        premium:        float,
        contracts:      int,
        vix:            float,
        iv_rank:        float,
        iv_hv_ratio:    float,
        earnings_days:  int = 999,
        option_type:    str = "put",
    ) -> RiskCheck:
        """
        Full pre-entry risk gate.

        Args:
            symbol:        Underlying symbol
            strike:        Option strike price
            premium:       Credit received per share ($)
            contracts:     Number of contracts to sell
            vix:           Current VIX
            iv_rank:       Current IV rank (0-1)
            iv_hv_ratio:   IV / HV ratio
            earnings_days: Days until next earnings
            option_type:   "put" or "call"

        Returns:
            RiskCheck pass/fail with reason
        """
        # Crisis gate — no new naked positions in extreme vol
        if vix >= self.config.vix_crisis_threshold:
            return RiskCheck(False, f"CRISIS gate: VIX={vix:.1f} >= {self.config.vix_crisis_threshold}")

        # IV rank gate
        if iv_rank < self.config.min_iv_rank:
            return RiskCheck(False, f"Low IV rank: {iv_rank:.2f} < {self.config.min_iv_rank}")

        # IV/HV ratio gate (premium must be elevated relative to realized vol)
        if iv_hv_ratio < self.config.min_iv_hv_ratio:
            return RiskCheck(False, f"Low IV/HV: {iv_hv_ratio:.2f} < {self.config.min_iv_hv_ratio}")

        # Earnings proximity
        if earnings_days < self.config.earnings_blackout_days:
            return RiskCheck(False, f"Earnings in {earnings_days}d (blackout = {self.config.earnings_blackout_days}d)")

        # Max concurrent positions
        if len(self.open_positions) >= self.config.max_concurrent_positions:
            return RiskCheck(False, f"Max positions ({self.config.max_concurrent_positions}) reached")

        # Position-level risk: credit received is max profit; naked risk ≈ notional
        credit_received = premium * contracts * 100
        notional_risk   = strike * contracts * 100   # Worst-case naked loss
        per_trade_risk  = credit_received * 2.0       # 2x credit stop-loss

        if per_trade_risk > self.max_risk_per_trade:
            return RiskCheck(False,
                f"Per-trade risk ${per_trade_risk:.0f} > limit ${self.max_risk_per_trade:.0f}")

        # Portfolio heat
        new_heat = self.current_heat + notional_risk
        if new_heat > self.max_portfolio_heat:
            return RiskCheck(False,
                f"Portfolio heat ${new_heat:.0f} > limit ${self.max_portfolio_heat:.0f}")

        return RiskCheck(True, f"OK | credit=${credit_received:.0f} | risk=${per_trade_risk:.0f}")

    def calculate_contracts(
        self,
        premium:      float,
        strike:       float,
        account_nav:  Optional[float] = None,
    ) -> int:
        """
        Kelly-fractional position sizing (capped at 1% risk).

        Args:
            premium:     Credit per share
            strike:      Strike price (notional basis for naked put)
            account_nav: Current account NAV (uses account_size if None)

        Returns:
            Number of contracts to sell
        """
        nav  = account_nav or self.account_size
        max_credit_risk = nav * self.config.max_risk_per_trade_pct
        # 2x credit stop means max loss ≈ 2x premium collected
        max_contracts_by_risk = max_credit_risk / max(premium * 2 * 100, 1)
        # Also cap by heat (notional)
        heat_remaining  = self.max_portfolio_heat - self.current_heat
        max_by_heat     = heat_remaining / max(strike * 100, 1)
        contracts = int(min(max_contracts_by_risk, max_by_heat))
        return max(0, min(contracts, 5))    # Hard cap at 5 contracts

    def check_stop_loss(
        self,
        current_premium: float,
        entry_premium:   float,
    ) -> bool:
        """Returns True if the 2x credit stop has been triggered."""
        loss = current_premium - entry_premium    # Positive = premium expanded (loss)
        return loss >= entry_premium * (self.config.stop_loss_credit_mult - 1)

    def check_profit_take(
        self,
        current_premium: float,
        entry_premium:   float,
    ) -> bool:
        """Returns True if the 50% profit target has been reached."""
        profit_pct = 1 - (current_premium / max(entry_premium, 0.001))
        return profit_pct >= self.config.profit_take_pct

    def record_open(self, position: dict):
        """Register a new open position."""
        self.open_positions.append(position)

    def record_close(self, symbol: str, pnl: float):
        """Close a position by symbol and record P&L."""
        self.open_positions = [p for p in self.open_positions
                               if p.get("symbol") != symbol]
        self.today_pnl    += pnl
        self.realized_pnl += pnl
        logger.info(f"[CLOSE] {symbol} P&L={pnl:+.2f} | realized_total={self.realized_pnl:.2f}")

    def get_status(self) -> dict:
        return {
            "account_size":       self.account_size,
            "open_positions":     len(self.open_positions),
            "current_heat":       round(self.current_heat, 2),
            "max_heat":           round(self.max_portfolio_heat, 2),
            "today_pnl":          round(self.today_pnl, 2),
            "realized_pnl":       round(self.realized_pnl, 2),
            "max_risk_per_trade": round(self.max_risk_per_trade, 2),
        }
