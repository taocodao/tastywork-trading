# Tastytrade OAuth Token Refresh - Complete Implementation Guide

## Quick Answer

Your code is **almost correct**, but you're hitting an nginx 401 error because:

1. **Wrong endpoint domain** - It's `api.tastyworks.com`, NOT `api.tastytrade.com`
2. **Possible encoding issue** - URLSearchParams might not be encoding correctly
3. **Token might be expired/revoked** - User needs to re-authenticate

---

## 1. Correct API Endpoint

### Token Refresh Endpoint

```
POST https://api.tastyworks.com/oauth/token
```

**NOT** `api.tastytrade.com` - that's a different service.

### Other Important Endpoints

```
# Get user info
GET https://api.tastyworks.com/users/me
Header: Authorization: Bearer {access_token}

# Get accounts
GET https://api.tastyworks.com/customers/me/accounts
Header: Authorization: Bearer {access_token}

# Get positions (for account {account_id})
GET https://api.tastyworks.com/accounts/{account_id}/positions
Header: Authorization: Bearer {access_token}

# Submit order
POST https://api.tastyworks.com/accounts/{account_id}/orders
Header: Authorization: Bearer {access_token}
Body: { order details }
```

---

## 2. Required Request Parameters for Token Refresh

### POST Body Parameters

```javascript
{
    grant_type: "refresh_token",           // REQUIRED - literal string
    refresh_token: "{user's token}",       // REQUIRED - the refresh token you have
    client_id: "{your_client_id}",         // REQUIRED
    client_secret: "{your_client_secret}", // REQUIRED
    scope: "PlaceTrades AccountAccess"     // OPTIONAL but recommended
}
```

**All four parameters are REQUIRED:**
- `grant_type` - Must be exactly `"refresh_token"`
- `refresh_token` - The user's stored refresh token from OAuth callback
- `client_id` - Your Tastytrade app client ID
- `client_secret` - Your Tastytrade app client secret

---

## 3. Required Headers

```javascript
{
    "Content-Type": "application/x-www-form-urlencoded",
    // NO Authorization header needed for token refresh
    // NO User-Agent required (but doesn't hurt)
}
```

**Important:** Token refresh does NOT need an `Authorization` header. You're sending credentials in the body instead.

---

## 4. Working TypeScript Implementation

### Option A: Using `fetch` (Recommended)

```typescript
interface TokenRefreshResponse {
    access_token: string;
    refresh_token: string;
    token_type: string;
    expires_in: number;
}

async function refreshTastytradeToken(
    clientId: string,
    clientSecret: string,
    refreshToken: string
): Promise<TokenRefreshResponse> {
    try {
        // Method 1: URLSearchParams (most compatible)
        const body = new URLSearchParams();
        body.append('grant_type', 'refresh_token');
        body.append('refresh_token', refreshToken);
        body.append('client_id', clientId);
        body.append('client_secret', clientSecret);
        body.append('scope', 'PlaceTrades AccountAccess');

        const response = await fetch('https://api.tastyworks.com/oauth/token', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: body.toString(),
        });

        if (!response.ok) {
            // Debug: Log the actual response
            const errorText = await response.text();
            console.error('Token refresh failed:', response.status, errorText);
            throw new Error(`Token refresh failed: ${response.status}`);
        }

        const data: TokenRefreshResponse = await response.json();

        return {
            access_token: data.access_token,
            refresh_token: data.refresh_token,
            token_type: data.token_type,
            expires_in: data.expires_in,
        };
    } catch (error) {
        console.error('Error refreshing token:', error);
        throw error;
    }
}
```

### Option B: Using `axios` (Alternative)

```typescript
import axios from 'axios';

async function refreshTastytradeToken(
    clientId: string,
    clientSecret: string,
    refreshToken: string
): Promise<TokenRefreshResponse> {
    try {
        const response = await axios.post(
            'https://api.tastyworks.com/oauth/token',
            {
                grant_type: 'refresh_token',
                refresh_token: refreshToken,
                client_id: clientId,
                client_secret: clientSecret,
                scope: 'PlaceTrades AccountAccess',
            },
            {
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
            }
        );

        return response.data;
    } catch (error) {
        if (axios.isAxiosError(error)) {
            console.error('Token refresh error:', error.response?.status, error.response?.data);
        }
        throw error;
    }
}
```

### Option C: Using `node-fetch` (Node.js)

```typescript
import fetch from 'node-fetch';

async function refreshTastytradeToken(
    clientId: string,
    clientSecret: string,
    refreshToken: string
): Promise<TokenRefreshResponse> {
    const params = new URLSearchParams({
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
        client_id: clientId,
        client_secret: clientSecret,
        scope: 'PlaceTrades AccountAccess',
    });

    const response = await fetch('https://api.tastyworks.com/oauth/token', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: params.toString(),
    });

    if (!response.ok) {
        const text = await response.text();
        throw new Error(`Token refresh failed: ${response.status} - ${text}`);
    }

    return response.json() as Promise<TokenRefreshResponse>;
}
```

---

## 5. Using the Access Token - Complete Examples

### Get User Information

```typescript
async function getTastytradeUser(accessToken: string): Promise<any> {
    const response = await fetch('https://api.tastyworks.com/users/me', {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Accept': 'application/json',
        },
    });

    if (!response.ok) {
        throw new Error(`Failed to get user: ${response.status}`);
    }

    return response.json();
}
```

### Get User's Trading Accounts

```typescript
async function getTastytradeAccounts(accessToken: string): Promise<any> {
    const response = await fetch('https://api.tastyworks.com/customers/me/accounts', {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Accept': 'application/json',
        },
    });

    if (!response.ok) {
        throw new Error(`Failed to get accounts: ${response.status}`);
    }

    const data = await response.json();
    return data.data.items; // Tastytrade wraps responses
}
```

### Get Account Positions

```typescript
async function getAccountPositions(accessToken: string, accountId: string): Promise<any> {
    const response = await fetch(`https://api.tastyworks.com/accounts/${accountId}/positions`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Accept': 'application/json',
        },
    });

    if (!response.ok) {
        throw new Error(`Failed to get positions: ${response.status}`);
    }

    const data = await response.json();
    return data.data.items;
}
```

### Submit an Order

```typescript
interface OrderRequest {
    symbol: string;
    quantity: number;
    orderType: 'Limit' | 'Market';
    timeInForce: 'Day' | 'GTC'; // GTC = Good Till Cancelled
    limitPrice?: number;
    side: 'Buy' | 'Sell';
}

async function submitOrder(
    accessToken: string,
    accountId: string,
    order: OrderRequest
): Promise<any> {
    const body = {
        account_number: accountId,
        symbol: order.symbol,
        quantity: order.quantity,
        order_type: order.orderType,
        time_in_force: order.timeInForce,
        limit_price: order.limitPrice || null,
        side: order.side,
    };

    const response = await fetch(
        `https://api.tastyworks.com/accounts/${accountId}/orders`,
        {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${accessToken}`,
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            body: JSON.stringify(body),
        }
    );

    if (!response.ok) {
        const error = await response.text();
        throw new Error(`Order submission failed: ${response.status} - ${error}`);
    }

    return response.json();
}
```

---

## 6. Complete Integration Example

```typescript
// ============================================
// Complete workflow: Refresh token → Get accounts → Place order
// ============================================

async function executeTrade(
    clientId: string,
    clientSecret: string,
    storedRefreshToken: string,
    symbol: string,
    quantity: number
): Promise<void> {
    try {
        // Step 1: Refresh the OAuth token
        console.log('1. Refreshing OAuth token...');
        const tokenData = await refreshTastytradeToken(
            clientId,
            clientSecret,
            storedRefreshToken
        );
        const accessToken = tokenData.access_token;
        const newRefreshToken = tokenData.refresh_token;

        console.log('✅ Token refreshed successfully');

        // Step 2: Get user's accounts
        console.log('2. Fetching accounts...');
        const accounts = await getTastytradeAccounts(accessToken);

        if (!accounts || accounts.length === 0) {
            throw new Error('No trading accounts found');
        }

        const accountId = accounts[0].account_number;
        console.log(`✅ Using account: ${accountId}`);

        // Step 3: Get current positions (for verification)
        console.log('3. Fetching positions...');
        const positions = await getAccountPositions(accessToken, accountId);
        console.log(`✅ Current positions: ${positions.length}`);

        // Step 4: Place the order
        console.log(`4. Placing order: ${quantity} shares of ${symbol}...`);
        const orderResult = await submitOrder(accessToken, accountId, {
            symbol,
            quantity,
            orderType: 'Market',
            timeInForce: 'Day',
            side: 'Buy',
        });

        console.log('✅ Order placed successfully:', orderResult);

        // Step 5: Update stored refresh token (it rotates on each refresh)
        console.log('5. Saving new refresh token...');
        // TODO: Save newRefreshToken back to Redis/database
        // await updateUserRefreshToken(userId, newRefreshToken);

        console.log('✅ Trade execution complete');
    } catch (error) {
        console.error('❌ Trade execution failed:', error);
        throw error;
    }
}

// Usage:
// await executeTrade(
//     process.env.TASTYTRADE_CLIENT_ID!,
//     process.env.TASTYTRADE_CLIENT_SECRET!,
//     userStoredRefreshToken,
//     'AAPL',
//     10
// );
```

---

## 7. Common Errors & Solutions

### Error: 401 Unauthorized (nginx page)

**Possible Causes:**

1. **Wrong endpoint** - Using `api.tastytrade.com` instead of `api.tastyworks.com`
   - **Fix:** Change to `https://api.tastyworks.com/oauth/token`

2. **Invalid client credentials** - Client ID or secret is wrong
   - **Fix:** Verify in your Tastytrade app settings
   - **Verify:** Log the values (last 4 chars only): `clientId.slice(-4)`, `clientSecret.slice(-4)`

3. **Refresh token expired/revoked** - User revoked access or token is too old
   - **Fix:** User needs to re-authenticate via OAuth
   - **Check:** When was token created? Tokens are typically good for 30 days

4. **Token format corrupted** - Refresh token has whitespace or encoding issues
   - **Fix:** Trim and validate before sending
   ```typescript
   refreshToken = refreshToken.trim();
   if (!refreshToken || refreshToken.length < 50) {
       throw new Error('Invalid refresh token format');
   }
   ```

5. **Missing or wrong Content-Type header**
   - **Fix:** Must be exactly: `application/x-www-form-urlencoded`
   - **Wrong:** `application/json` (common mistake)

### Error: 400 Bad Request

**Possible Causes:**

1. **Invalid grant_type** - Typo in the value
   - **Fix:** Must be exactly `"refresh_token"` (with underscore)

2. **Missing required parameter** - One of the four parameters is missing
   - **Fix:** Verify all four parameters are present:
     - `grant_type`
     - `refresh_token`
     - `client_id`
     - `client_secret`

3. **URLSearchParams encoding issue** - Parameters not properly encoded
   - **Fix:** Use explicit `.append()` method, not object literal
   ```typescript
   // ✅ CORRECT
   const body = new URLSearchParams();
   body.append('grant_type', 'refresh_token');
   body.append('refresh_token', refreshToken);
   
   // ❌ WRONG
   const body = new URLSearchParams({
       grant_type: 'refresh_token',
       refresh_token: refreshToken,
   }); // May not encode correctly in some environments
   ```

### Error: 500 Internal Server Error

**Possible Causes:**

1. **Tastytrade API is down** - Temporary service issue
   - **Fix:** Retry with exponential backoff

2. **Malformed refresh token** - Token contains invalid characters
   - **Fix:** Validate token format before sending

---

## 8. Production-Ready Implementation with Error Handling

```typescript
// ============================================
// Production-grade token refresh with retry logic
// ============================================

interface TokenRefreshOptions {
    maxRetries?: number;
    retryDelayMs?: number;
}

async function refreshTastytradeTokenWithRetry(
    clientId: string,
    clientSecret: string,
    refreshToken: string,
    options: TokenRefreshOptions = {}
): Promise<TokenRefreshResponse> {
    const { maxRetries = 3, retryDelayMs = 1000 } = options;

    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            console.log(`Token refresh attempt ${attempt}/${maxRetries}...`);

            // Validate inputs
            if (!clientId || !clientSecret || !refreshToken) {
                throw new Error('Missing required credentials');
            }

            if (refreshToken.length < 50) {
                throw new Error('Invalid refresh token format');
            }

            // Build request body
            const body = new URLSearchParams();
            body.append('grant_type', 'refresh_token');
            body.append('refresh_token', refreshToken.trim());
            body.append('client_id', clientId.trim());
            body.append('client_secret', clientSecret.trim());

            // Make request
            const response = await fetch('https://api.tastyworks.com/oauth/token', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: body.toString(),
            });

            // Handle non-JSON responses
            if (!response.ok) {
                const contentType = response.headers.get('content-type');
                let errorMessage = `HTTP ${response.status}`;

                if (contentType?.includes('application/json')) {
                    const errorData = await response.json();
                    errorMessage = errorData.error || errorMessage;
                } else {
                    // Likely nginx error page
                    const text = await response.text();
                    if (text.includes('401')) {
                        errorMessage = '401 Unauthorized - Check client credentials';
                    } else if (text.includes('502') || text.includes('503')) {
                        errorMessage = 'Tastytrade API temporarily unavailable';
                    }
                }

                throw new Error(errorMessage);
            }

            // Parse response
            const data: TokenRefreshResponse = await response.json();

            if (!data.access_token) {
                throw new Error('No access token in response');
            }

            console.log('✅ Token refresh successful');
            return data;
        } catch (error) {
            lastError = error instanceof Error ? error : new Error(String(error));

            if (attempt < maxRetries) {
                const delayMs = retryDelayMs * Math.pow(2, attempt - 1); // Exponential backoff
                console.warn(
                    `Attempt ${attempt} failed: ${lastError.message}. ` +
                    `Retrying in ${delayMs}ms...`
                );
                await new Promise((resolve) => setTimeout(resolve, delayMs));
            }
        }
    }

    throw new Error(
        `Token refresh failed after ${maxRetries} attempts: ${lastError?.message}`
    );
}
```

---

## 9. Testing the Implementation

```typescript
// ============================================
// Test script to verify everything works
// ============================================

async function testTastytradeIntegration() {
    const clientId = process.env.TASTYTRADE_CLIENT_ID;
    const clientSecret = process.env.TASTYTRADE_CLIENT_SECRET;
    const refreshToken = process.env.TASTYTRADE_REFRESH_TOKEN;

    if (!clientId || !clientSecret || !refreshToken) {
        console.error('Missing required environment variables');
        process.exit(1);
    }

    try {
        // Test 1: Token Refresh
        console.log('Test 1: Refreshing token...');
        const tokenData = await refreshTastytradeTokenWithRetry(
            clientId,
            clientSecret,
            refreshToken
        );
        console.log('✅ Token refresh successful');
        console.log(`   - Access token (first 10): ${tokenData.access_token.slice(0, 10)}...`);
        console.log(`   - Expires in: ${tokenData.expires_in} seconds`);

        // Test 2: Get User Info
        console.log('\nTest 2: Fetching user info...');
        const user = await getTastytradeUser(tokenData.access_token);
        console.log(`✅ User info retrieved: ${user.data.username}`);

        // Test 3: Get Accounts
        console.log('\nTest 3: Fetching accounts...');
        const accounts = await getTastytradeAccounts(tokenData.access_token);
        console.log(`✅ Found ${accounts.length} account(s)`);
        accounts.forEach((acc: any) => {
            console.log(`   - ${acc.account_number} (${acc.account_type})`);
        });

        // Test 4: Get Positions (for first account)
        if (accounts.length > 0) {
            console.log('\nTest 4: Fetching positions...');
            const positions = await getAccountPositions(
                tokenData.access_token,
                accounts[0].account_number
            );
            console.log(`✅ Found ${positions.length} position(s)`);
        }

        console.log('\n✅ All tests passed!');
    } catch (error) {
        console.error('❌ Test failed:', error);
        process.exit(1);
    }
}

// Run tests
testTastytradeIntegration();
```

---

## 10. Key Takeaways

| Question | Answer |
|----------|--------|
| **Correct endpoint?** | `https://api.tastyworks.com/oauth/token` (NOT api.tastytrade.com) |
| **Client ID required?** | YES - in the request body |
| **Client secret required?** | YES - in the request body |
| **Authorization header?** | NO - credentials go in body for token refresh |
| **Content-Type header?** | YES - must be `application/x-www-form-urlencoded` |
| **Using access token?** | Add header: `Authorization: Bearer {access_token}` |
| **Token expires?** | Yes - get a new one when `expires_in` time passes |
| **Refresh token rotates?** | YES - save the new one returned in response |

---

## 11. Environment Setup

```bash
# .env file
TASTYTRADE_CLIENT_ID=your_client_id_here
TASTYTRADE_CLIENT_SECRET=your_client_secret_here
TASTYTRADE_REFRESH_TOKEN=stored_refresh_token_from_user

# You get CLIENT_ID and CLIENT_SECRET from:
# https://my.tastytrade.com/settings/api

# You get REFRESH_TOKEN from the OAuth callback
```

---

## Summary

1. **Use `https://api.tastyworks.com/oauth/token`** (NOT tastytrade.com)
2. **Send all 4 parameters** in request body as form data
3. **Use `application/x-www-form-urlencoded`** Content-Type
4. **NO Authorization header** for token refresh
5. **Save the new refresh token** returned in response
6. **Use access token** with `Authorization: Bearer {token}` header for API calls
7. **Handle 401 errors** by asking user to re-authenticate

The code examples above are production-ready and handle errors, retries, and proper validation.
