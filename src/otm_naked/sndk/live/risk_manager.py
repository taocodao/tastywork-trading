"""
SNDK Naked Options Risk Manager V3
Margin-Aware Position Management Framework for Reg T / PM
"""

import math
import logging
from typing import List, Tuple
from src.otm_naked.sndk.live.state_manager import LivePosition
from src.otm_naked.sndk.config import SNDKLadderConfig

logger = logging.getLogger(__name__)

class LiveRiskManager:
    """
    Mechanical position manager for SNDK naked options ladder.
    Called by the main bot at each evaluation cycle (30s for margin, 5m for signals).
    """

    def __init__(self, config: SNDKLadderConfig):
        self.cfg = config
        self.daily_realized_pnl = 0.0

    def reset_daily_stats(self):
        """Called at market open to reset daily PnL trackers."""
        self.daily_realized_pnl = 0.0
        
    def record_pnl(self, realized_pnl: float):
        self.daily_realized_pnl += realized_pnl

    # ── Margin helpers ─────────────────────────────────────────────────────────

    @property
    def margin_per_contract(self) -> float:
        if self.cfg.use_portfolio_margin:
            return self.cfg.margin_per_contract_pm
        return self.cfg.margin_per_contract_regt

    @property
    def max_contracts(self) -> int:
        if self.cfg.use_portfolio_margin:
            return self.cfg.max_contracts_pm
        return self.cfg.max_contracts_hard

    def open_contracts(self, positions: List[LivePosition]) -> int:
        return sum(r.contracts for r in positions)

    def margin_in_use(self, positions: List[LivePosition]) -> float:
        return self.open_contracts(positions) * self.margin_per_contract

    def nav_deployed_pct(self, nav: float, positions: List[LivePosition]) -> float:
        if nav <= 0: return 0.0
        return self.margin_in_use(positions) / nav

    # ── Rung spacing calculation ────────────────────────────────────────────────

    def rung_spacing_dollars(
        self, sndk_price: float, iv_annual: float,
        regime: str, days: int = 5
    ) -> float:
        """Minimum adverse price move required before adding the next rung."""
        sigma = sndk_price * iv_annual * math.sqrt(days) / math.sqrt(252)
        sigma_mult = {
            'EXTREME_UPTREND': self.cfg.rung_spacing_sigma_extreme_up,
            'UPTREND': self.cfg.rung_spacing_sigma_uptrend,
            'SIDEWAYS': self.cfg.rung_spacing_sigma_sideways,
        }.get(regime, 1.0)
        return sigma * sigma_mult

    # ── Entry gate ─────────────────────────────────────────────────────────────

    def can_add_rung(
        self, side: str, sndk_price: float, iv: float, regime: str,
        nav: float, excess_liquidity: float, positions: List[LivePosition]
    ) -> Tuple[bool, str]:
        """Returns (allowed, reason). 'reason' describes the block if not allowed."""

        # Hard contract ceiling
        if self.open_contracts(positions) >= self.max_contracts:
            return False, f"At max contracts ({self.max_contracts})"

        # Cash reserve floor
        projected_margin = self.margin_in_use(positions) + self.margin_per_contract
        if nav > 0 and (projected_margin / nav) > (1 - self.cfg.cash_reserve_floor):
            return False, "Cash reserve floor breached"

        # Excess liquidity gate
        projected_el = excess_liquidity - self.margin_per_contract
        if projected_el < self.cfg.min_excess_liquidity:
            return False, f"Excess liquidity too low: ${excess_liquidity:,.0f}"

        # Rung spacing gate — are we far enough from last entry on this side?
        side_rungs = [r for r in positions if r.opt_type == side]
        if side_rungs:
            if side == 'put':
                last_entry_spot = min(r.entry_underlying_price for r in side_rungs)
                spacing_needed = self.rung_spacing_dollars(sndk_price, iv, regime)
                price_drop = last_entry_spot - sndk_price
                if price_drop < spacing_needed:
                    return False, f"Need {spacing_needed:.0f} drop, only {price_drop:.0f}"
            else:
                last_entry_spot = max(r.entry_underlying_price for r in side_rungs)
                spacing_needed = self.rung_spacing_dollars(sndk_price, iv, regime)
                price_rise = sndk_price - last_entry_spot
                if price_rise < spacing_needed:
                    return False, f"Need {spacing_needed:.0f} rise, only {price_rise:.0f}"

        return True, "OK"
        
    def is_safe_to_enter(self, nav: float, positions: List[LivePosition], target_direction: str, earnings_days_away: int) -> bool:
        """Legacy wrapper - now we mostly rely on can_add_rung, but keep this for basic checks."""
        if earnings_days_away <= 14:
            logger.warning(f"RISK LIMIT: Earnings within 14 days ({earnings_days_away} days away)")
            return False
            
        return True

    # ── Exit decisions ─────────────────────────────────────────────────────────

    def rungs_to_close(
        self, sndk_price: float, current_option_prices: dict,
        excess_liquidity: float, positions: List[LivePosition]
    ) -> List[Tuple[LivePosition, str]]:
        """
        Returns list of (rung, reason) for rungs that should be closed NOW.
        current_option_prices: {contract_id: current_mid_price}
        """
        to_close = []

        for rung in positions:
            key = f"{rung.strike}_{rung.opt_type}"
            current_price = current_option_prices.get(key)

            # Rule 1: DTE ≤ 7 — gamma emergency
            if rung.dte <= self.cfg.dte_emergency_close:
                to_close.append((rung, f"DTE ≤ {self.cfg.dte_emergency_close}"))
                continue

            if current_price is None or current_price <= 0:
                continue

            # Rule 2: Profit target reached
            profit_target = (
                self.cfg.profit_target_pct_low_dte
                if rung.dte <= self.cfg.dte_reduce_profit_target
                else self.cfg.profit_target_pct_normal
            )
            if current_price <= rung.entry_premium * (1 - profit_target):
                to_close.append((rung, f"Profit target {profit_target*100:.0f}% hit"))
                continue

            # Rule 3: Close favorable — underlying recovered to favorable level
            if rung.opt_type == 'put' and sndk_price >= rung.entry_underlying_price * (1 - self.cfg.favorable_close_fraction):
                if current_price <= rung.entry_premium * 0.65:
                    to_close.append((rung, "Favorable underlying recovery (Put)"))
                    continue
            elif rung.opt_type == 'call' and sndk_price <= rung.entry_underlying_price * (1 + self.cfg.favorable_close_fraction):
                if current_price <= rung.entry_premium * 0.65:
                    to_close.append((rung, "Favorable underlying recovery (Call)"))
                    continue

        # Rule 4: Emergency margin — close most ITM rung
        if excess_liquidity < self.cfg.emergency_close_threshold:
            if positions:
                most_itm = min(
                    positions,
                    key=lambda r: (sndk_price - r.strike) if r.opt_type == 'put'
                                  else (r.strike - sndk_price)
                )
                if not any(r == most_itm for r, _ in to_close):
                    to_close.append((most_itm, "EMERGENCY MARGIN CLOSE"))
                    logger.critical(
                        f"EMERGENCY MARGIN CLOSE triggered for {most_itm.opt_type} {most_itm.strike}! "
                        f"Excess Liquidity: ${excess_liquidity:,.0f}"
                    )

        return to_close

    # ── Monitoring — call every 30 seconds ─────────────────────────────────────

    def check_margin_health(self, excess_liquidity: float, nav: float, positions: List[LivePosition]) -> str:
        """
        Returns health status. Bot should pause new entries on WARNING or CRITICAL.
        """
        if excess_liquidity < self.cfg.emergency_close_threshold:
            return "CRITICAL"  # Trigger emergency close
        if excess_liquidity < self.cfg.min_excess_liquidity:
            return "WARNING"   # Pause new entries
        if nav > 0 and self.nav_deployed_pct(nav, positions) > 0.50:
            return "CAUTION"   # Getting concentrated; no new rungs
        return "OK"
