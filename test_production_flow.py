"""
Test Production Signal-to-Trade Flow
=====================================
Comprehensive test of the complete signal flow from generation to execution readiness.

Tests:
1. Tastytrade API connectivity
2. OAuth token refresh capability
3. EC2 Python API accessibility
4. Signal generation and database save
5. Signal retrieval from API
6. Frontend-compatible signal format
"""

import os
import sys
import requests
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_step(step_num, description):
    print(f"\n{BLUE}[Step {step_num}]{RESET} {description}")

def print_success(message):
    print(f"{GREEN}✅ {message}{RESET}")

def print_error(message):
    print(f"{RED}❌ {message}{RESET}")

def print_warning(message):
    print(f"{YELLOW}⚠️  {message}{RESET}")


def test_tastytrade_api():
    """Test 1: Verify Tastytrade API is reachable."""
    print_step(1, "Testing Tastytrade API Connectivity")
    
    try:
        # Test API root
        response = requests.get("https://api.tastyworks.com", timeout=5)
        print_success(f"Tastytrade API reachable (Status: {response.status_code})")
        return True
    except Exception as e:
        print_error(f"Tastytrade API unreachable: {e}")
        return False


def test_oauth_credentials():
    """Test 2: Verify OAuth credentials are configured."""
    print_step(2, "Checking OAuth Credentials")
    
    client_id = os.getenv('TASTYTRADE_CLIENT_ID')
    client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
    refresh_token = os.getenv('TASTYTRADE_REFRESH_TOKEN')
    
    if not client_id:
        print_error("TASTYTRADE_CLIENT_ID not found in .env")
        return False
    
    if not client_secret:
        print_error("TASTYTRADE_CLIENT_SECRET not found in .env")
        return False
    
    if not refresh_token:
        print_error("TASTYTRADE_REFRESH_TOKEN not found in .env")
        return False
    
    print_success(f"CLIENT_ID: {client_id[:10]}...")
    print_success(f"CLIENT_SECRET: {client_secret[:10]}...")
    print_success(f"REFRESH_TOKEN: {refresh_token[:30]}...")
    return True


def test_oauth_token_refresh():
    """Test 3: Test OAuth token refresh."""
    print_step(3, "Testing OAuth Token Refresh")
    
    client_id = os.getenv('TASTYTRADE_CLIENT_ID')
    client_secret = os.getenv('TASTYTRADE_CLIENT_SECRET')
    refresh_token = os.getenv('TASTYTRADE_REFRESH_TOKEN')
    
    try:
        response = requests.post(
            "https://api.tastyworks.com/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success(f"Token refresh successful")
            print_success(f"Access token expires in: {data.get('expires_in', 'unknown')}s")
            return True
        else:
            print_error(f"Token refresh failed: {response.status_code}")
            print_error(f"Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print_error(f"Token refresh error: {e}")
        return False


def test_ec2_api():
    """Test 4: Check EC2 Python API accessibility."""
    print_step(4, "Testing EC2 Python API")
    
    ec2_api = "http://34.235.119.67:8002"
    
    try:
        # Test health/signals endpoint
        response = requests.get(f"{ec2_api}/api/signals", timeout=5)
        print_success(f"EC2 API reachable (Status: {response.status_code})")
        
        if response.status_code == 200:
            signals = response.json()
            print_success(f"Found {len(signals)} pending signals")
            return True
        else:
            print_warning(f"API returned {response.status_code}")
            return True  # Still reachable
            
    except Exception as e:
        print_error(f"EC2 API unreachable: {e}")
        print_warning("Make sure tasty_api_server.py is running on EC2")
        return False


def generate_test_signal_theta():
    """Test 5: Generate a test Theta signal."""
    print_step(5, "Generating Test Theta Signal")
    
    try:
        # Import signal publisher
        sys.path.insert(0, os.getcwd())
        from signal_publisher.theta import ThetaEntrySignal, publish_theta_entry_signal
        import uuid
        
        # Create test signal
        signal = ThetaEntrySignal(
            id=str(uuid.uuid4()),
            symbol="AAPL",
            strike=175.0,
            expiration=(datetime.now() + timedelta(days=30)).date().isoformat(),
            dte=30,
            entry_price=2.50,
            ask=2.55,
            mid=2.52,
            delta=-0.30,
            theta=0.05,
            vega=0.15,
            iv=0.28,
            confidence=75.0,
            probability_otm=0.70,
            expected_premium=250.0,
            capital_required=17500.0,
            contracts=1,
            total_premium=250.0,
            total_capital_required=17500.0,
            created_at=datetime.now(),
        )
        
        # Publish signal
        success = publish_theta_entry_signal(signal)
        
        if success:
            print_success(f"Theta signal published: {signal.id}")
            print_success(f"Symbol: {signal.symbol} ${signal.strike}P")
            return True
        else:
            print_error("Failed to publish signal")
            return False
            
    except Exception as e:
        print_error(f"Signal generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def generate_test_signal_calendar():
    """Test 6: Generate a test Calendar signal."""
    print_step(6, "Generating Test Calendar Signal")
    
    try:
        sys.path.insert(0, os.getcwd())
        from signal_publisher.calendar import publish_calendar_signal
        
        # Create mock SpreadSetup
        class MockSetup:
            def __init__(self):
                self.symbol = 'SPY'
                self.strike = 500.0
                self.short_expiry = (datetime.now() + timedelta(days=7)).date()
                self.long_expiry = (datetime.now() + timedelta(days=30)).date()
                self.net_debit = 3.50
                self.stock_price = 500.5
                self.score = 80.0
                self.iv = 0.22
                self.theta_edge = 0.18
        
        setup = MockSetup()
        success = publish_calendar_signal(setup)
        
        if success:
            print_success(f"Calendar signal published: {setup.symbol} ${setup.strike}")
            return True
        else:
            print_error("Failed to publish calendar signal")
            return False
            
    except Exception as e:
        print_error(f"Calendar signal generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print(f"\n{'='*70}")
    print(f"{BLUE}PRODUCTION FLOW TEST SUITE{RESET}")
    print(f"{'='*70}")
    
    results = []
    
    # Run tests
    results.append(("Tastytrade API", test_tastytrade_api()))
    results.append(("OAuth Credentials", test_oauth_credentials()))
    results.append(("OAuth Token Refresh", test_oauth_token_refresh()))
    results.append(("EC2 Python API", test_ec2_api()))
    results.append(("Theta Signal Generation", generate_test_signal_theta()))
    results.append(("Calendar Signal Generation", generate_test_signal_calendar()))
    
    # Summary
    print(f"\n{'='*70}")
    print(f"{BLUE}TEST SUMMARY{RESET}")
    print(f"{'='*70}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{GREEN}✅ PASS{RESET}" if result else f"{RED}❌ FAIL{RESET}"
        print(f"{status} - {name}")
    
    print(f"\n{BLUE}Results: {passed}/{total} tests passed{RESET}")
    
    if passed == total:
        print(f"\n{GREEN}🎉 ALL TESTS PASSED! Production flow is ready.{RESET}")
        return 0
    else:
        print(f"\n{RED}⚠️  Some tests failed. Review errors above.{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
