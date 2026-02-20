"""
IB Market Data Hub
==================
Centralized singleton service for IB Gateway connections.
Implements pub/sub pattern for shared market data access.

Architecture:
- Data Client (ID 3000): Shared market data for all products
- Order Client (ID 3001): Shared order execution for all strategies

All strategies (theta, calendar, scanner) share these two connections
to avoid client ID conflicts (Error 326).
"""

import logging
import threading
import time
from typing import Dict, Callable, Optional, Set, Tuple
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Module-level singleton
_hub_instance = None
_hub_lock = threading.Lock()


def get_hub() -> "IBMarketDataHub":
    """Get singleton hub instance."""
    global _hub_instance
    if _hub_instance is None:
        with _hub_lock:
            if _hub_instance is None:
                _hub_instance = IBMarketDataHub()
    return _hub_instance


@dataclass
class PriceCache:
    """Cached price data with timestamp."""
    price: float
    bid: float = 0.0
    ask: float = 0.0
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def age_seconds(self) -> float:
        return (datetime.now() - self.timestamp).total_seconds()


class IBMarketDataHub:
    """
    Singleton hub for IB Gateway connections.
    
    Features:
    - Single market data connection shared by all products
    - Single order connection shared by all strategies
    - Pub/sub for real-time market data
    - Price caching to reduce duplicate requests
    - Automatic reconnection
    """
    
    # Client ID allocation (only 2 needed)
    DATA_CLIENT_ID = 3000
    ORDER_CLIENT_ID = 3001
    
    def __init__(self):
        """Initialize hub (called once via get_hub())."""
        import config
        self.host = getattr(config, 'IB_HOST', '127.0.0.1')
        self.port = getattr(config, 'IB_PORT', 4004)
        
        # IB connections (lazy initialized)
        self._data_ib = None
        self._order_ib = None
        self._data_connected = False
        self._order_connected = False
        
        # Subscriptions: symbol -> set of callbacks
        self._subscriptions: Dict[str, Set[Callable]] = {}
        
        # Price cache: symbol -> PriceCache
        self._price_cache: Dict[str, PriceCache] = {}
        
        # Active tickers for streaming
        self._active_tickers: Dict[str, object] = {}
        
        # Thread lock for connection safety
        self._lock = threading.Lock()
        
        # Connection retry settings
        self.max_retries = 3
        self.retry_delay = 2  # seconds
        
        logger.info(f"IB Market Data Hub initialized (host={self.host}, port={self.port})")
    
    # ========== Connection Management ==========
    
    def connect_data(self, timeout: int = 10) -> bool:
        """
        Connect market data client (ID 3000).
        Shared by all products for prices, options, Greeks.
        """
        with self._lock:
            if self._data_ib is None:
                from ib_insync import IB
                self._data_ib = IB()
            
            if self._data_ib.isConnected():
                return True
            
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"Hub: Connecting data client (ID {self.DATA_CLIENT_ID}), attempt {attempt + 1}...")
                    self._data_ib.connect(
                        self.host, 
                        self.port, 
                        clientId=self.DATA_CLIENT_ID,
                        timeout=timeout
                    )
                    # Request live market data (user has active subscription)
                    self._data_ib.reqMarketDataType(1)
                    self._data_connected = True
                    logger.info("Hub: Data connection established")
                    return True
                except Exception as e:
                    logger.warning(f"Hub: Data connection attempt {attempt + 1} failed: {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
            
            logger.error("Hub: Data connection failed after all retries")
            self._data_connected = False
            return False
    
    def connect_orders(self, timeout: int = 10) -> bool:
        """
        Connect order client (ID 3001).
        Shared by ALL strategies for order submission.
        """
        with self._lock:
            if self._order_ib is None:
                from ib_insync import IB
                self._order_ib = IB()
            
            if self._order_ib.isConnected():
                return True
            
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"Hub: Connecting order client (ID {self.ORDER_CLIENT_ID}), attempt {attempt + 1}...")
                    self._order_ib.connect(
                        self.host, 
                        self.port, 
                        clientId=self.ORDER_CLIENT_ID,
                        timeout=timeout
                    )
                    self._order_connected = True
                    logger.info("Hub: Order connection established")
                    return True
                except Exception as e:
                    logger.warning(f"Hub: Order connection attempt {attempt + 1} failed: {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay)
            
            logger.error("Hub: Order connection failed after all retries")
            self._order_connected = False
            return False
    
    def connect_all(self, timeout: int = 10) -> bool:
        """Connect both data and order clients."""
        data_ok = self.connect_data(timeout)
        order_ok = self.connect_orders(timeout)
        return data_ok and order_ok
    
    @property
    def data_client(self):
        """Get data IB client, connecting if needed."""
        if not self._data_connected or (self._data_ib and not self._data_ib.isConnected()):
            self.connect_data()
        return self._data_ib
    
    @property
    def order_client(self):
        """Get order IB client, connecting if needed."""
        if not self._order_connected or (self._order_ib and not self._order_ib.isConnected()):
            self.connect_orders()
        return self._order_ib
    
    def disconnect_all(self):
        """Disconnect all connections."""
        with self._lock:
            if self._data_ib and self._data_ib.isConnected():
                self._data_ib.disconnect()
                self._data_connected = False
                logger.info("Hub: Data connection closed")
            
            if self._order_ib and self._order_ib.isConnected():
                self._order_ib.disconnect()
                self._order_connected = False
                logger.info("Hub: Order connection closed")
    
    def is_connected(self) -> Tuple[bool, bool]:
        """Check connection status. Returns (data_connected, order_connected)."""
        data_ok = self._data_ib is not None and self._data_ib.isConnected()
        order_ok = self._order_ib is not None and self._order_ib.isConnected()
        return (data_ok, order_ok)
    
    # ========== Market Data ==========
    
    def get_price(self, symbol: str, max_age_seconds: int = 60) -> float:
        """
        Get stock price, using cache if fresh enough.
        
        Args:
            symbol: Stock symbol
            max_age_seconds: Max cache age before refetch
            
        Returns:
            Current price or 0.0 if unavailable
        """
        # Check cache
        if symbol in self._price_cache:
            cached = self._price_cache[symbol]
            if cached.age_seconds() < max_age_seconds:
                return cached.price
        
        # Fetch fresh
        if not self.data_client:
            return 0.0
        
        try:
            from ib_insync import Stock
            
            contract = Stock(symbol, 'SMART', 'USD')
            self.data_client.qualifyContracts(contract)
            ticker = self.data_client.reqMktData(contract, '', False, False)
            
            # Wait for data
            start = datetime.now()
            while (datetime.now() - start).total_seconds() < 2:
                self.data_client.sleep(0.1)
                price = ticker.last or ticker.close
                if price and price > 0:
                    self._price_cache[symbol] = PriceCache(
                        price=price,
                        bid=ticker.bid or 0,
                        ask=ticker.ask or 0
                    )
                    return price
            
            # Fallback to mid
            if ticker.bid and ticker.ask and ticker.bid > 0 and ticker.ask > 0:
                price = (ticker.bid + ticker.ask) / 2
                self._price_cache[symbol] = PriceCache(
                    price=price,
                    bid=ticker.bid,
                    ask=ticker.ask
                )
                return price
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Hub: Failed to get price for {symbol}: {e}")
            return 0.0
    
    def get_quote(self, symbol: str) -> Optional[PriceCache]:
        """Get full quote (bid/ask/last) for symbol."""
        self.get_price(symbol)  # Refresh cache
        return self._price_cache.get(symbol)
    
    # ========== Pub/Sub Subscriptions ==========
    
    def subscribe(self, symbol: str, callback: Callable[[str, float], None]):
        """
        Subscribe to real-time price updates for a symbol.
        
        Args:
            symbol: Stock symbol
            callback: Function called with (symbol, price) on updates
        """
        with self._lock:
            if symbol not in self._subscriptions:
                self._subscriptions[symbol] = set()
                self._start_streaming(symbol)
            self._subscriptions[symbol].add(callback)
            logger.debug(f"Hub: Added subscription for {symbol} (total: {len(self._subscriptions[symbol])})")
    
    def unsubscribe(self, symbol: str, callback: Callable = None):
        """
        Remove subscription for a symbol.
        
        Args:
            symbol: Stock symbol
            callback: Specific callback to remove, or None to remove all
        """
        with self._lock:
            if symbol in self._subscriptions:
                if callback:
                    self._subscriptions[symbol].discard(callback)
                    if not self._subscriptions[symbol]:
                        self._stop_streaming(symbol)
                        del self._subscriptions[symbol]
                else:
                    self._stop_streaming(symbol)
                    del self._subscriptions[symbol]
                logger.debug(f"Hub: Removed subscription for {symbol}")
    
    def _start_streaming(self, symbol: str):
        """Start streaming market data (internal)."""
        if not self.data_client or not self.data_client.isConnected():
            return
        
        try:
            from ib_insync import Stock
            
            contract = Stock(symbol, 'SMART', 'USD')
            self.data_client.qualifyContracts(contract)
            ticker = self.data_client.reqMktData(contract, '', False, False)
            self._active_tickers[symbol] = ticker
            
            logger.debug(f"Hub: Started streaming {symbol}")
        except Exception as e:
            logger.error(f"Hub: Failed to start streaming {symbol}: {e}")
    
    def _stop_streaming(self, symbol: str):
        """Stop streaming for symbol (internal)."""
        if symbol in self._active_tickers and self.data_client:
            try:
                ticker = self._active_tickers[symbol]
                self.data_client.cancelMktData(ticker.contract)
                del self._active_tickers[symbol]
                logger.debug(f"Hub: Stopped streaming {symbol}")
            except:
                pass
    
    def process_updates(self):
        """
        Process pending ticker updates and notify subscribers.
        Call this periodically in your main loop.
        """
        if not self.data_client or not self._active_tickers:
            return
        
        for symbol, ticker in self._active_tickers.items():
            price = ticker.last or ticker.close
            if not price and ticker.bid and ticker.ask:
                price = (ticker.bid + ticker.ask) / 2
            
            if price and price > 0:
                # Update cache
                old_price = self._price_cache.get(symbol, PriceCache(0)).price
                if abs(price - old_price) > 0.001:  # Price changed
                    self._price_cache[symbol] = PriceCache(
                        price=price,
                        bid=ticker.bid or 0,
                        ask=ticker.ask or 0
                    )
                    # Notify subscribers
                    for cb in self._subscriptions.get(symbol, set()):
                        try:
                            cb(symbol, price)
                        except Exception as e:
                            logger.error(f"Hub: Subscriber callback error: {e}")
    
    # ========== Order Execution ==========
    
    def place_order(self, contract, order, strategy: str = "unknown") -> Optional[object]:
        """
        Place an order using the shared order client.
        
        Args:
            contract: IB Contract object
            order: IB Order object
            strategy: Name of strategy placing order (for logging)
            
        Returns:
            Trade object if successful, None if failed
        """
        if not self.order_client:
            logger.error(f"Hub: Cannot place order - no order connection")
            return None
        
        try:
            trade = self.order_client.placeOrder(contract, order)
            logger.info(f"Hub: Order placed for {strategy} - {contract.symbol} {order.action} x{order.totalQuantity}")
            return trade
        except Exception as e:
            logger.error(f"Hub: Order placement failed: {e}")
            return None
    
    def get_positions(self) -> list:
        """Get all positions from order client."""
        if not self.order_client:
            return []
        
        try:
            return self.order_client.positions()
        except Exception as e:
            logger.error(f"Hub: Failed to get positions: {e}")
            return []
    
    def get_portfolio(self) -> list:
        """Get portfolio items from order client."""
        if not self.order_client:
            return []
        
        try:
            return self.order_client.portfolio()
        except Exception as e:
            logger.error(f"Hub: Failed to get portfolio: {e}")
            return []
    
    # ========== Status & Diagnostics ==========
    
    def status(self) -> dict:
        """Get hub status summary."""
        data_conn, order_conn = self.is_connected()
        return {
            "data_connected": data_conn,
            "order_connected": order_conn,
            "data_client_id": self.DATA_CLIENT_ID,
            "order_client_id": self.ORDER_CLIENT_ID,
            "cached_symbols": list(self._price_cache.keys()),
            "subscriptions": list(self._subscriptions.keys()),
            "active_streams": list(self._active_tickers.keys())
        }
    
    def __repr__(self):
        data_conn, order_conn = self.is_connected()
        return f"<IBMarketDataHub data={data_conn} order={order_conn}>"
