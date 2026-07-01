# Strategy Fix Plan — Root Cause Analysis & Code Changes

> **Account:** x5WI28023 | **Loss Period:** Jan–May 2026 | **Estimated Loss:** ~$20K–25K

---

## Root Cause #1: CCS Exit Pairs Only ONE Long Leg Per Expiry

### The Bug

[daily_order_generator.py:609-615](file:///D:/Projects/tastywork-trading-1/iv-switching-composite/daily_order_generator.py#L609-L615)

```python
elif symbol == 'QQQ' and opt_type in ('C', 'CALL'):
    if expiry_str not in ccs_pairs:
        ccs_pairs[expiry_str] = {}
    if qty < 0:
        ccs_pairs[expiry_str]['short'] = {'pos': pos, 'occ': occ, 'strike': strike}
    else:
        ccs_pairs[expiry_str]['long'] = {'pos': pos, 'occ': occ, 'strike': strike}
```

**Problem:** The `ccs_pairs` dict stores only **one** `'short'` and **one** `'long'` entry per expiry. But the transaction history shows the strategy opens **multiple CCS at the same expiry with different strikes**:

```
04/02: Short 616C/Long 635C (2 contracts)
04/02: Short 618C/Long 636C (2 contracts)  
04/06: Short 618C/Long 637C (2 contracts)
```

All expire 05/15, so they share `expiry_str = '260515'`. The second and third spreads **overwrite** the first in `ccs_pairs['260515']`. When exit logic runs, it only sees the **last** pair, leaving orphaned legs that go to assignment unmanaged.

### The Fix

Change `ccs_pairs` from `{ expiry: { short: pos, long: pos } }` to separate short/long lists, then pair by strike proximity:

```diff
- ccs_pairs = {} # QQQ C spreads: { expiry: { 'short': pos, 'long': pos } }
+ ccs_shorts = {}  # { expiry: [ { pos, occ, strike, qty }, ... ] }
+ ccs_longs  = {}  # { expiry: [ { pos, occ, strike, qty }, ... ] }
```

Then in the exit evaluation (lines 654-681), pair them by strike:

```python
for exp_str in set(ccs_shorts.keys()) | set(ccs_longs.keys()):
    shorts = sorted(ccs_shorts.get(exp_str, []), key=lambda x: x['strike'])
    longs  = sorted(ccs_longs.get(exp_str, []),  key=lambda x: x['strike'])
    
    for sl in shorts:
        # Find the nearest long leg above this short strike
        paired_long = None
        for ll in longs:
            if ll['strike'] > sl['strike']:
                paired_long = ll
                break
        if not paired_long:
            continue
        longs.remove(paired_long)  # consume this long leg
        
        # ... existing profit/loss/expiry evaluation ...
        close_legs.append({"action": "BUY_TO_CLOSE", ...})
        close_legs.append({"action": "SELL_TO_CLOSE", ...})
```

---

## Root Cause #2: No Expiration-Week Forced Close

### The Bug

[daily_order_generator.py:678](file:///D:/Projects/tastywork-trading-1/iv-switching-composite/daily_order_generator.py#L678)

```python
if profit_pct >= 0.50 or liability >= entry_premium * 3.0 or today >= exp_date:
```

This only closes **on or after** expiration day. By then, the OCC has already auto-exercised/assigned at 4 PM. The `check_exits()` function runs at 4:15 PM ET (after the daily order generator), which is **after** the OCC settlement cutoff.

### The Fix

Close all CCS positions **3 business days before expiration**:

```diff
- if profit_pct >= 0.50 or liability >= entry_premium * 3.0 or today >= exp_date:
+ dte = (exp_date - today).days
+ force_close_expiry = dte <= 3  # Close by Tuesday/Wednesday of opex week
+ if profit_pct >= 0.50 or liability >= entry_premium * 3.0 or force_close_expiry:
```

Apply the same fix to the ZEBRA exit at [line 712](file:///D:/Projects/tastywork-trading-1/iv-switching-composite/daily_order_generator.py#L710-L712):

```diff
- if profit_pct >= 0.50 or time_stop or val <= 0.01:
+ force_close_expiry = dte <= 3
+ if profit_pct >= 0.50 or time_stop or val <= 0.01 or force_close_expiry:
```

---

## Root Cause #3: TurboCore Rebalancer Creates Short Equity Positions

### The Bug

[auto_approve.py:948-958](file:///D:/Projects/tastywork-trading-1/auto_approve.py#L948-L958)

The sell cap prevents selling **more than currently held**, but `current_value` comes from `pos_map.get(sym, 0.0)`. After assignment settles shares into the account, the rebalancer may sell ALL of them. The code doesn't distinguish between long and short positions, and doesn't prevent creating new short equity positions.

### The Fix

```diff
  if action == 'Sell':
-     max_sell_value = int(current_value * 100) / 100.0
-     if order_dollar_value > max_sell_value:
-         order_dollar_value = max_sell_value
+     # CRITICAL: Never create short equity positions
+     if current_shares <= 0:
+         logger.warning(f"⚠️ {sym}: Skipping SELL — no long shares held")
+         continue
+     max_sell_value = current_shares * current_price
+     if order_dollar_value > max_sell_value:
+         logger.info(f"⚠️ {sym}: Capping SELL to current holdings (${max_sell_value:,.2f})")
+         order_dollar_value = max_sell_value
```

---

## Root Cause #4: CCS Quantity Mismatch Between Short and Long Legs

### The Bug

[daily_order_generator.py:661,680-681](file:///D:/Projects/tastywork-trading-1/iv-switching-composite/daily_order_generator.py#L661)

The exit uses `short_qty` for **both** the BUY_TO_CLOSE and SELL_TO_CLOSE legs. If a prior partial close changed one leg's quantity, the quantities become mismatched.

### The Fix

```diff
  short_qty = abs(int(getattr(sl['pos'], 'quantity', 0) or 0))
+ long_qty  = abs(int(getattr(ll['pos'], 'quantity', 0) or 0))
+ close_qty = min(short_qty, long_qty)
+ if short_qty != long_qty:
+     log.warning(f"CCS mismatch: short={short_qty} long={long_qty}")
  ...
- close_legs.append({..., "qty": short_qty, ...})
- close_legs.append({..., "qty": short_qty, ...})
+ close_legs.append({..., "qty": close_qty, ...})
+ close_legs.append({..., "qty": close_qty, ...})
```

---

## Root Cause #5: No Rebalance Throttle → Hundreds of Micro-Trades

### The Bug

[auto_approve.py:962](file:///D:/Projects/tastywork-trading-1/auto_approve.py#L962)

```python
if order_dollar_value >= 5.0: # TT min notional is $5
```

The $5 minimum is far too low. With QQQ at $700+, even a 0.01% drift generates a $70 order. This creates dozens of fills per day at $0.10 SEC fee each (~$40+ in fees, plus bid-ask spread).

### The Fix

```diff
- if order_dollar_value >= 5.0:
+ MIN_REBALANCE_NOTIONAL = 500.0
+ MIN_REBALANCE_PCT = 0.02  # 2% drift minimum
+ drift_pct = abs(diff_value) / max(target_value, 1) if target_value > 0 else 1.0
+ if order_dollar_value >= MIN_REBALANCE_NOTIONAL and drift_pct >= MIN_REBALANCE_PCT:
```

---

## Implementation Priority

| Priority | Fix | File | Risk if Unfixed |
|----------|-----|------|-----------------|
| 🔴 P0 | Flatten any short QQQ/QLD equity | **Manual in TT** | Uncapped loss at ATH |
| 🔴 P0 | Close 06/18 call spreads | **Manual in TT** | Assignment in 20 days |
| 🔴 P1 | Fix #3: Block short equity | auto_approve.py | Creates short positions |
| 🔴 P1 | Fix #1: Multi-leg CCS pairing | daily_order_generator.py | Orphaned legs |
| 🟡 P2 | Fix #2: Expiry-week close | daily_order_generator.py | Assignment risk |
| 🟡 P2 | Fix #4: Qty reconciliation | daily_order_generator.py | Mismatched closes |
| 🟢 P3 | Fix #5: Rebalance throttle | auto_approve.py | Fee bleed |

> [!IMPORTANT]
> **Before deploying any code fixes**, complete the P0 manual actions:
> 1. Check current QQQ/QLD net position in TastyTrade
> 2. Close any short equity positions immediately
> 3. Close both 06/18 QQQ call spreads

---

## NUGT Loss — Strategy Note

The $10.5K NUGT loss is **not a code bug** — it was a directional bet that went wrong when gold rallied. The roll from Jun 300P → Jan '27 270P extended duration without reducing delta.

**Recommendation:** Limit single-name options to ≤2% NAV. The IV-Switching strategy should stick to QQQ/QQQM/TQQQ/SQQQ.
