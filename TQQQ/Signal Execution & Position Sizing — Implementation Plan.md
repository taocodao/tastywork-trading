# TQQQ Signal Execution & Position Sizing — Implementation Plan
### Full End-to-End: User Settings → Signal Sizing → Tastytrade Order Placement

> **Date:** February 23, 2026
> **Status:** PLANNING — Perplexity research complete, ready for implementation
> **Estimated Time:** 4–6 hours
> **Priority:** CRITICAL — Required before strategy generates first live signal
> **SDK Version:** `tastytrade` v10.3.0 (unofficial, `tastyware/tastytrade`)

---

## Current State (What Exists)

### ✅ Frontend (trademind-app)
| Component | File | Status |
|:--|:--|:--|
| Investment Principal input | `InvestmentPrincipal.tsx` | ✅ Saves to localStorage via SettingsProvider |
| Risk Level selector (LOW/MEDIUM/HIGH) | `SettingsProvider.tsx` | ✅ Stored in localStorage |
| Auto-Approval toggle | Dashboard `page.tsx` | ✅ Stored in localStorage |
| Signal Card with Approve & Execute button | `SignalCard.tsx` | ✅ Sends `POST /api/tqqq/signals/execute` |
| Signal Card with Track Only button | `SignalCard.tsx` | ✅ Sends `POST /api/tqqq/signals/track` |
| Tastytrade OAuth link | `TastytradeLink.tsx` | ✅ Stores tokens in Redis |
| Tastytrade link status check | `/api/tastytrade/status` | ✅ Reads from Redis |

### ❌ What's Broken / Missing
| Gap | Detail |
|:--|:--|
| **Frontend doesn't pass OAuth tokens** | `handleApproveExecute` sends `{ signalId }` but the Python backend needs `{ signalId, refreshToken, accountNumber }` |
| **TQQQ execute handler doesn't place orders** | `_handle_tqqq_execute` delegates to `handle_approve_signal` which reads from PostgreSQL `SignalRepository` — TQQQ signals live in `tqqq_signals.json` |
| **No position sizing from principal/risk** | Signal card shows raw credit/maxLoss but never calculates how many contracts based on user's principal × risk% |
| **Settings not sent to backend** | Investment principal and risk level stay in localStorage — the backend never receives them |
| **TQQQOrderManager uses IB, not Tastytrade** | Currently wired for Interactive Brokers (`ib_insync`), but our users trade via Tastytrade OAuth |
| **Auto-approval not wired** | Backend doesn't check if user wants auto-approval |

---

## Architecture: How It Should Work (End-to-End)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (Next.js)                            │
│                                                                         │
│  SettingsProvider (localStorage)                                        │
│  ├── investmentPrincipal: 25000                                        │
│  ├── riskLevel: "MEDIUM" (LOW=5%, MEDIUM=7.5%, HIGH=10%)               │
│  └── autoApproval: false                                                │
│                                                                         │
│  SignalCard receives signal from GET /api/tqqq/signals:                 │
│  {                                                                      │
│    id, type: "PUT_CREDIT", strikes, credit: 0.85, maxLoss: 4.15,       │
│    suggestedQuantity: 4,  ← NEW (calculated by backend)                │
│    totalCredit: 340,      ← NEW                                        │
│    totalMaxLoss: 1660,    ← NEW                                        │
│  }                                                                      │
│                                                                         │
│  User clicks "Approve & Execute" →                                      │
│                                                                         │
│  POST /api/tqqq/signals/execute {                                       │
│    signalId: "abc-123",                                                 │
│    quantity: 4,            ← from suggestedQuantity (user can override) │
│  }                                                                      │
│                                                                         │
│  Next.js API route:                                                     │
│    1. Read user OAuth tokens from Redis (using Privy userId)            │
│    2. Forward to Python: { signalId, quantity, refreshToken,            │
│       accountNumber, userId }                                           │
└──────────────────────────────────────┬──────────────────────────────────┘
                                       │ HTTPS → EC2:8002
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       BACKEND (Python API Server)                       │
│                                                                         │
│  POST /api/tqqq/signals/execute                                         │
│    1. Read signal from tqqq_signals.json                                │
│    2. Create Tastytrade session from user's refreshToken                │
│    3. Get user's account                                                │
│    4. Build NewOrder with 2 legs:                                       │
│       Leg 1: SELL_TO_OPEN  → short put/call                            │
│       Leg 2: BUY_TO_OPEN   → long put/call (protection)                │
│    5. Place order via Tastytrade SDK                                    │
│    6. Update signal status in tqqq_signals.json                         │
│    7. Return order confirmation                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Position Sizing Engine (Backend)
**File:** `d:\Projects\tastywork-trading-1\src\tqqq\position_sizer.py` (NEW)

Creates a pure function that takes user settings and a signal, returns the optimal contract quantity.

```python
class TQQQPositionSizer:
    """
    Calculates how many contracts to trade based on:
      - User's investment principal ($25,000)
      - Risk level (LOW=5%, MEDIUM=7.5%, HIGH=10%)
      - Signal's max loss per contract
      - Max concurrent position cap (3 for LOW, 5 for MEDIUM, 7 for HIGH)
    """

    RISK_PCT = {"LOW": 0.05, "MEDIUM": 0.075, "HIGH": 0.10}
    MAX_POSITIONS = {"LOW": 3, "MEDIUM": 5, "HIGH": 7}

    @staticmethod
    def calculate(
        principal: float,
        risk_level: str,       # "LOW" | "MEDIUM" | "HIGH"
        credit: float,         # Per-contract credit received (e.g. $0.85)
        spread_width: float,   # Spread width in dollars (e.g. $5.00)
        active_positions: int, # How many TQQQ positions already open
    ) -> dict:
        risk_pct = TQQQPositionSizer.RISK_PCT.get(risk_level, 0.075)
        max_positions = TQQQPositionSizer.MAX_POSITIONS.get(risk_level, 5)

        max_risk_per_trade = principal * risk_pct
        max_loss_per_contract = (spread_width - credit) * 100  # e.g. ($5 - $0.85) × 100 = $415

        # Position cap: don't exceed max concurrent positions
        if active_positions >= max_positions:
            return {"quantity": 0, "reason": "max_positions_reached"}

        # Floor division: how many contracts stay within risk budget
        quantity = max(1, int(max_risk_per_trade / max_loss_per_contract))

        # Cap at 10 contracts regardless (avoid liquidity issues)
        quantity = min(quantity, 10)

        return {
            "quantity": quantity,
            "maxRiskPerTrade": round(max_risk_per_trade, 2),
            "maxLossPerContract": round(max_loss_per_contract, 2),
            "totalCredit": round(credit * quantity * 100, 2),
            "totalMaxLoss": round(max_loss_per_contract * quantity, 2),
            "riskPct": risk_pct,
        }
```

**Tests:**
- $25K principal + MEDIUM (7.5%) + $5 width + $0.85 credit → max_risk = $1,875, max_loss/contract = $415, quantity = 4
- $5K principal + LOW (5%) + $5 width + $0.85 credit → max_risk = $250, quantity = 1 (floor)
- $50K principal + HIGH (10%) + $3 width + $0.65 credit → max_risk = $5,000, max_loss/contract = $235, quantity = 10 (capped)

---

### Phase 2: Scheduler Emits Sized Signals
**File:** `d:\Projects\tastywork-trading-1\run_tqqq_scheduler.py` (MODIFY)

When `_scan_for_entry()` generates a signal via `publish_tqqq_entry_signal()`, it should also persist sizing metadata. Since the scheduler doesn't know each user's principal, it stores the **per-contract** values. The frontend/API will calculate quantity per-user.

**Changes:**
```python
# In _scan_for_entry(), after signal creation:
signal_dict = signal_msg.to_dict()
signal_dict.update({
    "spread_width": best.short_leg.strike - best.long_leg.strike,
    "type": "PUT_CREDIT",  # or "BEAR_CALL"
    "expiry_display": best.short_leg.expiration.strftime("%b %d"),
    "strikes_display": f"Sell ${best.short_leg.strike}P / Buy ${best.long_leg.strike}P",
})
self._persist_signal(signal_dict)
```

---

### Phase 3: User Settings API (New endpoint)
**File:** `d:\Projects\trademind-app\src\app\api\tqqq\settings\route.ts` (NEW)

Stores user's TQQQ-specific settings (principal, risk level) so the `/api/tqqq/signals` endpoint can calculate per-user quantity.

```typescript
// GET  /api/tqqq/settings  → returns user's saved settings
// POST /api/tqqq/settings  → saves { principal, riskLevel }

// Storage: Redis key `tqqq_settings:{userId}`
// {
//   principal: 25000,
//   riskLevel: "MEDIUM",
//   autoApproval: false,
// }
```

**Alternative (simpler):** Do sizing calculation entirely client-side:
- Frontend reads `investmentPrincipal` and `riskLevel` from localStorage
- Frontend reads `credit` and `spread_width` from signal
- Frontend calculates `quantity = floor(principal × risk% / maxLossPerContract)`
- Frontend passes calculated `quantity` in the execute request

**Recommendation:** Do it client-side for now (simpler, no backend changes needed). Phase 2+ can move to server-side if we want the backend to enforce position limits.

---

### Phase 4: Fix Signal Execute API Route (Frontend → Backend)
**File:** `d:\Projects\trademind-app\src\app\api\tqqq\signals\[action]\route.ts` (MODIFY)

The Next.js route needs to:
1. Read user's Tastytrade OAuth tokens from Redis
2. Include them in the request to the Python backend

```typescript
// Current: forwards { signalId } only
// Fixed:  forwards { signalId, quantity, refreshToken, accountNumber, userId }

export async function POST(request: NextRequest) {
    const body = await request.json();
    const { signalId, quantity } = body;

    const userId = await getPrivyUserId();

    // READ OAuth tokens from Redis
    const tokens = await getTastytradeTokens(userId);
    if (!tokens?.accessToken) {
        return NextResponse.json({ error: 'Tastytrade not linked' }, { status: 401 });
    }

    // Forward to Python with full credentials
    const res = await fetch(`${PYTHON_API}/api/tqqq/signals/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            signalId,
            quantity: quantity || 1,
            refreshToken: tokens.refreshToken,
            accountNumber: tokens.accountNumber,
            userId,
        }),
    });
    // ... handle response
}
```

---

### Phase 5: Tastytrade Order Placement (Backend) — CONFIRMED via Perplexity
**File:** `d:\Projects\tastywork-trading-1\src\tqqq\tastytrade_executor.py` (NEW)

Currently `order_manager.py` uses Interactive Brokers (`ib_insync`). We need a separate Tastytrade executor using the `tastytrade` Python SDK (v10.3.0).

**Key SDK findings from Perplexity:**
- Use `OAuthSession(provider_secret, refresh_token)` — NOT `Session.from_refresh_token()`
- Use `NewOrder` with 2 `Leg` objects — NOT `NewComplexOrder`
- Price: `Decimal('0.50')` = positive for credits, negative for debits
- OCC format: `TQQQ  260307P00072000` (6-char padded root symbol)
- Access token expires every 15 min — call `session.refresh()` as needed

```python
"""
TastytradeExecutor
==================
Places vertical spread orders via the Tastytrade Python SDK (v10.3.0).
Uses OAuthSession with user's refresh_token + app's client_secret.
"""

import os
import logging
from decimal import Decimal
from datetime import date
from typing import Optional

from tastytrade import OAuthSession, Account
from tastytrade.instruments import Option, get_option_chain
from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType

logger = logging.getLogger(__name__)

class TastytradeExecutor:
    """Places vertical spread orders on Tastytrade using user's OAuth session."""

    @staticmethod
    def create_session(refresh_token: str) -> OAuthSession:
        """
        Create a Tastytrade OAuth session from a user's refresh token.
        Requires TASTYTRADE_CLIENT_SECRET env var.
        """
        client_secret = os.environ.get('TASTYTRADE_CLIENT_SECRET', '')
        if not client_secret:
            raise ValueError('TASTYTRADE_CLIENT_SECRET not set')
        session = OAuthSession(client_secret, refresh_token)
        logger.info('Tastytrade OAuth session created successfully')
        return session

    @staticmethod
    def get_account(session: OAuthSession, account_number: str) -> Account:
        """Get a specific account by number."""
        accounts = Account.get(session)
        for a in accounts:
            if a.account_number == account_number:
                return a
        raise ValueError(f'Account {account_number} not found')

    @staticmethod
    def build_occ_symbol(
        root: str,           # "TQQQ"
        expiration: str,     # "2026-03-07" or date object
        option_type: str,    # "P" or "C"
        strike: float,       # 72.0
    ) -> str:
        """
        Builds OCC symbol: TQQQ  260307P00072000
        Root = 6 chars space-padded, exp = yymmdd, strike = 8 digits (price × 1000)
        """
        root_padded = root.ljust(6)
        if isinstance(expiration, str):
            # "2026-03-07" → "260307"
            parts = expiration.split('-')
            exp_str = parts[0][2:] + parts[1] + parts[2]
        else:
            exp_str = expiration.strftime('%y%m%d')
        strike_int = int(strike * 1000)
        strike_str = f'{strike_int:08d}'
        return f'{root_padded}{exp_str}{option_type}{strike_str}'

    @staticmethod
    def place_vertical_spread(
        session: OAuthSession,
        account: Account,
        symbol: str,              # "TQQQ"
        short_strike: float,      # e.g. 72.0
        long_strike: float,       # e.g. 67.0
        expiration: str,          # "2026-03-07"
        spread_type: str,         # "PUT" or "CALL"
        credit: float,            # net credit per contract (e.g. 0.85)
        quantity: int,            # number of contracts
        dry_run: bool = False,    # True for paper test
    ) -> dict:
        """
        Places a vertical credit spread:
          PUT CREDIT:  SELL higher put, BUY lower put
          CALL CREDIT: SELL lower call, BUY higher call

        Returns order confirmation dict.
        """
        opt_type = spread_type[0]  # "P" or "C"

        # Build OCC symbols
        short_occ = TastytradeExecutor.build_occ_symbol(symbol, expiration, opt_type, short_strike)
        long_occ  = TastytradeExecutor.build_occ_symbol(symbol, expiration, opt_type, long_strike)

        logger.info(f'Looking up options: {short_occ} / {long_occ}')

        # Fetch Option objects from Tastytrade
        short_option = Option.get(session, short_occ)
        long_option  = Option.get(session, long_occ)

        # Build legs with Decimal quantity
        qty = Decimal(str(quantity))
        short_leg = short_option.build_leg(qty, OrderAction.SELL_TO_OPEN)
        long_leg  = long_option.build_leg(qty, OrderAction.BUY_TO_OPEN)

        # Build order — positive Decimal = net credit
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[short_leg, long_leg],
            price=Decimal(str(round(credit, 2))),  # positive = credit received
        )

        logger.info(f'Placing order: {spread_type} spread '
                    f'{short_strike}/{long_strike} x{quantity} @ ${credit:.2f} credit'
                    f'{" (DRY RUN)" if dry_run else ""}')

        # Place order
        response = account.place_order(session, order, dry_run=dry_run)

        order_id = None
        if hasattr(response, 'order') and hasattr(response.order, 'id'):
            order_id = str(response.order.id)
        elif hasattr(response, 'id'):
            order_id = str(response.id)

        return {
            'orderId': order_id,
            'status': 'submitted' if not dry_run else 'dry_run',
            'legs': [
                {'action': 'SELL_TO_OPEN', 'strike': short_strike, 'type': spread_type, 'occ': short_occ},
                {'action': 'BUY_TO_OPEN',  'strike': long_strike,  'type': spread_type, 'occ': long_occ},
            ],
            'credit': credit,
            'quantity': quantity,
            'dryRun': dry_run,
        }
```

**Dependencies (all resolved):**
- `tastytrade` v10.3.0 Python SDK — install via `pip install tastytrade`
- `TASTYTRADE_CLIENT_SECRET` env var on EC2 (already set)
- User's `refreshToken` from Redis (never expires)
- Uses `OAuthSession(provider_secret, refresh_token)` — no `client_id` needed

**Important SDK conventions (confirmed by Perplexity):**
- `OAuthSession` — NOT `Session.from_refresh_token()`; requires `provider_secret` + `refresh_token`
- Access token auto-refreshes on init, expires every 15 min
- `Option.get(session, occ_symbol)` → returns `Option` object
- `option.build_leg(Decimal(qty), OrderAction)` → returns `Leg`
- `NewOrder(legs=[...], price=Decimal('0.50'))` → positive = credit
- `account.place_order(session, order, dry_run=True)` → test without trading
- OAuth sessions **cannot** create DXLink streamers (not needed for orders)

---

### Phase 6: Fix Backend Execute Handler
**File:** `d:\Projects\tastywork-trading-1\tasty_api_server.py` (MODIFY `_handle_tqqq_execute`)

Replace the current handler (which delegates to the broken `handle_approve_signal`) with one that:
1. Reads the signal from `tqqq_signals.json`
2. Uses `TastytradeExecutor` to place the vertical spread
3. Updates signal status

```python
def _handle_tqqq_execute(self, data: dict):
    """POST /api/tqqq/signals/execute"""
    signal_id = data.get('signalId')
    refresh_token = data.get('refreshToken')
    account_number = data.get('accountNumber')
    quantity = data.get('quantity', 1)
    user_id = data.get('userId', 'anonymous')

    if not signal_id:
        return self._send_json({'error': 'signalId required'}, 400)
    if not refresh_token:
        return self._send_json({'error': 'refreshToken required'}, 401)

    # 1. Read signal from tqqq_signals.json
    signal = self._tqqq_get_signal(signal_id)
    if not signal:
        return self._send_json({'error': 'Signal not found'}, 404)

    # 2. Create user session and place order
    from src.tqqq.tastytrade_executor import TastytradeExecutor

    try:
        session = TastytradeExecutor.create_session(refresh_token)
        account = TastytradeExecutor.get_account(session, account_number)

        result = TastytradeExecutor.place_vertical_spread(
            session=session,
            account=account,
            symbol="TQQQ",
            short_strike=signal['short_strike'],
            long_strike=signal['long_strike'],
            expiration=signal['expiration'],
            spread_type="PUT" if signal.get('type') == "PUT_CREDIT" else "CALL",
            credit=signal['credit'],
            quantity=quantity,
        )

        # 3. Update signal status
        self._tqqq_update_signal_status(signal_id, 'executed')

        self._send_json({
            'status': 'executed',
            'order': result,
            'signalId': signal_id,
        })

    except Exception as e:
        self._send_json({'error': str(e)}, 500)
```

---

### Phase 7: Frontend Signal Card Sizing
**File:** `d:\Projects\trademind-app\src\components\dashboard\SignalCard.tsx` (MODIFY)
**File:** `d:\Projects\trademind-app\src\app\dashboard\page.tsx` (MODIFY)

**SignalCard changes:**
- Show calculated quantity based on user's principal/risk settings
- Show total credit and total max loss (not just per-contract)
- Show risk utilization percentage

```tsx
// In dashboard page.tsx → handleApproveExecute:
const handleApproveExecute = async (id: string, quantity: number) => {
    setExecutingId(id);
    const res = await fetch('/api/tqqq/signals/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signalId: id, quantity }),
    });
    // ...
};

// SignalCard receives:
interface SignalCardProps {
    signal: TQQQSignal;
    suggestedQuantity: number;   // ← NEW: calculated from settings
    totalCredit: number;         // ← NEW: credit × quantity × 100
    totalMaxLoss: number;        // ← NEW: maxLoss × quantity × 100
}
```

**Quantity calculation (client-side, in page.tsx):**
```typescript
const riskPct = settings.riskLevel === 'LOW' ? 0.05
              : settings.riskLevel === 'HIGH' ? 0.10
              : 0.075;
const maxRisk = settings.investmentPrincipal * riskPct;
const maxLossPerContract = (signal.maxLoss) * 100;  // maxLoss is the spread width minus credit
const quantity = Math.max(1, Math.floor(maxRisk / maxLossPerContract));
```

---

### Phase 8: Auto-Approval Flow
**File:** `d:\Projects\trademind-app\src\app\dashboard\page.tsx` (MODIFY)

When `autoApproval` is enabled and a new signal arrives via the 15-second poll:

```typescript
const fetchSignals = useCallback(async () => {
    const res = await fetch('/api/tqqq/signals');
    if (!res.ok) return;
    const newSignals: TQQQSignal[] = await res.json();

    // Auto-approve if enabled
    if (settings.autoApproval && tastyLinked) {
        for (const sig of newSignals) {
            const alreadyExecuted = signals.find(s => s.id === sig.id);
            if (!alreadyExecuted) {
                // Calculate quantity from settings
                const quantity = calculateQuantity(sig, settings);
                handleApproveExecute(sig.id, quantity);
            }
        }
    }

    setSignals(newSignals);
}, [settings, tastyLinked, signals]);
```

**Safety guards for auto-approval:**
- Only auto-execute signals with confidence ≥ 70%
- Only if Tastytrade is linked
- Max 1 auto-execution per signal (deduplicate by ID)
- Show a toast notification when auto-executing: "Auto-executing PUT CREDIT 4x $72P/$67P…"

---

## File Change Summary

| File | Action | Description |
|:--|:--|:--|
| `src/tqqq/position_sizer.py` | **NEW** | Position sizing engine (principal × risk% → quantity) |
| `src/tqqq/tastytrade_executor.py` | **NEW** | Tastytrade SDK order placement for vertical spreads |
| `tasty_api_server.py` | **MODIFY** | Replace `_handle_tqqq_execute` with Tastytrade executor, add `_tqqq_get_signal` helper |
| `run_tqqq_scheduler.py` | **MODIFY** | Add `spread_width`, `type`, display fields to persisted signals |
| `trademind-app/.../[action]/route.ts` | **MODIFY** | Read OAuth tokens from Redis, pass to Python backend |
| `trademind-app/.../SignalCard.tsx` | **MODIFY** | Show quantity, total credit, total max loss |
| `trademind-app/.../page.tsx` | **MODIFY** | Calculate quantity from settings, pass to execute, implement auto-approval |

---

## Dependencies — ALL RESOLVED ✅

| Dependency | Answer | Status |
|:--|:--|:--|
| `tastytrade` Python SDK on EC2 | `pip install tastytrade` (v10.3.0) | ⚠️ Check with `pip show tastytrade` |
| Session creation from refresh token | `OAuthSession(provider_secret, refresh_token)` | ✅ Confirmed |
| OCC symbol format | `TQQQ  260307P00072000` (6-char root, yymmdd, P/C, 8-digit strike×1000) | ✅ Confirmed |
| Order class for vertical spread | `NewOrder` with 2 `Leg` objects (NOT `NewComplexOrder`) | ✅ Confirmed |
| Price convention | `Decimal('0.50')` positive = credit; negative = debit | ✅ Confirmed |
| Redis credentials on Vercel | `UPSTASH_REDIS_REST_*` env vars | ✅ Already used |
| Tastytrade OAuth scopes | `['read', 'trade', 'openid']` | ✅ Already includes `trade` |
| `TASTYTRADE_CLIENT_SECRET` on EC2 | Required for `OAuthSession` | ⚠️ Verify in `.env` |

---

## Implementation Order (Recommended)

```
Day 1 (2–3 hours):
  1. Create position_sizer.py + unit tests
  2. Create tastytrade_executor.py (use SDK docs)
  3. Fix _handle_tqqq_execute in tasty_api_server.py
  4. Fix [action]/route.ts to pass OAuth tokens

Day 2 (1–2 hours):
  5. Update SignalCard.tsx with quantity display
  6. Add quantity calculation to page.tsx
  7. Implement auto-approval flow
  8. Add spread_width/type to scheduler signal persistence
  
Day 2 (30 min):
  9. Push both repos
  10. SSH to EC2: pip install tastytrade, restart services
  11. E2E test: create a test signal, verify button → Tastytrade order
```

---

## Risk Mitigation

| Risk | Mitigation |
|:--|:--|
| Tastytrade SDK API changes | Pin SDK version in requirements.txt |
| OAuth token expired when user clicks Execute | Next.js route refreshes token first (already in `/api/tastytrade/account/route.ts` pattern) |
| Order rejected by Tastytrade | Return clear error message with Tastytrade rejection reason |
| User doesn't have enough buying power | Check `Account.buying_power` before placing order |
| Duplicate order placement | Deduplicate by signal ID — mark as "executed" immediately before placing order |
| Rate limiting | Tastytrade API has no documented rate limits for order placement, but add 500ms delay between orders |
