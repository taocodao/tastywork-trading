# TQQQ Dual-Sided Spread Strategy — Complete Implementation Plan
# VIX-Adaptive Put Credit Spreads + Bear Call Credit Spreads

> **Date:** February 2026  
> **Status:** Phase 1–3 COMPLETE (core logic), Phase 4–7 PENDING (integration + frontend)  
> **Backtest Winner:** Scenario B (Put + Call) — +98.3% return, Sharpe 6.01, -10.4% MaxDD  
> **Architecture:** This is the ONLY live strategy — all UI/backend customized for it

---

## Phase Summary

| Phase | Description | Status |
|:--|:--|:--|
| 1 | Config & Data Model | ✅ Complete |
| 2 | Core Logic (Spread Builder + State Machine) | ✅ Complete |
| 3 | Backtest Validation | ✅ Complete (Scenario B wins) |
| 4 | Execution Layer (Order Manager, Signals, Scheduler) | 🔲 Pending |
| 5 | Position Tracker + Risk Manager + Data Pipeline | 🔲 Pending |
| 6 | Frontend — Dashboard Redesign | 🔲 Pending |
| 7 | Settings — Principal, Risk Level, Auto-Approval | 🔲 Pending |

---

## Phase 1: Config & Data Model ✅ COMPLETE

### 1.1 `config.py` — Call Spread Parameters ✅

Added `TQQQ_CALL_PARAMS_BY_REGIME`:
```python
TQQQ_CALL_PARAMS_BY_REGIME = {
    "HIGH_VOL": {"dte": 14, "delta": 0.15, "width": 5, ...},
    "CRISIS":   {"dte": 7,  "delta": 0.10, "width": 3, ...},
}
TQQQ_CALL_RALLY_CIRCUIT_BREAKER_PCT = 0.05  # 5% intraday rally → auto-close
TQQQ_MAX_RISK_PCT = 0.10  # Updated from 5% to 10%
```

### 1.2 `src/tqqq/__init__.py` — New States ✅

```python
class TQQQStrategyState(Enum):
    IDLE = auto()
    FULL_SPREAD = auto()         # Put credit spread
    LONG_PUT_ONLY = auto()       # Legged out of short put
    FULL_CALL_SPREAD = auto()    # Bear call credit spread  ← NEW
    LONG_CALL_ONLY = auto()      # Legged out of short call ← NEW
    CLOSING = auto()
```

---

## Phase 2: Core Logic ✅ COMPLETE

### 2.1 `spread_builder.py` — Call Spread Selection ✅

Added `select_optimal_call_spread()`:
- Filters for CALL options with `_filter_structural_calls()`
- Short call delta capped ≤ 0.18
- Minimum credit ≥ $0.03
- Updated `_dict_to_leg()` to accept `right` param ('P' or 'C')

### 2.2 `vix_adaptive_strategy.py` — State Machine ✅

Full rewrite of `evaluate()` with dual-sided entry logic:

| Regime | VIX Direction | Action |
|:--|:--|:--|
| CRISIS | Any | `ENTER_CALL_SPREAD` |
| HIGH_VOL | Rising | `ENTER_CALL_SPREAD` |
| HIGH_VOL | Falling | `ENTER_SPREAD` (put) |
| NORMAL / LOW_VOL | Falling | `ENTER_SPREAD` (put) |

New actions: `ENTER_CALL_SPREAD`, `CLOSE_CALL_SPREAD`, `LEG_OUT_CALL`, `SELL_LONG_CALL`, `ABANDON_LONG_CALL`

Manages `FULL_CALL_SPREAD` state with profit target, loss limit, DTE exit, and 5% rally circuit breaker.

---

## Phase 3: Backtest Validation ✅ COMPLETE

Scenario B selected as winner:

| Scenario | Return | Sharpe | MaxDD |
|:--|:--|:--|:--|
| A: Put-only | +52.1% | 4.23 | -8.2% |
| **B: Put + Call** | **+98.3%** | **6.01** | **-10.4%** |
| C: Put + Call + IC | +82.7% | 5.12 | -14.8% |

---

## Phase 4: Execution Layer — Pending 🔲

### 4.1 MODIFY `src/tqqq/order_manager.py`

Currently only handles PUT legs. Need to add:

- **`place_call_spread_order()`** — sell OTM call + buy further OTM call as BAG combo
- **`close_call_spread_order()`** — buy-to-close the call spread (circuit breaker use)
- **`_make_tqqq_call()`** helper — creates a CALL contract (mirrors `_make_tqqq_put`)
- Update `close_single_leg()` to accept `right` param ('P' or 'C')

### 4.2 MODIFY `signal_publisher/tqqq.py`

Currently only has Put-side signals. Add:

- `TQQQCallSpreadEntrySignal` + `publish_tqqq_call_entry_signal()`
- `TQQQCallSpreadCloseSignal` + `publish_tqqq_call_close_signal()`
- Reason field for close: `PROFIT_TARGET`, `LOSS_LIMIT`, `RALLY_CIRCUIT_BREAKER`, `DTE_EXIT`

### 4.3 MODIFY `run_tqqq_scheduler.py`

#### In `_scan_for_entry()`:
- Handle `ENTER_CALL_SPREAD` → call `spread_builder.select_optimal_call_spread()`
- Fetch CALL chain with shorter DTE window (7–14 vs 21–45)
- Publish call spread entry signal
- If `TQQQ_AUTO_TRADE` → `order_manager.place_call_spread_order()`

#### In `_position_check()`:
- Handle `FULL_CALL_SPREAD` state — fetch call leg values (not put)
- Pass `tqqq_entry_price`, `tqqq_current_price`, `short_call_value`, `long_call_value` to `evaluate()`
- Handle: `CLOSE_CALL_SPREAD`, `LEG_OUT_CALL`, `SELL_LONG_CALL`, `ABANDON_LONG_CALL`

#### In `_pre_close_check()`:
- Check 5% rally circuit breaker on all open call spreads

---

## Phase 5: Position Tracker + Risk Manager — Pending 🔲

### 5.1 MODIFY `src/tqqq/position_tracker.py`

Add call spread fields to `TQQQPosition`:
```python
spread_type: str = "PUT"          # "PUT" or "CALL"
short_call_strike: float = 0.0
long_call_strike: float = 0.0
tqqq_entry_price: float = 0.0    # For circuit breaker
long_call_legout_value: Optional[float] = None
```

Update `is_active` to include `FULL_CALL_SPREAD`, `LONG_CALL_ONLY`.
Update `get_unrealized_pnl()` for call spread states.

### 5.2 MODIFY `src/tqqq/data_pipeline.py`

`get_options_chain()` currently hardcodes `right="P"`. Accept parameter:
```python
def get_options_chain(self, symbol="TQQQ", dte_min=21, dte_max=45, right="P"):
```

### 5.3 MODIFY `src/tqqq/tqqq_risk_manager.py`

- Update `MAX_RISK_PCT` to pull from config (now 10% instead of 5%)
- Add `can_leg_out_call()` validation
- Track put and call positions separately

---

## Phase 6: Frontend — Dashboard Redesign — Pending 🔲

> **Critical constraint:** Mobile-first, single-column. Home screen fits one phone screen.
> Shown at `www.trademind.bot` as PWA + website.
> **Two user modes:** Tastytrade-linked (auto-execute) and Track-Only (signal-following without broker).

### 6.1 MODIFY `src/app/dashboard/page.tsx` — Home Screen

**Layout (top → bottom, fits one phone screen):**

```
┌──────────────────────────────────┐
│●Live  🏠Home  📊Signals  📈Pos  📋Activity  ⚙Set│  ← TOP NAV (moved from bottom)
├──────────────────────────────────┤
│ Welcome back               🔄 🔔│
│ erichuang2005@...                │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ ✅ TQQQ DUAL-SIDED  ACTIVE  │ │
│ │ VIX 18.2 │ HIGH_VOL │ $62.4 │ │
│ └──────────────────────────────┘ │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ 💰 Net Liq Value      73%🟢 │ │
│ │ $25,342.18                   │ │
│ │ Today: +$142.50              │ │
│ └──────────────────────────────┘ │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ 🏆 Your Progress  Leader >  │ │
│ │ [🔥0 Streak][🎯0% Win][🏅-] │ │
│ │ Total Profit         $0.00  │ │
│ └──────────────────────────────┘ │
│                                  │
│ ☑ Auto-Approve Trades           │
│   Signals execute on Tastytrade  │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ Trade Signals      1 pending│ │
│ │ ┌────────────────────────┐   │ │
│ │ │🐻 BEAR CALL SPREAD     │   │ │
│ │ │TQQQ Mar 7  HIGH_VOL    │   │ │
│ │ │Sell $72C / Buy $77C    │   │ │
│ │ │Credit: $0.85  Risk:$4.15│  │ │
│ │ │Confidence: 82%  VIX ↑  │   │ │
│ │ │                        │   │ │
│ │ │[Approve & Execute][Track Only]│ │
│ │ └────────────────────────┘   │ │
│ │                              │ │
│ │ No Tastytrade? Use Track Only│ │
│ └──────────────────────────────┘ │
└──────────────────────────────────┘
```

**Navigation bar:**
- **Moved from bottom → top** (matches existing app icons: Live, Home, Signals, Positions, Activity, Settings)
- Each tab opens a full-screen detail page with back arrow (existing pattern)
- Purple highlight on active tab

**Signal flow on home screen:**
- **Auto-Approve checkbox** above signals section — when ON, new signals execute immediately on Tastytrade
- **Each pending signal** shows: spread type, strikes, credit, max loss, confidence, VIX context
- **Two action buttons per signal:**
  - **"Approve & Execute"** (purple gradient) — sends order to Tastytrade, converts signal → position
  - **"Track Only"** (gray outlined) — marks position for P&L tracking WITHOUT executing on Tastytrade
- When auto-approve is ON → signals skip the buttons and auto-execute (shows brief toast confirmation)
- When signal is executed/tracked → it disappears from signals, appears in Positions

**Non-Tastytrade user support:**
- Users who haven't linked Tastytrade see only the **"Track Only"** button
- "Approve & Execute" is disabled/hidden without broker connection
- Track-Only positions still show live P&L (calculated from market data), just no actual order placed
- This lets users follow signals and measure performance before committing to broker link

**Remove:**
- ❌ Bottom navigation bar (moved to top)
- ❌ Deep Value Overlay link (DVO)
- ❌ Gamification card → replaced with "Your Progress" (kept, same data)

**Keep:**
- ✅ Header (welcome, username, refresh/bell)
- ✅ Balance card (Net Liq, P&L, win rate)
- ✅ Your Progress (streak, win rate, rank, total profit)
- ✅ Circuit breaker banner → rewired to `/api/tqqq/status`

### 6.2 NEW `src/components/dashboard/SignalCard.tsx`

Reusable signal card component:
```typescript
interface SignalCardProps {
    signal: TQQQSignal;
    tastyLinked: boolean;
    autoApprove: boolean;
    onApproveExecute: (signalId: string) => void;
    onTrackOnly: (signalId: string) => void;
}
```
- Shows spread type badge (PUT CREDIT / BEAR CALL), strikes, credit, max loss
- Confidence meter, VIX direction indicator
- **"Approve & Execute"** button (hidden if `!tastyLinked`)
- **"Track Only"** button (always visible)
- When `autoApprove && tastyLinked` → card auto-submits on render, shows toast

### 6.3 NEW `src/components/dashboard/InvestmentPrincipal.tsx` ✅ (already done)

Editable principal input (shown on Settings page):
- `$` prefix, comma formatting, min $1,000
- Save to localStorage via `SettingsProvider`

### 6.4 MODIFY `src/components/diagonal/CircuitBreakerBanner.tsx`

- Default `apiEndpoint` → `/api/tqqq/status`
- TQQQ fields: `tqqq_price`, `regime`, `vix_direction`
- Compact mode for home screen (single row)

---

## Phase 7: Settings — Pending 🔲

### 7.1 MODIFY `src/components/providers/SettingsProvider.tsx` ✅ (already done)

Added to settings context:
```typescript
investmentPrincipal: number;   // e.g. 25000
riskLevel: 'LOW' | 'MEDIUM' | 'HIGH';
autoApproval: boolean;
```

### 7.2 MODIFY `src/app/settings/page.tsx`

Full-screen settings page (follows existing back-arrow pattern):

```
┌──────────────────────────────────┐
│ ← Settings                ⚙     │
│   Configure your strategy        │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ 💰 Investment Principal      │ │
│ │ $ [  25,000  ]   [Set]      │ │
│ │ Max risk/trade: $2,500       │ │
│ └──────────────────────────────┘ │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ Risk Level                   │ │
│ │ [🛡️Low] [⚖️Med] [🔥High]   │ │
│ │ +52%    +98%★   +135%       │ │
│ └──────────────────────────────┘ │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ Auto-Approval   [━━━━━ ON]  │ │
│ │ Trades execute immediately   │ │
│ └──────────────────────────────┘ │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ Strategy: TQQQ Dual-Sided   │ │
│ │ Backtest: +98.3% | Sharpe 6 │ │
│ └──────────────────────────────┘ │
│                                  │
│ [Tastytrade Credentials]         │
│ ● Live                           │
└──────────────────────────────────┘
```

1. **Investment Principal** — editable input with Set button
2. **Risk Level** — 3 tappable cards side by side:
   - **Low 🛡️** — Put spreads only, 5% risk
   - **Medium ⚖️** — Put + Call (Scenario B), 7.5% risk ★ default
   - **High 🔥** — Full dual-sided, 10% risk
3. **Auto-Approval** — simple toggle switch (ON/OFF)
4. **Strategy Summary** — TQQQ Dual-Sided with backtest stats
5. **Tastytrade Credentials** — keep existing component

### 7.3 SIMPLIFY `src/components/gamification/AutoApproveSettings.tsx`

Strip Theta/Diagonal/Zebra/DVO (706 lines → ~80 lines). Single TQQQ card with risk level + auto-approval toggle.

### 7.4 MODIFY `src/app/page.tsx` (Landing Page)

- Tagline: "TQQQ Dual-Sided Options Strategy"
- Features: "98% Backtest Return", "VIX-Adaptive", "Auto-Managed"

---

## API Endpoint

### NEW `api/routes/tqqq.py` (backend)

- `GET /api/tqqq/status` — position state, regime, P&L, circuit breaker
- `GET /api/tqqq/history` — trade history
- `POST /api/settings/principal` — save investment amount

---

## Implementation Order

| Step | Files | Effort |
|:--|:--|:--|
| **Phase 4.1** | `order_manager.py` | Small |
| **Phase 4.2** | `signal_publisher/tqqq.py` | Small |
| **Phase 4.3** | `run_tqqq_scheduler.py` | Medium |
| **Phase 5.1** | `position_tracker.py` | Small |
| **Phase 5.2** | `data_pipeline.py` | Small |
| **Phase 5.3** | `tqqq_risk_manager.py` | Small |
| **Phase 6.1** | `dashboard/page.tsx` — home screen | Medium |
| **Phase 6.2** | `SignalCard.tsx` — signal + approve/track buttons | Medium |
| **Phase 6.3** | `InvestmentPrincipal.tsx` | ✅ Done |
| **Phase 6.4** | `CircuitBreakerBanner.tsx` | Small |
| **Phase 7.1** | `SettingsProvider.tsx` | ✅ Done |
| **Phase 7.2** | `settings/page.tsx` | Medium |
| **Phase 7.3** | `AutoApproveSettings.tsx` | Medium |
| **Phase 7.4** | `page.tsx` (landing) | Small |
| **API** | `api/routes/tqqq.py` | Small |
