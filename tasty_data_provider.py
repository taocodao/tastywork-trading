"""
Tastytrade Data Provider
========================
Adapts TastytradeClient to the data provider interface required by CalendarSpreadScanner.
"""

import logging
from datetime import date
from typing import List, Optional
from scanner import OptionQuote
from tastytrade_client import TastytradeClient

logger = logging.getLogger(__name__)

class TastytradeDataProvider:
    def __init__(self, client: Optional[TastytradeClient] = None):
        self.client = client or TastytradeClient()
        
    def connect(self) -> bool:
        """Connect to Tastytrade API."""
        if self.client.is_connected:
            return True
        return self.client.connect()
        
    def get_price(self, symbol: str) -> float:
        """Get current stock price."""
        try:
            return self.client.get_stock_price(symbol)
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return 0.0
            
    def get_options(self, symbol: str, expiry: date, option_type: str = "call") -> List[OptionQuote]:
        """Get option chain converted to scanner's OptionQuote format."""
        try:
            # TastytradeClient uses 'C' or 'P'
            tt_type = 'C' if option_type.lower() == 'call' else 'P'
            
            # CRITICAL FIX: Force token refresh before option chain calls
            # OAuth access tokens expire after 15 minutes
            if hasattr(self.client, '_session') and self.client._session:
                try:
                    self.client._session.refresh()
                    logger.debug("OAuth session refreshed successfully")
                except Exception as e:
                    logger.warning(f"Session refresh failed: {e}")
            
            # 1. Get all expiries first to find the closest match
            # We can't trust the scanner's calculated date to exist exactly
            chain_dates = self.client.get_option_chain(symbol).keys()
            
            # If empty, try direct REST API as fallback
            if not chain_dates:
                logger.warning(f"Empty chain from SDK for {symbol}, trying direct REST API...")
                try:
                    response = self.client._session.get(f'/option-chains/{symbol}/nested')
                    if response and 'data' in response:
                        items = response['data'].get('items', [])
                        if items:
                            expirations = items[0].get('expirations', [])
                            logger.info(f"Direct API found {len(expirations)} expirations for {symbol}")
                            # Extract dates from direct response
                            from datetime import datetime
                            chain_dates = [datetime.strptime(e['expiration-date'], '%Y-%m-%d').date() 
                                           for e in expirations]
                except Exception as e:
                    logger.error(f"Direct REST API fallback failed: {e}")
            
            if not chain_dates:
                logger.warning(f"No option chain found for {symbol}")
                return []
                
            # Find closest available expiry
            closest_expiry = min(chain_dates, key=lambda d: abs((d - expiry).days))
            
            # Log adjustment if meaningful difference (>1 day)
            if abs((closest_expiry - expiry).days) > 1:
                logger.info(f"Adjusted expiry for {symbol}: Requested {expiry} -> Using {closest_expiry}")
            
            tt_options = self.client.get_options_for_expiry(symbol, closest_expiry, tt_type)
            
            quotes = []
            for opt in tt_options:
                # Convert Tastytrade OptionData to Scanner OptionQuote
                quote = OptionQuote(
                    symbol=symbol,
                    strike=float(opt.strike),
                    expiry=expiry,
                    bid=opt.bid,
                    ask=opt.ask,
                    last=opt.mid, # Use mid as proxy for last if not available
                    volume=opt.volume,
                    open_interest=opt.open_interest,
                    iv=opt.iv or 0.0
                )
                quotes.append(quote)
                
            return quotes
            
        except Exception as e:
            logger.error(f"Error getting options for {symbol} {expiry}: {e}")
            return []
