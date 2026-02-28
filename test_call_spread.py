import asyncio
import logging
from src.tqqq.order_manager import TQQQOrderManager

logging.basicConfig(level=logging.INFO)

async def test_call_spread():
    # Initialize the order manager (it will run without actual Tastytrade credentials if mock is built in,
    # or we can just trace the print output)
    manager = TQQQOrderManager()
    
    print("Testing call spread order generation...")
    # This should internally call _make_tqqq_call for both legs
    try:
        # Testing the place_call_spread_order method added in Step 1
        await manager.place_call_spread_order(
            short_strike=80.0,
            long_strike=85.0,
            expiration="2026-03-20",
            quantity=1,
            account_id="MOCK_TEST_ACCOUNT"
        )
        print("SUCCESS: place_call_spread_order ran without exceptions.")
    except Exception as e:
        print(f"FAILED place_call_spread_order: {e}")

    print("\nTesting call spread closing...")
    try:
        await manager.close_call_spread_order(
            short_strike=80.0,
            long_strike=85.0,
            expiration="2026-03-20",
            quantity=1,
            account_id="MOCK_TEST_ACCOUNT"
        )
        print("SUCCESS: close_call_spread_order ran without exceptions.")
    except Exception as e:
        print(f"FAILED close_call_spread_order: {e}")

if __name__ == "__main__":
    asyncio.run(test_call_spread())
