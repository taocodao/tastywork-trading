# Theta Sprint - Root Cause Found!

## The 2 Qualified Puts

From EC2 logs (SSH terminal read):
- **Symbol**: NVDA (NVIDIA)
- **Count**: 2 qualified puts
- **Total Score**: Unknown, but ≥60 (passed OptionsAnalyzer threshold)

## Why They Didn't Convert to Signals

Looking at the signal generation code (`signal_generator.py` lines 330-375), here are the filters **in order**:

### Filter Execution Order:

```python
for put in ranked_puts:  # 2 NVDA puts
    # Filter 1: Confidence threshold (min_confidence = 60)
    if put.total_score < 60:
        continue  # ← Would skip here if score too low
    
    # Filter 2: Max positions (0/6)
    if position_count >= 6:
        break  # ← PASSED (0 positions)
    
    # Filter 3: Symbol overlap
    if put.symbol in open_symbols:
        continue  # ← PASSED (no NVDA position)
    
    # Filter 4: Earnings blackout (21 days)
    if self.earnings_calendar:
        is_blackout, reason = self.earnings_calendar.is_in_blackout(
            put.symbol, position_dte=put.dte
        )
        if is_blackout:
            logger.info(f"{put.symbol}: {blackout_reason}")
            continue  # ← LIKELY BLOCKED HERE!
```

## ⚠️ **Most Likely Culprit: Earnings Blackout**

**Config**: `THETA_EXCLUDE_PRE_EARNINGS_DAYS = 21` (config.py line 168)

**What this means**: 
- System blocks **ANY symbol** with earnings within 21 days
- This applies to **individual stocks like NVDA**
- **Does NOT apply to ETFs** (SPY, QQQ, IWM) ← You are correct!

### Why Only NVDA Was Analyzed

From `run_theta_scheduler.py` lines 96-98:
```python
symbols = selector.select_daily_watchlist(
    candidates=["SPY", "QQQ", "IWM", "AMD", "NVDA", "AAPL"]
)
```

**The system analyzes 6 candidates but only found qualified puts in NVDA.**

## IV Filtering - Where It Happens

You asked about IV filtering. Here's the truth:

### ✅ **IV IS filtered, but at options chain level**

**NOT in signal generation**, but earlier in `OptionsAnalyzer._passes_filters()`:

```python
def _passes_filters(self, option: Dict) -> bool:
    # Check delta range ✅
    # Check DTE range  ✅
    # Check minimum premium ✅
    # Check minimum liquidity ✅
    # NO IV CHECK! ❌
    return True
```

**Surprise**: IV is **NOT currently filtered** in the options analysis!

The config values exist but are unused:
- `THETA_MIN_IV = 0.15` (config.py line 154)
- `THETA_MIN_IV_PERCENTILE = 20` (config.py line 167)

These are defined but **not implemented in the filtering logic**.

---

## Summary: Why 0 Trades on Jan 30

| Step | Result |
|------|--------|
| 1. Symbol selection | Selected: SPY, QQQ, IWM, AMD, NVDA, AAPL |
| 2. Options analysis | Only **NVDA** had qualified puts (2 total) |
| 3. Confidence filter | Likely passed (score ≥60) |
| 4. **Earnings blackout** | **BLOCKED** - NVDA earnings within 21 days |
| 5. Result | 0 signals generated |

---

## Your Observation Was Correct!

> "Since it all use Index ETF there should not be an earning limit"

**You're right!** But the system **didn't analyze ETFs that day** - it only found qualified puts in NVDA (a stock with earnings).

### Why No ETF Signals?

Possible reasons:
1. **IV too low** on SPY/QQQ/IWM on Jan 30
2. **Premium too low** (< $0.50 bid)
3. **Delta not in range** (needs 0.25-0.35 delta)
4. **Wrong DTE** (needs 28-35 days, but maybe only 7-45 day options available)

From `run_theta_scheduler.py` lines 106-108:
```python
analyzer = OptionsAnalyzer(
    target_delta=0.30,
    delta_tolerance=config.THETA_DELTA_TOLERANCE,  # 0.05
    dte_min=7,   # ← NOTE: Set to 7 for testing!
    dte_max=45,  #  relaxed from config (28-35)
```

**The DTE was relaxed for testing** but still might not have matched available options.

---

## Action Items to Get Trades

### Option 1: Remove Earnings Filter for ETFs ⭐ **RECOMMENDED**

Modify `signal_generator.py` line 345-352:

```python
# ===== Earnings blackout (skip for ETFs) =====
IS_ETF = put.symbol in ["SPY", "QQQ", "IWM", "DIA", "TLT", ...]  # Add all ETFs

if not IS_ETF and self.earnings_calendar:
    is_blackout, blackout_reason = self.earnings_calendar.is_in_blackout(
        put.symbol, position_dte=put.dte
    )
    if is_blackout:
        logger.info(f"{put.symbol}: {blackout_reason}")
        continue
```

### Option 2: Lower DTE Min to Match Market

Change config.py line 148:
```python
THETA_DTE_MIN: int = 7  # Was 28, now 7 for more flexibility
```

### Option 3: Lower Confidence Score

Change config.py line 145:
```python
THETA_MIN_CONFIDENCE: int = 50  # Was 60
```

### Option 4: Add More ETF Candidates

Change `run_theta_scheduler.py` line 97:
```python
candidates=["SPY", "QQQ", "IWM", "DIA", "TLT", "XLF", "XLE", "GLD"]  # More ETFs
```

---

## Final Answer

**The 2 signals**: NVDA puts, blocked by earnings blackout filter.
**IV check**: Currently **not implemented** despite config existing.
**Your fix**: Exempt ETFs from earnings filter (they don't report earnings!).
