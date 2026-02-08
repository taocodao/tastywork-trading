"""
Tastytrade Data Provider - Bridge for Scanner
=============================================

Provides data feed interface for the CalendarSpreadScanner using Tastytrade API.
"""

import logging
from datetime import date
from typing import List, Optional

from tastytrade_client import TastytradeClient, OptionData

logger = logging.getLogger(__name__)


class TastytradeDataProvider:
    """
    Data provider that wraps TastytradeClient for use with CalendarSpreadScanner.
    
    Converts between Tastytrade API data and the OptionQuote format
    expected by the scanner.
    """
    
    def __init__(self, client: TastytradeClient = None):
        """
        Initialize data provider.
        
        Args:
            client: TastytradeClient instance (creates new one if not provided)
        """
        self.client = client or TastytradeClient()
        self._connected = False
        self._price_cache = {}
    
    def connect(self) -> bool:
        """Connect to Tastytrade API."""
        if not self._connected:
            self.client.connect()
            self._connected = True
        return self._connected
    
    def disconnect(self):
        """Disconnect from Tastytrade API."""
        if self._connected:
            self.client.disconnect()
            self._connected = False
    
    def get_price(self, symbol: str) -> float:
        """
        Get current stock price.
        
        Args:
            symbol: Stock symbol (e.g., 'SPY')
            
        Returns:
            Current mid price
        """
        if not self._connected:
            self.connect()
        
        # Check cache first
        if symbol in self._price_cache:
            return self._price_cache[symbol]
        
        price = self.client.get_stock_price(symbol)
        self._price_cache[symbol] = price
        return price
    
    def get_options(
        self,
        symbol: str,
        expiry: date,
        option_type: str = "call"
    ) -> List:
        """
        Get options for a symbol and expiry.
        
        Args:
            symbol: Underlying symbol
            expiry: Expiration date
            option_type: 'call' or 'put'
            
        Returns:
            List of OptionQuote objects (scanner format)
        """
        if not self._connected:
            self.connect()
        
        # Import here to avoid circular import
        from scanner import OptionQuote
        
        opt_type = 'C' if option_type.lower() == 'call' else 'P'
        options = self.client.get_options_for_expiry(symbol, expiry, opt_type)
        
        # Convert OptionData to OptionQuote format
        quotes = []
        for opt in options:
            try:
                quote = OptionQuote(
                    symbol=opt.symbol,
                    strike=float(opt.strike),
                    expiry=opt.expiry,
                    bid=opt.bid,
                    ask=opt.ask,
                    last=opt.mid,
                    volume=opt.volume,
                    open_interest=opt.open_interest,
                    iv=opt.iv or 0.20  # Default IV if not available
                )
                quotes.append(quote)
            except Exception as e:
                logger.debug(f"Skipping option {opt.symbol}: {e}")
                continue
        
        return quotes
    
    def get_vix(self) -> float:
        """
        Get current VIX level.
        
        Returns:
            VIX value
        """
        if not self._connected:
            self.connect()
        
        try:
            return self.client.get_stock_price('VIX')
        except Exception as e:
            logger.warning(f"Could not fetch VIX: {e}")
            return 0.0  # Return 0.0 to indicate failure, upstream should handle this


def create_tastytrade_scanner():
    """
    Create a CalendarSpreadScanner configured to use Tastytrade data.
    
    Returns:
        CalendarSpreadScanner with Tastytrade data provider
    """
    from scanner import CalendarSpreadScanner
    
    provider = TastytradeDataProvider()
    provider.connect()
    
    return CalendarSpreadScanner(data_provider=provider)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Tastytrade Data Provider")
    print("=" * 50)
    
    provider = TastytradeDataProvider()
    
    try:
        provider.connect()
        
        # Test price fetching
        for symbol in ['SPY', 'IWM', 'QQQ']:
            price = provider.get_price(symbol)
            print(f"{symbol}: ${price:.2f}")
        
        # Test VIX
        vix = provider.get_vix()
        print(f"VIX: {vix:.2f}")
        
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure you have set up your .env file with Tastytrade credentials.")
    finally:
        provider.disconnect()
