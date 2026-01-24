# Research: Multi-User Signals & Expiration Logic
**Date:** 2026-01-23
**Source:** Market Research & Industry Standards

## 1. Multi-User Signal Execution

### Should signals be "consumed" after first execution?
**NO - Signals should NOT be consumed. Each user executes independently.**

**Industry Standards:**
- **TradersPost / SignalStack:** Single strategy broadcasts to multiple subscribed accounts.
- **Copy Trading:** One master signal replicates to many followers.

**Implementation Strategy:**
- Each user gets their own execution record (`UserSignalExecution` table).
- The "parent" signal remains available until expiration.
- Users can execute the same signal simultaneously without conflict.

### Liquidity Analysis (50+ Users)
**Can 50+ retail users execute the same order on SPY/QQQ/IWM?**
**YES.**

| ETF | Daily Volume | Avg Spread | Impact of 50 Orders |
|-----|-------------|------------|---------------------|
| **SPY** | 400M+ | $0.01 | Negligible (<0.01%) |
| **QQQ** | 200M+ | $0.01-0.02 | Negligible |
| **IWM** | 80M+ | $0.02-0.05 | Minimal (~1-2 bps) |

**Conclusion:** For highly liquid ETFs, simultaneous retail execution is safe. Market makers actively compete for this flow.

---

## 2. Signal Expiration Logic

### Calendar Spreads (Short leg 3-7 DTE)
**Recommendation: Expire 1-2 days before front leg expiration.**

- **Theta Decay:** Peaks 1-2 days before expiry (optimal entry window closes).
- **Gamma Risk:** Increases exponentially on expiration day.
- **Protocol:** Signal becomes invalid if `DTE < 1`.

### Price Movement Sensitivity
**Standard: 1.5-2% move invalidates ATM signals.**

| Movement | Status |
|----------|--------|
| 0% - 1.0% | ✅ Valid |
| 1.0% - 1.5% | ⚠️ Caution |
| > 1.5% | ❌ Stale/Expired |

**Reason:** Calendar spreads rely on ATM strikes. If price moves significantly, the delta profile changes, and the trade thesis (neutrality) is broken.

### IV Changes
**Calendar Spreads:** Rising IV is generally beneficial (vega positive).
- **Do NOT expire** on IV spike.
- **Expire** if IV drops significantly (>20%).

### Proposed Expiration Rules (Implemented)
We have implemented a multi-factor check:
1. **Time Limit:** 24 hours from creation (catch-all for staleness).
2. **DTE Limit:** 1 day before short leg expiration.
3. **Status:** Users can only execute `pending` signals.

---

## Implemented Architecture
We have already implemented this "Industry Best Practice" model:
- **Database:** `UserSignalExecution` tracks independent status.
- **Expiration:** Calculated at creation time based on DTE/Time.
- **API:** Filters expired signals automatically.
