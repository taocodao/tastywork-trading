"""
Test the market close expiration logic to ensure it's working correctly
"""
from datetime import datetime, timedelta

def get_market_close_time(date):
    """Python version of the market close logic"""
    year = date.year
    month = date.month
    day = date.day
    
    # Create market close time: 4:00 PM ET on the same day
    # This creates a NAIVE datetime (no timezone info)
    market_close = datetime(year, month, day, 16, 0, 0, 0)
    
    # The JavaScript version tries to adjust for ET timezone
    # ET is UTC-5 (standard) or UTC-4 (daylight)
    # But this logic is WRONG - it's double-adjusting
    
    print(f"  Market close (naive): {market_close}")
    print(f"  Market close timestamp: {market_close.timestamp() * 1000}")
    
    return market_close

def is_signal_expired_js_logic(created_at):
    """Replicate the JavaScript logic"""
    if not created_at:
        return True
    
    created_time = created_at if isinstance(created_at, datetime) else datetime.fromisoformat(created_at.replace('Z', '+00:00'))
    market_close = get_market_close_time(created_time)
    now = datetime.now()
    
    print(f"\n  Created: {created_time}")
    print(f"  Market Close: {market_close}")
    print(f"  Now: {now}")
    print(f"  Expired: {now > market_close}")
    
    return now > market_close

# Test with signals from the database
print("\n" + "="*80)
print("Testing Market Close Expiration Logic")
print("="*80)

# Test 1: Signal from Feb 10 (yesterday) should be expired
print("\n1. Signal from yesterday (Feb 10, 5:02 PM):")
signal1_time = datetime(2026, 2, 10, 17, 2, 34)
is_signal_expired_js_logic(signal1_time)

# Test 2: Signal from today before market close
print("\n2. Signal from today (Feb 11, 10:00 AM):")
signal2_time = datetime(2026, 2, 11, 10, 0, 0)
is_signal_expired_js_logic(signal2_time)

# Test 3: Signal from today after market close
print("\n3. Signal from today (Feb 11, 5:00 PM):")
signal3_time = datetime(2026, 2, 11, 17, 0, 0)
is_signal_expired_js_logic(signal3_time)

print("\n" + "="*80)
print("Current time:", datetime.now())
print("Market close for today:", get_market_close_time(datetime.now()))
print("="*80)
