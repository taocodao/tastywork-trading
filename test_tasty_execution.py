from google_secrets import create_or_update_secret
import os
import getpass
from dotenv import load_dotenv
import logging
from tastytrade import Session, Account
from tastytrade.instruments import Equity

load_dotenv()


def test_tastytrade():
    log("Testing Tastytrade API Connection...")
    
    # 1. Get OAuth Credentials
    client_secret = os.getenv("TASTYTRADE_CLIENT_SECRET")
    refresh_token = os.getenv("TASTYTRADE_REFRESH_TOKEN")
    
    if not client_secret or not refresh_token:
        log("❌ Missing OAuth credentials in environment (TASTYTRADE_CLIENT_SECRET, TASTYTRADE_REFRESH_TOKEN)")
        log("Please check .env file.")
        return
            
    if not client_secret or not refresh_token:
        log("❌ Missing OAuth credentials (CLIENT_SECRET, REFRESH_TOKEN)")
        return

    session = None

    try:
        log(f"Attempting OAuth login...")
        # Note: In SDK 11+, Session() accepts (client_secret, refresh_token) as arguments 
        # but treats them as OAuth credentials if they look like it, or we use explicit params.
        # Actually proper usage is often just passing them to Session constructor directly.
        session = Session(client_secret, refresh_token)
        log("✅ OAuth Session created successfully!")
        log("Authenticated!")
        
    except Exception as auth_err:
        log(f"❌ AUTH FAILED: {auth_err}")
        import traceback
        log(traceback.format_exc())
        return

    try:    
        # 3. Fetch Accounts
        accounts = Account.get(session)
        if not accounts:
            log("❌ No accounts found.")
            return
            
        account = accounts[0]
        log(f"✅ Found Account: {account.account_number}")
        
        # 4. Get Balances
        balances = account.get_balances(session)
        log(f"💰 Net Liquidating Value: ${balances.net_liquidating_value}")
        
        # 5. Symbol Check (Pre-Trade Validation)
        symbol = "SPY"
        equity = Equity.get_equity(session, symbol)
        log(f"✅ Symbol lookup confirmed: {equity.symbol} - {equity.description}")
        
        log("All systems GO for trading! 🚀")
        
    except Exception as e:
        log(f"❌ Tastytrade Test Failed: {e}")
        import traceback
        log(traceback.format_exc())

def log(msg):
    try:
        with open("tasty_test.log", "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")
    except Exception:
        pass 

if __name__ == "__main__":
    # Clear log
    with open("tasty_test.log", "w") as f:
        f.write("--- TEST STARTED ---\n")
    
    try:
        log("Entering main block...")
        test_tastytrade()
        log("--- TEST FINISHED ---")
    except Exception as e:
        log(f"CRITICAL CRASH IN MAIN: {e}")
        import traceback
        log(traceback.format_exc())
