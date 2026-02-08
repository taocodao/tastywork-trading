# Theta Sprint Strategy - Complete Logic Explained

## Strategy Overview

**Core Concept**: Sell cash-secured puts on high-quality ETFs to collect premium from time decay (theta), while managing risk through early profit-taking and defensive exits.

---

## Part 1: Entry Logic - "Is This Trade Worth It?"

### Step 1: Risk Assessment

**What's at stake?**

```python
Capital_Required = Strike_Price × 100 × Contracts
# Example: $150 strike = $15,000 capital required per contract
```

This is **NOT** your max loss (you can own the ETF if assigned), but it's your **capital tied up**.

### Step 2: Premium Collection

**What do we get paid?**

```python
Premium_Received = Bid_Price × 100 × Contracts  
# Example: $0.75 bid = $75 premium per contract
```

### Step 3: Return on Capital (ROC)

**Is the juice worth the squeeze?**

```python
ROC = Premium_Received / Capital_Required
# Example: $75 / $15,000 = 0.5% over 30 days = 6% annualized
```

**Decision rule**: Only trade if ROC meets minimum threshold (typically 0.5%+)

---

## Part 2: Scoring System - "How Good Is This Trade?"

The strategy doesn't just compare premium to risk—it **scores** each option on multiple factors:

### Scoring Factors (from `options_analyzer.py`)

| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| **Symbol Quality** | 30% | How desirable the underlying is (IV rank, liquidity) |
| **Delta Score** | 25% | Probability of staying OTM (lower delta = safer) |
| **Premium Score** | 20% | Premium relative to capital (higher = better) |
| **Theta Score** | 15% | Daily time decay (higher = faster profit) |
| **Liquidity Score** | 10% | Bid-ask spread & open interest |

### Example Score Calculation

**SPY 600P, 30 DTE, 0.30 delta, $0.80 bid**

```python
Symbol_Score = 85 (SPY is high quality)
Delta_Score = 70 (0.30 delta is good - 70% prob OTM)
Premium_Score = 80 ($0.80 / $600 = 0.13% per contract)
Theta_Score = 75 (Decent daily decay)
Liquidity_Score = 95 (SPY is super liquid)

Total_Score = (85×0.30) + (70×0.25) + (80×0.20) + (75×0.15) + (95×0.10)
            = 25.5 + 17.5 + 16 + 11.25 + 9.5
            = **79.75** (Good trade!)
```

**Decision**: Only generate signal if **Total_Score ≥ 60** (configurable)

---

## Part 3: Position Sizing - "How Many Contracts?"

### Capital Allocation Rules

```python
# From config
Max_Portfolio_Heat = $50,000  # Max capital at risk
Max_Positions = 6             # Diversification limit
Contracts_Per_Trade = 1       # Starting size

# Check available capital
Available_Capital = Total_Capital - Currently_Reserved
if Capital_Required > Available_Capital:
    REJECT  # Not enough capital
    
# Check portfolio heat
if Current_Heat + Capital_Required > Max_Portfolio_Heat:
    REJECT  # Would exceed risk limit
```

### VIX-Based Position Sizing

**Higher VIX = Reduce size** (from `signal_generator.py` lines 310-315)

```python
if VIX < 15:
    Size_Multiplier = 1.0   # Full size
elif VIX 15-20:
    Size_Multiplier = 1.0   # Normal
elif VIX 20-25:
    Size_Multiplier = 0.75  # Reduce 25%
elif VIX 25-30:
    Size_Multiplier = 0.50  # Cut in half
else:  # VIX > 30
    BLOCK_ALL_ENTRIES       # Too dangerous
```

---

## Part 4: Entry Execution - "How Do We Enter?"

### Order Type

```python
Action: SELL TO OPEN
Order_Type: LIMIT
Limit_Price: Bid_Price  # Sell at current bid (conservative)
# Or: Mid_Price for better fill
```

**No market orders** - Always use limit orders to avoid slippage.

### Example Entry

```
Symbol: SPY
Strike: 600
Expiration: 2026-03-07 (30 DTE)
Action: SELL 1 SPY Mar7 600 PUT @ $0.80
Premium Received: $80
Capital Required: $60,000
```

---

## Part 5: Exit Logic - "When Do We Close?"

### **NOT a trailing stop** - It's **time-based profit targets**!

This is the key differentiator of the Theta Sprint strategy.

### Time-Based Profit Targets

From `signal_generator.py` lines 539-586:

```python
# Week 1 (Days 1-7): Take 50% profit
if days_in_trade <= 7:
    if profit_pct >= 50%:
        EXIT  # "Quick win - lock it in!"

# Week 2 (Days 8-14): Take 60% profit  
elif days_in_trade <= 14:
    if profit_pct >= 60%:
        EXIT

# Week 3 (Days 15-21): Take 75% profit
elif days_in_trade <= 21:
    if profit_pct >= 75%:
        EXIT

# Week 4 (Days 22+): Take 90% profit
else:
    if profit_pct >= 90%:
        EXIT
```

### Why Time-Based Exits?

**Theta decay is non-linear**:
- **First week**: Option loses 30-40% of value (fast decay)
- **Second week**: Another 20-30%
- **Third week**: Another 15-20%
- **Last week**: Final 10-15% (risky to hold)

**Strategy**: Capture the "easy money" (first 50-75% decay) and exit early to avoid assignment risk.

### Example Exit Scenario

**Entry:**
- Sold SPY 600P @ $0.80 (received $80)
- Capital required: $60,000

**Day 5 (Week 1):**
- Current price: $0.40 (option lost 50% of value)
- Profit: $0.80 - $0.40 = $0.40 = **50% profit**
- **Action**: BUY TO CLOSE @ $0.40

**Result:**
- Profit: $40 (50% of premium)
- Days in trade: 5
- Annualized return: ($40/$60,000) × (365/5) = **4.9% annualized**
- Capital released: $60,000 now available for next trade

---

## Part 6: Defensive Exits - "Emergency Escape"

### Breach Detection (NOT trailing stop)

From `signal_generator.py` lines 502-530:

```python
Breach_Threshold = Strike × (1 - Defensive_Breach_Pct / 100)
# Example: $600 strike × (1 - 0.02) = $588

if Underlying_Price < Breach_Threshold:
    # Underlying dropped below strike by 2%
    Breach_Day_Counter += 1
    
    if Breach_Day_Counter >= 3:  # 3 consecutive days
        EXIT_IMMEDIATELY  # "Get out before assignment!"
```

**This is NOT a trailing stop** - it's a **defensive breach alert**.

### Why 3-Day Confirmation?

Avoid whipsaws. Stock might dip below strike for 1 day then recover. Wait for **confirmation** before exiting.

### Defensive Exit Example

**Position:**
- Sold SPY 600P @ $0.80
- Strike: $600

**Day 10:**
- SPY drops to $586 (below $588 breach threshold)
- Breach Day 1 - Monitor

**Day 11:**
- SPY still at $585
- Breach Day 2 - Monitor

**Day 12:**
- SPY at $584
- Breach Day 3 - **EXIT TRIGGERED**
- Buy back put (probably at a loss)

**Result:**
- Lost money on this trade, but avoided **assignment** (having to buy SPY at $600 when it's $584)
- Capital preserved for better opportunities

---

## Part 7: Expiration Protection

### Close Before Expiration

```python
if DTE <= 3:  # 3 days to expiration
    EXIT_IMMEDIATELY  # Too risky to hold
```

**Why?**
- Gamma risk increases exponentially near expiration
- Assignment risk spikes
- Better to close early even at small profit/loss

---

## Complete Trade Lifecycle Example

### Entry (Day 0)

```
Selected: QQQ 500P (30 DTE)
Score: 78 (passed 60 threshold)
Premium: $1.00 bid
Capital: $50,000 required
IV: 22% (passed 15% minimum)
VIX: 18 (normal - full size)

→ SELL 1 QQQ 500P @ $1.00
→ Received: $100
→ Heat: $50,000 / $50,000 max
```

### Monitoring (Days 1-30)

**Daily checks:**
1. Current option price
2. Days in trade
3. Profit %
4. Underlying price vs strike

**Day 6:**
- QQQ @ $515 (well above strike)
- Option @ $0.48
- Profit: $52 = **52% profit**
- Days in trade: 6 (Week 1)

**Decision**: 52% > 50% Week 1 target → **EXIT!**

### Exit (Day 6)

```
→ BUY TO CLOSE 1 QQQ 500P @ $0.50
→ Paid: $50
→ Profit: $100 - $50 = $50
→ Return: $50 / $50,000 = 0.10% in 6 days
→ Annualized: ~6.1%
→ Capital released: $50,000 available for new trade
```

---

## Risk vs. Reward Summary

### What Gets Measured

| Risk Factor | How It's Assessed |
|-------------|-------------------|
| **Capital Required** | Strike × 100 × Contracts |
| **Probability of Assignment** | Delta (lower = better) |
| **IV Regime** | VIX level (higher = reduce size) |
| **Correlation** | Don't trade correlated symbols |
| **Earnings** | Block if earnings in next 21 days |

| Reward Factor | How It's Measured |
|---------------|-------------------|
| **Premium** | Bid price × 100 |
| **Theta Decay** | Daily time decay |
| **ROC** | Premium / Capital |
| **Annualized Return** | (Premium / Capital) × (365 / DTE) |

### The Final Decision

```python
if (
    Total_Score >= 60 AND
    Capital_Available >= Capital_Required AND
    Current_Heat + Capital_Required <= Max_Heat AND
    Symbol not in Current_Positions AND
    VIX < 30 AND
    IV >= 15% AND
    No_Earnings_Within_21_Days
):
    → CREATE TRADE
else:
    → SKIP (doesn't meet criteria)
```

---

## Key Differences from Your Description

### ❌ Not Quite Right:
- "Trailing stop" → **Time-based profit targets**
- "Risk vs premium" → **Multi-factor scoring**

### ✅ What You Got Right:
- Compare risk to reward ✅
- Early exit if not favorable ✅
- Premium collection is key ✅

---

## Summary: The Strategy in One Sentence

**"Sell puts on high-quality,high-liquidity ETFs during elevated volatility, collect premium from theta decay, and exit early when we've captured 50-90% of the profit based on time in trade, while defending against assignment through breach monitoring."**

---

## Philosophical Approach

**Conservative Theta Harvesting:**
- Quality > Quantity (only trade high scores)
- Small, consistent wins > Big risky bets
- Exit early = Compound faster
- Defend capital = Survive black swans

**Why It Works:**
- Theta decay is predictable
- High-quality ETFs rarely crash
- Time-based exits avoid late-stage gamma risk
- Diversification across 6 positions reduces single-point failure
