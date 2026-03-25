"""
IB Options Pricing Utilities
=============================
Fetches real option chain data from Interactive Brokers gateway.

Usage (falls back to None if IB not available):
    from ib_options_pricing import get_option_spread_quote
    result = get_option_spread_quote("QQQ", short_strike=622, long_strike=643, expiry_str="260515", opt_type="C")
    if result:
        net_credit = result["net_credit"]
        short_strike, long_strike = result["short_strike"], result["long_strike"]

Requires:
    pip install ibapi  (Interactive Brokers Python API)
    IB Gateway or TWS running locally on port 7497
"""

import logging
import threading
import time
import os
from typing import Optional, Dict, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "7497"))
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID_OPTIONS", "250"))  # Separate client ID from screener

# ── Result dataclass ──────────────────────────────────────────────────────────
@dataclass
class SpreadQuote:
    underlying: str
    short_strike: int
    long_strike: int
    expiry_str: str           # YYMMDD
    opt_type: str             # "C" or "P"
    short_bid: float = 0.0
    short_ask: float = 0.0
    long_bid: float = 0.0
    long_ask: float = 0.0

    @property
    def short_mid(self) -> float:
        return round((self.short_bid + self.short_ask) / 2, 2) if self.short_ask > 0 else 0.0

    @property
    def long_mid(self) -> float:
        return round((self.long_bid + self.long_ask) / 2, 2) if self.long_ask > 0 else 0.0

    @property
    def net_credit(self) -> float:
        """For a credit spread: short_mid - long_mid (positive = credit received)."""
        return round(self.short_mid - self.long_mid, 2)

    @property
    def net_debit(self) -> float:
        """For a debit spread: long_mid - short_mid (positive = debit paid)."""
        return round(self.long_mid - self.short_mid, 2)


# ── IB Quote Fetcher ──────────────────────────────────────────────────────────
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract
    _IBAPI_AVAILABLE = True
except ImportError:
    _IBAPI_AVAILABLE = False
    logger.warning("ibapi not installed — IB option pricing unavailable, using B-S fallback")


class _IBOptionFetcher(EClient if _IBAPI_AVAILABLE else object,
                       EWrapper if _IBAPI_AVAILABLE else object):
    """Thin IB wrapper: connects, fetches option bid/ask for 1-2 contracts, disconnects."""

    def __init__(self, host, port, client_id):
        if _IBAPI_AVAILABLE:
            EClient.__init__(self, self)
            EWrapper.__init__(self)
        self.host = host
        self.port = port
        self.client_id = client_id
        self._lock = threading.Lock()
        self._prices: Dict[int, Dict] = {}   # reqId → {bid, ask}
        self._done: Dict[int, bool] = {}
        self._next_req_id = 8000
        self._connected = False

    def connect_sync(self, timeout: float = 5.0) -> bool:
        if not _IBAPI_AVAILABLE:
            return False
        try:
            self.connect(self.host, self.port, self.client_id)
            t = threading.Thread(target=self.run, daemon=True)
            t.start()
            deadline = time.time() + timeout
            while not self._connected and time.time() < deadline:
                time.sleep(0.1)
            return self._connected
        except Exception as e:
            logger.debug(f"IB connect failed: {e}")
            return False

    def nextValidId(self, orderId: int):
        self._connected = True

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib):
        if price <= 0:
            return
        with self._lock:
            if reqId not in self._prices:
                self._prices[reqId] = {}
            if tickType == 1:   # Bid
                self._prices[reqId]["bid"] = price
            elif tickType == 2: # Ask
                self._prices[reqId]["ask"] = price

    def tickSnapshotEnd(self, reqId: int):
        with self._lock:
            self._done[reqId] = True

    def error(self, reqId, errorCode, errorString, *args):
        if errorCode not in (2104, 2106, 2158, 200):
            logger.debug(f"IB error {errorCode}: {errorString}")
        if errorCode in (200, 354):   # No security definition / No data
            with self._lock:
                self._done[reqId] = True

    def _make_option_contract(self, symbol: str, expiry_str: str,
                               strike: int, right: str) -> "Contract":
        c = Contract()
        c.symbol = symbol.strip()
        c.secType = "OPT"
        c.exchange = "SMART"
        c.currency = "USD"
        c.lastTradeDateOrContractMonth = f"20{expiry_str}"   # YYYYMMDD
        c.strike = float(strike)
        c.right = right          # "C" or "P"
        c.multiplier = "100"
        return c

    def _request_snapshot(self, contract) -> int:
        req_id = self._next_req_id
        self._next_req_id += 1
        with self._lock:
            self._prices[req_id] = {}
            self._done[req_id] = False
        self.reqMktData(req_id, contract, "", True, False, [])   # snapshot=True
        return req_id

    def _wait_for_snapshot(self, req_id: int, timeout: float = 4.0) -> Dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._done.get(req_id):
                    return dict(self._prices.get(req_id, {}))
            time.sleep(0.1)
        logger.debug(f"IB snapshot timeout for reqId={req_id}")
        return dict(self._prices.get(req_id, {}))

    def get_spread_quote(self, symbol: str, expiry_str: str,
                         short_strike: int, long_strike: int,
                         opt_type: str = "C") -> Optional[SpreadQuote]:
        """Fetch bid/ask for both legs of a spread, return SpreadQuote."""
        quote = SpreadQuote(
            underlying=symbol,
            short_strike=short_strike,
            long_strike=long_strike,
            expiry_str=expiry_str,
            opt_type=opt_type,
        )
        # Short leg
        sc = self._make_option_contract(symbol, expiry_str, short_strike, opt_type)
        rid1 = self._request_snapshot(sc)
        p1 = self._wait_for_snapshot(rid1)
        quote.short_bid = p1.get("bid", 0.0)
        quote.short_ask = p1.get("ask", 0.0)

        # Long leg
        lc = self._make_option_contract(symbol, expiry_str, long_strike, opt_type)
        rid2 = self._request_snapshot(lc)
        p2 = self._wait_for_snapshot(rid2)
        quote.long_bid = p2.get("bid", 0.0)
        quote.long_ask = p2.get("ask", 0.0)

        if quote.short_mid > 0 or quote.long_mid > 0:
            return quote
        logger.debug("IB returned zero prices for both legs — falling back to B-S")
        return None


# ── Public API ────────────────────────────────────────────────────────────────
_fetcher_cache: Optional[_IBOptionFetcher] = None

def _get_fetcher() -> Optional["_IBOptionFetcher"]:
    global _fetcher_cache
    if not _IBAPI_AVAILABLE:
        return None
    if _fetcher_cache is not None and _fetcher_cache._connected:
        return _fetcher_cache
    fetcher = _IBOptionFetcher(IB_HOST, IB_PORT, IB_CLIENT_ID)
    if fetcher.connect_sync():
        _fetcher_cache = fetcher
        logger.info(f"✅ IB option pricer connected at {IB_HOST}:{IB_PORT}")
        return fetcher
    return None


def get_option_spread_quote(
    symbol: str,
    short_strike: int,
    long_strike: int,
    expiry_str: str,      # YYMMDD, e.g. "260515"
    opt_type: str = "C",  # "C" or "P"
) -> Optional[SpreadQuote]:
    """
    Fetch real IB option spread prices.

    Returns SpreadQuote (with .net_credit / .net_debit) or None if IB unavailable.
    """
    fetcher = _get_fetcher()
    if fetcher is None:
        return None
    try:
        return fetcher.get_spread_quote(symbol, expiry_str, short_strike, long_strike, opt_type)
    except Exception as e:
        logger.warning(f"IB option quote error: {e}")
        return None


def get_single_option_quote(
    symbol: str,
    strike: int,
    expiry_str: str,
    opt_type: str = "P",
) -> Optional[Tuple[float, float]]:
    """
    Returns (bid, ask) for a single option contract, or None.
    """
    fetcher = _get_fetcher()
    if fetcher is None:
        return None
    try:
        c = fetcher._make_option_contract(symbol, expiry_str, strike, opt_type)
        rid = fetcher._request_snapshot(c)
        p = fetcher._wait_for_snapshot(rid)
        bid = p.get("bid", 0.0)
        ask = p.get("ask", 0.0)
        if ask > 0:
            return bid, ask
    except Exception as e:
        logger.warning(f"IB single option quote error: {e}")
    return None


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing IB option pricing...")
    quote = get_option_spread_quote("QQQ", 622, 643, "260515", "C")
    if quote:
        print(f"Short leg: bid={quote.short_bid} ask={quote.short_ask} mid={quote.short_mid}")
        print(f"Long leg:  bid={quote.long_bid} ask={quote.long_ask} mid={quote.long_mid}")
        print(f"Net credit: ${quote.net_credit}")
    else:
        print("IB not available or no data returned")
