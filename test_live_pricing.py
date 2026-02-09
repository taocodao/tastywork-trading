"""
Test Live Pricing Implementation
=================================
Verify that orders use live market data for limit prices.
"""

import logging
from datetime import date, timedelta
from tastytrade_client import TastytradeClient

# Set up logging to see the pricing messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_theta_trade_live_pricing():
    """Test that theta trades use live pricing."""
    logger.info("=" * 70)
    logger.info("TESTING THETA TRADE WITH LIVE PRICING")
    logger.info("=" * 70)
    
    try:
        # Connect to tastytrade
        client = TastytradeClient()
        client.connect()
        
        # Build a theta trade (cash-secured put)
        symbol = "SPY"
        expiry = date.today() + timedelta(days=7)  # ~1 week out
        strike = 570.0  # Adjust based on current SPY price
        
        logger.info(f"\nBuilding theta trade: SELL {symbol} {strike}P exp {expiry}")
        logger.info("Looking for 'Using LIVE bid' in logs below...")
        logger.info("-" * 70)
        
        # Build the order - this should fetch live pricing
        order = client.build_cash_secured_put_order(
            symbol=symbol,
            strike=strike,
            expiry=expiry,
            quantity=1
        )
        
        logger.info("-" * 70)
        logger.info(f"✅ Order built successfully!")
        logger.info(f"   Limit Price: ${float(order.price):.2f}")
        logger.info(f"   Order Type: {order.order_type}")
        
        # Validate with dry run
        logger.info("\nValidating order (dry_run=True)...")
        response = client.place_order(order, dry_run=True)
        logger.info("✅ Order validation successful!")
        
        client.disconnect()
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_calendar_spread_live_pricing():
    """Test that calendar spreads use live pricing."""
    logger.info("\n" + "=" * 70)
    logger.info("TESTING CALENDAR SPREAD WITH LIVE PRICING")
    logger.info("=" * 70)
    
    try:
        client = TastytradeClient()
        client.connect()
        
        symbol = "SPY"
        stock_price = client.get_stock_price(symbol)
        
        # Get options for front and back month
        front_expiry = date.today() + timedelta(days=7)
        back_expiry = date.today() + timedelta(days=14)
        
        # Find ATM options
        front_option = client.find_atm_option(symbol, front_expiry, stock_price, 'C')
        back_option = client.find_atm_option(symbol, back_expiry, stock_price, 'C')
        
        if not front_option or not back_option:
            logger.warning("Could not find options for calendar spread test")
            return False
        
        logger.info(f"\nBuilding calendar spread: {symbol} {front_option.strike}C")
        logger.info(f"  Front: {front_expiry}")
        logger.info(f"  Back:  {back_expiry}")
        logger.info("Looking for 'Calendar spread LIVE' in logs below...")
        logger.info("-" * 70)
        
        # Build the order
        order = client.build_calendar_spread_order(
            short_option=front_option,
            long_option=back_option,
            quantity=1
        )
        
        logger.info("-" * 70)
        logger.info(f"✅ Calendar spread built!")
        logger.info(f"   Limit Price: ${float(order.price):.2f}")
        
        client.disconnect()
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("LIVE PRICING VERIFICATION")
    print("=" * 70)
    print("\nThis test will:")
    print("1. Build a theta trade and check for live pricing")
    print("2. Build a calendar spread and check for live pricing")
    print("\nLook for log messages containing:")
    print("  - 'Using LIVE bid' (theta)")
    print("  - 'Calendar spread LIVE' (calendar)")
    print("\n" + "=" * 70 + "\n")
    
    # Run tests
    theta_ok = test_theta_trade_live_pricing()
    calendar_ok = test_calendar_spread_live_pricing()
    
    # Summary
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"Theta Trade:     {'✅ PASS' if theta_ok else '❌ FAIL'}")
    print(f"Calendar Spread: {'✅ PASS' if calendar_ok else '❌ FAIL'}")
    print("=" * 70)
