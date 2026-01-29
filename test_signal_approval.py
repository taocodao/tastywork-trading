#!/usr/bin/env python3
"""
Test signal approval end-to-end by calling backend API directly.
This bypasses the frontend to prove the execution flow works.
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# Configuration
BACKEND_URL = "http://34.235.119.67:8002"
SIGNAL_ID = "5a2b9650-8bbd-4c6f-948b-2134fb5f5e55"  # SPY signal in database
REFRESH_TOKEN = os.getenv("TASTYTRADE_REFRESH_TOKEN")
ACCOUNT_NUMBER = os.getenv("TASTYTRADE_ACCOUNT_NUMBER", "5WV69035")

if not REFRESH_TOKEN:
    print("❌ TASTYTRADE_REFRESH_TOKEN not set in .env")
    sys.exit(1)

print(f"🧪 Testing signal approval end-to-end")
print(f"Signal ID: {SIGNAL_ID}")
print(f"Backend: {BACKEND_URL}")
print(f"Account: {ACCOUNT_NUMBER}")
print("")

# Prepare request
url = f"{BACKEND_URL}/api/signals/{SIGNAL_ID}/approve"
payload = {
    "execute": True,  # Actually execute the trade
    "userId": "test-e2e",
    "refreshToken": REFRESH_TOKEN,
    "accountNumber": ACCOUNT_NUMBER,
    "email": "erichuang2005"  # USERNAME, not email (remember_token requires same format)
}

print(f"📡 POST {url}")
print(f"Payload: execute=True, userId=test-e2e")
print("")

try:
    response = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30
    )
    
    print(f"Status: {response.status_code}")
    print("")
    
    try:
        data = response.json()
        print("Response:")
        print(json.dumps(data, indent=2))
        
        if response.status_code == 200 and data.get("status") == "executed":
            print("")
            print("✅ SUCCESS! Trade executed to Tastytrade!")
            print(f"Order ID: {data.get('order', {}).get('orderId', 'N/A')}")
        elif data.get("status") == "failed":
            print("")
            print(f"❌ Trade failed: {data.get('error')}")
        else:
            print("")
            print(f"⚠️  Unexpected status: {data.get('status')}")
            
    except json.JSONDecodeError:
        print("Response body:")
        print(response.text)
        
except requests.exceptions.RequestException as e:
    print(f"❌ Request failed: {e}")
    sys.exit(1)
