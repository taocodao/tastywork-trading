# Perplexity Question: IB Options Level 4 Still Getting Permission Error

## Question for Perplexity:

I have an Interactive Brokers paper trading account with **Options Level 4** permissions enabled, but I'm still getting "Error 201: You are not able to submit this order because you do not have trading permissions for this options strategy" when trying to place a cash-secured put order via the IB API.

**My current setup:**
- Account Type: Paper Trading (DUK782510)
- Options Permission: **Level 4** (confirmed enabled in account settings)
- Other Permissions: Stocks ✅, Currency/Forex ✅
- Order Type: SELL TO OPEN (Cash-Secured Put)
- Symbol: SPY 580P expiring March 20, 2026
- API: ib_insync Python library via IB Gateway
- Connection: Working perfectly (order creates with Order ID)

**The error:**
```
Error 201, reqId: Order rejected - reason: You are not able to submit this order because you do not have trading permissions for this options strategy.
```

**What I've tried:**
1. Enabled Options Level 4 in Account Management
2. Waited 30+ minutes for permissions to propagate
3. Restarted IB Gateway
4. Verified permissions show as active in the web portal
5. Order submission code works (creates Order ID before rejection)

**Questions:**
1. Is there a difference between web portal permissions and API permissions for paper trading accounts?
2. Do I need to enable additional permissions beyond "Options Level 4" for selling naked puts or cash-secured puts?
3. Is there a separate setting for enabling options trading specifically via the API?
4. Does IB Gateway require a restart or re-login after permissions changes?
5. Are there regional or market-specific permissions I need to enable (e.g., "US Options")?
6. Is there a delay between enabling permissions in the web portal and them being active for API trading?

**Screenshot context:**
My account shows "Options level 4" with an Edit button (enabled), but API orders are still being rejected for permissions.

---

## Alternative Focused Version:

Why am I getting "Error 201: You are not able to submit this order because you do not have trading permissions for this options strategy" from Interactive Brokers API when I have Options Level 4 already enabled in my paper trading account? Is Level 4 sufficient for selling cash-secured puts, or do I need additional permissions beyond the standard options level?

---

## Follow-up if needed:

"What is the difference between the options permission levels (1-4) in Interactive Brokers, and which specific level is required for selling cash-secured puts via the API?"
