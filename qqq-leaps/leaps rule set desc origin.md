<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# yes, can you  turn this into a very specific, backtest‑ready ruleset for QQQ PMCC (exact deltas, roll triggers, drawdown limits) that fits the qqq leaps strategy mention in the attached file

Based on your attached TurboCore \& QQQ LEAPS Strategy Report, here is a fully specified, backtest-ready PMCC ruleset that integrates directly into your existing five-layer architecture (particularly Layer D, which you noted is not yet fully automated).[^1]

***

## QQQ LEAPS + PMCC — Full Backtest Ruleset

### Prerequisite: Regime Gate (Layer A)

PMCC short call initiation is only allowed when the regime is **BULL_STRONG** or **BULL_MODERATE**. Never initiate a new short call in **CHOPPY**, and immediately close any open short call when regime shifts to **BEAR** or **BEAR_SMA_FORCED**.[^1]


| Regime | Allow New Short Call? | Short Call Strike Aggression |
| :-- | :-- | :-- |
| BULL_STRONG (HMM > 70%, VIX < 25) | ✅ Yes | 0.28–0.30 delta |
| BULL_MODERATE (HMM 55–70%, VIX < 35) | ✅ Yes | 0.22–0.25 delta |
| CHOPPY (HMM 35–55%) | ❌ No | Hold existing, do not open new |
| BEAR / BEAR_SMA_FORCED | ❌ Close immediately | Emergency close |


***

### Entry Rule: When to Sell the Short Call

Once a LEAPS position is open, initiate the short call leg when **all five** of the following conditions are met:[^1]

1. **LEAPS held ≥ 5 days** (position has stabilized from the gap-down entry, per Part 6 item 3)
2. **LEAPS DTE > 60** (per Layer D rule: no short leg when LEAPS is expiring)
3. **QQQ is NOT within 3% below the LEAPS entry price** (you want QQQ to have bounced modestly, not still in freefall)
4. **Regime is BULL_STRONG or BULL_MODERATE** (see table above)
5. **VIX ≥ 16** (sell calls when implied vol is elevated enough to make premium worthwhile; avoid selling in crushingly low-IV environments)

**Short call specification:**

- **Expiration:** 30–35 DTE (captures peak theta decay zone around the 30-day mark)
- **Delta:** 0.28–0.30 in BULL_STRONG; 0.22–0.25 in BULL_MODERATE (these are capped at 0.30 per your Layer D rule)
- **Minimum premium threshold:** Short call must collect at least **\$0.50/contract** (\$50 total) — below this, the income doesn't justify the complexity and bid-ask cost
- **Limit order entry:** Use midpoint − \$0.05 to avoid selling at the bid on wide-spread index ETF options

***

### Profit-Take Rule (Primary Exit)

- **Close at 50% of premium collected** — consistent with Tastylive's proven rule already in your Layer D spec[^1]
- Concretely: if you sold the short call for \$1.20 credit, buy it back at \$0.60
- Do **not** wait until expiration; closing at 50% and immediately reloading a new 30-DTE call maximizes annualized theta capture

**Re-entry after profit take:** Immediately sell a new 30-DTE, same-delta call provided regime conditions still pass (see entry rules above). This "perpetual roll" is what generates the \$200–400/contract/month income estimate in your report.[^1]

***

### Roll Triggers: When to Roll Instead of Close

A roll means you **buy back the existing short call** and **sell a new one** in the same action (for a net credit where possible).


| Trigger | Action | Target |
| :-- | :-- | :-- |
| QQQ within **3% of short strike** (approaching threat) | Roll up and out | New strike: +\$3–5 higher; New expiry: current +21 days |
| Short call hits **200% of original premium** (loss limit) | Buy back immediately at a loss; do NOT roll | Wait for regime confirmation before next entry |
| Regime drops from BULL to CHOPPY mid-cycle | Roll to a **further OTM strike** (0.15 delta), same expiry | Defensive repositioning without closing |
| Regime drops to BEAR | **Emergency close** short call immediately at market | No replacement |
| LEAPS delta drops below **0.65** (Layer E Tier 1 trigger from your report) | Roll short call **down** to 0.15 delta, same expiry | Reduce risk on a weakening LEAPS |

**Roll rule:** Always target a **net credit or break-even debit ≤ \$0.10** when rolling. If you cannot achieve this, close the short call outright and do not re-open until conditions improve.

***

### Drawdown Limits (Integrating with Layer E)

Your existing Layer E has three tiers for the **LEAPS** itself. Here's how the PMCC short call interacts with each:[^1]


| Layer E Tier | Trigger | LEAPS Action | Short Call Action |
| :-- | :-- | :-- | :-- |
| Tier 1 | LEAPS delta < 0.65 | Roll short call down | Move to 0.15 delta, same expiry |
| Tier 2 | LEAPS delta < 0.30 AND DTE < 60 | Exit LEAPS | Buy back short call simultaneously (market order) |
| Tier 3 | QQQ near 52-week low | Emergency exit LEAPS | Buy back short call at market, no delay |

**Key rule:** **Always close the short call before or simultaneously with closing the LEAPS**. Never be left with a naked short call after the long LEAPS is closed — this converts a defined-risk diagonal into unlimited-risk exposure.

***

### Position Sizing (Short Call)

Consistent with your 33% virtual NAV per LEAPS position:[^1]

- Sell **1 short call per every 1 LEAPS contract held** (maintain 1:1 ratio)
- If you hold the hard-capped 5 LEAPS contracts, sell a maximum of 5 short calls
- Track short call credit received in the `shadow_positions` table as a separate `pmcc_short_call` record, linked to the parent LEAPS position ID — this lets you compute the **net cost basis** of each diagonal spread:
> Net cost basis = LEAPS debit paid − cumulative short call credits received

***

### Full PMCC Lifecycle for Backtesting

Here is the complete state machine to implement in your backtester:

```
STATE: LEAPS_ONLY
  Day 5+ after entry AND conditions met → ENTER short call → STATE: PMCC_ACTIVE

STATE: PMCC_ACTIVE
  Short call ≥ 50% profit → BUY BACK → if conditions met → SELL NEW CALL → STATE: PMCC_ACTIVE
  Short call ≥ 200% loss → BUY BACK → STATE: LEAPS_ONLY (wait)
  QQQ within 3% of short strike → ROLL UP+OUT → STATE: PMCC_ACTIVE
  LEAPS delta < 0.65 → ROLL SHORT CALL DOWN → STATE: PMCC_ACTIVE
  Regime → CHOPPY → ROLL to 0.15 delta → STATE: PMCC_DEFENSIVE
  Regime → BEAR → CLOSE short call → STATE: LEAPS_ONLY

STATE: PMCC_DEFENSIVE
  Regime returns to BULL_MODERATE+ → ROLL to 0.25 delta → STATE: PMCC_ACTIVE
  Regime → BEAR → CLOSE short call → STATE: LEAPS_ONLY

STATE: LEAPS_ONLY (after bear close)
  Regime returns to BULL + conditions met → SELL NEW CALL → STATE: PMCC_ACTIVE

STATE: FULL_EXIT (Layer E Tier 2 or 3 triggered)
  Close short call AND LEAPS simultaneously → STATE: CLOSED
```


***

### Backtest Slippage Model for Short Calls

Your report already flags LEAPS bid-ask spreads of 1–4% in normal markets and 4–8% during panics. For the short calls (shorter-dated, closer to ATM), the spread is typically narrower:[^1]

- **Normal markets (VIX < 20):** model 0.5% slippage on the short call premium
- **Elevated markets (VIX 20–35):** model 1% slippage
- **Panic days (VIX > 35):** do **not** initiate new short calls (per the VIX ≥ 16 but implicitly the extreme-vol situation makes selling calls dangerous near the bottom)

***

### Expected P\&L Attribution (per your report estimates)

At \$200–400/contract/month from the short call leg:[^1]

- 5 contracts at 30-DTE cycle = \$1,000–2,000/month in gross short call income
- Subtract slippage + buyback costs: net ~\$700–1,600/month
- Over the LEAPS holding period of 12 months: ~\$8,400–19,200 in cumulative short call income per 5-contract LEAPS position
- This income directly reduces your net LEAPS cost basis, which is why the PMCC structurally outperforms a naked LEAPS-only hold in sideways/mildly bullish regimes

***

### The One Critical Production Fix First

Before backtesting PMCC rolls, fix the **EXIT confidence gate bug** from Part 5 of your report  — short call close/roll signals will also carry `confidence = 0.0` and will be blocked by `should_auto_approve()` the same way LEAPS exits are. Add:[^1]

```python
if signal.get("action") in ["EXIT", "ROLL", "PMCC_CLOSE", "PMCC_ROLL"]:
    return True  # Never gate protective or management actions
```

This single fix unblocks both the LEAPS exit bug and all future PMCC automation.

<div align="center">⁂</div>

[^1]: strategy_performance_report.md-1.pdf

