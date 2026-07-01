# TastyTrade Strategy Review — Critical Issues & Fix Plan

> **Account:** x5WI28023 | **Period:** Jan 1 – May 29, 2026 | **Deposits:** $110,003 | **Current Net Change:** ~$159,526

---

## Executive Summary

Despite QQQ being near all-time highs (~$711 on 5/20), the account is **underperforming** relative to a simple buy-and-hold of the initial deposits. The core strategy appears to be an automated **IV Switch / Volatility Rotation** system that swaps between QQQ, QLD (2x), TQQQ (3x), and SGOV (T-Bills), combined with **QQQ LEAPS call spreads** and **individual equity/commodity put spreads**. 

> [!CAUTION]
> The **20% underperformance** is NOT from a single catastrophic trade. It's from **five compounding structural problems** in the strategy execution.

---

## Problem #1: QQQ 05/15 Call Spread — Assignment Disaster (Pin Risk)

### What Happened

You sold **bull call spreads** on QQQ expiring 05/15/26:

| Date | Action | Strike | Qty | Premium |
|------|--------|--------|-----|---------|
| 04/02 | Sell 616C / Buy 635C | 616/635 | 2 | +$769 net credit |
| 04/02 | Sell 618C / Buy 636C | 618/636 | 2 | +$671 net credit |
| 04/06 | Sell 618C / Buy 637C | 618/637 | 2 | +$751 net credit |
| 04/07 | **BUY TO CLOSE** 616C | 616 | 2 | **-$1,256** |

**Net option premium collected:** ~$935

### The Assignment on 05/15

On expiration day (QQQ closed ~$618-$637 range), ALL options were exercised/assigned:

```
Short 4x 618 Calls → ASSIGNED → Sold 400 QQQ @ $618 = +$247,190
Long 2x 635 Calls → EXERCISED → Bought 200 QQQ @ $635 = -$127,005
Long 2x 636 Calls → EXERCISED → Bought 200 QQQ @ $636 = -$127,205
Long 2x 637 Calls → EXERCISED → Bought 200 QQQ @ $637 = -$127,405
```

**Net stock settlement:** +$247,190 − $127,005 − $127,205 − $127,405 = **-$134,425**

> [!WARNING]
> **The Problem:** You were short 4 contracts at the 618 strike (400 shares sold at $618) but only long 2+2+2=6 contracts at different higher strikes (600 shares bought at $635-637). This is a **quantity mismatch**: 400 shares sold short vs. 600 shares bought long, resulting in a **net long 200 QQQ position** after settlement that was NOT intended. On 5/20 you started selling QQQ, meaning you may now be **short QQQ equity** heading into ATH.

### The Real Issue
The 616C position (2 contracts) was **closed on 04/07 at a $1,256 loss** — but the corresponding long legs (635C) were **NOT closed**. This left:
- 2 orphaned long 635C calls that exercised into 200 shares bought at $635
- Combined with the 618C assignment (sold 400 shares at $618)

The strategy assumed max loss = spread width × contracts. But the **early close of only one leg** broke the hedged structure.

---

## Problem #2: IV Switch Rotation — Excessive Friction

### The Pattern

The bot appears to rotate the portfolio between different leverage levels based on implied volatility:

| IV Regime | Target Allocation |
|-----------|------------------|
| **Low IV** (bullish) | QQQ + QLD (short SGOV for cash) |
| **Rising IV** | Shift to TQQQ (leveraged for rebound) |
| **High IV** (defensive) | Rotate into SGOV (T-Bills / cash) |

### The Problem: Friction Cost is Enormous

Looking at daily flows, the bot is executing **massive same-day roundtrips**:

```
2026-04-22: QQQ: $-28,784  |  QLD: $-624   |  TQQQ: $3,959  |  SGOV: $-2,717
2026-04-16: QQQ: $24,000   |  QLD: $8,697  |  TQQQ: $1,015  |  SGOV: $-1,106
2026-04-13: QQQ: $15,230   |  QLD: $3,036  |  TQQQ: $-904   |  SGOV: $1,506
```

**On 04/22 alone**, the bot bought/sold $7,196 × 5 fills of QQQ (totaling ~$35K in buys), then immediately sold $5,887 × 4 fills of QQQ, plus bought ~180 TQQQ shares and sold ~92 TQQQ shares — all within minutes. The **bid-ask spread loss** on fractional-share fills at $0.10 per fill is adding up.

> [!IMPORTANT]
> **$0.10 per fill × ~400 equity fills in the period = ~$40 just in SEC fees, plus the hidden bid-ask spread cost.** The IV signal needs to have less frequent, larger conviction rotations rather than minute-by-minute micro-rebalancing.

### Specific Equity Trading Totals

| Symbol | Net Cash Flow | Interpretation |
|--------|--------------|----------------|
| QQQ | +$161,827 | Net seller (shorting into highs or taking profit) |
| QLD | +$24,674 | Net seller |
| TQQQ | +$3,331 | Roughly flat |
| SGOV | -$2,212 | Net buyer (parking cash) |
| **Combined** | **+$187,620** | |

This looks fine on the surface, but the **current open positions** are what matter — you may be **net short QQQ** after the 05/15 assignment and the 05/20 sales, which is extremely dangerous at ATH.

---

## Problem #3: NUGT Put Spread Roll — $10,500 Loss

The gold miner (NUGT) trades were a significant bleed:

```
03/02: Sell 300P / Buy 190P (Jun 18) → +$2,773 net credit
03/03: Sell 245P (Jun 18)           → +$4,809
03/13: Roll 300P→270P (Jan 27)      → -$70 net
03/23: Close ALL three legs          → -$18,000 total closeout
```

**Net NUGT Loss: -$10,489**

> [!NOTE]
> NUGT surged with gold prices. The short put spread was directionally wrong. The roll from the 300P (Jun) to the 270P (Jan '27) was an attempt to "buy time" but actually **deepened the loss** by extending duration without changing delta enough. The $13,542 cost to buy back the Jan '27 270P vs. the $10,800 received was a -$2,741 loss on the roll alone.

---

## Problem #4: QQQ 06/18 Call Spreads — Still Open, Pin Risk Ahead

You have two open bull call spreads:

| Opened | Short Strike | Long Strike | Width | Net Credit |
|--------|-------------|-------------|-------|------------|
| 04/08 | 645C | 665C | $20 | +$420 |
| 04/09 | 640C | 660C | $20 | +$505 |

With QQQ at ~$711 as of 05/20, **both spreads are DEEP in the money**. They will be assigned at max loss:
- Max loss per spread = ($20 width − credit) × 100 = ~**$1,580 + $1,495 = $3,075 combined**

> [!WARNING]
> These WILL result in another assignment event like 05/15. You need to **close both before 06/18** to avoid another round of involuntary stock delivery and the same orphaned-leg problem.

---

## Problem #5: Current Net Position — Potentially Short QQQ at ATH

After the 05/15 assignment settled (+400 sold, -600 bought = net +200 long), you then **sold aggressively on 05/14 and 05/20**:

```
05/14: Sold 12 QQQ + 14 QLD
05/20: Sold 24 QQQ + 28 QLD  
```

If you didn't have a long stock position before these sales, the `SELL_TO_OPEN` tags confirm you are now **short QQQ and short QLD** heading into all-time highs. This is the single biggest current risk.

---

## Fix Plan

### Step 1: Immediately Audit Net Position (TODAY)
Check your TastyTrade positions tab. Verify:
- [ ] Current QQQ share count (likely short ~24+ shares)
- [ ] Current QLD share count (likely short ~42+ shares)
- [ ] Current SGOV holding
- [ ] Open QQQ 06/18 call spread status

### Step 2: Close the 06/18 Call Spreads (THIS WEEK)
```
BUY TO CLOSE: QQQ 06/18 645C × 1
SELL TO CLOSE: QQQ 06/18 665C × 1
BUY TO CLOSE: QQQ 06/18 640C × 1
SELL TO CLOSE: QQQ 06/18 660C × 1
```
Accept the ~$3,000 max loss now rather than risk another assignment/exercise mismatch. At current QQQ ~$711, these are $66-71 ITM and will settle near max loss anyway. Closing early avoids overnight assignment risk and the cash drag of holding 200 shares of QQQ through settlement.

### Step 3: Flatten the Short QQQ/QLD Equity (THIS WEEK)
If you are net short QQQ/QLD:
```
BUY TO CLOSE: all short QQQ shares at market
BUY TO CLOSE: all short QLD shares at market
```
Every day you hold a short equity position at ATH is an uncapped loss risk. The IV Switch bot should only go to SGOV for defense, **never naked short QQQ equity**.

### Step 4: Fix the IV Switch Bot Logic

The bot needs these rule changes:

| Current Behavior | Fix |
|---|---|
| Rebalances every few minutes with fractional fills | **Minimum rebalance interval: 4 hours.** Only act on sustained IV regime changes, not tick-by-tick noise |
| Uses `SELL_TO_OPEN` for QQQ/QLD (creates short positions) | **NEVER use SELL_TO_OPEN for QQQ/QLD/TQQQ.** Only `SELL_TO_CLOSE` existing long positions. The bot should only be LONG equities or CASH (SGOV) |
| Fills in $587-$654 fractional lots with $0.10 fee each | **Batch fills into whole shares.** A single 50-share order has the same $0.10 fee as a 0.99 share order |
| No position limits | **Max position: 80% of NAV in equities, 20% SGOV floor** |

### Step 5: Fix the LEAPS Call Spread Management

| Current Behavior | Fix |
|---|---|
| Closes individual legs independently | **ALWAYS close spreads as a single order (leg-into).** Never close one leg and leave the other orphaned |
| No early management | **Close at 50% max profit or 21 DTE,** whichever comes first |
| No assignment protection | **Close ALL spreads 3 trading days before expiration.** Do not hold through expiration |
| Quantity mismatch between short/long legs | **Enforce strict 1:1 ratio.** If short 4 contracts at 618, must have exactly 4 long contracts at ONE strike above |
| Multiple long strikes for same short strike | **Use a SINGLE long strike per spread.** Don't split the 618 short across 635/636/637 longs — this makes management impossible |

---

## Summary of Estimated Losses by Category

| Category | Estimated Loss |
|----------|---------------|
| QQQ 05/15 Call Spread (assignment + orphaned legs) | ~$3,000–5,000 |
| QQQ 06/18 Call Spread (max loss pending) | ~$3,075 |
| NUGT Put Spread roll | ~$10,489 |
| IV Switch friction (spread costs + fees on ~400 fills) | ~$2,000–4,000 |
| Short QQQ/QLD equity at ATH (unrealized) | **Unknown — check positions** |
| ASML, SLV, SNDK losses | ~$1,309 |
| **Total Identified Losses** | **~$20,000–24,000** |

> [!IMPORTANT]  
> The "20% loss" perception likely comes from comparing **current portfolio value** (with open short positions) against the all-time high the account reached. The net cash P&L from trades is actually +$49,310, but unrealized losses from current short positions and the pending 06/18 spread are dragging the mark-to-market value down significantly.

---

## Priority Actions (Ordered)

1. 🔴 **Check and flatten any short QQQ/QLD equity TODAY**
2. 🔴 **Close 06/18 call spreads THIS WEEK** 
3. 🟡 **Disable the SELL_TO_OPEN capability in the IV Switch bot**
4. 🟡 **Add 4-hour minimum rebalance interval**
5. 🟢 **Implement spread close-as-unit rule for all future LEAPS**
6. 🟢 **Never hold options through expiration week**
