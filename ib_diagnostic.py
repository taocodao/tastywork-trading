#!/usr/bin/env python3
"""
IB Paper Trading Diagnostic Script
===================================
Comprehensive diagnostics to identify permission issues.
Based on IB official documentation and troubleshooting guides.
"""

from ib_insync import *
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def diagnostic_check():
    """Run comprehensive diagnostics on IB paper account."""
    
    print("\n" + "=" * 70)
    print("🔍 IB PAPER TRADING DIAGNOSTIC")
    print("=" * 70)
    print(f"Time: {datetime.now()}")
    print("=" * 70 + "\n")
    
    ib = IB()
    
    # Custom error handler to capture detailed errors
    errors = []
    def onError(reqId, errorCode, errorString, advancedOrderRejectJson=None):
        error_info = {
            'reqId': reqId,
            'errorCode': errorCode,
            'errorString': errorString,
            'advancedReject': advancedOrderRejectJson
        }
        errors.append(error_info)
        print(f"⚠️  Error {errorCode}, reqId {reqId}: {errorString}")
        if advancedOrderRejectJson:
            print(f"   Advanced Reject JSON: {advancedOrderRejectJson}")
    
    ib.errorEvent += onError
    
    try:
        # Test 1: Connection
        print("TEST 1: IB Gateway Connection")
        print("-" * 70)
        ib.connect('127.0.0.1', 4004, clientId=110)
        print("✅ Connected to IB Gateway on port 4004")
        
        # Test 2: Account Information
        print("\nTEST 2: Account Information")
        print("-" * 70)
        accounts = ib.managedAccounts()
        if not accounts:
            print("❌ No accounts found!")
            return
        
        account = accounts[0]
        print(f"✅ Account: {account}")
        
        # Test 3: Account Summary
        print("\nTEST 3: Account Summary & Buying Power")
        print("-" * 70)
        summary = ib.accountSummary(account)
        
        important_tags = [
            'AccountType',
            'CashBalance', 
            'EquityWithLoanValue',
            'BuyingPower',
            'OptionMarketValue',
            'NetLiquidation'
        ]
        
        for tag in important_tags:
            value = next((s.value for s in summary if s.tag == tag), 'N/A')
            currency = next((s.currency for s in summary if s.tag == tag), '')
            print(f"   {tag}: {value} {currency}")
        
        # Test 4: Stock Order (Control Test)
        print("\nTEST 4: Stock Order Test (Control)")
        print("-" * 70)
        print("Testing if stock orders work (permissions baseline)...")
        
        stock = Stock('SPY', 'SMART', 'USD')
        ib.qualifyContracts(stock)
        print(f"✅ Stock contract qualified: {stock.symbol}")
        
        stock_order = LimitOrder('BUY', 1, 0.01)
        stock_trade = ib.placeOrder(stock, stock_order)
        ib.sleep(2)
        
        print(f"   Order ID: {stock_trade.order.orderId}")
        print(f"   Status: {stock_trade.orderStatus.status}")
        
        if stock_trade.orderStatus.status in ['PreSubmitted', 'Submitted']:
            print("✅ Stock orders work - permissions OK for stocks")
            ib.cancelOrder(stock_trade.order)
            print("   (Order cancelled)")
        else:
            print("⚠️  Stock order also failed - broader permissions issue")
        
        # Test 5: Option Contract Qualification
        print("\nTEST 5: Option Contract Qualification")
        print("-" * 70)
        
        contract = Option('SPY', '20260320', 580, 'P', 'SMART')
        qualified = ib.qualifyContracts(contract)
        
        if qualified:
            opt = qualified[0]
            print(f"✅ Option contract qualified")
            print(f"   Symbol: {opt.symbol}")
            print(f"   Local Symbol: {opt.localSymbol}")
            print(f"   Contract ID: {opt.conId}")
            print(f"   Exchange: {opt.exchange}")
            print(f"   Strike: {opt.strike}")
            print(f"   Expiration: {opt.lastTradeDateOrContractMonth}")
        else:
            print("❌ Option contract could not be qualified")
            return
        
        # Test 6: Market Data for Option
        print("\nTEST 6: Market Data Access")
        print("-" * 70)
        ticker = ib.reqMktData(contract)
        ib.sleep(3)
        
        print(f"   Bid: ${ticker.bid if ticker.bid else 'N/A'}")
        print(f"   Ask: ${ticker.ask if ticker.ask else 'N/A'}")
        print(f"   Last: ${ticker.last if ticker.last else 'N/A'}")
        
        if ticker.bid and ticker.bid > 0:
            print("✅ Market data accessible")
            bid_price = ticker.bid
        else:
            print("⚠️  No market data (might be after hours)")
            bid_price = 5.00
        
        # Test 7: Option Order Placement (The Critical Test)
        print("\nTEST 7: Option Order Placement (CRITICAL TEST)")
        print("-" * 70)
        print("Attempting to place SPY 580P SELL order...")
        
        option_order = LimitOrder('SELL', 1, bid_price)
        option_order.tif = 'DAY'
        option_trade = ib.placeOrder(contract, option_order)
        
        print(f"   Order ID: {option_trade.order.orderId}")
        print(f"   Initial Status: {option_trade.orderStatus.status}")
        
        # Wait and monitor status changes
        ib.sleep(5)
        
        print(f"   Final Status: {option_trade.orderStatus.status}")
        print(f"   Filled: {option_trade.orderStatus.filled}")
        
        # Print all log entries
        print("\n   Order Log:")
        for entry in option_trade.log:
            print(f"      [{entry.time}] {entry.status}: {entry.message}")
        
        # Analyze result
        print("\nTEST 7 RESULT:")
        print("-" * 70)
        
        if option_trade.orderStatus.status in ['PreSubmitted', 'Submitted', 'Filled']:
            print("✅✅✅ SUCCESS! Option order was ACCEPTED")
            print("🎉 Permissions are working correctly!")
            ib.cancelOrder(option_trade.order)
        elif any('201' in str(entry.message) for entry in option_trade.log):
            print("❌ FAILED: Error 201 - Permission Issue Confirmed")
            print("\n🔍 ROOT CAUSE: Options trading permissions not active for API")
            print("\nACTION REQUIRED:")
            print("1. Log into LIVE account Client Portal (not paper)")
            print("2. Check Settings → Trading → Trading Permissions → Options")
            print("3. Verify Status shows 'Active' (not 'Pending')")
            print("4. If approved < 48 hours ago → Wait for backend sync")
            print("5. If approved 48+ hours ago → Call IB: 1-877-442-2757")
        else:
            print(f"⚠️  Order failed with status: {option_trade.orderStatus.status}")
            print("   Check logs above for details")
        
        # Test 8: Error Summary
        print("\nTEST 8: Error Summary")
        print("-" * 70)
        
        if errors:
            print(f"Total errors captured: {len(errors)}")
            for err in errors:
                print(f"\n   Error {err['errorCode']}:")
                print(f"      ReqId: {err['reqId']}")
                print(f"      Message: {err['errorString']}")
                if err['advancedReject']:
                    print(f"      Advanced: {err['advancedReject']}")
        else:
            print("No errors captured during tests")
        
    except Exception as e:
        print(f"\n❌ Exception: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("\n✅ Disconnected from IB Gateway")
    
    # Final Summary
    print("\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)
    print("\nNEXT STEPS:")
    print("1. Review test results above")
    print("2. If Error 201 appears → Check LIVE account permissions")
    print("3. If stock orders work but not options → Definitely permissions")
    print("4. Contact IB Support: 1-877-442-2757")
    print("   Say: 'Paper account DUK782510 gets Error 201 for options'")
    print("   Ask: 'Check backend options permission and API flags'")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    diagnostic_check()
