import os
import sys
import json
from datetime import date
from decimal import Decimal
from dotenv import load_dotenv

# Add iv-switching-composite to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'iv-switching-composite'))

def run_mock_engine():
    load_dotenv()
    refresh_token = os.getenv("TASTYTRADE_REFRESH_TOKEN")
    account_number = os.getenv("TASTYTRADE_ACCOUNT_NUMBER")
    
    if not refresh_token or not account_number:
        print("Missing TastyTrade credentials in .env")
        return
        
    print("1. Authenticating with TastyTrade...")
    from tastytrade_utils import create_user_session, get_user_account
    from tastytrade.order import (
        NewOrder, OrderLeg as TTOrderLeg, OrderAction, OrderType,
        OrderTimeInForce, PriceEffect
    )
    
    session = create_user_session(refresh_token)
    account = get_user_account(session, account_number)
    print(f"✅ Account loaded: {account.account_number}")
    
    # 2. Mock IV-Switching Signal & Account State
    print("\n2. Mocking IV-Switching Signal for a Bullish ZEBRA on TQQQ...")
    mock_signal = {
        "trade_date": date.today(),
        "mode": "BULL",
        "tqqq_px": 85.0, # Approximate current TQQQ price
        "iv_tqqq_10d": 0.50,
        "rf": 0.04
    }
    
    balances = account.get_balances(session)
    mock_account_state = {
        "cash": float(getattr(balances, 'cash_balance', 10000)),
        "nlv": float(getattr(balances, 'net_liquidating_value', 10000)),
        "buying_power": float(getattr(balances, 'derivative_buying_power', 10000)),
        "position_counts": {
            "zebra": 0, "csp": 0, "ccs": 0, "sqqq": 0, "pmcc": 0
        }
    }
    
    # 3. Generate Order using the real IV-Switching logic
    print("\n3. Generating Order via IV-Switching Engine...")
    from daily_order_generator import reconcile_and_generate_order
    order = reconcile_and_generate_order(mock_signal, mock_account_state)
    
    print(f"✅ Signal Type: {order.get('signal_type')}")
    print(f"✅ Target Strike Price: {order.get('limit_price')}")
    
    if not order.get("order_legs"):
        print("❌ No order legs generated!")
        return
        
    print(f"✅ Order Legs:\n{json.dumps(order['order_legs'], indent=2)}")
    
    # 4. Map to TastyTrade order structure (identical to _place_iv_order_internal)
    print("\n4. Translating to TastyTrade API format...")
    _action_map = {
        "BUY_TO_OPEN":   OrderAction.BUY_TO_OPEN,
        "SELL_TO_OPEN":  OrderAction.SELL_TO_OPEN,
    }
    
    legs = []
    for leg in order['order_legs']:
        action = _action_map.get(leg['action'])
        legs.append(TTOrderLeg(
            instrument_type='Equity Option',
            symbol=leg['symbol'],
            quantity=leg['qty'],
            action=action
        ))
        
    price_effect = PriceEffect.DEBIT # ZEBRA is a debit spread
    limit_px = Decimal(str(round(order.get('limit_price', 1.0), 2)))
    
    tt_order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.LIMIT,
        legs=legs,
        price=limit_px,
        price_effect=price_effect
    )
    
    # 5. Place Dry Run Order
    print(f"\n5. Submitting Dry-Run Order to TastyTrade (Price: {limit_px} {price_effect})...")
    try:
        response = account.place_order(session, tt_order, dry_run=True)
        print("\n🏆 --- DRY RUN SUCCESSFUL! --- 🏆")
        print("TastyTrade API accepted the IV-Switching order structure perfectly.")
        if hasattr(response, 'warnings') and response.warnings:
            print(f"Warnings: {response.warnings}")
        if hasattr(response, 'buying_power_effect'):
            print(f"Buying Power Effect: ${response.buying_power_effect.value}")
    except Exception as e:
        print("\n❌ --- DRY RUN FAILED --- ❌")
        print(f"TastyTrade threw an error: {e}")

if __name__ == "__main__":
    run_mock_engine()
