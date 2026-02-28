# Unified TQQQ Strategy — Comprehensive Implementation Plan

## Architecture: Three Non-Conflicting Return Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                    CAPITAL BUDGET (e.g. $25K)                   │
├─────────────────────────────────┬───────────────────────────────┤
│    THETA POOL (70% = $17.5K)   │  SWING POOL (30% = $7.5K)    │
│                                 │                               │
│  Layer 1: Dual-Sided Spread    │  Layer 2: RSI Swing Overlay   │
│  • Put credit spread (LOW/NORM)│  • Put diagonal (RSI-2 < 20)  │
│  • Call credit spread (HI/CRIS)│  • Uses CrashGuard scoring    │
│  • VIX regime-driven entries   │  • Uses SwingExitEngine        │
│  • Hold 14-35 days             │  • Hold 3-7 days              │
│  • Exit: PT / SL / DTE         │  • Exit: RSI > 65 / bounce    │
│                                 │                               │
│  ≈ 12% annual                  │  ≈ 5-8% annual               │
├─────────────────────────────────┴───────────────────────────────┤
│              Layer 3: Dynamic Position Sizing                   │
│  • CrashGuard score (55-100) → 1.0x to 2.0x multiplier         │
│  • Higher conviction = larger theta positions                   │
│  • ≈ 2-3% annual lift                                          │
├─────────────────────────────────────────────────────────────────┤
│              Combined Target: 17-22% annual                     │
└─────────────────────────────────────────────────────────────────┘
```

### Why these don't conflict

| Concern | Resolution |
|---|---|
| **Margin overlap** | Separate capital pools (70/30 split). Theta pool for credit spreads, swing pool for diagonals |
| **Directional conflict** | Theta puts = bullish bias. Theta calls = bearish bias. Swing diagonals = dip-buying (bullish). In HIGH_VOL when calls are active, swing diagonals are gated by CrashGuard (score < 55 → blocked) |
| **Entry signal conflict** | Theta uses VIX regime + direction. Swing uses RSI-2 + CrashGuard score. Completely independent signals |
| **Position limits** | `TQQQPositionSizer.MAX_POSITIONS` already enforces per-pool caps (LOW=3, MED=5, HI=7) |

---

## What Already Exists (Reuse Map)

| Component | File | Layer | Status |
|---|---|---|---|
| VIX Adaptive Strategy (put+call state machine) | [vix_adaptive_strategy.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/vix_adaptive_strategy.py) | Theta | ✅ Built |
| Call spread builder | [spread_builder.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/spread_builder.py#L342) | Theta | ✅ Built |
| Diagonal spread builder | [spread_builder.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/spread_builder.py#L462) | Swing | ✅ Built |
| CrashGuard (5-layer scoring) | [crash_guard.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/crash_guard.py) | Swing | ✅ Built |
| SwingExitEngine (5-priority cascade) | [swing_exit_engine.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/swing_exit_engine.py) | Swing | ✅ Built |
| Position sizer (risk-tiered) | [position_sizer.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/position_sizer.py) | Both | ✅ Built |
| Put order manager | [order_manager.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/order_manager.py) | Theta | ✅ Put only |
| Signal publisher (put + diagonal) | [signal_publisher/tqqq.py](file:///d:/Projects/tastywork-trading-1/signal_publisher/tqqq.py) | Both | ✅ No call signals |
| HMM Regime Detector | `src/tqqq/ml/regime_detector.py` | Theta | ✅ Built |
| VIX Ensemble Predictor | `src/tqqq/ml/vix_predictor.py` | Theta | ✅ Built |

---

## Proposed Changes

### Step 1: Order Manager — Add Call Spread Support

#### [MODIFY] [order_manager.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/order_manager.py)

Add 3 methods mirroring existing put logic:

```diff
+    def _make_tqqq_call(self, strike, expiration):
+        # Same as _make_tqqq_put but right="C"
+
+    async def place_call_spread_order(self, short_strike, long_strike, expiration, quantity, account_id):
+        # Sell lower call + buy higher call as BAG combo
+
+    async def close_call_spread_order(self, short_strike, long_strike, expiration, quantity, account_id):
+        # Buy-to-close the call spread (debit order)
```

Update `close_single_leg()` to accept `right` param (`"P"` or `"C"`).

---

### Step 2: Signal Publisher — Add Call Spread Signals

#### [MODIFY] [signal_publisher/tqqq.py](file:///d:/Projects/tastywork-trading-1/signal_publisher/tqqq.py)

```diff
+    class TQQQCallSpreadEntrySignal(BaseSignal):
+        short_call_strike, long_call_strike, expiration, credit, regime
+
+    class TQQQCallSpreadCloseSignal(BaseSignal):
+        position_id, reason  # PROFIT_TARGET / LOSS_LIMIT / RALLY_CIRCUIT_BREAKER / DTE_EXIT
+
+    def publish_tqqq_call_entry_signal(...)
+    def publish_tqqq_call_close_signal(...)
```

---

### Step 3: Position Tracker — Support All Position Types

#### [MODIFY] [position_tracker.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/position_tracker.py)

```diff
+    spread_type: str = "PUT"              # "PUT", "CALL", or "DIAGONAL"
+    pool: str = "THETA"                   # "THETA" or "SWING" — capital pool assignment
+    short_call_strike: float = 0.0
+    long_call_strike: float = 0.0
+    tqqq_entry_price: float = 0.0        # For rally circuit breaker
+    long_call_legout_value: Optional[float] = None
+    # Diagonal swing fields
+    anchor_strike: float = 0.0
+    anchor_expiration: str = ""
+    hedge_strike: float = 0.0
+    hedge_expiration: str = ""
+    crash_guard_score: int = 0            # Score at entry for Layer 3 sizing
```

Update `is_active` → include `FULL_CALL_SPREAD`, `LONG_CALL_ONLY`, `DIAGONAL_OPEN`.
Update `get_unrealized_pnl()` → handle all spread types.

---

### Step 4: Risk Manager — Capital Pool Budgeting

#### [MODIFY] [tqqq_risk_manager.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/tqqq_risk_manager.py)

```diff
+    THETA_POOL_PCT = 0.70    # 70% of capital for theta positions
+    SWING_POOL_PCT = 0.30    # 30% of capital for swing positions
+
+    def get_pool_budget(self, pool: str, principal: float) -> float:
+        """Returns available capital for a specific pool."""
+
+    def can_enter_theta_position(self, active_theta_positions, proposed_risk) -> bool:
+        """Checks theta pool has budget for a new credit spread."""
+
+    def can_enter_swing_position(self, active_swing_positions, proposed_risk) -> bool:
+        """Checks swing pool has budget for a new diagonal."""
+
+    def can_enter_call_spread(self, ...) -> bool:
+    def can_leg_out_call(self, ...) -> bool:
```

---

### Step 5: Data Pipeline — Support Call Chain Fetching

#### [MODIFY] [data_pipeline.py](file:///d:/Projects/tastywork-trading-1/src/tqqq/data_pipeline.py)

```diff
- def get_options_chain(self, symbol="TQQQ", dte_min=21, dte_max=45):
+ def get_options_chain(self, symbol="TQQQ", dte_min=21, dte_max=45, right="P"):
```

---

### Step 6: Scheduler — Wire All Three Layers Together

#### [MODIFY] [run_tqqq_scheduler.py](file:///d:/Projects/tastywork-trading-1/run_tqqq_scheduler.py)

This is the largest change — the scheduler becomes the orchestrator of all three layers.

**`_scan_for_entry()` changes:**
```python
# LAYER 1: Theta entries (existing VIX regime logic)
action, detail = strategy.evaluate(position, regime, vix_direction, ...)
if action == "ENTER_SPREAD":      # Put credit spread
    # Use THETA pool budget
    # → spread_builder.select_optimal_spread()
    # → order_manager.place_spread_order()

elif action == "ENTER_CALL_SPREAD":  # NEW: Bear call credit spread
    # Use THETA pool budget
    # → spread_builder.select_optimal_call_spread()
    # → order_manager.place_call_spread_order()

# LAYER 2: Swing entries (RSI-2 dip detection) — runs INDEPENDENTLY
if self._has_swing_budget():
    crash_result = crash_guard.evaluate_entry(daily_df, intraday_row, ml_prob)
    if crash_result.passed and crash_result.score >= 55:
        # Use SWING pool budget
        # → spread_builder.select_optimal_diagonal()
        # → order_manager.place_spread_order() (put diagonal)
        # → Scale quantity by crash_result.multiplier (Layer 3)
```

**`_position_check()` changes:**
```python
for position in active_positions:
    if position.pool == "THETA":
        # Existing theta logic: profit target / stop loss / DTE / leg-out
        if position.spread_type == "CALL":
            # NEW: Handle FULL_CALL_SPREAD state + circuit breaker
    elif position.pool == "SWING":
        # Use SwingExitEngine for diagonal positions
        exit_decision = swing_exit.evaluate(position, current_price, rsi_2, ...)
        if exit_decision.decision == ExitDecisionType.CLOSE_ALL:
            # Close diagonal
        elif exit_decision.decision == ExitDecisionType.ROLL_HEDGE:
            # Theta kicker: roll expiring hedge
```

**`_pre_close_check()` changes:**
```python
# Check 5% rally circuit breaker on ALL open call spreads
# Check emergency close on ALL swing positions if daily drop > 10%
```

---

### Step 7: Config — Unified Parameters

#### [MODIFY] [config.py](file:///d:/Projects/tastywork-trading-1/diagonal_strategy/config.py)

```diff
+# Capital Pool Allocation
+TQQQ_THETA_POOL_PCT = 0.70
+TQQQ_SWING_POOL_PCT = 0.30
+
+# Swing Overlay Parameters (Layer 2)
+TQQQ_SWING_RSI_THRESHOLD = 20       # Relaxed from 10 for more signals
+TQQQ_SWING_MIN_CRASH_GUARD = 55     # Minimum CrashGuard score
+TQQQ_SWING_MAX_CONCURRENT = 3       # Max simultaneous swing positions
+TQQQ_SWING_MAX_HOLD_DAYS = 7        # Force close after 7 days
```

---

## Implementation Order

| Step | File | Layer | Effort | Dependencies |
|---|---|---|---|---|
| **1** | `order_manager.py` | Theta | Small | None |
| **2** | `signal_publisher/tqqq.py` | Theta | Small | None |
| **3** | `position_tracker.py` | Both | Small | None |
| **4** | `tqqq_risk_manager.py` | Both | Medium | Step 3 |
| **5** | `data_pipeline.py` | Theta | Small | None |
| **6** | `config.py` | Both | Small | None |
| **7** | `run_tqqq_scheduler.py` | Both | **Large** | Steps 1-6 |

Steps 1-6 can be done in parallel. Step 7 (scheduler wiring) is the final integration.

---

## Expected Return Profile

| Layer | Mechanism | Annual Contribution | Trades/Year |
|---|---|---|---|
| 1: Theta (Put spreads) | VIX falling → sell puts, theta decay | ~8% | ~10 |
| 1: Theta (Call spreads) | VIX rising → sell calls, theta decay | ~4% | ~4 |
| 2: Swing overlay | RSI-2 dip → diagonal, bounce exit | ~5-8% | ~14-20 |
| 3: Dynamic sizing | CrashGuard score → 1-2x multiplier | ~2-3% | — |
| **Combined** | | **~17-22%** | **~28-34** |

---

## Verification Plan

### Automated
1. Run `tqqq_backtest_simulation.py` Scenario B → confirm 98.3% baseline
2. Extend backtest to include swing overlay with separate capital pool
3. Unit test: call spread order flow in sim mode
4. Unit test: capital pool budget enforcement

### Integration Test
1. Start scheduler in paper mode
2. Verify it generates BOTH theta signals (put + call) AND swing signals (diagonal)
3. Verify capital pool isolation — swing trades don't consume theta budget
4. Verify CrashGuard gates swing entries correctly (blocked when score < 55)
5. Verify SwingExitEngine closes diagonals on RSI-2 > 65 bounce
