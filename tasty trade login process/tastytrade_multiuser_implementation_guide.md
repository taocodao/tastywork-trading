# TradeMind: Multi-User Tastytrade Integration - Complete Implementation Guide

## Overview

This document provides the exact step-by-step process for implementing a multi-user Tastytrade integration where:
- Each user has their own **Privy account** (authentication)
- Each user has their own **Tastytrade credentials** (trading account)
- Trades are executed with **user-specific credentials**
- Order status and account data are fetched **per user**

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        TradeMind Frontend (Next.js)              │
├──────────────────────────────────────────────────────────────────┤
│ 1. User logs in via Privy (privy-token cookie)                   │
│ 2. User connects Tastytrade account (OAuth flow)                 │
│ 3. Frontend stores refresh_token in Redis (keyed by userId)      │
│ 4. User approves signal → Calls backend API                      │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                     TradeMind Backend (Python)                   │
├──────────────────────────────────────────────────────────────────┤
│ 1. Receives user_id from frontend                                │
│ 2. Retrieves refresh_token from Redis (keyed by user_id)         │
│ 3. Creates OAuthSession using:                                   │
│    - TASTYTRADE_CLIENT_SECRET from backend .env                  │
│    - user's refresh_token from Redis                             │
│ 4. Executes trade using session                                  │
│ 5. Returns order confirmation to frontend                        │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│                   Tastytrade OAuth Server                        │
├──────────────────────────────────────────────────────────────────┤
│ Validates refresh_token + client_secret combination              │
│ Issues new access_token for API calls                            │
└──────────────────────────────────────────────────────────────────┘
```

---

## CRITICAL: Credential Alignment Requirement

**🔴 MANDATORY SETUP STEP:**

Before any coding, ensure your OAuth credentials are synchronized:

### Step 0: Get Your OAuth Credentials

1. Go to https://my.tastytrade.com (log in)
2. Navigate to Settings → API
3. Find your OAuth application (or create one)
4. Copy these values:
   - `client_id` (example: `ABC123xyz`)
   - `client_secret` (example: `XYZ789abc`)
   - Verify `redirect_uri` = `https://yourdomain.com/api/tastytrade/oauth/callback`

### Step 0b: Set Identical Environment Variables

**Frontend (.env on Vercel):**
```
NEXT_PUBLIC_TASTYTRADE_CLIENT_ID=ABC123xyz
TASTYTRADE_CLIENT_SECRET=XYZ789abc
TASTYTRADE_REDIRECT_URI=https://yourdomain.com/api/tastytrade/oauth/callback
```

**Backend (.env for Python):**
```
TASTYTRADE_CLIENT_ID=ABC123xyz
TASTYTRADE_CLIENT_SECRET=XYZ789abc
TASTYTRADE_OAUTH_URL=https://api.tastytrade.com
```

**⚠️ CRITICAL:** The `client_secret` MUST be identical in both places. If they differ, refresh tokens will become invalid.

---

## Process Flow: Step-by-Step

### PHASE 1: USER AUTHENTICATION (Privy)

#### Step 1.1: User Logs In

**Where:** `components/PrivyProvider.tsx`

**What Happens:**
```typescript
// Privy automatically handles login
// Sets privy-token cookie containing JWT with sub (userId) claim
// This cookie is accessible in Next.js API routes
```

**Output:**
- User has valid Privy session
- `privy-token` cookie set in browser
- `userId` is available from this token

---

### PHASE 2: TASTYTRADE OAUTH SETUP

#### Step 2.1: Initiate OAuth Connection

**Where:** `pages/api/tastytrade/oauth/url/route.ts`

**Request:** User clicks "Connect Tastytrade" button

**Code to Implement:**
```typescript
import { NextRequest, NextResponse } from 'next/server';
import { verifyAuth } from '@privy-io/react-auth';

export async function GET(request: NextRequest) {
  try {
    // Get user ID from Privy token
    const privy_token = request.cookies.get('privy-token')?.value;
    
    if (!privy_token) {
      return NextResponse.json(
        { error: 'Not authenticated' },
        { status: 401 }
      );
    }

    // Decode Privy token to get userId
    // (You may already have a utility for this)
    const userId = await extractUserIdFromPrivyToken(privy_token);

    // Get OAuth credentials from environment
    const clientId = process.env.NEXT_PUBLIC_TASTYTRADE_CLIENT_ID;
    const redirectUri = process.env.TASTYTRADE_REDIRECT_URI;

    if (!clientId || !redirectUri) {
      console.error('Missing Tastytrade OAuth env vars');
      return NextResponse.json(
        { error: 'Server configuration error' },
        { status: 500 }
      );
    }

    // Encode userId in state parameter (for later retrieval)
    const state = Buffer.from(JSON.stringify({ userId })).toString('base64url');

    // Build OAuth authorization URL
    const oauthUrl = new URL('https://api.tastytrade.com/oauth/authorize');
    oauthUrl.searchParams.append('client_id', clientId);
    oauthUrl.searchParams.append('redirect_uri', redirectUri);
    oauthUrl.searchParams.append('response_type', 'code');
    oauthUrl.searchParams.append('state', state);
    // Optional: scope (check Tastytrade docs for available scopes)
    // oauthUrl.searchParams.append('scope', 'PlaceTrades AccountAccess');

    return NextResponse.json({
      oauth_url: oauthUrl.toString()
    });

  } catch (error) {
    console.error('OAuth URL generation failed:', error);
    return NextResponse.json(
      { error: 'Failed to generate OAuth URL' },
      { status: 500 }
    );
  }
}
```

**Frontend Usage:**
```typescript
// In TastytradeLink.tsx
const response = await fetch('/api/tastytrade/oauth/url');
const { oauth_url } = await response.json();
window.location.href = oauth_url; // Redirect to Tastytrade login
```

**Output:**
- User redirected to Tastytrade OAuth login page
- After login, Tastytrade redirects back with `code` and `state`

---

#### Step 2.2: Handle OAuth Callback & Exchange Code

**Where:** `pages/api/tastytrade/oauth/callback/route.ts`

**What Happens:**
- Tastytrade OAuth server returns `code` and `state`
- Backend exchanges code for tokens
- Tokens stored in Redis keyed by userId

**Code to Implement:**
```typescript
import { NextRequest, NextResponse } from 'next/server';
import axios from 'axios';
import { redis } from '@/lib/redis'; // Your Redis client

export async function GET(request: NextRequest) {
  try {
    const code = request.nextUrl.searchParams.get('code');
    const state = request.nextUrl.searchParams.get('state');
    const error = request.nextUrl.searchParams.get('error');

    // Handle OAuth errors
    if (error) {
      console.error(`OAuth error: ${error}`);
      return NextResponse.redirect(
        `${process.env.NEXT_PUBLIC_FRONTEND_URL}/settings?error=${error}`
      );
    }

    if (!code || !state) {
      return NextResponse.json(
        { error: 'Missing code or state parameter' },
        { status: 400 }
      );
    }

    // Decode state to extract userId
    let userId: string;
    try {
      const stateData = JSON.parse(
        Buffer.from(state, 'base64url').toString('utf-8')
      );
      userId = stateData.userId;
    } catch (e) {
      console.error('Failed to decode state:', e);
      return NextResponse.json(
        { error: 'Invalid state parameter' },
        { status: 400 }
      );
    }

    // Get OAuth credentials from environment
    const clientId = process.env.NEXT_PUBLIC_TASTYTRADE_CLIENT_ID;
    const clientSecret = process.env.TASTYTRADE_CLIENT_SECRET;
    const redirectUri = process.env.TASTYTRADE_REDIRECT_URI;

    if (!clientId || !clientSecret || !redirectUri) {
      console.error('Missing Tastytrade OAuth credentials in .env');
      return NextResponse.json(
        { error: 'Server configuration error' },
        { status: 500 }
      );
    }

    // Exchange authorization code for tokens
    const tokenResponse = await axios.post(
      'https://api.tastytrade.com/oauth/token',
      {
        grant_type: 'authorization_code',
        code,
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: redirectUri
      },
      {
        headers: { 'Content-Type': 'application/json' }
      }
    );

    const {
      access_token,
      refresh_token,
      expires_in,
      token_type
    } = tokenResponse.data;

    if (!refresh_token) {
      console.error('No refresh token received from Tastytrade');
      return NextResponse.json(
        { error: 'Failed to obtain refresh token' },
        { status: 500 }
      );
    }

    // Fetch user's account number using access token
    const accountResponse = await axios.get(
      'https://api.tastytrade.com/customers/me/accounts',
      {
        headers: {
          'Authorization': `Bearer ${access_token}`,
          'Content-Type': 'application/json'
        }
      }
    );

    const accountNumber = accountResponse.data.data[0]?.account_number;

    // Store credentials in Redis with userId as key
    const credentialKey = `tastytrade:${userId}`;
    const credentialData = {
      accessToken: access_token,
      refreshToken: refresh_token,
      expiresAt: Date.now() + (expires_in * 1000),
      linkedAt: Date.now(),
      accountNumber: accountNumber || null,
      tokenType: token_type
    };

    // Store with TTL (long expiry since refresh_token doesn't expire)
    await redis.setex(
      credentialKey,
      30 * 24 * 60 * 60, // 30 days TTL
      JSON.stringify(credentialData)
    );

    console.log(`✅ Tastytrade credentials stored for user ${userId}`);

    // Redirect to success page
    return NextResponse.redirect(
      `${process.env.NEXT_PUBLIC_FRONTEND_URL}/settings?tastytrade=connected`
    );

  } catch (error) {
    console.error('OAuth callback error:', error);
    
    if (axios.isAxiosError(error)) {
      console.error('Response status:', error.response?.status);
      console.error('Response data:', error.response?.data);
    }

    return NextResponse.redirect(
      `${process.env.NEXT_PUBLIC_FRONTEND_URL}/settings?error=oauth_failed`
    );
  }
}
```

**Output:**
- Tokens stored in Redis at key `tastytrade:{userId}`
- User redirected to success page
- Ready for trade execution

**Redis Storage Format:**
```json
{
  "accessToken": "string",      // Short-lived (15 min)
  "refreshToken": "string",     // Long-lived (no expiration)
  "expiresAt": 1704067200000,   // Unix timestamp when access_token expires
  "linkedAt": 1704067200000,    // When account was linked
  "accountNumber": "ABC123",    // User's trading account number
  "tokenType": "Bearer"
}
```

---

### PHASE 3: TRADE EXECUTION

#### Step 3.1: User Approves Signal

**Where:** Frontend signal approval button

**Request:**
```typescript
// In your signal approval component
const approveSignal = async (signalId: string) => {
  const response = await fetch(
    `/api/signals/${signalId}/approve`,
    { method: 'POST' }
  );
  
  const result = await response.json();
  // Handle result
};
```

---

#### Step 3.2: Backend Receives Approval & Retrieves Credentials

**Where:** `pages/api/signals/[id]/approve/route.ts`

**Code to Implement:**
```typescript
import { NextRequest, NextResponse } from 'next/server';
import { redis } from '@/lib/redis';

export async function POST(
  request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const signalId = params.id;

    // Extract userId from Privy token
    const privy_token = request.cookies.get('privy-token')?.value;
    
    if (!privy_token) {
      return NextResponse.json(
        { error: 'Not authenticated' },
        { status: 401 }
      );
    }

    const userId = await extractUserIdFromPrivyToken(privy_token);

    // Get user's Tastytrade credentials from Redis
    const credentialKey = `tastytrade:${userId}`;
    const credentialsJson = await redis.get(credentialKey);

    if (!credentialsJson) {
      return NextResponse.json(
        { error: 'Tastytrade account not connected' },
        { status: 400 }
      );
    }

    const credentials = JSON.parse(credentialsJson);
    const { refreshToken, accountNumber } = credentials;

    // Get signal details from database
    const signal = await getSignalFromDB(signalId);

    if (!signal) {
      return NextResponse.json(
        { error: 'Signal not found' },
        { status: 404 }
      );
    }

    // Send to Python backend for execution
    const pythonBackendUrl = process.env.PYTHON_BACKEND_URL;
    
    const tradeResponse = await fetch(
      `${pythonBackendUrl}/execute-trade`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          account_number: accountNumber,
          refresh_token: refreshToken,
          signal_data: {
            symbol: signal.symbol,
            quantity: signal.quantity,
            order_type: signal.order_type,
            side: signal.side // 'BUY' or 'SELL'
          }
        })
      }
    );

    const result = await tradeResponse.json();

    if (!tradeResponse.ok) {
      console.error('Trade execution failed:', result);
      return NextResponse.json(
        { error: result.error || 'Trade execution failed' },
        { status: tradeResponse.status }
      );
    }

    // Store order information
    await saveOrderToDB({
      user_id: userId,
      signal_id: signalId,
      order_id: result.order_id,
      status: 'PENDING',
      created_at: new Date()
    });

    return NextResponse.json({
      success: true,
      order_id: result.order_id,
      status: result.status
    });

  } catch (error) {
    console.error('Signal approval error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
```

**Output:**
- Credentials retrieved from Redis
- Request sent to Python backend with:
  - `user_id` (for logging/tracking)
  - `account_number` (which trading account to use)
  - `refresh_token` (for API authentication)
  - `signal_data` (what to trade)

---

#### Step 3.3: Python Backend Executes Trade

**Where:** `tasty_api_server.py` or similar

**Code to Implement:**
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from tastytrade import OAuthSession, Account
import os
from datetime import datetime
import logging

app = FastAPI()
logger = logging.getLogger(__name__)

class TradeRequest(BaseModel):
    user_id: str
    account_number: str
    refresh_token: str
    signal_data: dict

class OrderResponse(BaseModel):
    order_id: str
    status: str
    symbol: str
    quantity: int
    side: str

@app.post("/execute-trade", response_model=OrderResponse)
async def execute_trade(request: TradeRequest):
    """
    Execute a trade for a specific user using their Tastytrade credentials.
    
    CRITICAL: The refresh_token was issued to the OAuth app identified by
    client_secret in the .env file. This client_secret MUST match the one
    used during the initial OAuth code exchange on the frontend.
    """
    
    user_id = request.user_id
    account_number = request.account_number
    refresh_token = request.refresh_token
    signal_data = request.signal_data
    
    logger.info(f"Executing trade for user {user_id}, account {account_number}")
    
    try:
        # Create OAuthSession with credentials
        client_secret = os.getenv("TASTYTRADE_CLIENT_SECRET")
        
        if not client_secret:
            logger.error("TASTYTRADE_CLIENT_SECRET not set in environment")
            raise HTTPException(
                status_code=500,
                detail="Server configuration error: Missing TASTYTRADE_CLIENT_SECRET"
            )
        
        # Create session using refresh_token
        # This will automatically refresh the access_token if needed
        session = OAuthSession(client_secret, refresh_token)
        
        logger.info(f"✅ OAuthSession created for user {user_id}")
        
        # Get account
        account = Account.get_account(session, account_number)
        
        if not account:
            logger.error(f"Account {account_number} not found for user {user_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Account {account_number} not found"
            )
        
        # Build trade parameters
        symbol = signal_data['symbol']
        quantity = signal_data['quantity']
        side = signal_data['side']  # 'BUY' or 'SELL'
        order_type = signal_data.get('order_type', 'MARKET')
        
        logger.info(
            f"Placing {side} order: {quantity} x {symbol} "
            f"({order_type}) for account {account_number}"
        )
        
        # Execute the trade
        # This is pseudocode - adjust based on Tastytrade SDK actual API
        order = account.place_order(
            symbol=symbol,
            quantity=quantity,
            side=side,
            order_type=order_type,
            session=session
        )
        
        logger.info(
            f"✅ Trade executed for user {user_id}: "
            f"Order ID {order.id}, Status: {order.status}"
        )
        
        return OrderResponse(
            order_id=order.id,
            status=order.status,
            symbol=symbol,
            quantity=quantity,
            side=side
        )
    
    except Exception as e:
        error_message = str(e)
        logger.error(
            f"❌ Trade execution failed for user {user_id}: {error_message}"
        )
        
        # Check for specific credential mismatch errors
        if "invalid_credentials" in error_message.lower():
            logger.critical(
                f"CREDENTIAL MISMATCH for user {user_id}. "
                f"Backend TASTYTRADE_CLIENT_SECRET does not match "
                f"frontend credentials that issued refresh_token. "
                f"Error: {error_message}"
            )
            raise HTTPException(
                status_code=401,
                detail="OAuth credential mismatch. Contact support."
            )
        
        raise HTTPException(
            status_code=500,
            detail=f"Trade execution failed: {error_message}"
        )
```

**Critical Notes:**
- The `OAuthSession(client_secret, refresh_token)` will fail if `client_secret` doesn't match the one used during OAuth exchange
- Must match the `TASTYTRADE_CLIENT_SECRET` from the frontend
- The session automatically handles token refresh
- All subsequent API calls use this session

**Output:**
- Order placed with Tastytrade
- Order ID returned to frontend
- Order stored in database for tracking

---

### PHASE 4: ORDER TRACKING & ACCOUNT DATA

#### Step 4.1: Check Order Status

**Where:** `pages/api/orders/[orderId]/status/route.ts`

**Code to Implement:**
```typescript
import { NextRequest, NextResponse } from 'next/server';
import { redis } from '@/lib/redis';

export async function GET(
  request: NextRequest,
  { params }: { params: { orderId: string } }
) {
  try {
    const orderId = params.orderId;

    // Get user ID from Privy token
    const privy_token = request.cookies.get('privy-token')?.value;
    
    if (!privy_token) {
      return NextResponse.json(
        { error: 'Not authenticated' },
        { status: 401 }
      );
    }

    const userId = await extractUserIdFromPrivyToken(privy_token);

    // Get user's Tastytrade credentials from Redis
    const credentialKey = `tastytrade:${userId}`;
    const credentialsJson = await redis.get(credentialKey);

    if (!credentialsJson) {
      return NextResponse.json(
        { error: 'Tastytrade account not connected' },
        { status: 400 }
      );
    }

    const credentials = JSON.parse(credentialsJson);
    const { refreshToken, accountNumber } = credentials;

    // Call Python backend to get order status
    const pythonBackendUrl = process.env.PYTHON_BACKEND_URL;
    
    const statusResponse = await fetch(
      `${pythonBackendUrl}/orders/${orderId}/status`,
      {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          account_number: accountNumber,
          refresh_token: refreshToken
        })
      }
    );

    const result = await statusResponse.json();

    if (!statusResponse.ok) {
      return NextResponse.json(
        { error: result.error || 'Failed to get order status' },
        { status: statusResponse.status }
      );
    }

    // Update order in database
    await updateOrderStatusInDB(orderId, result.status);

    return NextResponse.json(result);

  } catch (error) {
    console.error('Order status check error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
```

---

#### Step 4.2: Fetch Account Balance & Positions

**Where:** `pages/api/account/balance/route.ts`

**Code to Implement:**
```typescript
import { NextRequest, NextResponse } from 'next/server';
import { redis } from '@/lib/redis';

export async function GET(request: NextRequest) {
  try {
    // Get user ID from Privy token
    const privy_token = request.cookies.get('privy-token')?.value;
    
    if (!privy_token) {
      return NextResponse.json(
        { error: 'Not authenticated' },
        { status: 401 }
      );
    }

    const userId = await extractUserIdFromPrivyToken(privy_token);

    // Get user's Tastytrade credentials from Redis
    const credentialKey = `tastytrade:${userId}`;
    const credentialsJson = await redis.get(credentialKey);

    if (!credentialsJson) {
      return NextResponse.json(
        { error: 'Tastytrade account not connected' },
        { status: 400 }
      );
    }

    const credentials = JSON.parse(credentialsJson);
    const { refreshToken, accountNumber } = credentials;

    // Call Python backend to get account data
    const pythonBackendUrl = process.env.PYTHON_BACKEND_URL;
    
    const accountResponse = await fetch(
      `${pythonBackendUrl}/account/balance`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          account_number: accountNumber,
          refresh_token: refreshToken
        })
      }
    );

    const result = await accountResponse.json();

    if (!accountResponse.ok) {
      return NextResponse.json(
        { error: result.error || 'Failed to get account balance' },
        { status: accountResponse.status }
      );
    }

    return NextResponse.json({
      account_number: accountNumber,
      balance: result.balance,
      buying_power: result.buying_power,
      cash: result.cash,
      positions: result.positions,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Account balance check error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
```

---

#### Step 4.3: Python Backend - Order Status & Account Data

**Code to Implement:**
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from tastytrade import OAuthSession, Account
import os
import logging

logger = logging.getLogger(__name__)

class OrderStatusRequest(BaseModel):
    user_id: str
    account_number: str
    refresh_token: str

class BalanceRequest(BaseModel):
    user_id: str
    account_number: str
    refresh_token: str

@app.get("/orders/{order_id}/status")
async def get_order_status(order_id: str, request: OrderStatusRequest):
    """
    Fetch the status of a specific order from Tastytrade.
    """
    
    user_id = request.user_id
    account_number = request.account_number
    refresh_token = request.refresh_token
    
    logger.info(f"Fetching order status for user {user_id}, order {order_id}")
    
    try:
        client_secret = os.getenv("TASTYTRADE_CLIENT_SECRET")
        session = OAuthSession(client_secret, refresh_token)
        
        account = Account.get_account(session, account_number)
        
        # Fetch the specific order
        order = account.get_order(order_id, session=session)
        
        logger.info(f"Order {order_id} status: {order.status}")
        
        return {
            "order_id": order.id,
            "status": order.status,
            "symbol": order.symbol,
            "quantity": order.quantity,
            "side": order.side,
            "filled_quantity": order.filled_quantity,
            "price": order.price,
            "executed_price": getattr(order, 'executed_price', None),
            "created_at": order.created_at,
            "updated_at": order.updated_at
        }
    
    except Exception as e:
        logger.error(f"Failed to get order status for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get order status: {str(e)}"
        )

@app.post("/account/balance")
async def get_account_balance(request: BalanceRequest):
    """
    Fetch account balance, buying power, and positions for a user.
    """
    
    user_id = request.user_id
    account_number = request.account_number
    refresh_token = request.refresh_token
    
    logger.info(f"Fetching account balance for user {user_id}")
    
    try:
        client_secret = os.getenv("TASTYTRADE_CLIENT_SECRET")
        session = OAuthSession(client_secret, refresh_token)
        
        account = Account.get_account(session, account_number)
        
        # Get account details
        balance = account.balance
        buying_power = account.buying_power
        cash = account.cash
        
        # Get positions
        positions = account.get_positions(session=session)
        
        formatted_positions = []
        for position in positions:
            formatted_positions.append({
                "symbol": position.symbol,
                "quantity": position.quantity,
                "average_price": position.average_price,
                "current_price": position.current_price,
                "unrealized_gain_loss": position.unrealized_gain_loss,
                "unrealized_percent": position.unrealized_percent
            })
        
        logger.info(
            f"Account balance for user {user_id}: "
            f"Balance={balance}, BuyingPower={buying_power}, "
            f"Positions={len(formatted_positions)}"
        )
        
        return {
            "account_number": account_number,
            "balance": balance,
            "buying_power": buying_power,
            "cash": cash,
            "positions": formatted_positions,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Failed to get account balance for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get account balance: {str(e)}"
        )
```

---

## Database Schema

### Orders Table

```sql
CREATE TABLE orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id VARCHAR(255) NOT NULL,
  signal_id UUID NOT NULL,
  order_id VARCHAR(255) NOT NULL,
  account_number VARCHAR(255) NOT NULL,
  symbol VARCHAR(10) NOT NULL,
  quantity INT NOT NULL,
  side VARCHAR(10) NOT NULL, -- 'BUY' or 'SELL'
  order_type VARCHAR(20) NOT NULL, -- 'MARKET', 'LIMIT', etc.
  status VARCHAR(50) NOT NULL, -- 'PENDING', 'OPEN', 'FILLED', 'CANCELLED', 'REJECTED'
  price DECIMAL(10, 2),
  executed_price DECIMAL(10, 2),
  filled_quantity INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (signal_id) REFERENCES signals(id)
);

CREATE INDEX idx_user_id ON orders(user_id);
CREATE INDEX idx_order_id ON orders(order_id);
CREATE INDEX idx_status ON orders(status);
```

### Tastytrade Connections Table (Optional, for UI)

```sql
CREATE TABLE tastytrade_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id VARCHAR(255) NOT NULL UNIQUE,
  account_number VARCHAR(255),
  connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_synced_at TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## Error Handling Guide

### Common Errors & Solutions

#### 1. `invalid_credentials` Error

**Cause:** Backend `TASTYTRADE_CLIENT_SECRET` doesn't match frontend's

**Solution:**
1. Verify both have identical client_secret from my.tastytrade.com
2. Redeploy both services
3. Delete old tokens from Redis
4. User reconnects Tastytrade account

**Code to add:**
```python
except Exception as e:
    if "invalid_credentials" in str(e):
        logger.critical(
            f"CREDENTIAL MISMATCH detected. "
            f"Backend TASTYTRADE_CLIENT_SECRET does not match "
            f"frontend credentials. Please verify .env synchronization."
        )
        raise HTTPException(
            status_code=401,
            detail="OAuth configuration mismatch. Contact support."
        )
```

#### 2. `Tastytrade account not connected` Error

**Cause:** User hasn't linked their Tastytrade account yet

**Solution:** Redirect user to "Connect Tastytrade" flow

**Code:**
```typescript
if (!credentialsJson) {
  return NextResponse.json(
    { error: 'Tastytrade account not connected. Please link your account.' },
    { status: 400 }
  );
}
```

#### 3. `Account not found` Error

**Cause:** Account number doesn't exist on Tastytrade

**Solution:** Refresh credentials or use correct account number

#### 4. `Insufficient buying power` Error

**Cause:** Account doesn't have enough cash for the trade

**Solution:** Show user current balance and available buying power before trade

#### 5. `Expired refresh token` Error

**Cause:** Token stored in Redis has expired (shouldn't happen, but edge case)

**Solution:** User must reconnect account

---

## Environment Variables Checklist

### Frontend (.env.local & Vercel)

- [ ] `NEXT_PUBLIC_TASTYTRADE_CLIENT_ID=ABC123xyz`
- [ ] `TASTYTRADE_CLIENT_SECRET=XYZ789abc` (keep private!)
- [ ] `TASTYTRADE_REDIRECT_URI=https://yourdomain.com/api/tastytrade/oauth/callback`
- [ ] `PYTHON_BACKEND_URL=https://your-python-api.com`

### Backend (Python .env)

- [ ] `TASTYTRADE_CLIENT_ID=ABC123xyz` (same as frontend)
- [ ] `TASTYTRADE_CLIENT_SECRET=XYZ789abc` (same as frontend)
- [ ] `TASTYTRADE_OAUTH_URL=https://api.tastytrade.com`
- [ ] `REDIS_URL=redis://localhost:6379` (or your Redis instance)
- [ ] `DATABASE_URL=postgresql://...` (for order storage)

---

## Testing Checklist

### Before Going to Production

- [ ] **OAuth Flow**
  - [ ] User can click "Connect Tastytrade"
  - [ ] Redirected to Tastytrade login page
  - [ ] After login, redirected back with credentials
  - [ ] Credentials successfully stored in Redis

- [ ] **Trade Execution**
  - [ ] User can approve a signal
  - [ ] Backend receives correct credentials
  - [ ] `OAuthSession` created successfully (no `invalid_credentials` error)
  - [ ] Order placed with Tastytrade
  - [ ] Order ID returned to frontend
  - [ ] Order stored in database

- [ ] **Order Tracking**
  - [ ] Can check order status
  - [ ] Status updates correctly as order fills
  - [ ] Can check account balance
  - [ ] Can view open positions

- [ ] **Multi-User Scenarios**
  - [ ] User A can trade with their account
  - [ ] User B can trade with their account (simultaneously)
  - [ ] No credential leakage between users
  - [ ] Each user sees their own orders

- [ ] **Error Cases**
  - [ ] If client_secret mismatches, clear error message
  - [ ] If account not connected, user redirected to connect flow
  - [ ] If insufficient buying power, user sees specific error
  - [ ] If Tastytrade API is down, graceful error handling

---

## Summary for Antigravity

### Key Points to Implement

1. **OAuth Integration**
   - Frontend initiates OAuth → Tastytrade login → Code exchange
   - Tokens stored in Redis keyed by `userId`
   - User's `accountNumber` also stored for later lookups

2. **Critical: Credential Synchronization**
   - Frontend & Backend MUST have identical `TASTYTRADE_CLIENT_ID` and `TASTYTRADE_CLIENT_SECRET`
   - If different, refresh tokens will be invalid
   - Verify at my.tastytrade.com and set in both .env files

3. **Trade Execution Flow**
   - Frontend → Next.js API → Python Backend
   - Python backend creates `OAuthSession(client_secret, refresh_token)`
   - Places order via Tastytrade SDK
   - Returns `order_id` to frontend

4. **Account & Order Data**
   - Query order status: Python backend gets session, retrieves order
   - Query account balance: Python backend gets session, retrieves balance & positions
   - All operations use the stored `refresh_token` + `client_secret`

5. **Error Handling**
   - Watch for `invalid_credentials` → credential mismatch
   - Watch for missing credentials → account not connected
   - Log all OAuth operations for debugging

### Files to Create/Modify

**Frontend:**
- `pages/api/tastytrade/oauth/url/route.ts` (OAuth URL generation)
- `pages/api/tastytrade/oauth/callback/route.ts` (Token exchange & storage)
- `pages/api/signals/[id]/approve/route.ts` (Trade execution)
- `pages/api/orders/[orderId]/status/route.ts` (Order tracking)
- `pages/api/account/balance/route.ts` (Account data)
- `components/TastytradeLink.tsx` (Connect button)

**Backend:**
- `tasty_api_server.py` (Flask/FastAPI endpoints)
- Add endpoints: `/execute-trade`, `/orders/{orderId}/status`, `/account/balance`

**Database:**
- `orders` table (track executed orders)
- `tastytrade_connections` table (optional, for UI)

---

## Next Steps

1. **Verify OAuth credentials** at my.tastytrade.com
2. **Set environment variables** identically on frontend & backend
3. **Implement OAuth flow** (Steps 2.1 - 2.2)
4. **Implement trade execution** (Step 3)
5. **Add order/account tracking** (Step 4)
6. **Test multi-user scenarios** thoroughly
7. **Deploy to production**

---

## References

- Tastytrade OAuth: https://developer.tastytrade.com/oauth
- Tastytrade Python SDK: https://github.com/tastytrade/tastytrade-sdk-python
- OAuth 2.0 RFC 6749: https://datatracker.ietf.org/doc/html/rfc6749
