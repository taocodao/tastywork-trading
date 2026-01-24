# Fix: OAuth Scope Error & Grant Revoked
**Date:** 2026-01-23
**Status:** Implemented

## Problem 1: Invalid Scope
Error message:
```
OAuth error: Some of the requested scopes were unknown, malformed, or not authorized: offline_access
```

**Cause:** `offline_access` is a standard OIDC scope for getting refresh tokens, but Tastytrade's OAuth implementation doesn't support it.

**Fix:** Removed `offline_access` from the scopes array in `src/lib/tastytrade-oauth.ts`:
```typescript
// Before
scopes: ['read', 'trade', 'openid', 'offline_access'],

// After
scopes: ['read', 'trade', 'openid'],
```

Tastytrade automatically provides refresh tokens without explicitly requesting `offline_access`.

---

## Problem 2: Grant Revoked
Error message:
```json
{"error_code":"invalid_grant","error_description":"Grant revoked"}
```

**Cause:** The user's refresh token has been invalidated. This happens when:
- User revokes app access in Tastytrade settings
- Token was already used and rotated (but we didn't save the new one)
- Token expired after long inactivity

**Solution:** User must re-authenticate:
1. Go to the dashboard
2. Click "Reconnect Tastytrade"
3. Complete OAuth flow to get a fresh token

---

## Prevention
- Always store the rotated refresh token when Tastytrade returns a new one (already implemented in `account/route.ts`)
- Consider adding a "Disconnect" button that properly clears tokens
