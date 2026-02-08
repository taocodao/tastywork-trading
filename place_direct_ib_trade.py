#!/usr/bin/env python3
"""
Direct IB Paper Trading Order Placement
========================================
Bypass signal publishing and send order directly to IB Gateway.
Places order using ib_insync directly without going through IBOrderExecutor.
"""

from ib_insync import IB, Contract, Order
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def place_direct_ib_trade():
    """Place a test trade directly to IB paper account."""
    
    ib = IB()
    try:
        logger.info("Connecting to IB Gateway on port 4004...")
        ib.connect('127.0.0.1', 4004, clientId=105)
        
        accounts = ib.managedAccounts()
        account = accounts[0] if accounts else "Unknown"
        logger.info(f"✅ Connected to IB account: {account}")
        
        # Create option contract - SPY PUT expiring March 21, 2026
        contract = Contract()
        contract.symbol = 'SPY'
        contract.secType = 'OPT'
        contract.exchange = 'SMART'
        contract.currency = 'USD'
        contract.lastTradeDateOrContractMonth = '20260321'  # March 21, 2026
        contract.strike = 580.0
        contract.right = 'P'  # Put
        contract.multiplier = '100'
        
        logger.info("=" * 60)
        logger.info("📊 TEST ORDER DETAILS:")
        logger.info(f"   Symbol: SPY 580P")
        logger.info(f"   Expiration: 2026-03-21")
        logger.info(f"   Type: Cash-Secured Put (SELL TO OPEN)")
        logger.info("=" * 60)
        
        # Qualify the contract first
        logger.info("Qualifying contract...")
        qualified = ib.qualifyContracts(contract)
        
        if not qualified:
            logger.error("❌ Could not qualify contract - checking for valid expirations...")
            # Try different expirations
            for exp in ['20260320', '20260327', '20260403']:
                contract.lastTradeDateOrContractMonth = exp
                qualified = ib.qualifyContracts(contract)
                if qualified:
                    logger.info(f"✅ Found valid expiration: {exp}")
                    break
        
        if not qualified:
            logger.error("❌ No valid contract found")
            return False
            
        logger.info(f"✅ Contract qualified: {qualified[0].localSymbol}")
        
        # Get current market data for limit price
        ticker = ib.reqMktData(contract)
        ib.sleep(2)
        bid = ticker.bid if ticker.bid and ticker.bid > 0 else 5.00
        logger.info(f"Current bid: ${bid}")
        
        # Create SELL order (cash-secured put)
        order = Order()
        order.action = 'SELL'
        order.orderType = 'LMT'
        order.totalQuantity = 1
        order.lmtPrice = bid
        
        logger.info(f"🚀 Placing SELL order @ ${bid}...")
        trade = ib.placeOrder(contract, order)
        
        # Wait for order status
        ib.sleep(3)
        
        logger.info("=" * 60)
        logger.info(f"📋 Order ID: {trade.order.orderId}")
        logger.info(f"📊 Status: {trade.orderStatus.status}")
        logger.info(f"📊 Filled: {trade.orderStatus.filled}")
        
        if trade.orderStatus.filled > 0:
            logger.info(f"✅ FILLED at ${trade.orderStatus.avgFillPrice}")
            logger.info(f"💰 Premium: ${trade.orderStatus.avgFillPrice * 100:.2f}")
        elif trade.orderStatus.status == 'Submitted' or trade.orderStatus.status == 'PreSubmitted':
            logger.info(f"⏳ Order is working - check IB Gateway/TWS")
        else:
            logger.info(f"Order status: {trade.orderStatus.status}")
            
        logger.info("=" * 60)
        return True
            
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from IB Gateway")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🧪 DIRECT IB PAPER TRADING - TEST ORDER")
    print("=" * 60)
    print(f"Time: {datetime.now()}")
    print("=" * 60 + "\n")
    
    success = place_direct_ib_trade()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ TEST COMPLETE - Order sent to IB paper account!")
        print("Check your IB Gateway or TWS for order status")
    else:
        print("❌ TEST FAILED - See errors above")
    print("=" * 60)
