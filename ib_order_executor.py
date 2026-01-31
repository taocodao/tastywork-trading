"""
IB Order Executor
==================
Direct order placement for theta strategy in IB paper trading.
Uses centralized hub for shared order connection (client ID 3001).
"""

import logging
from typing import Optional
from ib_insync import Contract, Order
from datetime import datetime

logger = logging.getLogger(__name__)


class IBOrderExecutor:
    """Execute theta trades directly in IB paper trading account."""
    
    def __init__(self, ib_provider=None):
        """
        Initialize executor with IB connection.
        
        Args:
            ib_provider: IBDataProvider instance (optional, uses hub if None)
        """
        # Try to use hub (new pattern)
        try:
            from ib_market_data_hub import get_hub
            self._hub = get_hub()
            self._use_hub = True
            logger.info("IBOrderExecutor initialized with hub (order client 3001)")
        except ImportError:
            # Fallback to legacy mode
            if ib_provider is None:
                raise ValueError("Must provide ib_provider when hub not available")
            self._use_hub = False
            self._legacy_ib = ib_provider.ib
            self._ib_provider = ib_provider
            logger.info("IBOrderExecutor initialized with legacy connection")
    
    @property
    def ib(self):
        """Get IB client for order execution."""
        if self._use_hub:
            return self._hub.order_client
        return self._legacy_ib
        
    def place_theta_entry(self, signal, dry_run: bool = False) -> Optional[int]:
        """
        Place cash-secured put order (SELL TO OPEN).
        
        Args:
            signal: ThetaEntrySignal with contract details
            dry_run: If True, log order but don't place
            
        Returns:
            Order ID if successful, None if failed
        """
        try:
            # Create option contract
            contract = Contract()
            contract.symbol = signal.symbol
            contract.secType = "OPT"
            contract.exchange = "SMART"
            contract.currency = "USD"
            # Format expiration: YYYYMMDD
            contract.lastTradeDateOrContractMonth = signal.expiration.replace('-', '')
            contract.strike = signal.strike
            contract.right = "P"  # Put option
            contract.multiplier = "100"
            
            # Create limit order
            order = Order()
            order.action = "SELL"  # Sell to open
            order.orderType = "LMT"  # Limit order
            order.totalQuantity = signal.contracts
            order.lmtPrice = signal.entry_price  # Limit at bid price
            order.transmit = not dry_run  # Don't transmit if dry run
            
            if dry_run:
                logger.info(f"🔍 DRY RUN: {signal.symbol} {signal.strike}P x{signal.contracts} @ ${signal.entry_price}")
                logger.info(f"   Expiration: {signal.expiration}, Delta: {signal.delta:.2f}")
                return None
            
            # Place order in IB
            trade = self.ib.placeOrder(contract, order)
            order_id = trade.order.orderId
            
            logger.info(f"✅ IB Order #{order_id}: SELL {signal.symbol} {signal.strike}P x{signal.contracts} @ ${signal.entry_price}")
            logger.info(f"   Premium: ${signal.total_premium:.2f}, Capital: ${signal.total_capital_required:.2f}")
            
            return order_id
            
        except Exception as e:
            logger.error(f"❌ Failed to place order for {signal.symbol} {signal.strike}P: {e}")
            return None
    
    def place_theta_exit(self, position, exit_price: float, exit_reason: str, dry_run: bool = False) -> Optional[int]:
        """
        Close put position (BUY TO CLOSE).
        
        Args:
            position: ThetaPosition object
            exit_price: Current ask price
            exit_reason: Reason for exit (profit_target, stop_loss, etc.)
            dry_run: If True, log order but don't place
            
        Returns:
            Order ID if successful, None if failed
        """
        try:
            # Create option contract
            contract = Contract()
            contract.symbol = position.symbol
            contract.secType = "OPT"
            contract.exchange = "SMART"
            contract.currency = "USD"
            contract.lastTradeDateOrContractMonth = position.expiration.replace('-', '')
            contract.strike = position.strike
            contract.right = "P"
            contract.multiplier = "100"
            
            # Create limit order
            order = Order()
            order.action = "BUY"  # Buy to close
            order.orderType = "LMT"
            order.totalQuantity = position.contracts
            order.lmtPrice = exit_price  # Limit at ask price
            order.transmit = not dry_run
            
            if dry_run:
                pnl = (position.entry_price - exit_price) * 100 * position.contracts
                logger.info(f"🔍 DRY RUN EXIT: {position.symbol} {position.strike}P @ ${exit_price}")
                logger.info(f"   Reason: {exit_reason}, P&L: ${pnl:.2f}")
                return None
            
            # Place order in IB
            trade = self.ib.placeOrder(contract, order)
            order_id = trade.order.orderId
            
            pnl = (position.entry_price - exit_price) * 100 * position.contracts
            logger.info(f"✅ IB Exit Order #{order_id}: BUY {position.symbol} {position.strike}P @ ${exit_price}")
            logger.info(f"   Reason: {exit_reason}, P&L: ${pnl:.2f}")
            
            return order_id
            
        except Exception as e:
            logger.error(f"❌ Failed to place exit order for {position.symbol}: {e}")
            return None
    
    def get_order_status(self, order_id: int) -> dict:
        """
        Get current status of an order.
        
        Args:
            order_id: IB order ID
            
        Returns:
            Dictionary with order status details
        """
        try:
            trades = self.ib.trades()
            for trade in trades:
                if trade.order.orderId == order_id:
                    return {
                        'order_id': order_id,
                        'status': trade.orderStatus.status,
                        'filled': trade.orderStatus.filled,
                        'remaining': trade.orderStatus.remaining,
                        'avg_fill_price': trade.orderStatus.avgFillPrice
                    }
            
            return {'order_id': order_id, 'status': 'NOT_FOUND'}
            
        except Exception as e:
            logger.error(f"Failed to get order status for {order_id}: {e}")
            return {'order_id': order_id, 'status': 'ERROR', 'error': str(e)}
