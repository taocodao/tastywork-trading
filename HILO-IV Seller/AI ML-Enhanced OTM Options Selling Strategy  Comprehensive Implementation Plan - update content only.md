<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# I don't see the regenerated file, instead of regenerate the entire doc, just generate the update content only which  after place the GTC stop loss order check them periodically that make it maintain around 10%  if possible, to protect the profit. Actually in reality some option has the high spread, the stop price has be above the bid price which over the 10% of the ask price.

Great — here is the focused update content only, covering the enhanced GTC stop-loss monitoring logic with bid/ask spread awareness. You can insert this as an **updated Section 3.5** and a **new Section 3.5a** in the existing plan.

***

## 🔄 UPDATE: Section 3.5 — Risk Engine (`risk_engine.py`)

### Revised Stop-Loss Philosophy: Spread-Aware \& Periodically Adjusted

The original 10% stop is calculated on the **premium collected** (the credit received). However, in reality, many single-stock options carry wide bid/ask spreads. If the stop-to-close (BTC) order is placed naively at `premium × 1.10`, that price may sit *below* the current ask price at entry — meaning the GTC order would trigger immediately or fail to execute cleanly. The corrected approach:

> **The GTC stop price must always be set above the current ask price at the time of entry, and then periodically re-evaluated to trail profitability as the option decays.**

***

### 3.5a Spread-Aware Stop Price Calculation

**The Rule:** At entry, calculate two candidate stop prices and take the higher of the two:

```
candidate_1 = premium_collected × (1 + stop_loss_pct)   # e.g., $1.00 × 1.10 = $1.10
candidate_2 = ask_price_at_entry × (1 + stop_buffer_pct) # e.g., $1.15 × 1.05 = $1.21
stop_price  = max(candidate_1, candidate_2)
```

- `stop_loss_pct` = 0.10 (10% of premium, configurable)
- `stop_buffer_pct` = 0.05 (5% above ask, ensures the GTC lives above the current market, configurable)
- This prevents the GTC from sitting inside the spread at entry or triggering immediately

**Example with a wide-spread option:**


| Field | Value |
| :-- | :-- |
| Premium collected (bid at fill) | \$1.00 |
| Ask price at entry | \$1.20 (wide \$0.20 spread) |
| Candidate 1 (10% of premium) | \$1.10 |
| Candidate 2 (5% above ask) | \$1.26 |
| **Effective stop price set** | **\$1.26** |

In this case the naïve 10% stop at \$1.10 would sit below the current ask — the GTC would trigger on the next tick. The spread-aware calculation correctly sets it at \$1.26.

**Code:**

```python
def calculate_spread_aware_stop(
    premium_collected: float,
    ask_at_entry: float,
    stop_loss_pct: float = 0.10,
    ask_buffer_pct: float = 0.05
) -> float:
    """
    Returns the effective GTC stop price, adjusted for wide spreads.
    Always places the stop above the current ask to avoid immediate trigger.
    """
    candidate_naive  = round(premium_collected * (1 + stop_loss_pct), 2)
    candidate_spread = round(ask_at_entry * (1 + ask_buffer_pct), 2)
    stop_price = max(candidate_naive, candidate_spread)
    return stop_price
```


***

### 3.5b Periodic Stop-Loss Maintenance Job

After the GTC stop is placed, a **periodic monitoring job** re-evaluates and adjusts the stop every 30 minutes (or configurable interval) during market hours. The goal is twofold:

1. **Prevent stop from sitting inside a widened spread** — spreads widen intraday, especially near open/close. If the current ask drifts above the GTC stop price, the stop is stale and would trigger on the next bid touch.
2. **Trail the stop down as the option decays** — as theta erodes the option value, the 10% loss threshold in dollar terms should shrink, protecting accrued profit.

**Trailing Stop Adjustment Logic:**

```
current_mid    = (current_bid + current_ask) / 2
new_candidate1 = current_mid × (1 + stop_loss_pct)     # 10% above current mid
new_candidate2 = current_ask × (1 + ask_buffer_pct)    # 5% above current ask
new_stop       = max(new_candidate1, new_candidate2)

# Only LOWER the stop (trailing behavior — lock in profit as option decays)
# Never raise the stop above the original stop price (that would increase max loss)
adjusted_stop = min(new_stop, original_stop_price)
```

The key constraint: **the stop can only move down (tighter), never up**. This trails the option's market value downward as it decays toward zero, progressively protecting more of the collected premium.

**Example lifecycle:**


| Time | Option Mid | Current Ask | New Candidate Stop | Adjusted Stop (↓ only) |
| :-- | :-- | :-- | :-- | :-- |
| Entry (Day 0) | \$1.00 | \$1.20 | \$1.26 | \$1.26 (initial) |
| Day 7 (decay) | \$0.75 | \$0.88 | \$0.92 | \$0.92 ✅ lowered |
| Day 14 (decay) | \$0.45 | \$0.55 | \$0.58 | \$0.58 ✅ lowered |
| Day 21 (decay) | \$0.20 | \$0.28 | \$0.30 | \$0.30 ✅ close for 70% profit |

By Day 21, the stop has trailed from \$1.26 down to \$0.30 — if the option reverses, the position closes with most of the profit locked in rather than giving it all back.

**Code:**

```python
def adjust_trailing_stop(
    current_bid: float,
    current_ask: float,
    original_stop: float,
    stop_loss_pct: float = 0.10,
    ask_buffer_pct: float = 0.05
) -> tuple[float, bool]:
    """
    Recalculates stop price using current market data.
    Returns (new_stop, should_update) where should_update=True if
    the stop should be replaced on the broker side.
    
    Stop can only trail DOWN to lock in profit — never raised.
    """
    current_mid = round((current_bid + current_ask) / 2, 2)
    candidate_mid  = round(current_mid * (1 + stop_loss_pct), 2)
    candidate_ask  = round(current_ask * (1 + ask_buffer_pct), 2)
    new_stop_raw   = max(candidate_mid, candidate_ask)
    
    # Only trail downward — cap at original stop
    adjusted_stop  = min(new_stop_raw, original_stop)
    adjusted_stop  = round(adjusted_stop, 2)
    
    should_update  = adjusted_stop < original_stop  # meaningful improvement
    return adjusted_stop, should_update
```


***

### 3.5c Stop Maintenance Scheduler Job

Add this job to `scheduler.py` alongside the existing `position_monitor` job:

```python
scheduler.add_job(
    maintain_gtc_stops,
    "interval",
    minutes=30,                          # configurable — tighter near open/close
    start_date="2026-01-01 09:35:00",   # 5 min after open (spread settles)
    end_date  ="2026-12-31 15:30:00",   # stop before close
    id="gtc_stop_maintenance"
)
```

**`maintain_gtc_stops()` function:**

```python
def maintain_gtc_stops(
    order_manager,
    trade_logger,
    alert_system,
    config
):
    """
    Periodic job: for every open short option position,
    1. Fetch current bid/ask from broker
    2. Recompute spread-aware trailing stop
    3. If stop should move down: cancel old GTC, place new GTC
    4. Log the adjustment, alert if significant change (>10% move in stop)
    5. Alert if spread has blown out (ask > current GTC stop — danger zone)
    """
    open_trades = trade_logger.get_open_trades()

    for trade in open_trades:
        symbol       = trade["option_symbol"]
        original_stop = trade["stop_price"]
        entry_premium = trade["premium_collected"]

        # Fetch live quote
        quote = order_manager.get_option_quote(symbol)
        if not quote:
            continue
        
        bid = quote["bid"]
        ask = quote["ask"]
        mid = (bid + ask) / 2

        # ── Danger Zone Check ────────────────────────────────────────────────
        # If current ask is already above the GTC stop, the order is at risk
        # of not protecting us — flag immediately
        if ask >= original_stop:
            alert_system.spread_danger_alert(
                ticker=trade["ticker"],
                symbol=symbol,
                current_ask=ask,
                gtc_stop=original_stop,
                message="ASK has crossed GTC stop — spread blowout risk"
            )

        # ── Trailing Adjustment ───────────────────────────────────────────────
        new_stop, should_update = adjust_trailing_stop(
            current_bid=bid,
            current_ask=ask,
            original_stop=original_stop,
            stop_loss_pct=config["risk"]["stop_loss_pct"],
            ask_buffer_pct=config["risk"]["ask_buffer_pct"]
        )

        if should_update:
            # Cancel existing GTC, place new tighter GTC
            order_manager.cancel_gtc_stop(trade["gtc_order_id"])
            new_order = order_manager.place_gtc_stop(symbol, trade["qty"], new_stop)

            # Log and alert
            trade_logger.log_stop_adjustment(
                trade_id=trade["id"],
                old_stop=original_stop,
                new_stop=new_stop,
                current_mid=mid
            )

            pct_change = (original_stop - new_stop) / original_stop * 100
            if pct_change >= 5.0:   # only alert on meaningful moves
                alert_system.stop_adjusted_alert(
                    ticker=trade["ticker"],
                    old_stop=original_stop,
                    new_stop=new_stop,
                    current_mid=mid
                )

            # Update trade record with new stop and order ID
            trade_logger.update_trade_stop(
                trade_id=trade["id"],
                new_stop=new_stop,
                new_gtc_order_id=new_order.id
            )
```


***

### 3.5d Database Schema Addition

Add this table to `trade_logger.py` / `db/trades.db` to record every stop adjustment:

```sql
CREATE TABLE stop_adjustments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        INTEGER REFERENCES trades(id),
    timestamp       TEXT NOT NULL,
    old_stop        REAL,
    new_stop        REAL,
    current_bid     REAL,
    current_ask     REAL,
    current_mid     REAL,
    adjustment_pct  REAL,   -- (old_stop - new_stop) / old_stop * 100
    reason          TEXT    -- 'TRAILING_DECAY' | 'SPREAD_BLOWOUT_GUARD' | 'INITIAL'
);
```


***

### 3.5e Alert System Additions

Add these two new alert methods to `alert_system.py`:

```python
def stop_adjusted_alert(self, ticker, old_stop, new_stop, current_mid):
    pct = (old_stop - new_stop) / old_stop * 100
    msg = (f"📉 *Stop Trailed: {ticker}*\n"
           f"Old Stop: ${old_stop:.2f} → New Stop: ${new_stop:.2f}\n"
           f"Locked-in improvement: {pct:.1f}%\n"
           f"Current Mid: ${current_mid:.2f}")
    asyncio.run(self.send(msg))

def spread_danger_alert(self, ticker, symbol, current_ask, gtc_stop, message):
    msg = (f"⚠️ *Spread Danger: {ticker}*\n"
           f"Option: {symbol}\n"
           f"Current Ask: ${current_ask:.2f} | GTC Stop: ${gtc_stop:.2f}\n"
           f"⚡ {message}\n"
           f"Action: Consider canceling GTC and re-entering at wider stop")
    asyncio.run(self.send(msg))
```


***

### Summary of Logic Flow

```
At Entry:
  stop = max(premium × 1.10,  ask_at_entry × 1.05)
  → place GTC BTC at stop

Every 30 minutes:
  fetch current bid/ask
  IF ask > current_GTC_stop → fire SPREAD DANGER alert immediately
  new_stop = max(mid × 1.10, ask × 1.05)
  adjusted  = min(new_stop, original_stop)   ← can only trail DOWN
  IF adjusted < current_stop:
    → cancel old GTC
    → place new tighter GTC
    → log adjustment + alert if Δ ≥ 5%

On Roll Trigger:
  re-run full spread-aware stop calc on the NEW option's bid/ask
  reset trail history (original_stop = new entry stop)
```


***

This update slots directly into the existing plan. The three key additions are: **(1)** spread-aware initial stop placement, **(2)** a 30-min trailing maintenance job that can only move the stop down to lock in profit, and **(3)** a spread-danger alert that fires when a blowout pushes the ask above your protection level.[^1][^2][^3][^4]

<div align="center">⁂</div>

[^1]: https://www.tradingblock.com/blog/iv-rank-vs-iv-percentile

[^2]: https://www.schwab.com/learn/story/three-types-options-exit-strategies

[^3]: https://www.youtube.com/watch?v=uWcNlO-4LB8

[^4]: https://optionalpha.com/learn/rolling-options

