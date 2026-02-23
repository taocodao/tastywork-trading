"""
TQQQ Order Manager
==================
Handles Interactive Brokers order placement for TQQQ put credit spreads
using ib_insync. Supports:
  - Placing a combo (BAG) spread order
  - Closing a single leg (leg-out or profit-take)
  - Smart limit order walking (mid → improve $0.01 every 15 s)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Guard import so the module is importable even without ib_insync installed
try:
    from ib_insync import IB, Contract, ComboLeg, Order, Trade, util
    IB_AVAILABLE = True
except ImportError:
    logger.warning("ib_insync not installed. TQQQOrderManager will run in simulation mode.")
    IB = ComboLeg = Order = Trade = Contract = util = None
    IB_AVAILABLE = False


@dataclass
class OrderResult:
    success: bool
    fill_price: float
    order_id: Optional[int] = None
    message: str = ""


class TQQQOrderManager:
    """
    Wraps ib_insync to place TQQQ spread and single-leg orders.
    Reuses the existing IB connection managed by ib_data_provider.py.
    """

    MAX_ADJUSTMENTS  = 6     # walk price up to 6 times
    ADJUST_INTERVAL  = 15    # seconds between each adjustment
    PRICE_STEP       = 0.01  # $0.01 per adjustment
    MAX_SLIPPAGE     = 0.10  # abort if we've moved more than $0.10 from mid

    def __init__(self, ib_client=None):
        """
        Args:
            ib_client: a connected ib_insync.IB instance. If None, a simulation
                       stub is used so the rest of the strategy code can run.
        """
        self.ib = ib_client
        self._sim_mode = (ib_client is None)

    # ─────────────────────── Public API ──────────────────────────────────

    async def place_spread_order(
        self,
        short_strike: float,
        long_strike: float,
        expiration: str,
        quantity: int,
        account_id: str,
    ) -> OrderResult:
        """
        Opens a TQQQ put credit spread (sell short put / buy long put) as a
        ib_insync BAG combo order.

        ``expiration``: YYYYMMDD string
        """
        if self._sim_mode:
            logger.info(f"[SIM] Place spread {short_strike}P / {long_strike}P x{quantity}")
            return OrderResult(success=True, fill_price=0.85, message="SIMULATED")

        short_con = self._make_tqqq_put(short_strike, expiration)
        long_con  = self._make_tqqq_put(long_strike, expiration)

        await self._qualify([short_con, long_con])

        combo = self._build_combo(short_con, long_con, quantity)
        mid   = await self._get_mid(combo)

        order = self._limit_order("SELL", quantity, round(mid, 2), account_id)
        trade = self.ib.placeOrder(combo, order)

        result = await self._walk_and_fill(trade, mid, direction="credit")
        return result

    async def close_single_leg(
        self,
        strike: float,
        expiration: str,
        quantity: int,
        action: str,          # "BUY" (leg-out) or "SELL" (take profit)
        account_id: str,
    ) -> OrderResult:
        """
        Manages a single put leg: either buying back the short put (leg-out)
        or selling the retained long put (profit capture).
        """
        if self._sim_mode:
            logger.info(f"[SIM] {action} single leg {strike}P x{quantity}")
            return OrderResult(success=True, fill_price=0.12, message="SIMULATED")

        con = self._make_tqqq_put(strike, expiration)
        await self._qualify([con])

        mid   = await self._get_mid(con)
        order = self._limit_order(action, quantity, round(mid, 2), account_id)
        trade = self.ib.placeOrder(con, order)

        direction = "debit" if action == "BUY" else "credit"
        return await self._walk_and_fill(trade, mid, direction)

    # ─────────────────────── IB Helpers ──────────────────────────────────

    def _make_tqqq_put(self, strike: float, expiration: str) -> "Contract":
        con = Contract()
        con.symbol    = "TQQQ"
        con.secType   = "OPT"
        con.exchange  = "SMART"
        con.currency  = "USD"
        con.right     = "P"
        con.strike    = strike
        con.lastTradeDateOrContractMonth = expiration
        con.multiplier = "100"
        return con

    def _build_combo(
        self, short_con: "Contract", long_con: "Contract", quantity: int
    ) -> "Contract":
        combo  = Contract()
        combo.symbol   = "TQQQ"
        combo.secType  = "BAG"
        combo.exchange = "SMART"
        combo.currency = "USD"

        leg1 = ComboLeg()
        leg1.conId    = short_con.conId
        leg1.ratio    = 1
        leg1.action   = "SELL"
        leg1.exchange = "SMART"

        leg2 = ComboLeg()
        leg2.conId    = long_con.conId
        leg2.ratio    = 1
        leg2.action   = "BUY"
        leg2.exchange = "SMART"

        combo.comboLegs = [leg1, leg2]
        return combo

    @staticmethod
    def _limit_order(action: str, quantity: int, price: float, account: str) -> "Order":
        order          = Order()
        order.action   = action
        order.orderType = "LMT"
        order.totalQuantity = quantity
        order.lmtPrice = price
        order.account  = account
        order.tif      = "DAY"
        return order

    async def _qualify(self, contracts) -> None:
        if self.ib:
            await self.ib.qualifyContractsAsync(*contracts)

    async def _get_mid(self, contract) -> float:
        ticker = self.ib.reqMktData(contract, "", False, False)
        await asyncio.sleep(1.5)
        bid    = ticker.bid if ticker.bid and ticker.bid > 0 else 0.0
        ask    = ticker.ask if ticker.ask and ticker.ask > 0 else 0.0
        self.ib.cancelMktData(contract)
        return (bid + ask) / 2.0

    async def _walk_and_fill(
        self, trade: "Trade", initial_mid: float, direction: str
    ) -> OrderResult:
        """
        Attempts to fill a limit order, walking the price each interval.
        For credit orders: price decreases (give up a little credit).
        For debit orders: price increases (pay a little more).
        """
        current_price = initial_mid
        slippage      = 0.0

        for attempt in range(self.MAX_ADJUSTMENTS):
            await asyncio.sleep(self.ADJUST_INTERVAL)
            if trade.isDone():
                fill = trade.orderStatus.avgFillPrice
                logger.info(f"Order filled at ${fill:.2f} after {attempt} adjustments.")
                return OrderResult(success=True, fill_price=fill,
                                   order_id=trade.order.orderId)

            # Walk price towards more aggressive fill
            step          = self.PRICE_STEP if direction == "debit" else -self.PRICE_STEP
            current_price = round(current_price + step, 2)
            slippage     += self.PRICE_STEP

            if slippage > self.MAX_SLIPPAGE:
                logger.warning("Max slippage reached. Cancelling order.")
                self.ib.cancelOrder(trade.order)
                return OrderResult(
                    success=False,
                    fill_price=0.0,
                    message=f"MAX_SLIPPAGE exceeded after {attempt + 1} attempts"
                )

            trade.order.lmtPrice = current_price
            self.ib.placeOrder(trade.contract, trade.order)
            logger.debug(f"Price adjusted to ${current_price:.2f} (attempt {attempt + 1})")

        self.ib.cancelOrder(trade.order)
        return OrderResult(success=False, fill_price=0.0, message="TIMEOUT")
