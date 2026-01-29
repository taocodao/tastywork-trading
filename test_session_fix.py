"""
Test script to verify the tastytrade_utils module and session creation fix.
This validates that the missing function has been properly replaced.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all imports work correctly."""
    print("=" * 60)
    print("Testing imports...")
    print("=" * 60)
    
    try:
        from tastytrade_utils import create_user_session, get_user_account, get_all_user_accounts
        print("✅ Successfully imported tastytrade_utils functions")
        print(f"   - create_user_session: {create_user_session}")
        print(f"   - get_user_account: {get_user_account}")
        print(f"   - get_all_user_accounts: {get_all_user_accounts}")
    except ImportError as e:
        print(f"❌ Failed to import tastytrade_utils: {e}")
        return False
    
    try:
        # This will fail if there are syntax errors in tasty_api_server.py
        import tasty_api_server
        print("✅ Successfully imported tasty_api_server")
    except Exception as e:
        print(f"❌ Failed to import tasty_api_server: {e}")
        return False
    
    return True


def test_function_signature():
    """Test that the functions have expected signatures."""
    print("\n" + "=" * 60)
    print("Testing function signatures...")
    print("=" * 60)
    
    from tastytrade_utils import create_user_session, get_user_account
    import inspect
    
    # Check create_user_session
    sig = inspect.signature(create_user_session)
    params = list(sig.parameters.keys())
    print(f"✅ create_user_session parameters: {params}")
    assert 'refresh_token' in params, "Missing 'refresh_token' parameter"
    
    # Check get_user_account
    sig = inspect.signature(get_user_account)
    params = list(sig.parameters.keys())
    print(f"✅ get_user_account parameters: {params}")
    assert 'session' in params, "Missing 'session' parameter"
    assert 'account_number' in params, "Missing 'account_number' parameter"
    
    return True


def test_error_handling():
    """Test that functions raise appropriate errors."""
    print("\n" + "=" * 60)
    print("Testing error handling...")
    print("=" * 60)
    
    from tastytrade_utils import create_user_session
    
    # Test with missing environment variable
    original_secret = os.environ.get('TASTYTRADE_CLIENT_SECRET')
    if original_secret:
        del os.environ['TASTYTRADE_CLIENT_SECRET']
    
    try:
        create_user_session("fake_token")
        print("❌ Should have raised ValueError for missing CLIENT_SECRET")
        return False
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")
    finally:
        if original_secret:
            os.environ['TASTYTRADE_CLIENT_SECRET'] = original_secret
    
    return True


def verify_server_code():
    """Verify that tasty_api_server.py doesn't reference the old function."""
    print("\n" + "=" * 60)
    print("Verifying server code...")
    print("=" * 60)
    
    with open('tasty_api_server.py', 'r') as f:
        content = f.read()
    
    # Check that old function is NOT called
    if 'get_user_oauth_session(' in content:
        print("❌ Found reference to old get_user_oauth_session() function!")
        return False
    else:
        print("✅ No references to old get_user_oauth_session() function")
    
    # Check that new functions ARE imported
    if 'from tastytrade_utils import' in content:
        print("✅ Found import of tastytrade_utils")
    else:
        print("❌ Missing import of tastytrade_utils!")
        return False
    
    # Check that new functions ARE used
    if 'create_user_session(' in content:
        print("✅ Found usage of create_user_session()")
    else:
        print("❌ Missing usage of create_user_session()!")
        return False
    
    if 'get_user_account(' in content:
        print("✅ Found usage of get_user_account()")
    else:
        print("❌ Missing usage of get_user_account()!")
        return False
    
    return True


def main():
    """Run all verification tests."""
    print("\n🔍 TASTYTRADE SESSION CREATION FIX VERIFICATION")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Import Test", test_imports()))
    
    if results[0][1]:  # Only continue if imports work
        results.append(("Function Signature Test", test_function_signature()))
        results.append(("Error Handling Test", test_error_handling()))
        results.append(("Server Code Verification", verify_server_code()))
    
    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        all_passed = all_passed and passed
    
    print("=" * 60)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("\nThe session creation fix has been successfully implemented:")
        print("  1. tastytrade_utils.py created with shared utilities")
        print("  2. tasty_api_server.py updated to use new utilities")
        print("  3. Missing get_user_oauth_session() replaced")
        print("  4. Multi-user architecture preserved")
        return 0
    else:
        print("❌ SOME TESTS FAILED - Please review the errors above")
        return 1


if __name__ == "__main__":
    exit(main())
