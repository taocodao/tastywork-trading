"""
IBKR Client — thin wrapper around ib_async for TurboCore Pro paper trading.

Handles: connection management, historical bar fetching, position/NAV queries,
and order submission. Keeps the IBKR layer isolated from strategy logic.
"""
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("turbocore.live.ibkr")

try:
    from ib_async import IB, Stock, BarData, Order, MarketOrder, LimitOrder, PortfolioItem
    from ib_async.util import df
    HAS_IB_ASYNC = True
except ImportError:
    HAS_IB_ASYNC = False
    log.warning("ib_async not installed — running in offline/dry-run mode only")


@dataclass
class Position:
    symbol: str
    shares: float
    avg_cost: float
    market_price: float
    market_value: float


class IBKRClient:
    """Thin IBKR Gateway connection wrapper."""

    def __init__(self, host: str = "127.0.0.1", port: int = 4002,
                 client_id: int = 12, timeout: int = 30):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.timeout = timeout
        self.ib: Optional[IB] = None

    def connect(self) -> bool:
        if not HAS_IB_ASYNC:
            log.warning("ib_async not available — cannot connect to IBKR")
            return False
        try:
            self.ib = IB()
            self.ib.connect(self.host, self.port, clientId=self.client_id,
                            timeout=self.timeout)
            log.info(f"Connected to IBKR Gateway at {self.host}:{self.port} "
                     f"(clientId={self.client_id})")
            return True
        except Exception as e:
            log.error(f"IBKR connection failed: {e}")
            return False

    def disconnect(self):
        if self.ib:
            self.ib.disconnect()
            log.info("Disconnected from IBKR")

    def get_account_summary(self) -> dict:
        """Get key account metrics: NAV, cash, positions value."""
        if not self.ib:
            return {}
        acct = self.ib.managedAccounts()[0] if self.ib.managedAccounts() else ""
        summary = self.ib.accountSummary(acct)
        return {s.tag: s.value for s in summary}

    def get_nav(self) -> float:
        """Get net liquidation value."""
        summary = self.get_account_summary()
        return float(summary.get("NetLiquidation", 0))

    def get_positions(self) -> dict[str, Position]:
        """Get current positions keyed by symbol."""
        if not self.ib:
            return {}
        portfolio = self.ib.portfolio()
        positions = {}
        for p in portfolio:
            if p.position != 0:
                positions[p.contract.symbol] = Position(
                    symbol=p.contract.symbol,
                    shares=p.position,
                    avg_cost=p.averageCost,
                    market_price=p.marketPrice,
                    market_value=p.marketValue,
                )
        return positions

    def fetch_hourly_bars(self, symbol: str, lookback_bars: int = 1500) -> list:
        """Fetch historical hourly bars for a symbol."""
        if not self.ib:
            return []
        contract = Stock(symbol, "SMART", "USD")
        self.ib.qualifyContracts(contract)
        # Convert lookback_bars (hourly) to IBKR duration string
        # ~7 bars/day, ~252 trading days/year. 1500 bars ≈ 214 trading days ≈ 10 months
        lookback_days = max(int(lookback_bars / 7 * 1.5), 30)  # add 50% buffer for holidays
        if lookback_days > 365:
            duration_str = f"2 Y"
        else:
            duration_str = f"{lookback_days} D"
        bars = self.ib.reqHistoricalData(
            contract, endDateTime="",
            durationStr=duration_str,
            barSizeSetting="1 hour",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        log.info(f"Fetched {len(bars)} hourly bars for {symbol}")
        return bars

    def fetch_hourly_bars_df(self, symbol: str, lookback_bars: int = 1500):
        """Fetch hourly bars as a pandas DataFrame."""
        import pandas as pd
        bars = self.fetch_hourly_bars(symbol, lookback_bars)
        if not bars:
            return pd.DataFrame()
        df_data = []
        for b in bars:
            df_data.append({
                "datetime": b.date,
                "open": b.open, "high": b.high,
                "low": b.low, "close": b.close,
                "volume": b.volume,
            })
        return pd.DataFrame(df_data).set_index("datetime")

    def submit_order(self, symbol: str, action: str, quantity: float,
                     order_type: str = "MKT", limit_price: float = None,
                     dry_run: bool = True) -> dict:
        """Submit an order (or log it if dry_run)."""
        order_info = {
            "symbol": symbol, "action": action, "quantity": quantity,
            "order_type": order_type, "limit_price": limit_price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
        }
        if dry_run:
            log.info(f"[DRY-RUN] Would submit: {action} {quantity} {symbol} "
                     f"({order_type}" +
                     (f" @ {limit_price}" if limit_price else "") + ")")
            order_info["status"] = "DRY_RUN"
            return order_info

        if not self.ib:
            log.error("No IBKR connection — cannot submit order")
            order_info["status"] = "ERROR_NO_CONNECTION"
            return order_info

        contract = Stock(symbol, "SMART", "USD")
        self.ib.qualifyContracts(contract)

        if order_type == "MKT":
            order = MarketOrder(action, quantity)
        elif order_type == "LMT" and limit_price:
            order = LimitOrder(action, quantity, limit_price)
        else:
            log.error(f"Unsupported order type: {order_type}")
            order_info["status"] = "ERROR_BAD_ORDER_TYPE"
            return order_info

        trade = self.ib.placeOrder(contract, order)
        log.info(f"Submitted: {action} {quantity} {symbol} ({order_type})")
        order_info["status"] = "SUBMITTED"
        order_info["order_id"] = trade.order.orderId
        return order_info
