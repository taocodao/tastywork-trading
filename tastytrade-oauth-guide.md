# TastyTrade Multi-User OAuth Trading Integration Guide
## Complete Implementation with Code Examples

---

## Architecture Overview

Your approach is correct: **per-user OAuth tokens → per-user trade execution**. Here's what you need to understand:

### Key Concept: Tastytrade OAuth Fundamentals

**Token Types:**
- **Access Token** (15 minutes): Used for actual API requests (authorization header)
- **Refresh Token** (never expires): Used to generate new access tokens
- **Session Token** (15 minutes): SDK's internal representation of access token

**Best Practice Pattern:**
- Frontend: OAuth flow + store refresh token in Redis/database
- Backend: Retrieve user's refresh token → create session → execute trades
- SDK vs REST API: Use SDK (cleaner), but can use REST if needed

---

## Answer to Each Question

### 1. Per-User Trade Submission

**Question:** How do I submit trades using a specific user's OAuth access_token instead of master account?

**Answer:** You have two approaches:

#### **Approach A: Use tastytrade Python SDK (RECOMMENDED)**

```python
from tastytrade import OAuthSession
from tastytrade.instruments import Equity, EquityOption
from tastytrade.orders import NewOrder, OrderLeg, OrderStatus

def place_order_for_user(user_id: str, refresh_token: str, order_spec: dict):
    """
    Place order using per-user OAuth credentials.
    
    Args:
        user_id: User identifier
        refresh_token: User's stored refresh token
        order_spec: Order specification dict
    """
    try:
        # Create session for THIS USER using their refresh token
        session = OAuthSession(
            client_secret=os.getenv('TASTYTRADE_CLIENT_SECRET'),
            refresh_token=refresh_token,
            is_test=False  # or True for sandbox
        )
        
        # Get user's accounts (returns all accounts linked to OAuth login)
        from tastytrade import Account
        accounts = Account.get_accounts(session)
        
        # Select primary account
        account = accounts[0]  # Or use user's preferred account
        
        # Build order with legs
        legs = [
            OrderLeg(
                instrument_type=leg['instrument_type'],  # 'Equity Option', etc
                symbol=leg['symbol'],
                quantity=leg['quantity'],
                action=leg['action'],  # 'Buy' or 'Sell'
                ratio_quantity=leg.get('ratio_quantity')  # For ratio spreads
            )
            for leg in order_spec['legs']
        ]
        
        # Create order
        new_order = NewOrder(
            account_number=account.account_number,
            order_type=order_spec['order_type'],  # 'Limit', 'Market'
            time_in_force=order_spec['time_in_force'],  # 'Day', 'GTC'
            legs=legs,
            price=order_spec.get('price'),  # For limit orders
            price_effect=order_spec.get('price_effect'),  # 'Debit' or 'Credit'
            source='my-api-trading-app'
        )
        
        # Submit order
        order = new_order.place(session)
        
        return {
            'success': True,
            'order_id': order.id,
            'account': account.account_number,
            'status': order.status,
            'message': f'Order placed successfully for user {user_id}'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'user_id': user_id
        }
```

#### **Approach B: Direct REST API Call (Alternative)**

If you prefer bypassing the SDK:

```python
import requests
import asyncio
from datetime import datetime

async def place_order_rest_api(user_id: str, access_token: str, order_spec: dict):
    """
    Place order directly via REST API using access_token.
    """
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    # Order payload for calendar spread
    payload = {
        'account-number': order_spec['account_number'],
        'time-in-force': order_spec['time_in_force'],  # 'Day', 'GTC'
        'order-type': order_spec['order_type'],  # 'Limit', 'Market'
        'legs': [
            {
                'instrument-type': 'Equity Option',
                'symbol': leg['symbol'],  # e.g., 'TSLA 240215C00250000'
                'quantity': leg['quantity'],
                'action': leg['action'],  # 'Buy' or 'Sell'
                'ratio-quantity': leg.get('ratio_quantity')
            }
            for leg in order_spec['legs']
        ],
        'price': order_spec.get('price'),  # For limit orders
        'price-effect': order_spec.get('price_effect'),  # 'Debit', 'Credit'
        'source': 'my-api-trading-app'
    }
    
    url = 'https://api.tastyworks.com/accounts/{account_number}/orders'
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url.format(account_number=order_spec['account_number']),
            json=payload,
            headers=headers
        ) as response:
            if response.status == 201:
                data = await response.json()
                return {
                    'success': True,
                    'order_id': data['data']['id'],
                    'status': data['data']['status']
                }
            else:
                error_data = await response.json()
                return {
                    'success': False,
                    'error': error_data.get('error', {}).get('message'),
                    'status_code': response.status
                }
```

**Recommendation:** Use SDK (Approach A) because:
- ✅ Automatic token refresh handling
- ✅ Built-in validation
- ✅ Type safety
- ✅ Error handling

---

### 2. Session Management per User

**Question:** How do I instantiate a session for a specific user using their tokens?

**Answer:** Here's the complete pattern:

```python
# tastytrade_session_service.py

from tastytrade import OAuthSession
from typing import Optional
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class TastyTradeSessionService:
    """
    Production-ready session management for per-user OAuth.
    Implements "session-per-task" pattern (no session caching).
    """
    
    CLIENT_SECRET = os.getenv('TASTYTRADE_CLIENT_SECRET')
    IS_TEST = os.getenv('TASTYTRADE_IS_TEST', 'false').lower() == 'true'
    
    @classmethod
    def create_session(cls, refresh_token: str, user_id: Optional[str] = None) -> OAuthSession:
        """
        Create fresh session for user (no caching).
        
        Args:
            refresh_token: User's stored refresh token
            user_id: Optional user ID for logging
            
        Returns:
            OAuthSession object ready for API calls
            
        Raises:
            ValueError: If refresh_token invalid
            Exception: If session creation fails
        """
        
        if not refresh_token:
            raise ValueError(f"Invalid refresh token for user {user_id}")
        
        try:
            # Create fresh session using refresh token
            session = OAuthSession(
                client_secret=cls.CLIENT_SECRET,
                refresh_token=refresh_token,
                is_test=cls.IS_TEST
            )
            
            # Verify session is valid by checking expiration
            # SDK automatically tracks session_expiration
            if session.session_expiration < datetime.now(session.session_expiration.tzinfo):
                logger.warning(f"Session already expired for user {user_id}")
                raise ValueError("Session token already expired")
            
            logger.info(f"Created fresh session for user {user_id}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to create session for user {user_id}: {str(e)}")
            raise
    
    @classmethod
    def refresh_session(cls, session: OAuthSession) -> OAuthSession:
        """
        Refresh session token if expired or about to expire.
        
        Automatically called during session creation but useful for long-running tasks.
        """
        
        from tastytrade.utils import now_in_new_york
        
        if now_in_new_york() > session.session_expiration:
            logger.info("Session token expired, refreshing...")
            session.refresh()
            logger.info(f"Session refreshed. New expiration: {session.session_expiration}")
        
        return session
    
    @classmethod
    def validate_token(cls, refresh_token: str, user_id: Optional[str] = None) -> bool:
        """
        Quick validation that refresh token is valid.
        """
        try:
            session = cls.create_session(refresh_token, user_id)
            from tastytrade import Account
            accounts = Account.get_accounts(session)
            return len(accounts) > 0
        except:
            return False


# Usage in your trade service:

class TradeExecutionService:
    """Service for executing trades on behalf of users."""
    
    def __init__(self, user_id: str, refresh_token: str):
        self.user_id = user_id
        self.refresh_token = refresh_token
        self.session = None
    
    def get_session(self) -> OAuthSession:
        """Get or create fresh session for this user."""
        if self.session is None:
            self.session = TastyTradeSessionService.create_session(
                self.refresh_token,
                self.user_id
            )
        return self.session
    
    def place_trade(self, order_spec: dict) -> dict:
        """Execute trade for this user."""
        session = self.get_session()
        # Your trade execution logic here
        pass
```

**Key Points:**

✅ **Session-per-task pattern**: Create new session for EVERY operation
✅ **No session caching**: Eliminates distributed system bugs
✅ **Automatic refresh**: SDK handles token expiration internally
✅ **Per-user isolation**: Each user gets their own session from their token

---

### 3. Token Refresh (Server-Side)

**Question:** How do I refresh expired tokens without user re-authorization?

**Answer:** Refresh tokens never expire in tastytrade, but access tokens do (15 min). Here's how to handle it:

```python
# token_management.py

import os
import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class TokenRefreshService:
    """
    Manage tastytrade OAuth token refresh headlessly.
    """
    
    TOKEN_ENDPOINT = 'https://api.tastyworks.com/oauth/token'
    CLIENT_ID = os.getenv('TASTYTRADE_CLIENT_ID')
    CLIENT_SECRET = os.getenv('TASTYTRADE_CLIENT_SECRET')
    
    @classmethod
    def refresh_token(cls, user_id: str, old_refresh_token: str) -> Optional[dict]:
        """
        Refresh OAuth token server-side without user interaction.
        
        Args:
            user_id: User identifier (for logging)
            old_refresh_token: Current refresh token
            
        Returns:
            {'access_token': '...', 'refresh_token': '...', 'expires_in': 900}
            Or None if refresh fails
        """
        
        payload = {
            'grant_type': 'refresh_token',
            'client_id': cls.CLIENT_ID,
            'client_secret': cls.CLIENT_SECRET,
            'refresh_token': old_refresh_token
        }
        
        try:
            response = requests.post(
                cls.TOKEN_ENDPOINT,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                token_data = response.json().get('data')
                
                logger.info(f"Token refreshed for user {user_id}")
                
                return {
                    'access_token': token_data.get('access-token'),
                    'refresh_token': token_data.get('refresh-token'),
                    'expires_in': token_data.get('expires-in', 900),  # seconds
                    'token_type': token_data.get('token-type', 'Bearer'),
                    'scope': token_data.get('scope')
                }
            
            elif response.status_code == 401:
                logger.error(f"Refresh failed for user {user_id}: Invalid credentials")
                # Token is invalid - user needs to re-authenticate
                return None
            
            else:
                logger.error(f"Refresh failed for user {user_id}: {response.status_code}")
                logger.error(f"Response: {response.text}")
                return None
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error refreshing token for user {user_id}: {str(e)}")
            return None
    
    @classmethod
    def refresh_token_if_expired(
        cls,
        user_id: str,
        old_refresh_token: str,
        token_expiry: datetime
    ) -> Optional[dict]:
        """
        Only refresh if token is expired or about to expire (within 5 min buffer).
        """
        
        time_until_expiry = token_expiry - datetime.now()
        
        if time_until_expiry < timedelta(minutes=5):
            logger.info(f"Token expires in {time_until_expiry}, refreshing for user {user_id}")
            return cls.refresh_token(user_id, old_refresh_token)
        
        return None  # No refresh needed


# Usage in database model:

class UserTradingAccount:
    """Django/SQLAlchemy model for storing user OAuth credentials."""
    
    user_id: str
    access_token: str
    refresh_token: str
    token_expires_at: datetime
    created_at: datetime
    updated_at: datetime
    
    def refresh_access_token(self) -> bool:
        """Refresh token if expired, update database."""
        
        result = TokenRefreshService.refresh_token_if_expired(
            self.user_id,
            self.refresh_token,
            self.token_expires_at
        )
        
        if result:
            # Update tokens in database
            self.access_token = result['access_token']
            self.refresh_token = result['refresh_token']
            self.token_expires_at = datetime.now() + timedelta(
                seconds=result['expires_in']
            )
            self.updated_at = datetime.now()
            self.save()  # Save to database
            
            return True
        
        return False
```

**Request/Response Format:**

```bash
# Request
POST https://api.tastyworks.com/oauth/token
Content-Type: application/json

{
  "grant_type": "refresh_token",
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "refresh_token": "user_refresh_token_here"
}

# Response (200 OK)
{
  "data": {
    "access-token": "new_15min_token",
    "refresh-token": "eternal_refresh_token",
    "expires-in": 900,
    "token-type": "Bearer",
    "scope": "PlaceTrades AccountAccess"
  }
}
```

**Important:**
- Refresh tokens DON'T expire (keep them safe!)
- Access tokens expire in 900 seconds (15 min)
- SDK automatically handles refresh - you only need manual refresh for REST API calls
- If refresh fails with 401, user revoked access → force re-authentication

---

### 4. Order Submission Endpoint & Format

**Question:** What's the exact endpoint and request format for multi-leg options (calendar spread)?

**Answer:** Here's the complete reference:

#### **REST API Endpoint**

```
POST https://api.tastyworks.com/accounts/{account_number}/orders
Content-Type: application/json
Authorization: Bearer {access_token}
```

#### **Calendar Spread Request Payload**

```json
{
  "account-number": "123456",
  "time-in-force": "Day",
  "order-type": "Limit",
  "legs": [
    {
      "instrument-type": "Equity Option",
      "symbol": "TSLA 250117C00250000",
      "quantity": 1,
      "action": "Sell",
      "ratio-quantity": 1
    },
    {
      "instrument-type": "Equity Option",
      "symbol": "TSLA 250221C00250000",
      "quantity": 1,
      "action": "Buy",
      "ratio-quantity": 1
    }
  ],
  "price": 0.50,
  "price-effect": "Credit",
  "source": "my-api-trading-app"
}
```

**Field Explanations:**

| Field | Values | Example |
|-------|--------|---------|
| `time-in-force` | Day, GTC, IOC, FOK | Day |
| `order-type` | Limit, Market | Limit |
| `price-effect` | Debit, Credit | Credit (for credit spreads) |
| `action` | Buy, Sell, BuyToClose, SellToClose | Sell (short leg), Buy (long leg) |
| `ratio-quantity` | Usually 1 for spreads, >1 for ratios | 1 |
| `symbol` | OCC format: `SPY 250117C00500000` | See below |

**OCC Symbol Format (Standard):**

```
{Underlying}{ExpirationYYMMDD}{CallOrPut}{StrikePrice}

Example breakdown:
TSLA 250221C00250000
├─ TSLA: Underlying
├─ 250221: Feb 21, 2025 (YYMMDD)
├─ C: Call (P = Put)
└─ 00250000: Strike $250.00 (8 digits, 2 decimal places)
```

#### **Python SDK Version (Simpler)**

```python
from tastytrade import OAuthSession, Account
from tastytrade.instruments import EquityOption
from tastytrade.orders import NewOrder, OrderLeg

def place_calendar_spread(
    refresh_token: str,
    underlying: str,
    short_expiration: str,  # "2025-02-21"
    long_expiration: str,   # "2025-03-21"
    strike: float,
    price: float
) -> dict:
    """
    Place calendar spread: Sell short call, buy long call at same strike.
    """
    
    session = OAuthSession(
        client_secret=os.getenv('TASTYTRADE_CLIENT_SECRET'),
        refresh_token=refresh_token
    )
    
    accounts = Account.get_accounts(session)
    account = accounts[0]
    
    # Retrieve option chains from IB (your market data source)
    # You'll get back OCC symbols like "TSLA 250221C00250000"
    short_symbol = f"{underlying} {short_expiration.replace('-', '')}C{int(strike*100):08d}"
    long_symbol = f"{underlying} {long_expiration.replace('-', '')}C{int(strike*100):08d}"
    
    # Build legs
    legs = [
        OrderLeg(
            instrument_type='Equity Option',
            symbol=short_symbol,
            quantity=1,
            action='Sell'  # Short the call
        ),
        OrderLeg(
            instrument_type='Equity Option',
            symbol=long_symbol,
            quantity=1,
            action='Buy'  # Buy the call
        )
    ]
    
    # Create order
    new_order = NewOrder(
        account_number=account.account_number,
        order_type='Limit',
        time_in_force='Day',
        legs=legs,
        price=price,
        price_effect='Credit',  # Calendar spreads are typically credit strategies
        source='my-api-trading-app'
    )
    
    # Place order
    order = new_order.place(session)
    
    return {
        'order_id': order.id,
        'status': order.status,
        'account': account.account_number
    }
```

#### **cURL Example**

```bash
curl -X POST https://api.tastyworks.com/accounts/123456/orders \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "account-number": "123456",
    "time-in-force": "Day",
    "order-type": "Limit",
    "legs": [
      {
        "instrument-type": "Equity Option",
        "symbol": "TSLA 250221C00250000",
        "quantity": 1,
        "action": "Sell"
      },
      {
        "instrument-type": "Equity Option",
        "symbol": "TSLA 250321C00250000",
        "quantity": 1,
        "action": "Buy"
      }
    ],
    "price": 0.50,
    "price-effect": "Credit",
    "source": "my-api-trading-app"
  }'
```

---

### 5. Account Number Retrieval

**Question:** Do I need the user's account number? How do I retrieve it?

**Answer:** YES, you need the account number. Here's how to get it:

```python
from tastytrade import Account, OAuthSession

def get_user_accounts(refresh_token: str, user_id: str) -> list:
    """
    Retrieve all accounts associated with OAuth login.
    
    OAuth returns ALL accounts linked to the user's TastyTrade login:
    - Trading accounts (margin)
    - IRA accounts
    - Entity accounts
    - etc.
    """
    
    session = OAuthSession(
        client_secret=os.getenv('TASTYTRADE_CLIENT_SECRET'),
        refresh_token=refresh_token
    )
    
    accounts = Account.get_accounts(session)
    
    result = []
    for account in accounts:
        result.append({
            'account_number': account.account_number,
            'account_type': account.account_type,  # 'margin', 'ira', etc
            'is_margin': account.is_margin,
            'buying_power': account.buying_power,
            'cash_balance': account.cash_balance,
            'account_value': account.account_value,
            'is_active': account.is_active
        })
    
    # Store accounts in database for later use
    for account_data in result:
        save_account_for_user(user_id, account_data)
    
    return result


# Store in database once:

class UserAccount(Model):
    """Store user's account info from OAuth fetch."""
    
    user_id: str
    account_number: str
    account_type: str  # 'margin', 'ira'
    is_primary: bool = True  # Which account to use for trading
    metadata: dict = {}  # Store full account data
    fetched_at: datetime

    @classmethod
    def get_primary_account(cls, user_id: str):
        """Get user's primary trading account."""
        return cls.query.filter(
            cls.user_id == user_id,
            cls.is_primary == True
        ).first()
```

**When OAuth Callback Fires:**

```python
# In your OAuth callback handler

def tastytrade_oauth_callback(code: str, state: str, user_id: str):
    """Handle OAuth callback."""
    
    # Exchange code for tokens
    tokens = exchange_code_for_tokens(code)
    
    # Fetch user's accounts using new refresh token
    session = OAuthSession(
        client_secret=CLIENT_SECRET,
        refresh_token=tokens['refresh_token']
    )
    
    accounts = Account.get_accounts(session)
    
    # Store account info
    for account in accounts:
        UserAccount.create(
            user_id=user_id,
            account_number=account.account_number,
            account_type=account.account_type,
            is_primary=True,  # First account is primary
            metadata={
                'buying_power': account.buying_power,
                'cash_balance': account.cash_balance,
                'account_value': account.account_value
            },
            fetched_at=datetime.now()
        )
    
    # Store tokens
    store_tokens(
        user_id=user_id,
        access_token=tokens['access_token'],
        refresh_token=tokens['refresh_token'],
        expires_at=datetime.now() + timedelta(seconds=tokens['expires_in'])
    )
```

---

## Complete End-to-End Flow

```
STEP 1: Frontend OAuth Flow
─────────────────────────────────────
User clicks "Connect TastyTrade"
    ↓
Frontend redirected to: 
  https://tastyworks.com/oauth/authorize?
    client_id=YOUR_CLIENT_ID&
    response_type=code&
    redirect_uri=https://yourapp.com/oauth/callback&
    scope=PlaceTrades,AccountAccess
    ↓
User authorizes your app
    ↓
Browser redirected to: https://yourapp.com/oauth/callback?code=AUTH_CODE


STEP 2: Backend - Exchange Code for Tokens
──────────────────────────────────────────────
POST https://api.tastyworks.com/oauth/token
{
  "grant_type": "authorization_code",
  "code": "AUTH_CODE",
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET",
  "redirect_uri": "https://yourapp.com/oauth/callback"
}

Response:
{
  "data": {
    "access-token": "short_lived_token",
    "refresh-token": "long_lived_token",
    "expires-in": 900
  }
}

→ Store refresh_token in Redis/Database keyed by user_id


STEP 3: Store Account Info
──────────────────────────
OAuthSession(client_secret, refresh_token).get_accounts()
→ Returns: [Account(account_number='123456', ...)]
→ Store account_number in database


STEP 4: User Approves Trade Signal
──────────────────────────────────
Frontend: GET /api/execute-trade?signal_id=ABC&user_id=XYZ


STEP 5: Backend - Retrieve Tokens & Execute
──────────────────────────────────────────────
1. Retrieve user's refresh_token from Redis
2. Create OAuthSession(client_secret, refresh_token)
3. SDK auto-refreshes 15-min access token if needed
4. Get user's account_number from database
5. Build NewOrder with user's legs
6. Call order.place(session)

Response:
{
  "data": {
    "id": "order_123",
    "status": "accepted",
    "account_number": "123456"
  }
}

→ Frontend gets: {'order_id': 'order_123', 'status': 'accepted'}
```

---

## Complete Producti-Ready Implementation

```python
# services/tastytrade_service.py

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from tastytrade import OAuthSession, Account
from tastytrade.instruments import EquityOption
from tastytrade.orders import NewOrder, OrderLeg

logger = logging.getLogger(__name__)

class TastyTradeOrderService:
    """
    Production-ready order service for multi-user trading.
    Handles per-user OAuth, session management, and order execution.
    """
    
    CLIENT_SECRET = os.getenv('TASTYTRADE_CLIENT_SECRET')
    IS_TEST = os.getenv('TASTYTRADE_IS_TEST', 'false').lower() == 'true'
    
    @staticmethod
    def get_session(refresh_token: str) -> OAuthSession:
        """Create fresh session from refresh token."""
        return OAuthSession(
            client_secret=TastyTradeOrderService.CLIENT_SECRET,
            refresh_token=refresh_token,
            is_test=TastyTradeOrderService.IS_TEST
        )
    
    @staticmethod
    def place_calendar_spread(
        user_id: str,
        refresh_token: str,
        account_number: str,
        underlying: str,
        short_expiry: str,  # "2025-02-21"
        long_expiry: str,   # "2025-03-21"
        strike: float,
        bid_ask_price: float
    ) -> Dict:
        """Place calendar spread order."""
        
        try:
            session = TastyTradeOrderService.get_session(refresh_token)
            
            # Build OCC symbols
            short_occ = TastyTradeOrderService.build_occ_symbol(
                underlying, short_expiry, 'C', strike
            )
            long_occ = TastyTradeOrderService.build_occ_symbol(
                underlying, long_expiry, 'C', strike
            )
            
            # Build order legs
            legs = [
                OrderLeg(
                    instrument_type='Equity Option',
                    symbol=short_occ,
                    quantity=1,
                    action='Sell'
                ),
                OrderLeg(
                    instrument_type='Equity Option',
                    symbol=long_occ,
                    quantity=1,
                    action='Buy'
                )
            ]
            
            # Create and place order
            order = NewOrder(
                account_number=account_number,
                order_type='Limit',
                time_in_force='Day',
                legs=legs,
                price=bid_ask_price,
                price_effect='Credit',
                source='my-api-trading-app'
            ).place(session)
            
            logger.info(f"Order {order.id} placed for user {user_id}")
            
            return {
                'success': True,
                'order_id': order.id,
                'status': order.status,
                'account': account_number
            }
        
        except Exception as e:
            logger.error(f"Failed to place order for user {user_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'user_id': user_id
            }
    
    @staticmethod
    def build_occ_symbol(underlying: str, expiry: str, call_or_put: str, strike: float) -> str:
        """
        Build OCC option symbol.
        
        Format: {Underlying}{YYMMDD}{C|P}{StrikePrice(8 digits)}
        Example: TSLA 250221C00250000
        """
        exp_date = datetime.strptime(expiry, '%Y-%m-%d')
        strike_str = f"{int(strike * 100):08d}"
        occ = f"{underlying} {exp_date.strftime('%y%m%d')}{call_or_put}{strike_str}"
        return occ
    
    @staticmethod
    def get_accounts(refresh_token: str, user_id: str) -> List[Dict]:
        """Fetch all accounts for user."""
        try:
            session = TastyTradeOrderService.get_session(refresh_token)
            accounts = Account.get_accounts(session)
            
            return [
                {
                    'account_number': acc.account_number,
                    'account_type': acc.account_type,
                    'buying_power': float(acc.buying_power),
                    'cash_balance': float(acc.cash_balance)
                }
                for acc in accounts
            ]
        except Exception as e:
            logger.error(f"Failed to fetch accounts for user {user_id}: {str(e)}")
            return []


# Flask API example

from flask import Blueprint, request, jsonify
from functools import wraps

api = Blueprint('trading', __name__, url_prefix='/api/trading')

def require_auth(f):
    """Decorator to require user authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = request.headers.get('X-User-ID')
        if not user_id:
            return jsonify({'error': 'User ID required'}), 401
        request.user_id = user_id
        return f(*args, **kwargs)
    return decorated_function

@api.route('/place-calendar-spread', methods=['POST'])
@require_auth
def place_calendar_spread_endpoint():
    """Execute calendar spread order for authenticated user."""
    
    data = request.json
    user_id = request.user_id
    
    # Retrieve user's credentials from database
    user_account = UserAccount.get_primary_account(user_id)
    if not user_account:
        return jsonify({'error': 'No trading account connected'}), 404
    
    refresh_token = get_refresh_token(user_id)  # From Redis/DB
    
    # Execute order
    result = TastyTradeOrderService.place_calendar_spread(
        user_id=user_id,
        refresh_token=refresh_token,
        account_number=user_account.account_number,
        underlying=data['underlying'],
        short_expiry=data['short_expiry'],
        long_expiry=data['long_expiry'],
        strike=data['strike'],
        bid_ask_price=data['price']
    )
    
    if result['success']:
        return jsonify(result), 201
    else:
        return jsonify(result), 400
```

---

## Key Takeaways

| Question | Answer |
|----------|--------|
| **Per-user trades?** | Use user's refresh_token → OAuthSession → place_order |
| **Session management?** | Session-per-task pattern (create fresh, no caching) |
| **Token refresh?** | SDK auto-refreshes; manual refresh to token endpoint for REST |
| **Order endpoint?** | `POST /accounts/{account_number}/orders` with multi-leg payload |
| **Account number?** | `Account.get_accounts(session)` returns all accounts |
| **Calendar spread format?** | Two legs: Sell short-dated call, Buy long-dated call |

---

## Security Checklist

✅ Store refresh tokens encrypted (use Django's encrypted fields or HashiCorp Vault)
✅ Never expose access tokens in logs
✅ Implement token rotation (refresh before each operation)
✅ Validate OAuth state parameter (prevents CSRF)
✅ Use HTTPS only for token transmission
✅ Implement rate limiting on trade endpoints
✅ Audit log all trades with user ID + timestamp
✅ Never cache sessions across requests
✅ Mark tokens invalid if user revokes access

---

## Debugging

```python
# Enable tastytrade SDK debug logging
import logging
logging.getLogger('tastytrade').setLevel(logging.DEBUG)

# Test token validity
from tastytrade import OAuthSession, Account

session = OAuthSession(client_secret='...', refresh_token='...')
print(f"Token expires: {session.session_expiration}")

accounts = Account.get_accounts(session)
print(f"Found {len(accounts)} accounts")
for acc in accounts:
    print(f"  - {acc.account_number} ({acc.account_type}): {acc.account_value}")
```

File created: `tastytrade_integration_guide.md`
