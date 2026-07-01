import logging
from ib_insync import LimitOrder, Trade, Option

logger = logging.getLogger(__name__)

class OrderExecutor:
    """Executes limit orders and monitors fills."""
    
    def __init__(self, ib_connector):
        self.ib_connector = ib_connector
        
    @property
    def ib(self):
        return self.ib_connector.get_ib()
        
    def _cap_fill_price(self, trade: Trade) -> float:
        """
        Paper trading workaround: IB paper sometimes fills at a price better than limit.
        This caps the fill price to the limit price to prevent overestimating returns.
        """
        if not trade.orderStatus.status == 'Filled':
            return 0.0
            
        avg_fill = trade.orderStatus.avgFillPrice
        limit = trade.order.lmtPrice
        
        if trade.order.action == 'SELL':
            return min(avg_fill, limit)
        else:
            return max(avg_fill, limit)
        
    def sell_to_open(self, contract: Option, quantity: int, limit_price: float, available_funds: float = None) -> Trade:
        """Submit STO order with margin pre-check."""
        order = LimitOrder('SELL', quantity, round(limit_price, 2), tif='DAY', outsideRth=False)
        order.account = self.ib.wrapper.accounts[0] if self.ib.wrapper.accounts else ""
        
        # Margin Check (What-If)
        if available_funds:
            what_if_order = LimitOrder('SELL', quantity, round(limit_price, 2), tif='DAY')
            what_if_order.whatIf = True
            state = self.ib.whatIfOrder(contract, what_if_order)
            
            try:
                margin_change = float(state.initMarginChange)
                if margin_change > available_funds * 0.80:
                    logger.warning(f"Margin too large ({margin_change} > {available_funds * 0.80}), skipping trade")
                    return None
            except Exception as e:
                logger.warning(f"Could not parse margin change: {e}")
                
        logger.info(f"Submitting STO: SELL {quantity} {contract.symbol} {contract.lastTradeDateOrContractMonth} {contract.strike} {contract.right} @ LMT {limit_price}")
        trade = self.ib.placeOrder(contract, order)
        
        # Wait up to 30 seconds for fill
        for _ in range(30):
            if trade.orderStatus.status == 'Filled':
                capped_fill = self._cap_fill_price(trade)
                logger.info(f"STO Filled. Capped fill price: {capped_fill} (Original: {trade.orderStatus.avgFillPrice})")
                trade.orderStatus.avgFillPrice = capped_fill # Monkey patch for downstream logic
                return trade
            self.ib.sleep(1)
            
        logger.warning(f"STO Order not fully filled after 30s. Status: {trade.orderStatus.status}. Canceling.")
        self.ib.cancelOrder(trade.order)
        return trade
        
    def buy_to_close(self, contract: Option, quantity: int, limit_price: float) -> Trade:
        """Submit BTC order."""
        order = LimitOrder('BUY', quantity, round(limit_price, 2), tif='DAY', outsideRth=False)
        order.account = self.ib.wrapper.accounts[0] if self.ib.wrapper.accounts else ""
        
        logger.info(f"Submitting BTC: BUY {quantity} {contract.symbol} {contract.lastTradeDateOrContractMonth} {contract.strike} {contract.right} @ LMT {limit_price}")
        trade = self.ib.placeOrder(contract, order)
        
        # Wait up to 30 seconds for fill
        for _ in range(30):
            if trade.orderStatus.status == 'Filled':
                capped_fill = self._cap_fill_price(trade)
                logger.info(f"BTC Filled. Capped fill price: {capped_fill} (Original: {trade.orderStatus.avgFillPrice})")
                trade.orderStatus.avgFillPrice = capped_fill
                return trade
            self.ib.sleep(1)
            
        logger.warning(f"BTC Order not fully filled after 30s. Status: {trade.orderStatus.status}. Canceling.")
        self.ib.cancelOrder(trade.order)
        return trade
        
    def get_net_liquidation(self) -> float:
        """Get net liquidation value (better proxy for NAV than buying power)."""
        summary = self.ib.accountSummary()
        for item in summary:
            if item.tag == 'NetLiquidation':
                return float(item.value)
        return 0.0
        
    def get_buying_power(self) -> float:
        """Get available funds for trading."""
        summary = self.ib.accountSummary()
        for item in summary:
            if item.tag == 'AvailableFunds':
                return float(item.value)
        return 0.0
