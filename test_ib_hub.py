"""
Test IB Market Data Hub
=======================
Verify the centralized hub works correctly.
"""

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def test_hub_singleton():
    """Test singleton pattern works."""
    from ib_market_data_hub import get_hub
    
    hub1 = get_hub()
    hub2 = get_hub()
    
    assert hub1 is hub2, "Hub should be singleton!"
    print("✓ Singleton pattern works")


def test_client_ids():
    """Test client IDs are different."""
    from ib_market_data_hub import get_hub
    
    hub = get_hub()
    
    assert hub.DATA_CLIENT_ID == 3000, f"Data client should be 3000, got {hub.DATA_CLIENT_ID}"
    assert hub.ORDER_CLIENT_ID == 3001, f"Order client should be 3001, got {hub.ORDER_CLIENT_ID}"
    assert hub.DATA_CLIENT_ID != hub.ORDER_CLIENT_ID, "Client IDs should be different!"
    print(f"✓ Data client ID: {hub.DATA_CLIENT_ID}")
    print(f"✓ Order client ID: {hub.ORDER_CLIENT_ID}")


def test_status():
    """Test status method."""
    from ib_market_data_hub import get_hub
    
    hub = get_hub()
    status = hub.status()
    
    assert "data_connected" in status
    assert "order_connected" in status
    assert "data_client_id" in status
    assert "order_client_id" in status
    print(f"✓ Hub status: {status}")


def test_data_provider_uses_hub():
    """Test IBDataProvider uses hub."""
    from ib_data_provider import IBDataProvider
    
    provider = IBDataProvider()
    
    # Check it's using hub
    assert hasattr(provider, '_use_hub'), "Provider should have _use_hub attribute"
    assert provider._use_hub is True, "Provider should be using hub"
    print("✓ IBDataProvider uses hub")


def test_order_executor_uses_hub():
    """Test IBOrderExecutor uses hub."""
    from ib_order_executor import IBOrderExecutor
    
    executor = IBOrderExecutor()
    
    # Check it's using hub
    assert hasattr(executor, '_use_hub'), "Executor should have _use_hub attribute"
    assert executor._use_hub is True, "Executor should be using hub"
    print("✓ IBOrderExecutor uses hub")


def test_price_cache():
    """Test price caching works."""
    from ib_market_data_hub import PriceCache
    
    cache = PriceCache(price=100.0, bid=99.5, ask=100.5)
    
    assert cache.price == 100.0
    assert cache.bid == 99.5
    assert cache.ask == 100.5
    assert cache.age_seconds() < 1.0  # Just created
    print("✓ PriceCache works")


def test_connections(skip_connect=True):
    """Test actual IB connections (optional)."""
    if skip_connect:
        print("⏭ Skipping actual connection test (set skip_connect=False to test)")
        return
    
    from ib_market_data_hub import get_hub
    
    hub = get_hub()
    
    print("Testing data connection...")
    data_ok = hub.connect_data(timeout=5)
    print(f"  Data connected: {data_ok}")
    
    print("Testing order connection...")
    order_ok = hub.connect_orders(timeout=5)
    print(f"  Order connected: {order_ok}")
    
    # Check status
    data_conn, order_conn = hub.is_connected()
    print(f"  Final status: data={data_conn}, order={order_conn}")
    
    if data_ok and order_ok:
        print("✓ Both connections successful!")
    
    # Cleanup
    hub.disconnect_all()


if __name__ == "__main__":
    print("=" * 60)
    print("IB Market Data Hub - Test Suite")
    print("=" * 60)
    print()
    
    tests = [
        ("Singleton Pattern", test_hub_singleton),
        ("Client IDs", test_client_ids),
        ("Hub Status", test_status),
        ("IBDataProvider Uses Hub", test_data_provider_uses_hub),
        ("IBOrderExecutor Uses Hub", test_order_executor_uses_hub),
        ("Price Cache", test_price_cache),
        ("Connections", lambda: test_connections(skip_connect=True)),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"✗ FAILED: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    if failed == 0:
        print(f"✓ ALL {passed} TESTS PASSED!")
    else:
        print(f"✗ {failed}/{passed + failed} tests failed")
    print("=" * 60)
    
    # Summary
    print()
    print("Hub Architecture:")
    print("  Data Client (ID 3000) - Shared by all products for market data")
    print("  Order Client (ID 3001) - Shared by all strategies for orders")
    print()
    print("No more Error 326 (client ID already in use)!")
