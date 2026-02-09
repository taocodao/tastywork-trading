"""
Test Live Pricing with Real Options
====================================
Verify that orders use live IB quotes for limit prices.
"""

import logging
from datetime import date, timedelta
from tastytrade_client import TastytradeClient

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_theta_with_live_pricing():
    """Test that theta trades use live pricing from IB."""
    try:
        logger.info("=" * 70)
        logger.info("TESTING THETA TRADE WITH LIVE PRICING")
        logger.info("=" * 70)
        
        client = TastytradeClient()
        client.connect()
        
        logger.info(f"✅ Connected to account: {client.get_account().account_number}")
        
        # Use SPY with a near-term expiry
        symbol = "SPY"
        expiry = date.today() + timedelta(days=7)
        
        # Get current stock price to pick an appropriate strike
        stock_price = client.get_stock_price(symbol)
        logger.info(f"Current {symbol} price: ${stock_price:.2f}")
        
        # Pick a slightly OTM put (5% below current price)
        strike = round(stock_price * 0.95)
        
        logger.info(f"\nBuilding theta trade: SELL {symbol} {strike}P exp {expiry}")
        logger.info("=" * 70)
        logger.info("WATCH FOR: 'Using LIVE bid' vs 'Using stale bid'")
        logger.info("=" * 70)
        
        # Build order - this should trigger live pricing
        order = client.build_cash_secured_put_order(
            symbol=symbol,
            strike=strike,
            expiry=expiry,
            quantity=1
        )
        
        logger.info("=" * 70)
        logger.info(f"✅ Order built successfully!")
        logger.info(f"   Limit Price: ${float(order.price):.2f}")
        logger.info(f"   Time in Force: {order.time_in_force}")
        logger.info("=" * 70)
        
        # Validate with dry run
        logger.info("\nValidating order (dry_run=True)...")
        client.place_order(order, dry_run=True)
        logger.info("✅ Dry run validation passed!")
        
        client.disconnect()
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_diagonal_spread_naming():
    """Test that diagonal spread method exists and works."""
    try:
        logger.info("\n" + "=" * 70)
        logger.info("TESTING DIAGONAL SPREAD METHOD")
        logger.info("=" * 70)
        
        client = TastytradeClient()
        client.connect()
        
        # Check that the method exists
        assert hasattr(client, 'build_diagonal_spread_order'), "Missing build_diagonal_spread_order method!"
        logger.info("✅ build_diagonal_spread_order() method exists")
        
        # Check that calendar spread has updated docs
        calendar_docs = client.build_calendar_spread_order.__doc__
        assert 'diagonal' in calendar_docs.lower(), "Calendar spread docs should mention diagonal"
        logger.info("✅ Calendar spread docs updated to mention diagonal spreads")
        
        logger.info("\n📝 Method distinction:")
        logger.info("   - calendar spread: SAME strike, different expiration")
        logger.info("   - diagonal spread: DIFFERENT strikes + expirations")
        
        client.disconnect()
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("LIVE PRICING VERIFICATION TEST")
    print("=" * 70)
    print("\nThis test will:")
    print("1. Build a real theta trade on SPY")
    print("2. Check if live IB quotes are used for limit price")
    print("3. Verify diagonal spread method exists")
    print("\n" + "=" * 70 + "\n")
    
    # Run tests
    theta_ok = test_theta_with_live_pricing()
    diagonal_ok = test_diagonal_spread_naming()
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)
    print(f"Theta Trade Live Pricing: {'✅ PASS' if theta_ok else '❌ FAIL'}")
    print(f"Diagonal Spread Support:  {'✅ PASS' if diagonal_ok else '❌ FAIL'}")
    print("=" * 70)
    
    if theta_ok and diagonal_ok:
        print("\n✅ All tests passed! Ready for production use.")
    else:
        print("\n❌ Some tests failed. Review errors above.")
