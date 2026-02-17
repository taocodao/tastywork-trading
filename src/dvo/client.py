
"""
DVO Client
==========
Handles DVO-specific interactions with Tastytrade API.
- Execute Short Puts (Portfolio-Secured)
- Execute LEAPS Calls (Recycling)
- Monitor Margin Usage
"""

import logging
from typing import Optional, Dict, List
from datetime import datetime

# Inherit from ZebraClient or TastytradeClient to reuse session logic
# ZebraClient already has some advanced order building
from ..zebra.client import ZebraClient 

logger = logging.getLogger(__name__)

class DVOClient(ZebraClient):
    """
    DVO Client wrapping Tastytrade API (Synchronous).
    Inherits from ZebraClient for reusable logic.
    """
    
    def __init__(self, user_id: str = "default"):
        # parent init
        super().__init__() 
        self.user_id = user_id
        
    def get_margin_usage(self) -> Dict:
        """Get current margin usage and net liq."""
        if not self.is_connected:
            self.connect()
            
        balances = self.get_account_balance()
        # Calculate ratio
        net_liq = balances.get('net_liquidating_value', 0)
        buying_power = balances.get('buying_power', 0) 
        # Maintenance margin is roughly Net Liq - Buying Power (simplified)
        maint_margin = net_liq - buying_power
        
        return {
            'net_liquid': net_liq,
            'maintenance_margin': maint_margin,
            'margin_equity_ratio': maint_margin / net_liq if net_liq > 0 else 0
        }
        
    def execute_short_put(self,
                          symbol: str,
                          quantity: int,
                          expiry: str, # 'YYYY-MM-DD'
                          strike: float,
                          limit_price: float,
                          dry_run: bool = True) -> Optional[Dict]:
        """
        Execute SELL_TO_OPEN Put order.
        """
        if not self.is_connected:
             self.connect()
             
        logger.info(f"DVO Execute Put: {symbol} {expiry} {strike}P x{quantity} @ {limit_price} (DryRun={dry_run})")
        
        if dry_run:
            return {'status': 'dry_run', 'order_id': 'SIM_ORDER_123'}
            
        # Parse expiry
        from datetime import datetime
        try:
            exp_date = datetime.strptime(expiry, '%Y-%m-%d').date()
        except TypeError:
            exp_date = expiry # Already date object
            
        # Build Order
        order = self.build_cash_secured_put_order(
            symbol=symbol,
            strike=strike,
            expiry=exp_date,
            quantity=quantity,
            limit_price=limit_price
        )
        
        res = self.place_order(order, dry_run=False)
        order_id = str(res.order.id) if hasattr(res, 'order') else "unknown"
        
        return {'status': 'executed', 'order_id': order_id, 'details': str(res)}

    def execute_leaps_call(self,
                           symbol: str,
                           quantity: int,
                           expiry: str,
                           strike: float,
                           limit_price: float,
                           dry_run: bool = True) -> Optional[Dict]:
        """
        Execute BUY_TO_OPEN LEAPS Call.
        """
        if not self.is_connected:
             self.connect()
             
        logger.info(f"DVO Execute LEAPS: {symbol} {expiry} {strike}C x{quantity} @ {limit_price} (DryRun={dry_run})")
        
        if dry_run:
             return {'status': 'dry_run', 'order_id': 'SIM_LEAPS_123'}

        # Parse expiry
        from datetime import datetime
        try:
            exp_date = datetime.strptime(expiry, '%Y-%m-%d').date()
        except TypeError:
            exp_date = expiry

        # Use vertical spread builder but only 1 leg? 
        # Or raw leg builder.
        # Implemented custom here.
        
        from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
        from tastytrade.instruments import Option
        from decimal import Decimal
        
        # Find Option
        opt = self.find_option_at_strike(symbol, exp_date, strike, 'C')
        if not opt:
            raise ValueError(f"Option not found: {symbol} {expiry} {strike}C")
            
        instrument = Option.get(self._session, opt.symbol)
        leg = instrument.build_leg(Decimal(quantity), OrderAction.BUY_TO_OPEN)
        
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[leg],
            price=Decimal(str(limit_price))
        )
        
        res = self.place_order(order, dry_run=False)
        order_id = str(res.order.id) if hasattr(res, 'order') else "unknown"
        
        return {'status': 'executed', 'order_id': order_id, 'details': str(res)}

    def fetch_option_chain(self, symbol: str) -> Dict:
         if not self.is_connected:
              self.connect()
         return self.get_option_chain(symbol)
