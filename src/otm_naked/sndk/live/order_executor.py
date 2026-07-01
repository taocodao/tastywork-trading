import logging
import asyncio
from ib_insync import LimitOrder, MarketOrder, OrderStatus, Trade

logger = logging.getLogger(__name__)

class OrderExecutor:
    """Executes limit orders and monitors fills."""
    
    def __init__(self, ib_connector):
        self.ib_connector = ib_connector
        self.ib = ib_connector.get_ib()
        
    async def sell_to_open(self, contract, quantity: int, limit_price: float) -> Trade:
        """Submit STO order."""
        # STO means we are SELLING
        order = LimitOrder('SELL', quantity, round(limit_price, 2))
        order.account = self.ib.wrapper.accounts[0] if self.ib.wrapper.accounts else ""
        
        logger.info(f"Submitting STO: SELL {quantity} {contract.symbol} {contract.lastTradeDateOrContractMonth} {contract.strike} {contract.right} @ LMT {limit_price}")
        trade = self.ib.placeOrder(contract, order)
        
        # Wait up to 30 seconds for fill
        for _ in range(30):
            if trade.orderStatus.status == 'Filled':
                logger.info(f"STO Filled at {trade.orderStatus.avgFillPrice}")
                return trade
            await asyncio.sleep(1)
            
        logger.warning(f"STO Order not fully filled after 30s. Status: {trade.orderStatus.status}")
        return trade
        
    async def buy_to_close(self, contract, quantity: int, limit_price: float) -> Trade:
        """Submit BTC order."""
        # BTC means we are BUYING
        order = LimitOrder('BUY', quantity, round(limit_price, 2))
        order.account = self.ib.wrapper.accounts[0] if self.ib.wrapper.accounts else ""
        
        logger.info(f"Submitting BTC: BUY {quantity} {contract.symbol} {contract.lastTradeDateOrContractMonth} {contract.strike} {contract.right} @ LMT {limit_price}")
        trade = self.ib.placeOrder(contract, order)
        
        # Wait up to 30 seconds for fill
        for _ in range(30):
            if trade.orderStatus.status == 'Filled':
                logger.info(f"BTC Filled at {trade.orderStatus.avgFillPrice}")
                return trade
            await asyncio.sleep(1)
            
        logger.warning(f"BTC Order not fully filled after 30s. Status: {trade.orderStatus.status}")
        return trade
        
    async def get_buying_power(self) -> float:
        """Get available buying power."""
        # Need to request account summary
        summary = await self.ib.accountSummaryAsync()
        for item in summary:
            if item.tag == 'AvailableFunds':
                return float(item.value)
        return 0.0
