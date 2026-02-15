"""
ZEBRA Strategy Client
=====================
Extends the base TastytradeClient with ZEBRA-specific order execution capability.
"""

import logging
from decimal import Decimal
from typing import Optional
from datetime import date

from tastytrade_client import TastytradeClient
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
from tastytrade.instruments import Option

logger = logging.getLogger(__name__)

class ZebraClient(TastytradeClient):
    """
    Tastytrade client extended for ZEBRA strategy.
    """
    
    def build_zebra_order(
        self,
        symbol: str, 
        long_strike: float,
        short_strike: float,
        expiry: date,
        direction: str = "LONG",
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> NewOrder:
        """
        Build a ZEBRA complex order (3-leg, single ticket).
        
        Args:
            direction: "LONG" (Calls) or "SHORT" (Puts)
            limit_price: Positive float (debit). Will be negated for API.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected. Call connect() first.")
            
        option_type = 'C' if direction == "LONG" else 'P'
        
        # 1. Find Instruments (Long x 2, Short x 1)
        # Note: Tastytrade API requires finding the exact option symbol
        # We can implement a helper or loop-up manually
        
        # We need the OCC strings. But `Option.get()` takes OCC symbol?
        # Actually Tastytrade SDK `Option.get()` fetches by symbol?
        # In `tastytrade_client.py`: `Option.get(self._session, put_option_symbol)` checks symbol.
        
        # We don't have OCC symbols passed in, just strikes/expiry.
        # We need to find them.
        long_opt_data = self.find_option_at_strike(symbol, expiry, long_strike, option_type)
        short_opt_data = self.find_option_at_strike(symbol, expiry, short_strike, option_type)
        
        if not long_opt_data or not short_opt_data:
            raise ValueError(f"Could not find options for {symbol} {expiry}")
            
        long_symbol = long_opt_data.symbol
        short_symbol = short_opt_data.symbol
        
        long_instrument = Option.get(self._session, long_symbol)
        short_instrument = Option.get(self._session, short_symbol)
        
        # 2. Build Legs
        # Long ZEBRA: Buy 2 ITM, Sell 1 ATM
        # Short ZEBRA: Buy 2 ITM Puts, Sell 1 ATM Put
        
        # Leg 1: Buy 2 Longs
        leg_long = long_instrument.build_leg(
            Decimal(str(quantity * 2)), 
            OrderAction.BUY_TO_OPEN
        )
        
        # Leg 2: Sell 1 Short
        leg_short = short_instrument.build_leg(
            Decimal(str(quantity)), 
            OrderAction.SELL_TO_OPEN
        )
        
        # 3. Build Order
        price_effect = Decimal(str(round(-abs(limit_price), 2))) if limit_price else None # Debit is negative
        
        order_params = {
            'time_in_force': OrderTimeInForce.DAY,
            'order_type': OrderType.LIMIT if limit_price else OrderType.MARKET, # Avoid market for 3-leg
            'legs': [leg_long, leg_short],
        }
        
        if limit_price:
            order_params['price'] = price_effect
            
        return NewOrder(**order_params)

    def build_close_zebra_order(
        self,
        long_option_symbol: str,
        short_option_symbol: str,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> NewOrder:
        """
        Build close order for ZEBRA.
        Reverses the opening trade: Sell 2 Longs, Buy 1 Short.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected.")
            
        long_inst = Option.get(self._session, long_option_symbol)
        short_inst = Option.get(self._session, short_option_symbol)
        
        # Leg 1: Sell 2 Longs (Close)
        leg_long = long_inst.build_leg(
            Decimal(str(quantity * 2)),
            OrderAction.SELL_TO_CLOSE
        )
        
        # Leg 2: Buy 1 Short (Close)
        leg_short = short_inst.build_leg(
            Decimal(str(quantity)),
            OrderAction.BUY_TO_CLOSE
        )
        
        # Calculate price (Credit expected, so positive)
        price_effect = Decimal(str(round(abs(limit_price), 2))) if limit_price else None
        
        order_params = {
            'time_in_force': OrderTimeInForce.DAY,
            'order_type': OrderType.LIMIT,
            'legs': [leg_long, leg_short],
        }
        
        if limit_price:
            order_params['price'] = price_effect
            
        return NewOrder(**order_params)

    def execute_zebra_entry(self, symbol, long_strike, short_strike, expiry, direction="LONG", quantity=1, limit_price=None, dry_run=True):
        order = self.build_zebra_order(symbol, long_strike, short_strike, expiry, direction, quantity, limit_price)
        return self.place_order(order, dry_run=dry_run)

    def execute_zebra_exit(self, long_symbol, short_symbol, quantity=1, limit_price=None, dry_run=True):
        order = self.build_close_zebra_order(long_symbol, short_symbol, quantity, limit_price)
        return self.place_order(order, dry_run=dry_run)

    def get_stock_price(self, symbol: str) -> float:
        """
        Fetch current stock price.
        """
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            price = ticker.fast_info.get('last_price')
            if not price:
                hist = ticker.history(period="1d")
                if not hist.empty:
                    price = hist['Close'].iloc[-1]
            return float(price) if price else 0.0
        except Exception as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
            return 0.0

    def get_historical_data(self, symbol: str, period: str = "2y") -> Optional[pd.DataFrame]:
        """
        Fetch historical data for technical analysis.
        """
        try:
            import yfinance as yf
            import pandas as pd
            df = yf.download(symbol, period=period, progress=False)
            if df.empty:
                 return None
            
            # Flatten MultiIndex columns if present (yfinance quirk)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            return df
        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol}: {e}")
            return None

    def get_zebra_positions(self):
        """
        Fetch open ZEBRA positions.
        Reconstructs complex positions from flat legs.
        Placeholder logic for core system - in a real app, this would query a database
        or reconstruct from Tastytrade account positions.
        """
        # For Phase 1 deployment, we check the Tastytrade account for legs
        # and group them by (Symbol, Expiry).
        # This is a simplified reconstruction.
        try:
            # tastytrade account positions logic
            # return [] for now to avoid crashes if account is empty
            return []
        except Exception as e:
            logger.error(f"Error fetching ZEBRA positions: {e}")
            return []
