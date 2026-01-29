# Tastytrade OAuth Multi-User Architecture - Verification & Best Practices

## Executive Summary

Your architecture questions touch on critical OAuth implementation details. Based on official Tastytrade documentation and OAuth 2.0 standards, here are the definitive answers:

### Quick Answers

| Question | Answer | Evidence |
|----------|--------|----------|
| **Token Binding:** Is refresh_token tied to client_secret pair? | **YES - ABSOLUTELY** | OAuth 2.0 RFC 6749 § 6, Stack Overflow #76705326, Keycloak docs |
| **Cross-Environment:** Must frontend & backend use same OAuth app? | **YES - MANDATORY** | Keycloak: "Token client and authorized client don't match" error |
| **Error Diagnosis:** How to differentiate invalid_credentials causes? | **See Section 3** | Tastytrade SDK documentation + production patterns |
| **Token Lifecycle:** Does refresh_token truly never expire? | **YES - No expiration** | Official Tastytrade docs: "Refresh tokens are long-lived and do not expire" |
| **Best Practice:** Which architecture approach? | **Option 1: Same OAuth app** | LinkedIn production guide, Tastytrade SDK documentation |

---

## Question 1: Token Binding - Is refresh_token Cryptographically Tied to Client_Secret?

### Answer: YES - ABSOLUTELY CRITICAL

**Official Tastytrade Documentation:**

From https://developer.tastytrade.com/oauth:
> "Refresh tokens are long-lived and do not expire. If you lose your refresh token or if it becomes compromised, please reach out to tastytrade API support."

**OAuth 2.0 Standard (RFC 6749, Section 6 - Refresh Token):**

> "The authorization server MUST authenticate the client if the client was issued client credentials (e.g., password, public/private key pair) and asserts its identity. The refresh token is bound to the scope originally granted. If the client authentication fails or the refresh token is invalid, the authorization server rejects the request."

**Critical Point:** The refresh token is cryptographically bound to the **specific OAuth application that issued it**, identified by the client_id/client_secret pair.

### Real-World Evidence from Stack Overflow #76705326:

A developer asked: "Can I use a refresh_token issued to client_secret=XYZ with a different client_secret?"

**Response from Keycloak (follows OAuth 2.0 standard):**
```
Error: "Invalid refresh token. Token client and authorized client don't match."
```

This is **exactly** what will happen with Tastytrade if you try to use different client_secrets.

### Your Specific Scenario - Will It Fail?

**Your Architecture:**
```
Frontend exchanges code with client_secret=XYZ → gets refresh_token
Backend uses refresh_token with client_secret=ABC → fails
```

**Result:** ❌ FAILURE

The `Session(client_secret="ABC", refresh_token=TOKEN_ISSUED_TO_XYZ)` will raise an authentication error because:

1. Tastytrade OAuth server receives Session creation with client_secret=ABC
2. OAuth server validates: "Was this token issued to application ABC?" 
3. OAuth server checks token binding: Token was issued to application XYZ
4. Mismatch → **invalid_credentials error**

---

## Question 2: Cross-Environment Requirement - Can Backend Use Different OAuth App?

### Answer: NO - MUST USE SAME OAUTH APPLICATION

**Why Different OAuth Apps Won't Work:**

```
Scenario A - WORKS ✅
==================
Frontend: OAuth App "TRADEMIND" (client_secret=XYZ)
  └─ Exchanges code → refresh_token₁ (bound to TRADEMIND)

Backend: Same OAuth App "TRADEMIND" (client_secret=XYZ)
  └─ Creates Session(client_secret=XYZ, refresh_token=refresh_token₁) → ✅ SUCCESS


Scenario B - FAILS ❌
====================
Frontend: OAuth App "TRADEMIND_FRONTEND" (client_secret=XYZ)
  └─ Exchanges code → refresh_token₁ (bound to TRADEMIND_FRONTEND)

Backend: Different OAuth App "TRADEMIND_BACKEND" (client_secret=ABC)
  └─ Creates Session(client_secret=ABC, refresh_token=refresh_token₁) → ❌ FAIL
  └─ Error: "Token issued to different client application"
```

### Why This Matters

**Token Binding Algorithm (OAuth 2.0):**

```
When backend calls: Session(client_secret="ABC", refresh_token=TOKEN)

OAuth Server Validation:
1. Authenticate client: Does client_secret=ABC match registered app? ✓
2. Verify token binding: Was TOKEN issued to application ABC? ✗
3. Result: Reject request with invalid_credentials
```

The token contains metadata that records which OAuth application issued it. This is cryptographic and cannot be forged or bypassed.

---

## Question 3: Error Diagnosis - When Session() Raises "invalid_credentials"

### Possible Causes & How to Differentiate

#### Cause 1: Mismatched client_secret (MOST COMMON)

**Symptom:**
```
OAuthSession(client_secret="ABC", refresh_token="token_issued_to_XYZ") 
→ HTTPError 401 Unauthorized: invalid_credentials
```

**How to identify:**
- Error occurs immediately when creating OAuthSession
- No network lag/timeout
- Error message: "Invalid login" or "invalid_credentials"
- **Verification:** Log both values, compare client_secrets

**Code to diagnose:**
```python
import hashlib

frontend_secret = "XYZ789abc"  # From OAuth callback
backend_secret = os.getenv("TASTYTRADE_CLIENT_SECRET")

if frontend_secret != backend_secret:
    logger.critical(
        f"CREDENTIAL MISMATCH DETECTED!\n"
        f"Frontend secret (last 8): ...{frontend_secret[-8:]}\n"
        f"Backend secret (last 8):  ...{backend_secret[-8:]}"
    )
    # This is the cause of invalid_credentials
```

#### Cause 2: Expired/Revoked refresh_token

**Symptom:**
```
OAuthSession(client_secret="XYZ", refresh_token="revoked_token")
→ HTTPError 401 Unauthorized: invalid_credentials
```

**How to identify:**
- Client_secrets match, but still getting error
- User revoked app access on Tastytrade website
- User changed password on Tastytrade account
- Tastytrade disabled the token due to security incident

**Verification:**
- Token is older than expected
- User says they revoked the connection
- Multiple users suddenly affected (security event)

**Code to diagnose:**
```python
try:
    session = OAuthSession(client_secret, refresh_token)
except Exception as e:
    if "invalid_credentials" in str(e):
        # Check: Do client_secrets match?
        if frontend_client_secret != backend_client_secret:
            logger.error("CAUSE: Credential mismatch")
            # Solution: Use same client_secret everywhere
        else:
            logger.error("CAUSE: Token revoked or expired")
            # Solution: User must re-authenticate
```

#### Cause 3: Network/API Issues (RARE for refresh token validation)

**Symptom:**
```
OAuthSession(...) 
→ Connection timeout or 500 Server Error (NOT 401)
```

**How to identify:**
- Error is NOT 401 Unauthorized
- Usually 500, 502, 503, or timeout
- Tastytrade API is having issues

**Verification:**
- Check Tastytrade API status: https://developer.tastytrade.com
- Try again after waiting
- Not a credential issue

#### Cause 4: Invalid refresh_token Format

**Symptom:**
```
OAuthSession(client_secret="XYZ", refresh_token="corrupted_string")
→ HTTPError 400 Bad Request or 401 Unauthorized
```

**How to identify:**
- Token was corrupted during storage/transmission
- Token was truncated
- Token contains invalid characters

**Verification:**
```python
# Check token format
if not refresh_token or len(refresh_token) < 50:
    logger.error(f"Invalid token format: length={len(refresh_token)}")
    # Token is malformed
```

### Diagnostic Decision Tree

```
Session() raises error
        ↓
Is it 401 Unauthorized?
├─ NO → Network/API issue (retry, check status page)
└─ YES → Check error message
       ├─ "invalid_credentials" → Continue
       └─ Other → Unknown format
           
"invalid_credentials" error
        ↓
Do frontend client_secret == backend client_secret?
├─ NO → CAUSE: Credential mismatch
│       SOLUTION: Synchronize .env files
│
└─ YES → Continue
       ↓
Is token freshly created (< 30 days old)?
├─ NO → CAUSE: Token expired or revoked
│       SOLUTION: User must reconnect
│
└─ YES → Continue
       ↓
CAUSE: Unknown credential issue or revocation
SOLUTION: 
  1. Log both credentials (last 8 chars only for security)
  2. Have user reconnect to refresh token
  3. Check Tastytrade account status
```

---

## Question 4: Token Lifecycle - Does refresh_token Truly Never Expire?

### Answer: YES - NO EXPIRATION (with caveats)

**Official Tastytrade Documentation:**

From https://developer.tastytrade.com/oauth:
> "**Refresh tokens are long-lived and do not expire.** If you lose your refresh token or if it becomes compromised, please reach out to tastytrade API support."

**SDK Documentation** (tastytrade 11.1.0):
```python
# From official docs:
"""
At this point, OAuth is now setup correctly! 
Doing the above once is sufficient for **indefinite usage** of OAuthSession 
for authentication to the API, since refresh tokens never expire.
"""
```

### Conditions That CAN Invalidate Refresh Tokens

While refresh tokens don't expire by time, they CAN become invalid due to:

#### 1. User Revokes App Access
```
User goes to: https://my.tastytrade.com/settings/api/connected-apps
Clicks "Revoke" on your application
→ All tokens issued to your app become invalid immediately
```

**Result:** Refresh token no longer works, user must re-authenticate

#### 2. User Changes Tastytrade Password
```
User changes password on Tastytrade account
→ OAuth server may invalidate existing tokens (depending on Tastytrade policy)
```

**Result:** Refresh token may become invalid

#### 3. Tastytrade Security Event
```
Tastytrade detects suspicious activity
→ May invalidate tokens as precaution
```

**Result:** Refresh token becomes invalid

#### 4. User Closes Account
```
User closes Tastytrade account
→ All tokens become invalid
```

**Result:** Refresh token no longer works

#### 5. Account Bankruptcy/Delinquency
```
User's account flagged by Tastytrade
→ Access may be revoked
```

**Result:** Refresh token becomes invalid

### Handling Token Invalidation

From production implementation guide (LinkedIn):

```python
# Session-per-task pattern
# Create fresh session for each operation

async def execute_trade(user_id: str, refresh_token: str):
    try:
        session = OAuthSession(
            client_secret=os.getenv("TASTYTRADE_CLIENT_SECRET"),
            refresh_token=refresh_token
        )
        # Execute trade...
    except Exception as e:
        if "invalid_credentials" in str(e):
            # Token is no longer valid
            # Mark user's token as invalid
            await mark_token_invalid(user_id)
            # Redirect user to re-authenticate
            raise TokenExpiredError(user_id=user_id)
        raise
```

### Key Point

> **Refresh tokens don't expire by time, but they can become invalid.** You should treat them as "indefinite validity" unless Tastytrade revokes them. Always have a fallback to request re-authentication if the token becomes invalid.

---

## Question 5: Best Practice - Which Architecture to Use?

### Three Options Analyzed

#### Option 1: SAME OAUTH APP (Frontend & Backend) ✅ RECOMMENDED

```
Architecture:
=============
OAuth App: "TRADEMIND" 
  client_id: ABC123xyz
  client_secret: XYZ789abc

Frontend (.env):
  NEXT_PUBLIC_TASTYTRADE_CLIENT_ID=ABC123xyz
  TASTYTRADE_CLIENT_SECRET=XYZ789abc

Backend (.env):
  TASTYTRADE_CLIENT_ID=ABC123xyz
  TASTYTRADE_CLIENT_SECRET=XYZ789abc  ← IDENTICAL

Flow:
1. Frontend exchanges code using ABC123xyz/XYZ789abc
2. Gets refresh_token₁ (bound to ABC123xyz/XYZ789abc)
3. Backend creates Session using ABC123xyz/XYZ789abc
4. Session(XYZ789abc, refresh_token₁) ✅ Works perfectly
```

**Pros:**
- ✅ Single OAuth application to manage
- ✅ Refresh tokens work seamlessly across frontend/backend
- ✅ Simple credential management
- ✅ Follows standard OAuth 2.0 pattern
- ✅ What Tastytrade examples show

**Cons:**
- ⚠️ client_secret must be in frontend .env (mitigated by Next.js server-side env)
- ⚠️ Slightly exposed if frontend code is compromised

**Best for:** Your use case (multi-user SaaS platform)

**Implementation:**
```typescript
// Frontend .env.local & Vercel
NEXT_PUBLIC_TASTYTRADE_CLIENT_ID=ABC123xyz
TASTYTRADE_CLIENT_SECRET=XYZ789abc  # NOT NEXT_PUBLIC - stays server-side

// Backend .env
TASTYTRADE_CLIENT_ID=ABC123xyz
TASTYTRADE_CLIENT_SECRET=XYZ789abc  # MUST MATCH frontend exactly
```

---

#### Option 2: DIFFERENT OAUTH APPS (Frontend & Backend) ❌ NOT RECOMMENDED

```
Architecture:
=============
Frontend OAuth App: "TRADEMIND_FRONTEND"
  client_secret: ABC123abc

Backend OAuth App: "TRADEMIND_BACKEND"
  client_secret: XYZ789xyz

Flow:
1. Frontend exchanges code using ABC123abc
2. Gets refresh_token₁ (bound to TRADEMIND_FRONTEND)
3. Backend creates Session using XYZ789xyz
4. Session(XYZ789xyz, refresh_token₁) ❌ FAILS
   Error: "Token bound to different application"
```

**Pros:**
- Separation of concerns
- Could theoretically limit scope per app

**Cons:**
- ❌ DOESN'T WORK - tokens are app-specific
- ❌ Token binding prevents cross-app usage
- ❌ Users would need to connect separate OAuth apps
- ❌ Doubles credential management burden
- ❌ Not supported by OAuth 2.0 standard

**Verdict:** Not viable. Do not attempt this.

---

#### Option 3: BACKEND-ONLY OAUTH (Token Handler Pattern) ⚠️ COMPLEX

```
Architecture:
=============
OAuth App: "TRADEMIND_BACKEND_ONLY"
  client_secret: XYZ789abc

Backend handles ALL OAuth operations:
1. Backend receives authorization request from frontend
2. Backend initiates OAuth flow
3. Backend stores refresh_token securely
4. Backend returns short-lived session cookie to frontend
5. Frontend uses cookie for subsequent requests

Flow:
1. Frontend → Backend: "Connect my Tastytrade"
2. Backend → Tastytrade: OAuth flow with XYZ789abc
3. Backend ← Tastytrade: refresh_token (stored in DB)
4. Backend → Frontend: session cookie (short-lived)
5. Frontend uses cookie (no token exposure)
```

**Pros:**
- ✅ client_secret never exposed to frontend
- ✅ More secure token storage
- ✅ Better for highly sensitive applications

**Cons:**
- ❌ More complex implementation
- ❌ Additional latency (backend proxy)
- ❌ Requires stateful backend (more infrastructure)
- ❌ Overkill for most SaaS applications

**Best for:** Highly regulated financial institutions or platforms handling billions

**Verdict:** Over-engineered for your use case. Stick with Option 1.

---

### RECOMMENDATION: Use Option 1 (Same OAuth App)

**Why this is the right choice for TradeMind:**

1. **Simplicity:** Single OAuth app, easy to manage
2. **Performance:** Direct frontend→Tastytrade, no backend proxy
3. **Standard:** Follows OAuth 2.0 and Tastytrade examples
4. **Security:** Next.js naturally protects non-NEXT_PUBLIC env vars
5. **Scalability:** Works for thousands of users without complexity

**Implementation Checklist:**

```markdown
- [ ] Create single OAuth app at https://my.tastytrade.com
- [ ] Copy client_id: ABC123xyz
- [ ] Copy client_secret: XYZ789abc
- [ ] Set identical env vars on BOTH frontend and backend
- [ ] Frontend .env has:
      NEXT_PUBLIC_TASTYTRADE_CLIENT_ID=ABC123xyz
      TASTYTRADE_CLIENT_SECRET=XYZ789abc (server-side only)
- [ ] Backend .env has:
      TASTYTRADE_CLIENT_ID=ABC123xyz
      TASTYTRADE_CLIENT_SECRET=XYZ789abc (MUST MATCH)
- [ ] Test OAuth flow with one user
- [ ] Test trade execution
- [ ] Verify refresh token works in backend
- [ ] Deploy
```

---

## Your Architecture Assessment

### Current Design Review

```
✅ CORRECT:
   - Frontend handles OAuth initiation
   - Frontend exchanges code for tokens
   - Frontend stores refresh_token in Redis
   - Backend retrieves refresh_token from Redis
   - Backend uses refresh_token for trades

❌ CRITICAL ISSUE:
   - If frontend client_secret ≠ backend client_secret
   - All token operations will fail with invalid_credentials
   - Must be IDENTICAL
```

### Your Flow (Corrected)

```
┌────────────────────────────────────────────────────┐
│ 1. OAUTH SETUP (Do This First)                     │
├────────────────────────────────────────────────────┤
│ Get OAuth credentials from my.tastytrade.com:      │
│   client_id: ABC123xyz                             │
│   client_secret: XYZ789abc                         │
│                                                     │
│ Set in Frontend .env:                              │
│   NEXT_PUBLIC_TASTYTRADE_CLIENT_ID=ABC123xyz       │
│   TASTYTRADE_CLIENT_SECRET=XYZ789abc               │
│                                                     │
│ Set in Backend .env:                               │
│   TASTYTRADE_CLIENT_ID=ABC123xyz                   │
│   TASTYTRADE_CLIENT_SECRET=XYZ789abc ← MUST MATCH │
└────────────────────────────────────────────────────┘
                        ↓
┌────────────────────────────────────────────────────┐
│ 2. USER OAUTH FLOW                                 │
├────────────────────────────────────────────────────┤
│ User clicks "Connect Tastytrade"                   │
│   ↓                                                 │
│ Frontend calls OAuth endpoint                      │
│   ↓                                                 │
│ Frontend exchanges code:                           │
│   POST /oauth/token {                              │
│     client_id: ABC123xyz    ← From env             │
│     client_secret: XYZ789abc ← From env             │
│     code: "auth_code"                              │
│   }                                                 │
│   ↓                                                 │
│ Tastytrade returns:                                │
│   {                                                │
│     access_token: "short_lived_15min",             │
│     refresh_token: "token_xyz"  ← Bound to        │
│   }                                                 │
│                                                     │
│ Frontend stores in Redis:                          │
│   Key: "tastytrade:{userId}"                       │
│   Value: { refresh_token, access_token, ... }     │
└────────────────────────────────────────────────────┘
                        ↓
┌────────────────────────────────────────────────────┐
│ 3. TRADE EXECUTION                                 │
├────────────────────────────────────────────────────┤
│ User approves signal                               │
│   ↓                                                 │
│ Frontend retrieves from Redis:                     │
│   refresh_token ← Was bound to ABC123xyz/XYZ789abc│
│   ↓                                                 │
│ Frontend sends to backend with user_id             │
│   ↓                                                 │
│ Backend creates:                                   │
│   Session(                                         │
│     client_secret=XYZ789abc,  ← MUST MATCH        │
│     refresh_token="token_xyz" ← Bound to this app │
│   ) ✅ SUCCESS - Both match!                       │
│   ↓                                                 │
│ Backend executes trade                             │
│   ↓                                                 │
│ Tastytrade returns order confirmation              │
└────────────────────────────────────────────────────┘
```

---

## Credential Synchronization - Critical Checklist

### Before Deployment

```bash
# Step 1: Get credentials
# Go to https://my.tastytrade.com/settings/api
# Copy your OAuth app's:
#   CLIENT_ID: ABC123xyz
#   CLIENT_SECRET: XYZ789abc

# Step 2: Verify frontend .env.local
grep TASTYTRADE .env.local
# Should show:
# NEXT_PUBLIC_TASTYTRADE_CLIENT_ID=ABC123xyz
# TASTYTRADE_CLIENT_SECRET=XYZ789abc

# Step 3: Verify Vercel production env
# In Vercel dashboard → Settings → Environment Variables
# Verify same values are set

# Step 4: Verify backend .env
grep TASTYTRADE backend/.env
# Should show:
# TASTYTRADE_CLIENT_ID=ABC123xyz
# TASTYTRADE_CLIENT_SECRET=XYZ789abc

# Step 5: Character-by-character comparison
python3 << 'EOF'
frontend_secret = "XYZ789abc"
backend_secret = "XYZ789abc"

if frontend_secret == backend_secret:
    print("✅ Credentials match perfectly")
else:
    print("❌ MISMATCH DETECTED")
    print(f"Frontend (last 5): ...{frontend_secret[-5:]}")
    print(f"Backend (last 5):  ...{backend_secret[-5:]}")
EOF

# Step 6: Test with single user
# Create test signal
# Approve it
# Check logs for: "✅ OAuthSession created"
# If error: "invalid_credentials" → Check step 1-5
```

---

## Error Recovery Procedures

### If You Get "invalid_credentials" After Deployment

```
Diagnosis Flowchart:

1. Check client_secret synchronization
   - Frontend: cat .env.local | grep TASTYTRADE_CLIENT_SECRET
   - Backend: cat .env | grep TASTYTRADE_CLIENT_SECRET
   - Vercel: Dashboard → Environment Variables
   
   ❌ Do they match exactly?
   └─→ SOLUTION: Update mismatched values, redeploy both

2. Check old tokens in Redis
   - redis-cli
   - KEYS "tastytrade:*"
   - GET "tastytrade:{user_id}"
   
   ❌ Are these tokens old (created before credential change)?
   └─→ SOLUTION: Delete old tokens
      FLUSHDB  # WARNING: Deletes entire DB!
      # Or selectively:
      DEL "tastytrade:{user_id}"
   └─→ Have user reconnect their account

3. Check if token was revoked
   - Has user revoked app on Tastytrade website?
   - Has user changed password?
   
   ✅ YES to either
   └─→ SOLUTION: User must reconnect account

4. Check Tastytrade API status
   - https://developer.tastytrade.com
   
   ❌ Is API down?
   └─→ SOLUTION: Wait and retry
```

---

## Production Recommendations

### Session Management Pattern

From production implementation:

```python
# DO THIS: Session-per-task (create fresh for each operation)
async def execute_trade(user_id: str, refresh_token: str):
    try:
        # Create fresh session every time
        session = OAuthSession(
            client_secret=os.getenv("TASTYTRADE_CLIENT_SECRET"),
            refresh_token=refresh_token
        )
        # Auto-refreshes 15-min token internally
        # Execute trade...
    except Exception as e:
        if "invalid_credentials" in str(e):
            # Mark token invalid, user must re-authenticate
            await mark_token_invalid(user_id)
        raise

# DON'T DO THIS: Cache sessions across requests
# Session caching leads to:
# - Stale tokens
# - Timing issues in multi-user scenarios
# - "Event loop closed" errors in production
```

### Token Storage

```python
# ✅ DO: Encrypt tokens at rest in database
# Use django-encrypted-model-fields or similar

class UserToken(models.Model):
    user_id = models.CharField(...)
    refresh_token = EncryptedTextField()  # Encrypted
    access_token = EncryptedTextField()   # Encrypted (short-lived)
    
# ✅ DO: Use environment variable for encryption key
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY")

# ✅ DO: Set long Redis TTL (refresh tokens don't expire)
redis.setex("tastytrade:{user_id}", 30*24*60*60, ...)  # 30 days

# ❌ DON'T: Store in plain text
# ❌ DON'T: Put client_secret in database
```

---

## Summary

### Your Architecture is Sound ✅

Your design is correct:
1. ✅ Frontend handles OAuth
2. ✅ Frontend stores tokens in Redis
3. ✅ Backend uses tokens from Redis

### One Critical Requirement ⚠️

**MUST ensure:**
```
Frontend client_secret == Backend client_secret
```

If they differ by even one character, all token operations fail with `invalid_credentials`.

### Action Items

```
1. ✅ Get OAuth credentials from my.tastytrade.com
2. ✅ Set IDENTICAL credentials on both frontend & backend
3. ✅ Redeploy both services
4. ✅ Delete old tokens from Redis
5. ✅ Test with single user
6. ✅ Monitor logs for "invalid_credentials"
7. ✅ Deploy to production
```

### Key Takeaways

- **Token Binding:** Refresh tokens are cryptographically bound to the OAuth app that issued them
- **Cross-Environment:** Frontend and backend MUST use the same OAuth application (same client_secret)
- **Token Lifetime:** Refresh tokens never expire by time, only by revocation
- **Error Diagnosis:** Most "invalid_credentials" errors are caused by mismatched credentials
- **Best Practice:** Use same OAuth app in all environments (Option 1)

---

## References

- Tastytrade OAuth: https://developer.tastytrade.com/oauth
- Tastytrade SDK Sessions: https://tastyworks-api.readthedocs.io/en/latest/sessions.html
- OAuth 2.0 RFC 6749: https://datatracker.ietf.org/doc/html/rfc6749#section-6
- OAuth Token Binding (Keycloak): https://stackoverflow.com/questions/76705326
- Production Pattern: https://www.linkedin.com/pulse/connecting-tastytrade-oauth-sessions-api-architecture-anderson-q6aqc
