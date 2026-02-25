# Put Ratio Spread (1×2) vs. VIX-Adaptive Vertical Leg-Out: Strategy Comparison & Leverage Opportunities

## Video Strategy Overview

The video (钱路 channel, Oct 2024) presents a **Put Ratio Spread (1×2)** on SPY as an improvement over a simple sell put. The construction involves three legs: buy 1 higher-strike put (e.g., SPY 565) and sell 2 lower-strike puts (e.g., SPY 560 × 2), all same expiration (~30 DTE), for a net credit of approximately $526.[^1][^2][^3][^4]

The strategy decomposes into two recognizable components:[^2][^1]

- **Component A**: A standard naked/cash-secured sell put at the lower strike
- **Component B**: A bear put spread (buy higher strike, sell lower strike)

When combined, these produce a P/L curve with a distinctive "spike" (peak profit zone) between the two strike prices, a wider breakeven than a simple sell put, and higher probability of profit (83% vs. 79% in the video's example).[^3][^1]

## Head-to-Head Comparison

| Dimension | Our VIX-Adaptive Vertical (Leg-Out) | Put Ratio Spread (1×2) from Video |
|---|---|---|
| **Structure** | Buy 1 OTM put + Sell 1 put (1:1) | Buy 1 put + Sell 2 puts (1:2)[^1][^2] |
| **Risk profile** | **Defined risk** (max loss = width − credit) | **Undefined risk** below lower breakeven[^1][^2] |
| **Net credit** | Moderate | Slightly lower (extra long put costs money), but still net credit[^3] |
| **Breakeven** | Narrower | Wider (more downside cushion before loss)[^3][^4] |
| **Win probability** | ~79–80% (video's example) | ~83% (video's example) |
| **Peak profit** | Flat (max = credit received) | "Spike" between strikes (can exceed credit)[^1][^3] |
| **Theta (time decay)** | Positive (2 options) | More positive (3 options, net short 2)[^1] |
| **Vega (vol sensitivity)** | Short vega | More short vega (sells 2, buys 1)[^1][^3] |
| **Leg-out behavior** | Close short put → retain long put (long vol bet) | Close bear spread → retain naked short put (stock acquisition/income bet)[^2] |
| **Retained leg risk** | Long put: max loss = current value (defined) | Naked short put: **unlimited downside**[^1][^2] |
| **Margin requirement** | Spread margin only | Cash-secured or naked margin (much higher)[^2] |
| **Options approval needed** | Level 2 (most brokers) | Level 3+ for naked puts[^2] |
| **Small account suitability** | ✅ Excellent | ⚠️ Problematic (margin + approval barrier) |

## Key Insight: The Leg-Out Mechanics Are Mirror Images

The most striking overlap between the two strategies is the **leg management concept**. The video explicitly shows closing the bear spread component profitably when the underlying drops, leaving a single naked short put to be managed separately (roll, close, or accept assignment). This is structurally the mirror image of the VIX-adaptive leg-out strategy:[^1][^2]

- **Our strategy**: Enter vertical → close short put when cheap → retain long put for vol spike
- **Video strategy**: Enter ratio spread → close bear spread when profitable → retain naked short put for income/assignment

Both strategies recognize that a multi-leg position can be decomposed mid-trade and each component managed independently based on market conditions. The difference is *which leg is retained* and *what risk that creates*.

## What Can Be Leveraged from the Ratio Spread

### Leverage Point 1: Adaptive Strategy Selection (Vertical vs. Ratio by Regime)

The ratio spread's wider breakeven and higher POP make it objectively better in certain conditions. The ML regime detector can dynamically choose between structures:[^4][^3]

- **HIGH_VOL regime + user has margin approval**: Use put ratio spread (wider cushion is more valuable when vol is extreme; extra short vega benefits more from IV crush)
- **NORMAL/LOW_VOL regime OR small account**: Use standard vertical spread (defined risk, lower margin, simpler management)
- **CRISIS regime**: Use neither; wait or switch to long-only protective strategies

This turns the platform from a single-strategy engine into a **regime-adaptive structure selector** without adding a fundamentally different strategy—it's the same underlying thesis (sell puts when VIX is high) with an upgraded payoff structure for qualified accounts.

### Leverage Point 2: Wider Breakeven Concept for Strike Optimization

The ratio spread achieves a wider breakeven by embedding a bear spread that offsets losses as the underlying declines toward the short strike. Even within the standard vertical spread, the ML contract ranker can borrow this principle:[^2][^1]

- When IV skew is steep (OTM puts are relatively expensive), the system can **widen the spread** or **shift the short strike further OTM** to achieve a breakeven improvement, even if it reduces initial credit
- The Bayesian optimizer should include breakeven width as an objective alongside Sharpe ratio, not just raw P/L

### Leverage Point 3: "Spike Zone" Targeting with ML

The ratio spread's peak profit zone (between the two strike prices) is narrow but lucrative. ML can improve the probability of landing in this zone:[^3][^1]

- Use the VIX ensemble predictor to estimate the expected range of the underlying over the DTE period
- Select strikes such that the spike zone aligns with the 1-sigma expected move
- Track "spike hit rate" as a new performance metric alongside win rate and leg-out success rate

### Leverage Point 4: Tiered Product Offering

The ratio spread creates a natural product tier differentiation that aligns with the TradeMind.bot business model:

| Tier | Strategy Available | Account Requirement | Target User |
|---|---|---|---|
| Starter ($19–29/mo) | Vertical spread only (defined risk) | Level 2 options, $500+ | Gen Z beginners |
| Pro ($49/mo) | Vertical + leg-out management | Level 2, $2K+ | Intermediate |
| Elite ($99/mo) | Vertical + ratio spread + auto-select | Level 3+, $10K+, margin | Advanced/larger accounts |

This lets the platform serve a wider audience while keeping the flagship (vertical) accessible to the core Gen Z target market. The ratio spread becomes the "unlock" for users who grow their accounts and options approval over time.

### Leverage Point 5: Educational Content Funnel

The video's decomposition approach (ratio spread = sell put + bear spread) is excellent educational content. This can be repurposed for TradeMind.bot's content strategy:

- **TikTok/Shorts series**: "Building blocks of options: from sell put → vertical → ratio" (3-part series)
- **Discord workshop**: Interactive session showing how all three structures relate and when each is optimal
- **In-app progression**: Users start with verticals, graduate to ratio spreads as they level up their account and knowledge (gamification tie-in)

## Risks and Caveats of Adding the Ratio Spread

### Naked put exposure is real

The ratio spread's retained leg after closing the bear spread is a naked short put—unlimited downside risk. For a platform targeting Gen Z small accounts, this is a significant liability concern. Mitigations:[^1][^2]

- **Gate behind account verification**: Only show ratio spread signals to users who confirm Level 3+ approval and sufficient margin
- **Mandatory risk acknowledgment**: In-app confirmation before following ratio spread signals
- **Auto-sizing**: The risk manager must treat the naked put leg with much stricter position limits (e.g., max 1 ratio spread vs. max 3 verticals)

### Margin complexity

Ratio spreads require substantially more margin than defined-risk verticals. For a $5-wide TQQQ ratio spread, the naked put component alone could require $3,500–$5,000 in margin. This exceeds many Gen Z account sizes, reinforcing the decision to keep verticals as the flagship and ratio spreads as the advanced tier.[^2]

### Broker compatibility

Not all retail brokers handle 3-leg combo orders cleanly. E*TRADE and Interactive Brokers support them, but Robinhood does not support ratio spreads. The order manager would need explicit broker-compatibility checks.[^2]

## Implementation Recommendation

### Phase 1 (Launch): Vertical spread only (current plan)

No changes needed. The vertical spread with VIX-adaptive leg-out remains the optimal flagship for Gen Z small accounts. Defined risk, Level 2 approval, minimal margin.

### Phase 2 (Month 4–6): Add ratio spread as Elite tier feature

```
[NEW] src/tqqq/ratio_spread_builder.py
  - Extends SpreadBuilder with 1x2 ratio construction
  - Validates user has Level 3+ approval and sufficient margin
  - Shares same liquidity filters and ML regime detection
  - Additional risk checks: naked put margin, assignment probability

[MODIFY] src/tqqq/vix_adaptive_strategy.py
  - Add RATIO_SPREAD state alongside FULL_SPREAD
  - Strategy selector: if regime == HIGH_VOL and user.tier == ELITE
    and user.margin_available >= threshold → use ratio spread
  - Leg-out for ratio: close bear spread, manage naked put

[MODIFY] signal_publisher/tqqq.py
  - Add TQQQRatioSpreadEntrySignal
  - Add TQQQRatioLegCloseSignal (close bear spread component)
  - Add TQQQNakedPutManagementSignal (roll/close/accept)
```

### Phase 3 (Month 8+): ML-driven structure selection

The regime detector and Bayesian optimizer decide per-signal whether to recommend vertical or ratio based on current VIX regime, IV skew steepness, user account size, and margin availability. This becomes a true differentiator: no competitor offers AI-driven adaptive structure selection between defined-risk and ratio payoffs.

## Conclusion: What to Take from the Video

The put ratio spread is not a replacement for the vertical spread leg-out strategy—it is a **complementary advanced variant** that serves larger, more sophisticated accounts. The most valuable takeaway is the *concept* of decomposing multi-leg positions and managing components independently based on market conditions, which validates the core thesis of the VIX-adaptive leg-out approach. The ratio spread's wider breakeven and higher POP can be leveraged as an Elite-tier feature, an ML strike-optimization principle, and an educational content funnel that guides users from simple verticals to more complex structures over time.

---

## References

1. [1x2 Ratio Vertical Spread with Puts - Fidelity Investments](https://www.fidelity.com/learning-center/investment-products/options/options-strategy-guide/1x2-ratio-vertical-spread-puts) - Explanation. A 1x2 ratio vertical spread with puts is created by buying one higher-strike put and se...

2. [Intro to Put Ratio Options Spreads | Charles Schwab](https://www.schwab.com/learn/story/intro-to-put-ratio-options-spreads) - A standard put ratio spread consists of the purchase of a (long) put option and the sale of twice as...

3. [Ratio Spread: What are Front Ratio Puts and Calls? | tastylive](https://www.tastylive.com/concepts-strategies/ratio-spread) - The main difference between the two is that with a ratio spread the number of options that you sell ...

4. [Next Level: Turning Vertical Spreads Into Ratios](https://luckboxmagazine.com/techniques/next-level-turning-vertical-spreads-into-ratios/) - Any spread that involves at least two different legs, and a non-symmetrical number of contracts trad...

