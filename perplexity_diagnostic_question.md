# Perplexity Question: Diagnosing IB Error 201 Root Cause

## Main Question:

I've enabled Options Level 4 in my Interactive Brokers paper trading account 12+ hours ago, configured ReadOnlyApi=no, and restarted IB Gateway multiple times, but I STILL get "Error 201: You are not able to submit this order because you do not have trading permissions for this options strategy" when placing cash-secured put orders via API during market hours.

**What I need:**
1. **How to DEFINITIVELY verify** that Options Level 4 is actually active for API trading (not just showing in the web portal)
2. **Specific diagnostic steps** to identify the exact permission that's missing
3. **How to check if my LIVE account** (not paper) has the permissions fully activated
4. **Whether paper trading accounts have additional restrictions** beyond live account permissions

---

## Complete Context:

### What I've Already Done:

**Account Configuration:**
- ✅ Options Level 4 enabled in IB web portal (shows as "enabled")
- ✅ ReadOnlyApi=no in config.ini
- ✅ ReadOnlyLogin=no in config.ini
- ✅ IB Gateway restarted 4+ times
- ✅ Waited 12+ hours since enabling permissions
- ✅ Using paper trading port 4004
- ✅ Market is OPEN (tested at 10:11 AM EST)

**Order Details:**
- Symbol: SPY 580P expiring March 20, 2026
- Action: SELL TO OPEN (Cash-Secured Put)
- Order Type: Limit ($5.00)
- Quantity: 1 contract
- API: ib_insync Python library

**Consistent Error:**
```
Order Flow:
1. PendingSubmit ✅
2. Cancelled with Error 10349 (TIF set to DAY) ⚠️
3. Inactive ❌
4. Cancelled with Error 201 ❌

Error Message:
"Error 201, reqId 12: Order rejected - reason: You are not able to 
submit this order because you do not have trading permissions for 
this options strategy."
```

---

## Specific Questions:

### 1. How to Verify Live Account Permissions?

**Question:** How do I check in my LIVE Interactive Brokers account (not paper account) whether Options Level 4 is:
- a) Requested but pending approval?
- b) Approved but not yet synced to API?
- c) Fully active for API trading?

**What I need:** Exact navigation path in Client Portal and what text/status to look for to confirm API activation (not just web portal display).

### 2. Paper vs Live Account Permission Sync

**Question:** Do paper trading accounts require BOTH:
- a) The paper account to show Options Level 4 in settings
- AND
- b) The linked LIVE account to have Options Level 4 APPROVED and API-ACTIVATED?

**Follow-up:** If I only enabled permissions in the paper account settings page (not the live account), would that cause Error 201?

### 3. Diagnostic API Call

**Question:** Is there an IB API call or Python code I can run to query:
- What permission levels are ACTUALLY active for my account (not just what shows in web portal)?
- Which specific permission is missing for selling cash-secured puts?
- Whether the account is flagged as "read-only" from the server's perspective?

**Example code request:** Show me Python code using ib_insync to check actual active permissions.

### 4. Error 10349 Before Error 201

**Question:** I notice Error 10349 ("Order TIF was set to DAY") appears RIGHT BEFORE Error 201. Could the Error 10349 be related to the permission issue, or is it just a harmless warning?

**Context:** Order status log shows:
```
1. PendingSubmit (0.0 seconds)
2. Cancelled with Error 10349 (0.02 seconds)
3. Inactive (0.03 seconds)
4. Cancelled with Error 201 (0.05 seconds)
```

### 5. Cash-Secured Put Specific Permission

**Question:** Is there a SEPARATE permission beyond "Options Level 4" specifically for:
- Selling naked puts?
- Cash-secured puts?
- Short option positions?

**What to check:** Where in IB Client Portal can I verify I have explicit permission to SELL puts (not just buy)?

### 6. Account Type Restrictions

**Question:** Do IB paper trading accounts have restrictions on:
- Maximum option strike prices?
- Expiration dates (need approval for 30+ DTE)?
- Specific underlyings (SPY vs other symbols)?
- Selling vs buying options (separate permissions)?

**Test:** Should I try a different order (buy vs sell, different symbol, shorter expiration) to narrow down the issue?

### 7. Margin vs Cash Account

**Question:** Do cash-secured puts require:
- a) Margin account approval specifically?
- b) A minimum account balance in the paper account?
- c) Explicit "Margin Trading" permission beyond Options Level 4?

**My situation:** I have a $1M paper trading account. Could margin settings be the issue?

### 8. Hidden Permission Settings

**Question:** Are there ANY hidden or additional permission settings in IB that:
- Aren't visible in the standard "Trading Permissions" page?
- Control API trading separately from web portal trading?
- Require manual approval from IB support?
- Apply specifically to paper trading accounts?

---

## What Would Help Most:

**Priority 1:** Exact steps to verify my LIVE account has Options Level 4 APPROVED and API-ACTIVATED (not just "enabled" in web display)

**Priority 2:** Python code to query actual active permissions via IB API (not web portal)

**Priority 3:** List of all permissions required for selling cash-secured puts via API in a paper trading account

---

## Alternative Focused Question:

How do I verify that my Interactive Brokers LIVE account (not paper account) has Options Level 4 permissions that are FULLY ACTIVATED for API trading (not just showing as "enabled" in the web portal)? When I check the paper trading account settings, it shows "Options level 4" but API orders still get Error 201 after 12+ hours. Is there a difference between "web portal shows enabled" and "API accepts orders"?

---

## Expected Information Needed:

1. **Client Portal navigation path** to check LIVE account options status
2. **Specific text/status indicators** that confirm API activation (vs just approval)
3. **Python code** to query permissions via API
4. **List of ALL permissions** needed for cash-secured puts (beyond Options Level 4)
5. **Troubleshooting checklist** to identify which specific permission is missing
6. **Timeline** for when "approved in web portal" becomes "active for API"

---

## Why This is Confusing:

- Web portal shows "Options level 4" ✅
- Config shows ReadOnlyApi=no ✅
- IB Gateway connects fine ✅
- Order creates Order ID ✅
- But API consistently rejects with "permissions" error ❌

**Something is disconnected between what the web portal displays and what the API trading system recognizes.**

I need to find out EXACTLY where to look to see the REAL permission status that the API uses (not the web portal display).
