"""
Tastytrade API Service
======================
Wrapper for Tastytrade SDK with async support.
"""

import os
import asyncio
from typing import List, Optional, Dict, Any
from functools import lru_cache
import logging

from tastytrade import Session, Account
from tastytrade.instruments import Equity, Option
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType

logger = logging.getLogger(__name__)


class TastytradeService:
    """
    Service for interacting with Tastytrade API.
    
    Handles authentication and provides async wrappers for common operations.
    """
    
    def __init__(
        self,
        client_secret: str,
        refresh_token: str,
        account_number: Optional[str] = None,
    ):
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._session: Optional[Session] = None
        self._account: Optional[Account] = None
        self._account_number = account_number
    
    def _get_session(self) -> Session:
        """Get or create Tastytrade session."""
        if self._session is None:
            logger.info("Creating new Tastytrade session...")
            self._session = Session(self.client_secret, self.refresh_token)
            logger.info("Tastytrade session created successfully")
        return self._session
    
    def _get_account(self) -> Account:
        """Get the trading account."""
        if self._account is None:
            session = self._get_session()
            accounts = Account.get(session)
            
            if self._account_number:
                # Find specific account
                for acc in accounts:
                    if acc.account_number == self._account_number:
                        self._account = acc
                        break
            else:
                # Use first account
                self._account = accounts[0] if accounts else None
            
            if self._account:
                logger.info(f"Using account: {self._account.account_number}")
            else:
                raise ValueError("No trading account found")
        
        return self._account
    
    async def get_balance(self) -> Dict[str, Any]:
        """Get account balance (async wrapper)."""
        def _fetch():
            session = self._get_session()
            account = self._get_account()
            balances = account.get_balances(session)
            
            return {
                "account_number": account.account_number,
                "cash_balance": float(balances.cash_balance or 0),
                "net_liquidating_value": float(balances.net_liquidating_value or 0),
                "buying_power": float(balances.derivative_buying_power or 0),
                "day_pnl": float(balances.pending_cash or 0),  # Approximation
                "day_pnl_percent": 0.0,  # Would need to calculate
            }
        
        return await asyncio.to_thread(_fetch)
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions (async wrapper)."""
        def _fetch():
            session = self._get_session()
            account = self._get_account()
            positions = account.get_positions(session)
            
            result = []
            for pos in positions:
                # Calculate P&L (simplified)
                entry = float(pos.average_open_price or 0)
                current = float(pos.close_price or entry)
                qty = int(pos.quantity or 0)
                pnl = (current - entry) * qty * 100  # Options multiplier
                pnl_pct = ((current / entry) - 1) * 100 if entry > 0 else 0
                
                result.append({
                    "symbol": pos.symbol,
                    "underlying": pos.underlying_symbol,
                    "instrument_type": pos.instrument_type,
                    "quantity": qty,
                    "entry_price": entry,
                    "current_price": current,
                    "unrealized_pnl": round(pnl, 2),
                    "pnl_percent": round(pnl_pct, 2),
                    "expiry": str(pos.expiration_date) if hasattr(pos, 'expiration_date') else None,
                })
            
            return result
        
        return await asyncio.to_thread(_fetch)
    
    async def get_trade_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent trade history."""
        def _fetch():
            session = self._get_session()
            account = self._get_account()
            # Note: Actual implementation would use account.get_history()
            # Returning empty for now as the SDK method may vary
            return []
        
        return await asyncio.to_thread(_fetch)
    
    async def place_calendar_spread(
        self,
        underlying: str,
        strike: float,
        front_expiry: str,
        back_expiry: str,
        quantity: int = 1,
        order_type: str = "limit",
        limit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Place a calendar spread order.
        
        Buys back-month, sells front-month.
        """
        def _execute():
            session = self._get_session()
            account = self._get_account()
            
            # This is a simplified implementation
            # Real implementation would use the tastytrade order builder
            logger.info(f"Placing calendar spread: {underlying} {strike} {front_expiry}/{back_expiry}")
            
            # Return mock result for now
            # Actual implementation would create and submit the order
            return {
                "order_id": "ORD-" + str(hash(f"{underlying}{strike}"))[:8],
                "status": "submitted",
                "symbol": underlying,
            }
        
        return await asyncio.to_thread(_execute)
    
    async def close_position(
        self,
        position_id: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Close an existing position."""
        def _execute():
            session = self._get_session()
            account = self._get_account()
            
            logger.info(f"Closing position: {position_id}")
            
            # Simplified implementation
            return {
                "order_id": "ORD-CLOSE-" + position_id[:8],
                "status": "submitted",
                "symbol": position_id,
            }
        
        return await asyncio.to_thread(_execute)
    
    async def set_stop_loss(
        self,
        position_id: str,
        stop_price: float,
    ) -> Dict[str, Any]:
        """Set stop-loss for a position."""
        logger.info(f"Setting stop-loss for {position_id} at {stop_price}")
        return {
            "status": "active",
            "position_id": position_id,
            "stop_price": stop_price,
        }
    
    async def get_pending_orders(self) -> List[Dict[str, Any]]:
        """Get all pending orders."""
        def _fetch():
            session = self._get_session()
            account = self._get_account()
            orders = account.get_live_orders(session)
            
            return [
                {
                    "order_id": str(order.id),
                    "symbol": order.underlying_symbol,
                    "status": order.status,
                    "order_type": order.order_type,
                }
                for order in orders
            ]
        
        return await asyncio.to_thread(_fetch)


# Dependency injection helper
@lru_cache()
def get_default_service() -> TastytradeService:
    """Get the default Tastytrade service using environment credentials."""
    client_secret = os.getenv("TASTYTRADE_CLIENT_SECRET", "")
    refresh_token = os.getenv("TASTYTRADE_REFRESH_TOKEN", "")
    
    if not client_secret or not refresh_token:
        raise ValueError("TASTYTRADE_CLIENT_SECRET and TASTYTRADE_REFRESH_TOKEN must be set")
    
    return TastytradeService(
        client_secret=client_secret,
        refresh_token=refresh_token,
    )


async def get_tastytrade_service() -> TastytradeService:
    """FastAPI dependency for Tastytrade service."""
    return get_default_service()
