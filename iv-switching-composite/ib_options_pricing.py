"""
IB Options Pricing Utilities
=============================
Fetches real option bid/ask from Interactive Brokers Gateway using ib_insync.

IB Gateway is available on EC2 at port 4004 (Docker container: ib-gateway-data).
Locally (dev) it runs on port 7497 (TWS).

Usage:
    from ib_options_pricing import get_option_spread_quote
    quote = get_option_spread_quote("QQQ", 622, 643, "260515", "C")
    if quote:
        print(f"Net credit: ${quote.net_credit}")
"""

import logging
import os
from typing import Optional, Tuple
from dataclasses import dataclass

log = logging.getLogger("ib_options_pricing")

# IB Gateway connection — EC2 Docker runs on 4004, local TWS on 7497
IB_HOST     = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT     = int(os.getenv("IB_PORT", "4004"))
IB_CLIENT   = int(os.getenv("IB_CLIENT_ID_OPTIONS", "250"))

# ── Result dataclass ──────────────────────────────────────────────────────────
@dataclass
class SpreadQuote:
    underlying:   str
    short_strike: int
    long_strike:  int
    expiry_str:   str    # YYMMDD
    opt_type:     str    # "C" or "P"
    short_bid:    float = 0.0
    short_ask:    float = 0.0
    long_bid:     float = 0.0
    long_ask:     float = 0.0

    @property
    def short_mid(self) -> float:
        return round((self.short_bid + self.short_ask) / 2, 2) if self.short_ask > 0 else 0.0

    @property
    def long_mid(self) -> float:
        return round((self.long_bid + self.long_ask) / 2, 2) if self.long_ask > 0 else 0.0

    @property
    def net_credit(self) -> float:
        """Credit spreads: short_mid − long_mid (positive = credit received)."""
        return round(self.short_mid - self.long_mid, 2)

    @property
    def net_debit(self) -> float:
        """Debit spreads: long_mid − short_mid (positive = debit paid)."""
        return round(self.long_mid - self.short_mid, 2)


# ── ib_insync helper ──────────────────────────────────────────────────────────
def _get_option_tickers(
    underlying: str,
    strikes: list,
    expiry_str: str,   # YYMMDD → convert to YYYYMMDD
    right: str,
) -> dict:
    """
    Connect to IB Gateway, request snapshot tickers for each strike,
    return {strike: {"bid": float, "ask": float}}.
    """
    try:
        from ib_insync import IB, Option
    except ImportError:
        log.warning("ib_insync not installed — IB option pricing unavailable, using B-S fallback")
        return {}

    ib = IB()
    result = {}
    expiry_full = f"20{expiry_str}"   # YYMMDD → YYYYMMDD

    try:
        log.info(f"Connecting to IB Gateway at {IB_HOST}:{IB_PORT} (clientId={IB_CLIENT})...")
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT, timeout=5)

        contracts = []
        for strike in strikes:
            opt = Option(
                symbol=underlying,
                lastTradeDateOrContractMonth=expiry_full,
                strike=float(strike),
                right=right,
                exchange="SMART",
                currency="USD",
            )
            contracts.append(opt)

        # Qualify contracts (fills in conId etc.)
        qualified = ib.qualifyContracts(*contracts)
        if not qualified:
            log.warning(f"IB: no qualified contracts for {underlying} {expiry_str} {right}")
            return {}

        # Request snapshot tickers
        tickers = ib.reqTickers(*qualified)

        for ticker in tickers:
            strike = int(ticker.contract.strike)
            bid = ticker.bid if ticker.bid and ticker.bid > 0 else 0.0
            ask = ticker.ask if ticker.ask and ticker.ask > 0 else 0.0
            result[strike] = {"bid": bid, "ask": ask}
            log.debug(f"IB tick: {underlying} {strike}{right} bid={bid} ask={ask}")

    except Exception as e:
        log.warning(f"IB option data error: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()

    return result


# ── Public API ────────────────────────────────────────────────────────────────
def get_option_spread_quote(
    underlying: str,
    short_strike: int,
    long_strike: int,
    expiry_str: str,      # YYMMDD e.g. "260515"
    opt_type: str = "C",  # "C" or "P"
) -> Optional[SpreadQuote]:
    """
    Fetch real IB bid/ask for both legs of a spread.
    Returns SpreadQuote or None if IB unavailable/no data.
    """
    tickers = _get_option_tickers(
        underlying, [short_strike, long_strike], expiry_str, opt_type
    )
    if not tickers:
        return None

    short_data = tickers.get(short_strike, {})
    long_data  = tickers.get(long_strike,  {})

    quote = SpreadQuote(
        underlying=underlying,
        short_strike=short_strike,
        long_strike=long_strike,
        expiry_str=expiry_str,
        opt_type=opt_type,
        short_bid=short_data.get("bid", 0.0),
        short_ask=short_data.get("ask", 0.0),
        long_bid=long_data.get("bid", 0.0),
        long_ask=long_data.get("ask", 0.0),
    )

    if quote.short_mid > 0 or quote.long_mid > 0:
        log.info(
            f"IB spread quote {underlying} {short_strike}/{long_strike} {opt_type} "
            f"exp={expiry_str}: short_mid={quote.short_mid}, long_mid={quote.long_mid}, "
            f"net_credit={quote.net_credit}"
        )
        return quote

    log.debug("IB returned zero prices for both legs — falling back")
    return None


def get_single_option_quote(
    underlying: str,
    strike: int,
    expiry_str: str,
    opt_type: str = "P",
) -> Optional[Tuple[float, float]]:
    """Returns (bid, ask) for a single option, or None."""
    tickers = _get_option_tickers(underlying, [strike], expiry_str, opt_type)
    if not tickers:
        return None
    data = tickers.get(strike, {})
    bid, ask = data.get("bid", 0.0), data.get("ask", 0.0)
    return (bid, ask) if ask > 0 else None


def get_live_spot_prices(symbols: list) -> dict:
    """
    Fetch current live (or delayed) prices for multiple equities in ONE IB connection.
    Returns {symbol: price} for any symbols with valid data.

    Uses delayed market data (type 4 = delayed frozen, requires no live subscription).
    Runs in a daemon thread with an asyncio event loop (required by ib_insync).
    Hard 10s timeout prevents blocking the signal generator.
    """
    try:
        from ib_insync import IB, Stock
    except ImportError:
        log.warning("ib_insync not installed — live spot prices unavailable")
        return {}

    result = {}

    def _fetch():
        # ib_insync requires an asyncio event loop in the calling thread.
        # Simply create and set one — do NOT call util.startLoop() which blocks forever.
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        ib = IB()
        try:
            ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT + 1, timeout=5)
            # Delayed frozen data — works without live market data subscription
            ib.reqMarketDataType(4)  # 1=live, 2=frozen, 3=delayed, 4=delayed frozen
            contracts = [Stock(sym, "SMART", "USD") for sym in symbols]
            qualified = ib.qualifyContracts(*contracts)
            if not qualified:
                log.warning(f"IB: no qualified contracts for {symbols}")
                return
            # Non-blocking stream then sleep 4s for data to arrive
            tickers = [ib.reqMktData(c, '', False, False) for c in qualified]
            ib.sleep(4)
            for ticker in tickers:
                sym = ticker.contract.symbol
                price = None
                for val in (ticker.last, ticker.close, ticker.marketPrice()):
                    if val and not isinstance(val, float) or (isinstance(val, float) and val > 0):
                        try:
                            p = float(val)
                            if p > 0:
                                price = p
                                break
                        except (TypeError, ValueError):
                            pass
                if price:
                    result[sym] = price
                    log.info(f"IB spot {sym}: ${price:.2f}")
                else:
                    log.warning(f"IB: no price for {sym} (last={ticker.last} close={ticker.close})")
                ib.cancelMktData(ticker.contract)
        except Exception as e:
            log.warning(f"IB batch spot price error: {e}")
        finally:
            if ib.isConnected():
                ib.disconnect()

    import threading
    t = threading.Thread(target=_fetch, daemon=True)
    t.start()
    t.join(timeout=12)
    if t.is_alive():
        log.warning("IB spot price fetch timed out after 12s")

    return result


# Keep single-symbol version for backwards compatibility
def get_live_spot_price(symbol: str) -> 'Optional[float]':
    prices = get_live_spot_prices([symbol])
    return prices.get(symbol)


# ── Quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Testing IB option pricing on {IB_HOST}:{IB_PORT}...")
    quote = get_option_spread_quote("QQQ", 622, 643, "260515", "C")
    if quote:
        print(f"Short: bid={quote.short_bid} ask={quote.short_ask} mid={quote.short_mid}")
        print(f"Long:  bid={quote.long_bid} ask={quote.long_ask} mid={quote.long_mid}")
        print(f"Net credit: ${quote.net_credit}")
    else:
        print("IB not available or no data returned")
