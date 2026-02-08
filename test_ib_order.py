#!/usr/bin/env python3
"""
IB Paper Trading Test Script
=============================
Sends a single test order to IB paper trading account.

Usage:
    python3 test_ib_order.py [--dry-run]
"""

from ib_insync import IB, Contract, Order
from datetime import datetime, timedelta
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# IB Gateway paper trading settings
IB_HOST = "127.0.0.1"
IB_PORT = 4001  # Paper trading port (live = 7496)
CLIENT_ID = 100  # Use unique client ID to avoid conflicts

def place_test_theta_order(dry_run=False):
    """Place a test cash-secured put order."""
    
    ib = IB()
    
    try:
        # Connect to IB Gateway
        logger.info(f"Connecting to IB Gateway at {IB_HOST}:{IB_PORT}...")
        ib.connect(IB_HOST, IB_PORT, clientId=CLIENT_ID)
        
        # Get account info
        accounts = ib.managedAccounts()
        if not accounts:
            logger.error("No accounts found!")
            return False
            
        account = accounts[0]
        logger.info(f"✅ Connected to account: {account}")
        
        # Get account value
        portfolio = ib.accountValues()
        nav = [v for v in portfolio if v.tag == 'NetLiquidation']
        if nav:
            logger.info(f"   Account Value: ${float(nav[0].value):,.2f}")
        
        # Create option contract
        # SPY put, 30 days out, strike at current price - buffer
        expiry = (datetime.now() + timedelta(days=30)).strftime('%Y%m%d')
        strike = 575.0  # Adjust based on current SPY price
        
        contract = Contract()
        contract.symbol = "SPY"
        contract.secType = "OPT"
        contract.exchange = "SMART"
        contract.currency = "USD"
        contract.lastTradeDateOrContractMonth = expiry
        contract.strike = strike
        contract.right = "P"  # Put option
        contract.multiplier = "100"
        
        logger.info(f"📋 Option Contract:")
        logger.info(f"   Symbol: SPY {strike}P")
        logger.info(f"   Expiration: {expiry}")
        
        # Get current market data to determine limit price
        ib.qualifyContracts(contract)
        ticker = ib.reqMktData(contract)
        ib.sleep(2)  # Wait for data
        
        bid = ticker.bid if ticker.bid > 0 else 2.50  # Default if no data
        
        logger.info(f"   Current Bid: ${bid}")
        
        # Create limit order - SELL to open (cash-secured put)
        order = Order()
        order.action = "SELL"
        order.orderType = "LMT"
        order.totalQuantity = 1
        order.lmtPrice = bid
        order.transmit = not dry_run  # Only transmit if not dry run
        
        logger.info(f"📝 Order:")
        logger.info(f"   Action: SELL TO OPEN")
        logger.info(f"   Type: Limit @ ${bid}")
        logger.info(f"   Quantity: 1 contract")
        logger.info(f"   Premium: ${bid * 100:.2f}")
        
        if dry_run:
            logger.info(f"🔍 DRY RUN - Order NOT submitted")
            return True
            
        # Place order
        trade = ib.placeOrder(contract, order)
        
        # Wait for fill or status update
        logger.info("⏳ Waiting for order status...")
        ib.sleep(5)
        
        status = trade.orderStatus.status
        logger.info(f"📊 Order Status: {status}")
        
        if trade.orderStatus.filled > 0:
            logger.info(f"✅ Order FILLED!")
            logger.info(f"   Order ID: {trade.order.orderId}")
            logger.info(f"   Filled: {trade.orderStatus.filled}")
            logger.info(f"   Avg Price: ${trade.orderStatus.avgFillPrice}")
        else:
            logger.info(f"⏳ Order ID: {trade.order.orderId}")
            logger.info(f"   Status: {status}")
            logger.info(f"   Order is working, check IB Gateway for updates")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        ib.disconnect()
        logger.info("Disconnected from IB Gateway")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    
    print("=" * 60)
    print("🧪 IB PAPER TRADING TEST")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE ORDER'}")
    print(f"Time: {datetime.now()}")
    print("=" * 60)
    print()
    
    success = place_test_theta_order(dry_run=dry_run)
    
    print()
    print("=" * 60)
    if success:
        print("✅ TEST COMPLETE - Check IB Gateway/TWS for order status")
    else:
        print("❌ TEST FAILED - Check logs above")
    print("=" * 60)
