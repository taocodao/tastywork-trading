"""Quick IB Gateway Connection Test - Local or EC2"""
from ib_insync import *
import sys

# Try both local and EC2 connections
IB_HOSTS = [
    ('127.0.0.1', 4001, 'Local Paper Trading'),
    ('127.0.0.1', 7496, 'Local Live Trading'),
    ('34.203.194.137', 4002, 'EC2 IB Gateway (Port 4002)'),
    ('34.203.194.137', 4004, 'EC2 IB Gateway (Port 4004)'),
]

print("Testing IB Gateway connections...\n")

for host, port, name in IB_HOSTS:
    try:
        print(f"Trying {name} ({host}:{port})...")
        ib = IB()
        ib.connect(host, port, clientId=1, timeout=5)
        
        # Get account info
        account = ib.managedAccounts()[0]
        print(f"  ✅ Connected!")
        print(f"     Account: {account}")
        
        # Get account value
        portfolio = ib.accountValues()
        nav = [v for v in portfolio if v.tag == 'NetLiquidation'][0]
        print(f"     Account Value: ${float(nav.value):,.2f}")
        
        # Test market data
        spy = Stock('SPY', 'SMART', 'USD')
        ib.qualifyContracts(spy)
        ticker = ib.reqMktData(spy)
        ib.sleep(2)
        
        if ticker.last:
            print(f"     Market Data: SPY @ ${ticker.last}")
        
        ib.disconnect()
        print(f"  ✅ {name} is working!\n")
        sys.exit(0)  # Success, exit
        
    except Exception as e:
        print(f"  ❌ Failed: {str(e)[:50]}\n")
        continue

print("❌ No IB Gateway connection available")
print("\nTo connect to EC2 IB Gateway:")
print("1. Get EC2 public IP address")
print("2. Ensure port 4001 is open in security group")
print("3. Update IB_HOSTS list above with EC2 IP")
