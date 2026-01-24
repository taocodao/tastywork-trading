
import os
import sys
import logging
from dotenv import load_dotenv
from tastytrade import Session, Account

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load env
load_dotenv()

username = os.getenv('TASTYTRADE_USERNAME')
password = os.getenv('TASTYTRADE_PASSWORD')
use_sandbox = os.getenv('TASTYTRADE_USE_SANDBOX', 'true').lower() == 'true'

print(f"Testing with: User={username}, Sandbox={use_sandbox}")

try:
    print("Attempting to connect...")
    session = Session(username, password, is_test=use_sandbox)
    print("Session created successfully!")
    
    accounts = Account.get(session)
    print(f"Found {len(accounts)} accounts")
    
    if accounts:
        acc = accounts[0]
        print(f"Account Number: {acc.account_number}")
        balances = acc.get_balances(session)
        print(f"Net Liquidating Value: {balances.net_liquidating_value}")

except Exception as e:
    print("="*50)
    print("AUTHENTICATION FAILED")
    print("="*50)
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {e}")
    import traceback
    traceback.print_exc()
