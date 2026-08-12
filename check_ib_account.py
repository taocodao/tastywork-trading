"""
Check IB Paper Trading Account Activity
========================================
Connect to IB Gateway and check for:
- Current positions
- Recent orders
- Account balance
- Any signals generated
"""

from ib_insync import IB, util
import sys

def check_account_activity():
    """Check IB paper trading account for activity."""
    ib = IB()
    
    try:
        print("Connecting to EC2 IB Gateway...")
        ib.connect('34.203.194.137', 4004, clientId=7000)
        print("✅ Connected!\n")
        
        # Get account summary
        account = ib.managedAccounts()[0]
        print(f"Account: {account}")
        print("=" * 70)
        
        # Get account values
        account_values = ib.accountSummary(account)
        for item in account_values:
            if item.tag in ['NetLiquidation', 'CashBalance', 'TotalCashValue']:
                print(f"{item.tag}: {item.value} {item.currency}")
        
        print("\n" + "=" * 70)
        print("CURRENT POSITIONS")
        print("=" * 70)
        
        # Get current positions
        positions = ib.positions()
        if positions:
            for pos in positions:
                print(f"\n{pos.contract.symbol}:")
                print(f"  Position: {pos.position}")
                print(f"  Avg Cost: ${pos.avgCost:.2f}")
                if hasattr(pos.contract, 'strike'):
                    print(f"  Strike: {pos.contract.strike}")
                    print(f"  Expiry: {pos.contract.lastTradeDateOrContractMonth}")
                    print(f"  Right: {pos.contract.right}")
                print(f"  Contract: {pos.contract.localSymbol if hasattr(pos.contract, 'localSymbol') else pos.contract}")
        else:
            print("\nNo open positions found.")
        
        print("\n" + "=" * 70)
        print("RECENT ORDERS (if any)")
        print("=" * 70)
        
        # Get orders
        orders = ib.orders()
        if orders:
            for order in orders[-10:]:  # Last 10 orders
                print(f"\nOrder ID: {order.orderId}")
                print(f"  Symbol: {order.contract.symbol}")
                print(f"  Action: {order.action}")
                print(f"  Quantity: {order.totalQuantity}")
                print(f"  Status: {order.orderStatus.status}")
        else:
            print("\nNo recent orders found.")
        
        print("\n" + "=" * 70)
        
        ib.disconnect()
        print("\n✅ Account check complete!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        if ib.isConnected():
            ib.disconnect()
        sys.exit(1)


if __name__ == "__main__":
    check_account_activity()
