"""
MTASLadderManager -- live implementation of the exact rule set validated in
real_rule_backtest_5m.py (walk-forward validated 2026-07-16/17/18, see config_mtas.yaml
for the summary and the separate research workspace for the full sweep logs).

Rule mapping back to the backtest (`open_leg` / the exit elif-chain / `try_open` in
real_rule_backtest_5m.py), kept as literal a translation as live broker execution allows:

  ENTRY:  bootstrap the first rung on a side immediately (margin-gated). Every
          subsequent rung on that side opens only when spot breaks past the most
          extended existing rung's spot_at_open on that side (self-referencing
          breakout), gated by margin and the per-side leg cap. No gap/cooldown/
          trailing-entry/regime-filter logic -- none of those were adopted.
  SIZE:   always 1 contract per rung.
  EXIT (checked in this order, first match wins, exactly mirroring the backtest):
          1. cushion_floor  -- moneyness cushion (strike vs spot, NOT premium) erodes
             below the per-side floor (call 0.40, put 0.22).
          2. profit_take    -- (premium_open - mark)/premium_open >= 0.30.
          3. forced_expiry  -- dte_days_left <= 3.
  NOT implemented here on purpose (all tested and rejected/not-adopted upstream):
          premium-multiple stop-loss, ML regime gating, rolls, vol-percentile leg-cap
          throttle, entry gap/cooldown/trailing logic.

Key difference from the backtest: the backtest marks options with Black-Scholes because
it has no real intraday options-quote history; this live version marks with the actual
IB bid/ask mid, which is more accurate but also means profit_take timing will not be
identical to the backtest bar-by-bar -- this is expected and is a strictly better data
source than what the backtest could use.

STATUS: code-complete, walk-forward research validated, NOT yet run against a live IB
connection. Must be paper-traded and reconciled against real fills before any transition
to `mode: live` in config_mtas.yaml.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from ib_insync import Option

logger = logging.getLogger(__name__)


class MTASLadderManager:
    def __init__(self, ib, config: dict, market_data, option_selector, order_executor, state_manager):
        self.ib = ib
        self.cfg = config["strategy"]
        self.ticker = config["ticker"]
        self.margin_pct = config["account"]["margin_pct"]
        self.md = market_data
        self.selector = option_selector
        self.exec_ = order_executor
        self.state = state_manager

    # ---------------- helpers ----------------

    def _margin_per_contract(self, spot: float) -> float:
        return self.margin_pct * spot * 100

    def _rebuild_contract(self, leg) -> Option:
        return Option(self.ticker, leg.expiry, leg.strike, leg.right, "SMART", currency="USD")

    def _get_mark(self, leg) -> Optional[float]:
        """Live bid/ask mid for an open leg. Returns None if no usable quote (e.g. off-hours)."""
        contract = self._rebuild_contract(leg)
        greeks = self.md.get_contract_greeks_and_prices([contract])
        data = greeks.get(contract.conId)
        if not data:
            return None
        if data["mid"] > 0:
            return data["mid"]
        if data["ask"] > 0:
            return data["ask"]
        return None

    def _available_funds(self) -> float:
        try:
            return self.exec_.get_excess_liquidity()
        except Exception as e:
            logger.warning(f"Could not fetch excess liquidity, defaulting to 0: {e}")
            return 0.0

    # ---------------- exits ----------------

    def check_exits(self, spot: float):
        """Mirrors the exit elif-chain in run_backtest_5m(): cushion_floor, then
        profit_take, then forced_expiry, first match wins, per open leg."""
        for leg in list(self.state.get_open_legs()):
            floor_use = self.cfg["call_cushion_floor"] if leg.right == "C" else self.cfg["put_cushion_floor"]
            cushion = (leg.strike - spot) / spot if leg.right == "C" else (spot - leg.strike) / spot

            reason = None
            mark = None
            if cushion < floor_use:
                reason = "cushion_floor"
            else:
                mark = self._get_mark(leg)
                if mark is not None and leg.premium_open > 0:
                    unreal_gain_pct = (leg.premium_open - mark) / leg.premium_open
                    if unreal_gain_pct >= self.cfg["profit_take_pct"]:
                        reason = "profit_take"
                if reason is None and leg.dte <= self.cfg["forced_expiry_dte"]:
                    reason = "forced_expiry"

            if reason:
                self._close_leg(leg, spot, reason, mark)

    def _close_leg(self, leg, spot: float, reason: str, mark: Optional[float]):
        contract = self._rebuild_contract(leg)
        if mark is None:
            mark = self._get_mark(leg)
        # Use a conservative limit: for a BTC, willing to pay up to mark + small buffer;
        # if no live quote at all (e.g. forced_expiry near/at expiry), fall back to intrinsic.
        if mark is None:
            mark = max(spot - leg.strike, 0) if leg.right == "C" else max(leg.strike - spot, 0)
        limit_price = round(mark * 1.05, 2)  # 5% buffer over mid so a real BTC actually fills

        logger.info(f"Closing MTAS leg {leg.id} ({leg.right} {leg.strike} exp {leg.expiry}) "
                    f"reason={reason} mark={mark:.2f}")
        trade = self.exec_.buy_to_close(contract, leg.quantity, limit_price)
        fill_price = None
        if trade is not None and trade.orderStatus.status == "Filled":
            fill_price = trade.orderStatus.avgFillPrice
        else:
            logger.warning(f"BTC for leg {leg.id} did not confirm filled; recording at estimated mark "
                            f"{mark:.2f} pending manual reconciliation.")
            fill_price = mark

        realized_pnl = (leg.premium_open - fill_price) * leg.quantity * 100
        self.state.close_leg(leg.id, fill_price, reason, realized_pnl)

    # ---------------- entries ----------------

    def try_open_rungs(self, spot: float):
        self._try_open_side("C", self.cfg["call_otm_target"])
        self._try_open_side("P", self.cfg["put_otm_target"])

    def _try_open_side(self, right: str, otm_target: float):
        open_legs = self.state.get_open_legs(right)
        max_legs = self.cfg["max_legs_per_side"]

        if not open_legs:
            self._attempt_entry(right, otm_target, reason="bootstrap")
            return

        if len(open_legs) >= max_legs:
            return  # leg cap reached on this side

        spot_now = self.md.get_current_price(self.ticker)
        if spot_now <= 0:
            return
        trigger = max(l.spot_at_open for l in open_legs) if right == "C" else min(l.spot_at_open for l in open_legs)
        breached = spot_now > trigger if right == "C" else spot_now < trigger
        if breached:
            self._attempt_entry(right, otm_target, reason="breakout")

    def _attempt_entry(self, right: str, otm_target: float, reason: str):
        spot = self.md.get_current_price(self.ticker)
        if spot <= 0:
            logger.warning("No usable spot price, skipping entry attempt.")
            return

        available = self._available_funds()
        margin_needed = self._margin_per_contract(spot)
        if available < margin_needed:
            logger.info(f"Skipping {right} entry ({reason}): excess liquidity {available:.0f} < "
                        f"required margin {margin_needed:.0f}")
            return

        selected = self.selector.select_strike_by_otm(
            self.ticker, self.cfg["entry_dte_days"], otm_target, right
        )
        if selected is None:
            logger.warning(f"No valid strike selected for {right} side ({reason}), skipping.")
            return
        if selected["premium"] < self.cfg["min_premium"]:
            logger.info(f"Skipping {right} entry: premium {selected['premium']:.2f} below floor "
                        f"{self.cfg['min_premium']}")
            return

        contract = selected["contract"]
        limit_price = round(selected["premium"] * 0.97, 2)  # 3% below mid so an STO actually fills as a credit sale
        qty = self.cfg["contract_quantity"]

        logger.info(f"Opening MTAS {right} rung ({reason}): strike={selected['strike']} "
                    f"expiry={selected['expiry']} otm={selected['actual_otm_pct']:.1%} "
                    f"premium~{selected['premium']:.2f}")
        trade = self.exec_.sell_to_open(contract, qty, limit_price, available_funds=available)
        if trade is None or trade.orderStatus.status != "Filled":
            logger.warning(f"STO for {right} rung did not confirm filled; not recording a position.")
            return

        fill_price = trade.orderStatus.avgFillPrice
        from .mtas_state import MTASLeg
        leg = MTASLeg(
            id=str(uuid.uuid4())[:8],
            right=right,
            strike=selected["strike"],
            expiry=selected["expiry"],
            con_id=contract.conId,
            quantity=qty,
            spot_at_open=spot,
            premium_open=fill_price,
            entry_date=datetime.now().isoformat(),
            rung_id=self.state.next_rung_id(right),
        )
        self.state.add_leg(leg)

    # ---------------- main tick ----------------

    def on_management_tick(self):
        """Call periodically (see config_mtas.yaml: management_interval_seconds)."""
        spot = self.md.get_current_price(self.ticker)
        if spot <= 0:
            logger.warning("on_management_tick: no usable spot price, skipping this tick.")
            return
        self.check_exits(spot)
        self.try_open_rungs(spot)
