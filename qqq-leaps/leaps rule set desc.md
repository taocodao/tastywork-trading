<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# [https://www.youtube.com/results?search_query=pmcc](https://www.youtube.com/results?search_query=pmcc)  can you go through all the videos in the above link then summarize what is the insight and the method conclude from these videos. see if there are anything useful to improve the ruleset you just created, regenerate a new one

Most PMCC videos reinforce what you’re already doing (deep ITM LEAPS + ≤30‑delta short calls, 50% profit take), but they add two useful edges: (1) a **trade initialization constraint** so the whole diagonal is always closed at a profit in a runaway rally, and (2) more nuanced management around extrinsic value and 20%/10% buy‑back rules. I’ve folded these into an upgraded, backtest‑ready QQQ PMCC ruleset below.[^1][^2][^3][^4][^5][^6][^7][^8][^9][^10]

***

## New insights from PMCC content

Key patterns across the main PMCC resources:

- Long call structure and debits
    - Common guideline: long call around 0.75–0.85 delta, with 9–24 months to expiry, acting as stock surrogate.[^2][^3][^5][^6][^7][^1]
    - Several creators and BCI stress keeping the **debit paid** for the diagonal below about 80–85% of the strike width (for spread‑style setups) or making sure the **short call premium is large relative to the LEAPS extrinsic** so the trade is robust in a big rally.[^4][^5][^6]
- “Trade initialization formula” (Blue Collar Investor)
    - BCI’s PMCC formula: structure the initial trade so that if price explodes higher and you are forced to close both legs early, you **still close at a profit**; they explicitly test “if I must buy back the short and sell the LEAP at intrinsic, is P\&L ≥ 0?”[^5][^6][^9]
    - They use a calculator to enforce this and reject setups that fail it.[^9][^5]
- Short call guidelines
    - Short leg: typically 0.20–0.30 delta, 30–45 DTE, matching the Tastytrade “20–30 delta, manage ~21 DTE” playbook.[^3][^7][^8][^2][^4]
    - Upper delta cap: multiple sources stress **never going above 0.30–0.35**; above that, assignment risk blows up near expiration.[^7][^8][^2][^3][^4]
    - Lower delta limit: <0.15 delta premium is often considered not worth it.[^4][^7]
- Management: 20%/10% style and gamma risk
    - BCI uses a **20% / 10% rule** on the short call: buy back if the value drops to 20% of credit early in the cycle, and 10% later in the cycle, to bank premium and avoid gamma risk.[^5][^9]
    - Tastytrade emphasizes managing PMCCs before expiration (around 21 DTE) to dodge late‑cycle gamma and assignment risk.[^8][^4]
- Risk framing
    - Several videos explicitly call PMCC “more than covered call but cheaper” and emphasize that misunderstanding extrinsic value and assignment can flip it into a bad diagonal.[^6][^1][^2][^3][^7][^5]
    - They keep long‑call extrinsic modest (deep ITM) so the LEAP behaves like stock and exits/rolls are predictable.[^6][^7][^5]

These map nicely onto your existing QQQ LEAPS framework, especially Layer C (LEAPS structure), Layer D (PMCC), and your risk management tiers in Layer E.[^10]

***

## Improved QQQ PMCC ruleset (v2)

Below is a refined, backtest‑ready specification that merges your architecture with the best PMCC practices from YouTube/BCI/Tastytrade.

### 1. Long QQQ LEAPS (anchor leg)

Use your existing LEAPS selection logic, with one added BCI‑style constraint:

- Expiry and delta (unchanged, but explicit):
    - BULL_STRONG: 12‑month LEAPS, target 0.85 delta.[^10]
    - BULL_MODERATE: 12‑month LEAPS, target 0.80 delta.[^10]
    - CHOPPY: 18‑month LEAPS, target 0.80 delta.[^10]
- Extrinsic value and robustness checks (new):
    - **Extrinsic cap:** at entry, LEAPS extrinsic value per contract ≤ 25% of total option price (keeps it deep ITM; consistent with “time‑value component is key, keep it modest”).[^7][^5][^6]
    - **Robust exit test:** simulate a “forced close” where QQQ rallies sharply:
        - Assume QQQ price +10% from entry.
        - Short call is ITM; you buy it back at intrinsic + remaining extrinsic (model via mid + 1% slippage).
        - LEAPS is mostly intrinsic; you sell it at model midpoint − 1% slippage.
        - Require **P\&L ≥ 0** on the combined close; if not, reject the setup and adjust strike/tenor.[^9][^5][^6]

This “trade initialization formula” guarantees PMCCs are not fragile to upside breakouts.

***

### 2. Short call entry rules (PMCC activation)

PMCC remains layered on top of your LEAPS logic and regime filters.[^10]

**Regime gating:**

- Allow new short calls only if regime is **BULL_STRONG** or **BULL_MODERATE**.
- Do not open new shorts in **CHOPPY**; close all shorts in **BEAR / BEAR_SMA_FORCED**.[^10]

**Timing and conditions:**

1. LEAPS position age ≥ **5 trading days** since entry.[^10]
2. LEAPS **DTE > 60**.[^10]
3. QQQ has recovered at least **+2% off the LEAPS entry low**, so you’re not adding PMCC on maximum fear.
4. VIX between **16 and 35** (avoid super‑low IV and extreme panic spikes).[^2][^3][^5]
5. ML entry classifier confidence at original LEAPS entry still valid (the position has not violated your DrawdownGuard tiers).[^10]

**Short call spec:**

- Expiration: **30–35 DTE** (aligns with 30–45 DTE standard, but tight enough for frequent theta harvest).[^3][^8][^2][^4]
- Delta by regime:
    - BULL_STRONG: 0.28–0.30 delta.
    - BULL_MODERATE: 0.22–0.25 delta.
    - Enforce hard bounds: 0.15 ≤ delta ≤ 0.30 (TradingBlock/BCI guidance).[^4][^5][^7]
- Minimum premium: ≥ **\$0.50/contract**.
- Order type: limit at **mid − \$0.05** for realistic fills.

***

### 3. Short call management: 20%/10% + gamma rules

We replace the simple 50% take‑profit with a time‑aware 20%/10% framework plus a “manage at ≈21 DTE” gamma rule.[^8][^5][^9]

Let:

- $C_0$ = initial short call credit.
- $C_t$ = current option price.
- $T_0$ = initial DTE.
- $T_t$ = current DTE.

**Profit‑taking rules:**

- If **T_t ≥ T_0 − 10 days** (early in cycle) and $C_t ≤ 0.20 \cdot C_0$:
    - Buy back short call, book profit (≈80% of credit).
- If **T_t < T_0 − 10 days** and $C_t ≤ 0.10 \cdot C_0$:
    - Buy back short call, book profit (≈90% of credit).

**Gamma/expiration rule:**

- If **T_t ≤ 21 DTE** and short call is still open, **force management**:
    - If OTM: buy back regardless of residual premium to avoid gamma/assignment risk, then re‑sell a fresh 30–35 DTE call if conditions allow.[^8][^4]
    - If ITM/near ITM: roll (see roll section) or close with the LEAPS per drawdown rules.

This gives you faster profit capture than a simple 50% rule and aligns with BCI/Tastytrade risk practices.[^5][^9][^8]

***

### 4. Roll and loss rules

**1) Rally/assignment risk roll**

- Trigger: QQQ trades **within 3% of the short strike** OR short call delta ≥ **0.40**.
- Action: roll **up and out**:
    - New expiry: current expiry + 21–30 days.
    - New strike: at or above current stock price, target new delta 0.22–0.28.
    - Target net: **net credit or ≤ \$0.10 debit**; if that’s not feasible, close entire short call instead.[^2][^3][^7][^4][^8]

**2) Loss limit on short call**

- Trigger: short call price ≥ **2 × C_0** (200% of original credit).
- Action: buy back the short call (no roll by default).
- State: revert to **LEAPS‑only** until QQQ stabilizes and regime is BULL again, then consider a new short call.

**3) Regime deterioration**

- If regime goes from BULL_* to **CHOPPY**:
    - Roll short call **down in delta** to around 0.15 with same expiry (defensive, low income).[^7][^4]
- If regime switches to **BEAR / BEAR_SMA_FORCED**:
    - Immediately **close all short calls at market** (do not wait), then apply your LEAPS DrawdownGuard rules.[^10]

***

### 5. Integration with DrawdownGuard (Layer E)

Hook PMCC into your existing three‑tier LEAPS risk system.[^10]


| Layer E Tier | Trigger (existing) | LEAPS action | PMCC action (new) |
| :-- | :-- | :-- | :-- |
| Tier 1 | LEAPS delta < 0.65 | Keep LEAPS, defensive posture | Roll short call to 0.15 delta, same expiry; no new shorts until delta recovers ≥ 0.70 |
| Tier 2 | LEAPS delta < 0.30 AND DTE < 60 | Exit LEAPS | Buy back short call in **same transaction**; no naked short allowed |
| Tier 3 | QQQ near 52‑week low | Emergency exit | Market‑close both LEAPS and short call on 9:45 exit scan; PMCC state → CLOSED |

Always ensure: **no state exists where LEAPS is closed and the short call is still open**.

***

### 6. Position sizing \& portfolio constraints

This stays consistent with your Kelly‑inspired allocation.[^10]

- Each LEAPS position = **33% of virtual NAV**.[^10]
- Maximum 3 concurrent LEAPS positions (3 × 33% ≈ 100%).[^10]
- PMCC short call: maintain **1 short call per 1 LEAPS contract**; never over‑short.
- Aggregate PMCC exposure: limit virtual account to **≤ 25% of total options account** if you extend beyond QQQ into other tickers, echoing PMCC practitioners’ “keep to ~10–25%” suggestion.[^4]

In the `shadow_positions` table, track:

- `leaps_debit_total`
- `pmcc_credit_cumulative`
- `pmcc_state` (LEAPS_ONLY, PMCC_ACTIVE, PMCC_DEFENSIVE, CLOSED)

Net cost basis = `leaps_debit_total − pmcc_credit_cumulative`, which you can later visualize in per‑user dashboards.[^10]

***

### 7. State machine (v2)

Updated state diagram with the new rules:

- **STATE: LEAPS_ONLY**
    - If PMCC entry conditions met → open short call → **STATE: PMCC_ACTIVE**.
- **STATE: PMCC_ACTIVE**
    - Profit rules (20%/10% or T_t ≤ 21) hit → buy back, then if conditions still valid, sell fresh 30–35 DTE call → stay in **PMCC_ACTIVE**.
    - QQQ within 3% of strike or short delta ≥ 0.40 → roll up/out per spec → remain **PMCC_ACTIVE**.
    - Short call ≥ 2× credit → buy back, no re‑sell → **LEAPS_ONLY**.
    - Regime → CHOPPY → roll to 0.15 delta → **PMCC_DEFENSIVE**.
    - Regime → BEAR / BEAR_SMA_FORCED → close short call → **LEAPS_ONLY**.
    - DrawdownGuard Tier 2/3 → close both legs → **CLOSED**.
- **STATE: PMCC_DEFENSIVE**
    - If regime returns to BULL_STRONG/MODERATE and delta + conditions OK → roll up to 0.22–0.28 delta, 30–35 DTE → **PMCC_ACTIVE**.
    - If regime → BEAR or Tier 2/3 → close both legs → **CLOSED**.

***

If you want, next step I can help you write pseudo‑code or Python backtest logic that plugs this v2 PMCC ruleset into your existing LEAPS backtester, including how to simulate the BCI “forced close” check and the 20%/10% management cycles.
<span style="display:none">[^11][^12][^13][^14][^15][^16][^17]</span>

<div align="center">⁂</div>

[^1]: https://www.youtube.com/watch?v=Kz7Yt2USETw

[^2]: https://www.youtube.com/watch?v=8ehihuDf2MM

[^3]: https://www.youtube.com/watch?v=Y3vD-wyliZ8

[^4]: https://www.reddit.com/r/thetagang/comments/mobk8j/pmcc_discussion_how_many_of_you_trade_these/

[^5]: https://www.thebluecollarinvestor.com/the-poor-mans-covered-call-trade-initialization-formula-2/

[^6]: https://www.youtube.com/watch?v=Atz7R2A8lrg

[^7]: https://www.tradingblock.com/strategies/poor-mans-covered-call-pmcc

[^8]: https://www.youtube.com/watch?v=wFpDYSZc3uE

[^9]: https://thebluecollarinvestor.com/minimembership/poor-mans-covered-call-calculator/

[^10]: strategy_performance_report.md-1.pdf

[^11]: strategy_performance_report.md

[^12]: https://www.youtube.com/watch?v=ALgWxtNJBIU

[^13]: https://www.youtube.com/watch?v=wvhyj6uyQ-c

[^14]: https://www.thebluecollarinvestor.com/an-annualized-return-of-5000-and-feeling-miserable-interpreting-our-covered-call-trades/

[^15]: https://www.youtube.com/watch?v=NK9gVsmhdBc

[^16]: https://www.youtube.com/watch?v=i9XDoi1j3bM

[^17]: https://www.youtube.com/watch?v=lbv5CGQMZOQ

