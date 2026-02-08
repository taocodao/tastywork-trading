#!/usr/bin/env python3
"""
Manual Test Trade - Place a real trade to test position tracking
"""

from ib_insync import *
from datetime import datetime, timedelta
import json
import uuid
import os

def place_test_trade():
    """Place a small test trade and add to position tracker."""
    
    print("\n" + "="*70)
    print("🧪 MANUAL TEST TRADE - Position Tracking Test")
    print("="*70 + "\n")
    
    # Connect to IB Gateway
    ib = IB()
    ib.connect('127.0.0.1', 4004, clientId=120)
    print("✅ Connected to IB Gateway")
    
    # Create option contract (SPY 580P March 20, 2026)
    contract = Option('SPY', '20260320', 580, 'P', 'SMART')
    ib.qualifyContracts(contract)
    print(f"✅ Contract qualified: {contract.localSymbol}")
    
    # Get current market price
    ticker = ib.reqMktData(contract)
    ib.sleep(3)
    
    if ticker.bid and ticker.bid > 0:
        bid_price = ticker.bid
        print(f"✅ Market bid: ${bid_price:.2f}")
    else:
        bid_price = 5.00  # Fallback
        print(f"⚠️  No market data, using fallback: ${bid_price:.2f}")
    
    # Place SELL order (open position)
    print(f"\n📤 Placing order: SELL 1 SPY 580P @ ${bid_price:.2f}")
    order = LimitOrder('SELL', 1, bid_price)
    trade = ib.placeOrder(contract, order)
    
    # Wait for order to process
    print("⏳ Waiting for order status...")
    ib.sleep(5)
    
    print(f"\n📊 Order ID: {trade.order.orderId}")
    print(f"📊 Status: {trade.orderStatus.status}")
    print(f"📊 Filled: {trade.orderStatus.filled}")
    print(f"📊 Avg Fill Price: ${trade.orderStatus.avgFillPrice:.2f}")
    
    # Check if order was filled
    if trade.orderStatus.status in ['Filled', 'Submitted', 'PreSubmitted']:
        
        # Use fill price if filled, otherwise entry price
        fill_price = trade.orderStatus.avgFillPrice if trade.orderStatus.avgFillPrice > 0 else bid_price
        
        print(f"\n✅ Order accepted! Adding to position tracker...")
        
        # Calculate dates
        entry_date = datetime.now()
        exp_date = datetime(2026, 3, 20)
        dte = (exp_date - entry_date).days
        
        # Create position record
        position = {
            "id": str(uuid.uuid4())[:8],
            "symbol": "SPY",
            "strike": 580.0,
            "expiration": "2026-03-20",
            "dte": dte,
            "contracts": 1,
            "entry_price": fill_price,
            "entry_date": entry_date.isoformat(),
            "total_premium": fill_price * 100,  # Per contract
            "status": "open",
            "exit_targets": {
                "target_50": round(fill_price * 0.50, 2),
                "target_60": round(fill_price * 0.60, 2),
                "target_75": round(fill_price * 0.75, 2),
                "target_90": round(fill_price * 0.90, 2)
            }
        }
        
        # Load existing positions or create new file
        positions_file = 'theta_positions.json'
        try:
            with open(positions_file, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {"positions": [], "last_updated": datetime.now().isoformat()}
        
        # Add new position
        data["positions"].append(position)
        data["last_updated"] = datetime.now().isoformat()
        
        # Save to file
        with open(positions_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n✅ Position tracked successfully!")
        print(f"\n📝 Position Details:")
        print(f"   ID: {position['id']}")
        print(f"   Symbol: {position['symbol']} {position['strike']}P")
        print(f"   Expiration: {position['expiration']} ({dte} DTE)")
        print(f"   Entry Price: ${position['entry_price']:.2f}")
        print(f"   Total Premium: ${position['total_premium']:.2f}")
        print(f"\n🎯 Exit Targets:")
        print(f"   50% profit: ${position['exit_targets']['target_50']:.2f}")
        print(f"   60% profit: ${position['exit_targets']['target_60']:.2f}")
        print(f"   75% profit: ${position['exit_targets']['target_75']:.2f}")
        print(f"   90% profit: ${position['exit_targets']['target_90']:.2f}")
        
        print(f"\n✅ Position saved to {positions_file}")
        
        # Show positions summary
        open_positions = [p for p in data["positions"] if p["status"] == "open"]
        print(f"\n📊 Portfolio Summary:")
        print(f"   Total positions: {len(data['positions'])}")
        print(f"   Open positions: {len(open_positions)}")
        print(f"   Total premium collected: ${sum(p['total_premium'] for p in open_positions):.2f}")
        
    else:
        print(f"\n❌ Order not filled: {trade.orderStatus.status}")
        print("Try running again or check IB Gateway")
    
    # Disconnect
    ib.disconnect()
    print("\n✅ Disconnected from IB Gateway")
    
    print("\n" + "="*70)
    print("NEXT STEPS:")
    print("="*70)
    print("1. Check position file: cat theta_positions.json")
    print("2. Run scheduler to test exit logic: python3 run_theta_scheduler.py --once")
    print("3. Monitor position: cat theta_scheduler.log")
    print("4. To close manually, run this script with --close flag")
    print("="*70 + "\n")


if __name__ == "__main__":
    try:
        place_test_trade()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
