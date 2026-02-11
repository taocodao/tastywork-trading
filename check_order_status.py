#!/usr/bin/env python3
"""
Check Order Execution Status
=============================
Demonstrates how to monitor order execution via Tastytrade API.

Usage:
    python check_order_status.py                    # Check all live orders
    python check_order_status.py --order-id 12345   # Check specific order
"""

import argparse
import sys
from datetime import datetime
from tastytrade_client import TastytradeClient
from tastytrade import Order
import time


def check_all_live_orders(client: TastytradeClient):
    """Check status of all live (pending) orders."""
    print("\n" + "=" * 70)
    print("📋 LIVE ORDERS STATUS")
    print("=" * 70 + "\n")
    
    try:
        account = client.get_account()
        live_orders = account.get_live_orders(client._session)
        
        if not live_orders:
            print("✅ No pending orders - all orders completed or no orders placed")
            return
        
        print(f"Found {len(live_orders)} pending order(s):\n")
        
        for i, order in enumerate(live_orders, 1):
            print(f"{i}. Order ID: {order.id}")
            print(f"   Symbol: {order.underlying_symbol}")
            print(f"   Status: {order.status}")
            print(f"   Type: {order.order_type}")
            print(f"   Quantity: {order.quantity}")
            print(f"   Filled: {order.filled_quantity}/{order.quantity}")
            
            if order.filled_quantity > 0:
                print(f"   Avg Fill Price: ${order.average_fill_price:.2f}")
            
            if order.price:
                print(f"   Limit Price: ${order.price:.2f}")
            
            print()
        
    except Exception as e:
        print(f"❌ Error checking orders: {e}")
        import traceback
        traceback.print_exc()


def check_specific_order(client: TastytradeClient, order_id: str):
    """Check status of a specific order by ID."""
    print("\n" + "=" * 70)
    print(f"🔍 ORDER STATUS: {order_id}")
    print("=" * 70 + "\n")
    
    try:
        account = client.get_account()
        order = Order.get_order(client._session, account.account_number, order_id)
        
        print(f"Order ID: {order.id}")
        print(f"Symbol: {order.underlying_symbol}")
        print(f"Status: {order.status}")
        print(f"Order Type: {order.order_type}")
        print(f"Time In Force: {order.time_in_force}")
        print(f"\nQuantity: {order.quantity}")
        print(f"Filled: {order.filled_quantity}")
        print(f"Remaining: {order.remaining_quantity}")
        
        if order.filled_quantity > 0:
            print(f"\nAverage Fill Price: ${order.average_fill_price:.2f}")
            print(f"Total Fill Value: ${order.average_fill_price * order.filled_quantity:.2f}")
        
        if order.price:
            print(f"\nLimit Price: ${order.price:.2f}")
        
        # Execution status
        print("\n" + "-" * 70)
        if order.status == "Filled":
            print("✅ ORDER FULLY EXECUTED")
        elif order.filled_quantity > 0:
            print(f"⚠️ ORDER PARTIALLY FILLED ({order.filled_quantity}/{order.quantity})")
        elif order.status in ["Cancelled", "Rejected", "Expired"]:
            print(f"❌ ORDER {order.status.upper()}")
        else:
            print(f"⏳ ORDER PENDING ({order.status})")
        
    except Exception as e:
        print(f"❌ Error retrieving order: {e}")
        import traceback
        traceback.print_exc()


def monitor_order_until_filled(client: TastytradeClient, order_id: str, timeout: int = 120):
    """Monitor an order until it's filled or timeout."""
    print("\n" + "=" * 70)
    print(f"⏱️ MONITORING ORDER: {order_id}")
    print("=" * 70 + "\n")
    print(f"Timeout: {timeout} seconds\n")
    
    account = client.get_account()
    start_time = time.time()
    
    try:
        while time.time() - start_time < timeout:
            order = Order.get_order(client._session, account.account_number, order_id)
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            status = order.status
            filled = order.filled_quantity
            total = order.quantity
            
            print(f"[{timestamp}] Status: {status:<12} | Filled: {filled}/{total}", end="")
            
            if filled > 0:
                print(f" | Avg Price: ${order.average_fill_price:.2f}")
            else:
                print()
            
            # Check completion
            if status == "Filled":
                print("\n✅ ORDER FULLY EXECUTED!")
                print(f"   Filled Quantity: {filled}")
                print(f"   Average Price: ${order.average_fill_price:.2f}")
                print(f"   Total Value: ${order.average_fill_price * filled:.2f}")
                return True
            
            elif status in ["Cancelled", "Rejected", "Expired"]:
                print(f"\n❌ ORDER {status.upper()}")
                return False
            
            # Wait before next check
            time.sleep(3)
        
        # Timeout
        print(f"\n⏰ TIMEOUT REACHED ({timeout}s)")
        print("Order is still pending. Check manually later.")
        return False
        
    except Exception as e:
        print(f"\n❌ Monitoring error: {e}")
        return False


def check_positions_after_order(client: TastytradeClient, expected_symbol: str):
    """Verify that an order resulted in a position."""
    print("\n" + "=" * 70)
    print("📊 POSITION VERIFICATION")
    print("=" * 70 + "\n")
    
    try:
        positions = client.get_positions()
        
        # Look for matching positions
        matching = [p for p in positions if expected_symbol in p.symbol]
        
        if matching:
            print(f"✅ Found {len(matching)} position(s) for {expected_symbol}:\n")
            for pos in matching:
                print(f"   Symbol: {pos.symbol}")
                print(f"   Quantity: {pos.quantity}")
                print(f"   Market Value: ${pos.market_value:.2f}")
                print()
        else:
            print(f"⚠️ No positions found for {expected_symbol}")
            print("   Order may not have filled yet, or was cancelled.")
        
    except Exception as e:
        print(f"❌ Error checking positions: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Check Tastytrade order execution status"
    )
    parser.add_argument(
        "--order-id",
        help="Specific order ID to check"
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Monitor order until filled (requires --order-id)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout for monitoring in seconds (default: 120)"
    )
    parser.add_argument(
        "--verify-position",
        help="Verify position exists for symbol (e.g., SPY)"
    )
    
    args = parser.parse_args()
    
    # Initialize client
    print("\n🔐 Connecting to Tastytrade...")
    client = TastytradeClient()
    client.connect()
    print("✅ Connected\n")
    
    # Execute requested action
    if args.monitor:
        if not args.order_id:
            print("❌ Error: --monitor requires --order-id")
            sys.exit(1)
        monitor_order_until_filled(client, args.order_id, args.timeout)
    
    elif args.order_id:
        check_specific_order(client, args.order_id)
    
    elif args.verify_position:
        check_positions_after_order(client, args.verify_position)
    
    else:
        # Default: check all live orders
        check_all_live_orders(client)
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
