"""
Debug script for Tastytrade option chain access.
Tests OAuth refresh fix and direct REST API fallback.
"""
import logging
import sys
from datetime import date, timedelta

# Configure verbose logging
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_option_chain():
    with open('verify_output.txt', 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("Tastytrade Option Chain Diagnostic Test\n")
        f.write("=" * 60 + "\n\n")
        
        try:
            from tastytrade_client import TastytradeClient
            
            f.write("1. Initializing TastytradeClient...\n")
            client = TastytradeClient()
            
            f.write("2. Connecting...\n")
            client.connect()
            
            f.write(f"   Mode: {'SANDBOX' if client.use_sandbox else 'PRODUCTION'}\n")
            f.write(f"   Connected: {client.is_connected}\n")
            
            # Test stock price first
            f.write("\n3. Testing stock price fetch...\n")
            try:
                price = client.get_stock_price('SPY')
                f.write(f"   SPY Price: ${price:.2f}\n")
            except Exception as e:
                f.write(f"   ERROR: {e}\n")
            
            # Force session refresh (THE KEY FIX)
            f.write("\n4. Forcing OAuth session refresh...\n")
            try:
                client._session.refresh()
                f.write("   Session refreshed successfully!\n")
            except Exception as e:
                f.write(f"   Refresh failed: {e}\n")
            
            # Test SDK method
            f.write("\n5. Testing get_option_chain() via SDK...\n")
            try:
                chain = client.get_option_chain('SPY')
                chain_dates = list(chain.keys())
                f.write(f"   Chain dates found: {len(chain_dates)}\n")
                if chain_dates:
                    f.write(f"   First 5: {[d.strftime('%Y-%m-%d') for d in chain_dates[:5]]}\n")
            except Exception as e:
                f.write(f"   SDK Error: {e}\n")
                import traceback
                traceback.print_exc(file=f)
            
            # Test direct REST API
            f.write("\n6. Testing direct REST API...\n")
            try:
                response = client._session.get('/option-chains/SPY/nested')
                f.write(f"   Response type: {type(response)}\n")
                if response and 'data' in response:
                    items = response['data'].get('items', [])
                    f.write(f"   Items count: {len(items)}\n")
                    if items:
                        expirations = items[0].get('expirations', [])
                        f.write(f"   Expirations count: {len(expirations)}\n")
                        if expirations:
                            f.write(f"   First expiration: {expirations[0].get('expiration-date')}\n")
                            f.write("   SUCCESS! Direct API returns data.\n")
                        else:
                            f.write("   FAIL: No expirations in response.\n")
                    else:
                        f.write("   FAIL: No items in response.\n")
                else:
                    f.write(f"   FAIL: Unexpected response format: {response}\n")
            except Exception as e:
                f.write(f"   Direct API Error: {e}\n")
                import traceback
                traceback.print_exc(file=f)
            
            # Test NestedOptionChain alternative
            f.write("\n7. Testing NestedOptionChain alternative...\n")
            try:
                from tastytrade.instruments import NestedOptionChain
                nested_chain = NestedOptionChain.get(client._session, 'SPY')
                f.write(f"   Root symbol: {nested_chain.root_symbol}\n")
                f.write(f"   Expirations: {len(nested_chain.expirations)}\n")
                if nested_chain.expirations:
                    f.write(f"   First exp: {nested_chain.expirations[0].expiration_date}\n")
                    f.write("   SUCCESS! NestedOptionChain works.\n")
            except Exception as e:
                f.write(f"   NestedOptionChain Error: {e}\n")
            
            f.write("\n" + "=" * 60 + "\n")
            f.write("Diagnostic Complete\n")
            f.write("=" * 60 + "\n")
            
        except Exception as e:
            f.write(f"FATAL ERROR: {e}\n")
            import traceback
            traceback.print_exc(file=f)

if __name__ == "__main__":
    test_option_chain()
    print("Results written to verify_output.txt")
