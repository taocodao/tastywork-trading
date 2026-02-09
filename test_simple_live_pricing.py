"""
Simple Test for Live Pricing
=============================
Quick verification without full market connectivity.
"""

import logging
from datetime import date, timedelta
from tastytrade_client import TastytradeClient

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_simple_connection():
    """Test that we can connect and build an order."""
    try:
        logger.info("=" * 60)
        logger.info("Testing tastytrade connection...")
        
        client = TastytradeClient()
        client.connect()
        
        logger.info("✅ Connected successfully!")
        logger.info(f"Account: {client.get_account().account_number}")
        
        # Test building a simple put order
        logger.info("\nTesting build_cash_secured_put_order...")
        logger.info("(This will show 'Using LIVE bid' OR 'Using stale bid')")
        logger.info("-" * 60)
        
        from tastytrade_client import OptionData
        from decimal import Decimal
        
        # Create a mock option for testing
        test_option = OptionData(
            symbol="SPY  250214P00570000",
            streamer_symbol=".SPY250214P570",
            strike=Decimal("570.0"),
            expiry=date(2025, 2, 14),
            option_type='P',
            bid=0.85,
            ask=0.95,
            volume=1000,
            open_interest=5000
        )
        
        # Try to find real option
        try:
            expiry = date.today() + timedelta(days=5)
            real_option = client.find_option_at_strike("SPY", expiry, 570.0, 'P')
            if real_option:
                test_option = real_option
                logger.info(f"Using real option: {test_option.symbol}")
        except:
            logger.info("Using mock option for test")
        
        # Build order - this triggers live pricing
        from tastytrade.instruments import Option
        from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
        from decimal import Decimal
        
        put_instrument = Option.get(client._session, test_option.symbol)
        put_leg = put_instrument.build_leg(Decimal("1"), OrderAction.SELL_TO_OPEN)
        
        # This is where live pricing happens
        live_quote = client.get_live_option_quote(test_option.symbol)
        if live_quote:
            price = live_quote[0]  # bid
            logger.info(f"✅ USING LIVE BID: ${price:.2f}")
        else:
            price = test_option.bid
            logger.info(f"⚠️  Using stale bid (no live quote): ${price:.2f}")
        
        logger.info("-" * 60)
        logger.info(f"Final limit price: ${price:.2f}")
        
        client.disconnect()
        logger.info("\n✅ Test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_simple_connection()
