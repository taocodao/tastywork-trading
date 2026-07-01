#!/usr/bin/env python3
"""
Live Position Checker — Username/Password Auth
Uses direct username/password auth since the refresh token is expired.
"""
import os, sys, getpass
from dotenv import load_dotenv
load_dotenv(r"D:\Projects\tastywork-trading-1\.env")
sys.path.insert(0, r"D:\Projects\tastywork-trading-1")

USERNAME = input("TastyTrade username (email): ").strip()
PASSWORD = getpass.getpass("TastyTrade password: ")

print("\nConnecting...")
try:
    from tastytrade import Session
    session = Session(USERNAME, PASSWORD)
    print(f"Session created: {getattr(session, 'session_token', 'ok')[:20]}...")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

from tastytrade import Account
from tastytrade_utils import _get_accounts_safe
accounts = _get_accounts_safe(session)
print(f"Found {len(accounts)} accounts:")
for a in accounts:
    print(f"  {a.account_number}")

# Pick x5WI28023
account = next((a for a in accounts if a.account_number == "x5WI28023"), accounts[0])
print(f"\nUsing: {account.account_number}")

# Save the fresh session token to .env for re-use
try:
    new_token = getattr(session, 'session_token', None) or getattr(session, 'token', None)
    if new_token:
        print(f"\nSession token (first 30 chars): {str(new_token)[:30]}...")
except Exception:
    pass

# --- fetch positions ---
positions = account.get_positions(session)
balances  = account.get_balances(session)

nlv  = float(getattr(balances, 'net_liquidating_value', 0) or 0)
cash = float(getattr(balances, 'cash_balance', 0) or 0)
print(f"\nNLV: ${nlv:,.2f}  Cash: ${cash:,.2f}")
print(f"\nAll positions ({len(positions)}):")
for pos in positions:
    sym   = getattr(pos, 'symbol', '')
    qty   = float(getattr(pos, 'quantity', 0) or 0)
    itype = getattr(pos, 'instrument_type', '')
    avg   = float(getattr(pos, 'average_open_price', 0) or 0)
    print(f"  {sym.strip():<45} qty={qty:>+8.2f}  avg=${avg:>8.2f}  type={itype}")
