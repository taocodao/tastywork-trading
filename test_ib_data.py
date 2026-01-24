import sys

def log(msg):
    print(msg)
    with open("ib_test.log", "a") as f:
        f.write(str(msg) + "\n")

import random
import time
import logging
from ib_insync import *

def test_connection():
    # Enable internal debug logging
    util.logToConsole(level=logging.INFO)
    
    print("\n--- STARTING IB CONNECTION TEST ---")
    ib = IB()
    client_id = random.randint(1000, 9999)
    
    # Try AWS EC2 first on port 4001 (confirmed from docker ps)
    ports_to_try = [
        ("34.235.119.67", 4004, "AWS EC2 Gateway (tradecoinbot) - Port 4004"),
        ("34.235.119.67", 4001, "AWS EC2 Gateway (tradecoinbot) - Port 4001"),
        ("127.0.0.1", 4004, "Local Gateway (Docker) - Port 4004"),
        ("127.0.0.1", 4001, "Local Gateway - Port 4001"),
    ]
    
    connected = False
    for host, port, name in ports_to_try:
        print(f"\nTrying {name} ({host}:{port}) | ClientID: {client_id}")
        try:
            ib.connect(host, port, clientId=client_id, timeout=10)
            print(f"✅ SUCCESS: Connected to {name}!")
            connected = True
            break
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            client_id += 1  # Increment client ID for next attempt
    
    if not connected:
        print("\n❌ Could not connect to any IB Gateway.")
        print("Please ensure IB Gateway is running and API is enabled.")
        return
    
    try:
        symbol = "SPY"
        print(f"\nFetching 5 days of data for {symbol}...")
        stock = Stock(symbol, 'SMART', 'USD')
        
        bars = ib.reqHistoricalData(
            stock,
            endDateTime='',
            durationStr='5 D',
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True
        )
        
        if bars:
            print(f"✅ RECEIVED DATA: {len(bars)} bars")
            print(bars[0])
            print(bars[-1])
        else:
            print("❌ FAILURE: No data received (Check Market Data Subscriptions?)")
            
        ib.disconnect()
        print("--- TEST COMPLETE ---\n")
        
    except Exception as e:
        print("\n❌ DATA FETCH ERROR:")
        print(e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_connection()
