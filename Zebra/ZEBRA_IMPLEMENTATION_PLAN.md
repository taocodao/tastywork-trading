# ZEBRA Strategy — Comprehensive Integration Plan

> **Generated:** 2026-02-14  
> **Scope:** Full integration of the ZEBRA (Zero Extrinsic Back Ratio) strategy into the existing TradeMind trading platform  
> **Repositories:** `tastywork-trading-1` (Python backend / EC2) + `trademind-app` (Next.js frontend / Vercel)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Existing System Inventory](#2-existing-system-inventory)
3. [ZEBRA Strategy Recap](#3-zebra-strategy-recap)
4. [Architecture & Integration Map](#4-architecture--integration-map)
5. [Phase 1 — Core ZEBRA Engine & Execution (Weeks 1–4)](#5-phase-1--core-zebra-engine--execution)
6. [Phase 2 — ML Signal Engine & Anti-Crowding (Weeks 5–10)](#6-phase-2--ml-signal-engine--anti-crowding)
7. [Phase 3 — Portfolio Risk & Analytics (Weeks 11–14)](#7-phase-3--portfolio-risk--analytics)
8. [Phase 4 — ZEEHBS Hedge & Optimization (Weeks 15+)](#8-phase-4--zeehbs-hedge--optimization)
9. [Database Schema](#9-database-schema)
10. [API Contracts](#10-api-contracts)
11. [Daily Automation Schedule](#11-daily-automation-schedule)
12. [Testing Strategy](#12-testing-strategy)
13. [Deployment Plan](#13-deployment-plan)
14. [Risk & Open Questions](#14-risk--open-questions)

---

## 1. Executive Summary

The ZEBRA strategy replicates synthetic long stock exposure using a 3-leg options structure (Buy 2 ITM Calls + Sell 1 ATM Call) at ~50% of the capital cost with defined risk. This plan integrates ZEBRA as a **third strategy module** alongside the existing Theta (cash-secured puts) and Diagonal/Calendar spread strategies.

### Goals
- **AI-driven stock selection** using ensemble ML (Random Forest + XGBoost + LSTM)
- **Automated ZEBRA construction** with optimal strike/expiry selection and zero-extrinsic targeting
- **Full lifecycle management** (entry → monitoring → re-center/exit) on 15-min intervals
- **Anti-crowding intelligence** to avoid crowded trades and preserve alpha
- **Execution via Tastytrade** using complex multi-leg orders
- **Portfolio-level risk controls** including VIX regime rules, sector limits, and correlation filters
- **Seamless UI integration** into the existing TradeMind dashboard

---

## 2. Existing System Inventory

### 2.1 Python Backend (`tastywork-trading-1`)

| Component | File(s) | Purpose | Reuse for ZEBRA |
|---|---|---|---|
| **Signal Publisher** | `signal_publisher/{base,theta,calendar}.py` | Publishes signals to WebSocket + DB | ✅ Add `zebra.py` following same pattern |
| **WebSocket Server** | `websocket_server.py` | Broadcasts signals to frontend | ✅ Add `zebra_entry` / `zebra_exit` channels |
| **Theta Monitor** | `theta_monitor_continuous.py` | Continuous scan + position check loop | ✅ Clone pattern for `zebra_monitor_continuous.py` |
| **Scanner** | `scanner.py` | ATM strike finder + liquidity checks | 🔀 Extract shared utils; ZEBRA needs different logic |
| **Tastytrade Client** | `tastytrade_client.py` | Full API wrapper (auth, chains, orders) | ✅ Add `build_zebra_order()`, `close_zebra_order()` |
| **Config** | `config.py` | Strategy parameters + universe | ✅ Add ZEBRA-specific config section |
| **Risk Manager** | `risk_manager.py` | Position limits + risk checks | ✅ Extend with ZEBRA portfolio rules |
| **Theta Strategies** | `src/theta_spreads/` | Signal generation, options analysis, portfolio mgmt | 🔀 Reuse `options_analyzer.py`, `market_filters.py` patterns |
| **Greeks Calculator** | `greeks_calculator.py` | Spread Greeks computation | ✅ Extend for 3-leg ZEBRA Greeks |
| **Position Monitor** | `position_monitor.py` | Live position tracking | ✅ Extend for ZEBRA position states |
| **Auto-Approve** | `auto_approve.py` | Server-side auto-execution | ✅ Add ZEBRA approval path |

### 2.2 Next.js Frontend (`trademind-app`)

| Component | File(s) | Purpose | Reuse for ZEBRA |
|---|---|---|---|
| **Strategy Executor** | `src/lib/strategy-executor.ts` | Dispatches execution by strategy type | ✅ Add `executeZebraStrategy` + register in map |
| **Tastytrade API** | `src/lib/tastytrade-api.ts` | REST API client for orders/balances | ✅ Add `executeZebra()` function |
| **Signal Provider** | `src/components/providers/SignalProvider.tsx` | Global signal state + auto-approve | ✅ Add `zebra` channel subscription + auto-approve |
| **Signal Socket** | `src/hooks/useSignalSocket.ts` | WebSocket client | ✅ Add `zebra_entry` channel |
| **Dashboard** | `src/app/dashboard/page.tsx` | Main UI | ✅ Add ZEBRA signal cards + metrics |
| **Signals Page** | `src/app/signals/page.tsx` | Signal listing + approval | ✅ Add ZEBRA signal type rendering |
| **Settings** | `src/app/api/settings/auto-approve/route.ts` | Auto-approve config | ✅ Add `zebra` strategy settings |
| **Activity Log** | `src/components/dashboard/ActivityLog.tsx` | Trade execution history | ✅ Works automatically (source tracking) |
| **DB layer** | `src/lib/db.ts` | PostgreSQL queries | ✅ Add ZEBRA position/signal tables |

---

## 3. ZEBRA Strategy Recap

### 3.1 Structure
```
LONG Bullish ZEBRA = Buy 2 ITM Calls (δ ≈ 0.70) + Sell 1 ATM Call (δ ≈ 0.50)
───────────────────────────────────────────────────────────────────────────────
Net Delta ≈ 2(0.70) - 1(0.50) = 0.90 → ~100 shares equivalent
Net Extrinsic ≈ 2(ITM extrinsic) - 1(ATM extrinsic) ≈ $0 (zero time decay)
Max Loss = Net Debit Paid
Capital Needed ≈ 40-50% of 100-share cost
```

### 3.2 Key Parameters
| Parameter | Value | Source |
|---|---|---|
| Long Call Delta Range | 0.65 – 0.80 | Construction engine |
| Short Call Delta Range | 0.45 – 0.55 | Construction engine |
| Expiry Rule | 2× thesis horizon | ML engine output |
| Net Extrinsic Target | ≤ $0.10 | Construction scoring |
| Max Slippage | 3% above mid | Execution adapter |
| Profit Target | 50% of max theoretical profit | Lifecycle rules |
| Time Exit | 50% of duration elapsed | Lifecycle rules |
| Stop Loss | -40% of debit | Lifecycle rules |
| Re-center Down | Stock -8%, DC > 60 | Lifecycle rules |
| Re-center Up | Stock +15%, delta compressed | Lifecycle rules |

---

## 4. Architecture & Integration Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EC2 (Python Backend)                         │
│                                                                       │
│  ┌──────────────┐   ┌──────────────────┐   ┌──────────────────────┐ │
│  │ ZEBRA ML      │──▶│ ZEBRA Construction│──▶│ Signal Publisher     │ │
│  │ Signal Engine │   │ Engine           │   │ (zebra.py)           │ │
│  │               │   │                  │   │ → WS + DB            │ │
│  └──────┬───────┘   └────────┬─────────┘   └──────────┬───────────┘ │
│         │                    │                         │             │
│  ┌──────┴───────┐   ┌───────┴──────────┐              │             │
│  │ Universe &    │   │ Anti-Crowding    │              │             │
│  │ Feature Store │   │ Module           │              ▼             │
│  └──────────────┘   └──────────────────┘     ┌────────────────┐    │
│                                                │ WebSocket Srv  │    │
│  ┌──────────────┐   ┌──────────────────┐      │ (channels:     │    │
│  │ Lifecycle     │   │ Portfolio Risk   │      │  zebra_entry   │    │
│  │ Engine        │   │ Engine           │      │  zebra_exit)   │    │
│  │ (15-min loop) │   │ (VIX, sectors,  │      └───────┬────────┘    │
│  └──────┬───────┘   │  correlation)    │              │             │
│         │           └──────────────────┘              │             │
│         ▼                                             │             │
│  ┌──────────────┐                                     │             │
│  │ Tastytrade   │◀── Complex Multi-Leg Orders         │             │
│  │ Client       │                                     │             │
│  └──────────────┘                                     │             │
└───────────────────────────────────────────────────────┼─────────────┘
                                                        │
                        WebSocket Connection            │
                                                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Vercel (Next.js Frontend)                        │
│                                                                       │
│  ┌─────────────────┐  ┌────────────────┐  ┌─────────────────────┐  │
│  │ SignalProvider   │  │ ZEBRA Signal   │  │ Strategy Executor   │  │
│  │ + Auto-Approve   │  │ Card Component │  │ + executeZebra()    │  │
│  └────────┬────────┘  └────────────────┘  └─────────┬───────────┘  │
│           │                                          │              │
│           ▼                                          ▼              │
│  ┌─────────────────┐                      ┌─────────────────────┐  │
│  │ Dashboard        │                      │ Tastytrade API      │  │
│  │ + ZEBRA Metrics  │                      │ (complex orders)    │  │
│  └─────────────────┘                      └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Phase 1 — Core ZEBRA Engine & Execution

**Duration:** Weeks 1–4  
**Goal:** Build, construct, and execute ZEBRAs via Tastytrade with basic lifecycle management.

### 5.1 New Files to Create

#### Backend (`tastywork-trading-1`)

| File | Purpose |
|---|---|
| `src/zebra_spreads/__init__.py` | Package init |
| `src/zebra_spreads/construction_engine.py` | Strike optimization + zero-extrinsic scoring |
| `src/zebra_spreads/lifecycle_engine.py` | Position evaluation + decision tree |
| `src/zebra_spreads/universe.py` | ZEBRA-specific universe filtering |
| `signal_publisher/zebra.py` | Signal dataclass + publishing |
| `zebra_monitor_continuous.py` | 24/7 systemd service (scan + manage) |
| `zebra_monitor.service` | Systemd unit file for EC2 deployment |

#### Frontend (`trademind-app`)

| File | Purpose |
|---|---|
| `src/components/signals/ZebraSignalCard.tsx` | Rich ZEBRA signal display component |
| `src/app/api/signals/zebra/route.ts` | ZEBRA-specific signal API (if needed) |

### 5.2 Signal Publisher (`signal_publisher/zebra.py`)

Follow the exact pattern from `signal_publisher/theta.py`:

```python
# signal_publisher/zebra.py

@dataclass
class ZebraEntrySignal:
    """Signal for opening a ZEBRA position."""
    
    # Identity
    id: str
    symbol: str
    
    # Direction
    direction: str  # "LONG" or "SHORT" (bullish/bearish ZEBRA)
    
    # Structure - 3 legs
    long_strike: float       # ITM call strike (buy 2)
    long_delta: float        # Delta of each long call
    short_strike: float      # ATM call strike (sell 1)
    short_delta: float       # Delta of short call
    expiry: str              # YYYY-MM-DD
    dte: int
    
    # Pricing
    net_debit: float         # Total cost to open
    max_loss: float          # = net_debit
    breakeven: float         # Price where P&L = 0
    
    # Greeks (net position)
    net_delta: float         # Target ≈ 0.90-1.10
    net_theta: float         # Should be ≈ 0
    net_vega: float
    net_extrinsic: float     # Target: as close to $0 as possible
    
    # Scoring
    construction_score: float     # 0-100
    directional_confidence: float # 0-100 (from ML engine)
    capital_efficiency: float     # delta per dollar vs 100 shares
    anti_crowding_score: float    # 0-100
    composite_score: float        # Weighted ranking score
    
    # Individual leg pricing (for order construction)
    long_call_bid: float
    long_call_ask: float
    short_call_bid: float
    short_call_ask: float
    
    # Risk context
    capital_required: float      # = net_debit (for buying power check)
    expected_move_pct: float     # ML predicted 30-day move
    thesis_horizon_days: int     # How long we expect the move to take
    
    # Metadata
    contracts: int = 1           # Number of ZEBRA units (each = 3 legs)
    rationale: str = ""          # AI-generated explanation
    strategy: str = "zebra"
    signal_type: str = "entry"
    action: str = "OPEN"
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
```

**WebSocket channels:** `zebra_entry`, `zebra_exit`, `zebra_all`

### 5.3 Construction Engine (`src/zebra_spreads/construction_engine.py`)

Core algorithm:

```python
class ZebraConstructionEngine:
    """
    Finds optimal ZEBRA structures for a given candidate.
    
    Algorithm:
    1. Determine target expiry window (2× thesis horizon)
    2. Fetch full options chain from Tastytrade
    3. Filter for valid long strikes (δ 0.65-0.80) and short strikes (δ 0.45-0.55)
    4. For each valid combo: compute net extrinsic, Greeks, capital efficiency
    5. Score each combo and return top 3
    """
    
    def __init__(self, tastytrade_client: TastytradeClient):
        self.client = tastytrade_client
    
    def construct(
        self,
        symbol: str,
        stock_price: float,
        thesis_horizon_days: int = 30,
        direction: str = "LONG",
        config: ZebraConfig = None
    ) -> List[ZebraStructure]:
        """
        Returns top 3 ZEBRA structures sorted by construction_score.
        
        Steps:
        1. target_dte = thesis_horizon_days * 2
        2. Find available expiries within ±15 DTE of target
        3. For each expiry:
           a. Get all CALL options with Greeks
           b. Filter long candidates: delta in [0.65, 0.80]
           c. Filter short candidates: delta in [0.45, 0.55]
           d. For each (long, short) pair:
              - net_extrinsic = 2 * long.extrinsic - short.extrinsic
              - net_delta = 2 * long.delta - short.delta
              - net_debit = 2 * long.ask - short.bid  (worst case)
              - breakeven = long_strike + (net_debit / 2)
              - capital_efficiency = net_delta / (net_debit / (stock_price * 100))
              - construction_score = weighted scoring
        4. Sort by construction_score DESC
        5. Return top 3
        """
    
    def _score_structure(self, structure: ZebraStructure) -> float:
        """
        Construction Score = 
            Net-Extrinsic-to-Zero × 0.35 +
            Capital Efficiency × 0.25 +
            Bid-Ask Tightness × 0.25 +
            Open Interest Depth × 0.15
        
        Penalties:
        - Aggregate spread > 2% of debit → slippage_flag = True
        - Net delta outside [0.85, 1.15] → penalize
        """
    
    def _compute_extrinsic(self, option_price: float, stock_price: float, 
                           strike: float, option_type: str = "C") -> float:
        """Extrinsic = Option Price - Intrinsic Value"""
        intrinsic = max(0, stock_price - strike) if option_type == "C" else max(0, strike - stock_price)
        return option_price - intrinsic
```

### 5.4 Tastytrade Order Construction

**Add to `tastytrade_client.py`:**

```python
def build_zebra_order(
    self,
    symbol: str,
    long_strike: float,
    short_strike: float,
    expiry: date,
    direction: str = "LONG",  # LONG = bullish ZEBRA (calls), SHORT = bearish (puts)
    quantity: int = 1,
    limit_price: Optional[float] = None
) -> NewOrder:
    """
    Build a ZEBRA complex order (3-leg, single ticket).
    
    For LONG (bullish) ZEBRA:
      - Buy 2 ITM Calls at long_strike
      - Sell 1 ATM Call at short_strike
    
    For SHORT (bearish) ZEBRA:
      - Buy 2 ITM Puts at long_strike (higher strike)
      - Sell 1 ATM Put at short_strike (lower strike)
    
    CRITICAL: Must be submitted as a single complex order, never leg in.
    """
```

**Add to `src/lib/tastytrade-api.ts` (frontend):**

```typescript
export async function executeZebra(
    accessToken: string,
    accountNumber: string,
    signal: {
        symbol: string;
        long_strike: number;
        short_strike: number;
        expiry: string;       // YYYY-MM-DD
        direction: 'LONG' | 'SHORT';
        contracts: number;
        price?: number;       // Signal mid-price (backup)
    }
): Promise<OrderResponse> {
    // 1. Fetch live quotes for all 3 legs
    // 2. Compute optimal limit price (package mid)  
    // 3. Build 3-leg complex order
    // 4. Dry-run validation
    // 5. Submit order
}
```

**Register in `strategy-executor.ts`:**

```typescript
const executeZebraStrategy: StrategyExecutor = async (
    accessToken, accountNumber, signal, defaultExpiry
) => {
    return await executeZebra(accessToken, accountNumber, {
        symbol: signal.symbol || 'UNKNOWN',
        long_strike: signal.long_strike || signal.strike || 0,
        short_strike: signal.short_strike || 0,
        expiry: signal.expiration || signal.expiry || defaultExpiry.front,
        direction: (signal.direction === 'bearish' ? 'SHORT' : 'LONG'),
        contracts: signal.contracts || 1,
        price: signal.net_debit || signal.price || signal.cost,
    });
};

// Add to STRATEGY_EXECUTORS map:
'zebra': executeZebraStrategy,
'ZEBRA': executeZebraStrategy,
'zebra-spread': executeZebraStrategy,
```

### 5.5 Lifecycle Engine (`src/zebra_spreads/lifecycle_engine.py`)

```python
class ZebraLifecycleEngine:
    """
    Evaluates open ZEBRA positions and returns management actions.
    Called every 15 minutes during market hours.
    """
    
    class Action(Enum):
        HOLD = "HOLD"
        TAKE_PROFIT = "TAKE_PROFIT"       # P&L ≥ 50% of max theoretical
        TIME_EXIT = "TIME_EXIT"           # Time Used ≥ 50% of duration
        STOP_LOSS = "STOP_LOSS"           # P&L ≤ -40% of debit
        RECENTER_DOWN = "RECENTER_DOWN"   # Stock -8%, DC > 60
        RECENTER_UP = "RECENTER_UP"       # Stock +15%, delta compressed
        ASSIGNMENT_EXIT = "ASSIGNMENT_EXIT" # Short ITM with < 5 DTE
        DIVIDEND_EXIT = "DIVIDEND_EXIT"     # Ex-div within 3 days, short ITM
    
    def evaluate(self, position: ZebraPosition, market_data: dict) -> Tuple[Action, str]:
        """
        Evaluate a single ZEBRA position.
        
        Returns: (action, reason_string)
        
        Decision tree (evaluated in priority order):
        1. Assignment Risk: short call ITM AND DTE < 5 → ASSIGNMENT_EXIT
        2. Dividend Risk: ex-div within 3 days AND short ITM → DIVIDEND_EXIT
        3. Stop Loss: current_pnl_pct ≤ -40% → STOP_LOSS
        4. Profit Target: current_pnl ≥ 50% of max_theoretical → TAKE_PROFIT
        5. Time Exit: time_used ≥ 50% → TIME_EXIT
        6. Re-center Down: stock_move ≤ -8% AND DC > 60 → RECENTER_DOWN
        7. Re-center Up: stock_move ≥ +15% AND delta compressed → RECENTER_UP
        8. Default: HOLD
        """
    
    def execute_action(self, position: ZebraPosition, action: Action):
        """
        Execute the management action:
        - TAKE_PROFIT / TIME_EXIT / STOP_LOSS / ASSIGNMENT_EXIT / DIVIDEND_EXIT:
            → Close all 3 legs as single complex closing order
        - RECENTER_DOWN:
            → Close current ZEBRA, construct new one at lower strikes
        - RECENTER_UP:
            → Roll short call up (close short, open higher short) OR close/redeploy
        """
```

### 5.6 Continuous Monitor (`zebra_monitor_continuous.py`)

Mirror `theta_monitor_continuous.py` structure:

```python
"""
ZEBRA Strategy - Continuous Monitoring Service
===============================================
Runs 24/7 as a systemd service on EC2.

During market hours:
- Every 30 minutes: Scan for NEW ZEBRA entry opportunities
- Every 15 minutes: Evaluate all open ZEBRA positions for lifecycle actions
- 10:00-11:30 ET: Preferred entry window for new trades

Channels: zebra_entry, zebra_exit, zebra_all
"""

def run_entry_scan():
    """
    1. Get universe of eligible stocks
    2. For each: compute directional confidence (Phase 1: rule-based, Phase 2: ML)
    3. Filter by confidence > 65
    4. Run construction engine on top candidates
    5. Check portfolio capacity
    6. Publish ZEBRA entry signals
    """

def run_position_check():
    """
    1. Fetch all open ZEBRA positions
    2. Refresh per-leg live data (price, Greeks)
    3. Run lifecycle engine evaluate()
    4. Execute any non-HOLD actions
    5. Publish exit signals for closed positions
    """
```

### 5.7 Frontend Signal Card (`ZebraSignalCard.tsx`)

Display ZEBRA-specific information:
- **3-leg structure** visualization (2× Long Call @ strike, 1× Short Call @ strike)
- **Net extrinsic** indicator (green if ≈ $0)
- **Capital efficiency** ratio vs. 100 shares
- **Construction score** badge
- **Directional confidence** meter
- **Approve / Reject** buttons

### 5.8 Config Section

**Add to `config.py`:**

```python
# =============================================================================
# ZEBRA STRATEGY SETTINGS
# =============================================================================

# Universe
ZEBRA_UNIVERSE: List[str] = [
    # S&P 500 liquid names + high-volume mid-caps
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
    "JPM", "V", "MA", "UNH", "HD", "PG", "JNJ",
    "SPY", "QQQ", "IWM", "DIA",
    # ... expand to 50+ symbols
]

# Universe filters
ZEBRA_MIN_ADV: int = 1_000_000        # Min avg daily volume
ZEBRA_MAX_ATM_SPREAD: float = 0.50    # Max ATM option spread
ZEBRA_MIN_OI: int = 500               # Min open interest on target strikes

# Construction parameters
ZEBRA_LONG_DELTA_MIN: float = 0.65
ZEBRA_LONG_DELTA_MAX: float = 0.80
ZEBRA_SHORT_DELTA_MIN: float = 0.45
ZEBRA_SHORT_DELTA_MAX: float = 0.55
ZEBRA_MAX_NET_EXTRINSIC: float = 0.15   # Max acceptable net extrinsic ($)
ZEBRA_MAX_DEBIT_PCT: float = 0.50       # Max debit as % of 100-share cost
ZEBRA_MAX_SLIPPAGE_PCT: float = 3.0     # Max slippage above mid
ZEBRA_SLIPPAGE_WARNING_PCT: float = 2.0 # Flag if aggregate spread > 2% of debit

# Lifecycle thresholds
ZEBRA_PROFIT_TARGET_PCT: float = 50.0   # Close at 50% of max theoretical profit
ZEBRA_TIME_EXIT_PCT: float = 50.0       # Close when 50% of time elapsed
ZEBRA_STOP_LOSS_PCT: float = -40.0      # Stop loss at -40% of debit
ZEBRA_RECENTER_DOWN_PCT: float = -8.0   # Re-center when stock drops 8%
ZEBRA_RECENTER_UP_PCT: float = 15.0     # Re-center when stock rallies 15%
ZEBRA_ASSIGNMENT_DTE: int = 5           # Close if short ITM with < 5 DTE
ZEBRA_DIVIDEND_DAYS: int = 3            # Close if ex-div within 3 days

# Execution preferences
ZEBRA_ENTRY_WINDOW_START: time = time(10, 0)   # 10:00 AM ET
ZEBRA_ENTRY_WINDOW_END: time = time(11, 30)    # 11:30 AM ET
ZEBRA_PRICE_ADJUST_TIMEOUT: int = 900          # 15 min before adjusting
ZEBRA_PRICE_ADJUST_STEP: float = 0.05          # $0.05 per adjustment

# Scanning frequency
ZEBRA_SCAN_INTERVAL_MIN: int = 30       # Scan for new entries every 30 min
ZEBRA_POSITION_CHECK_MIN: int = 15      # Check positions every 15 min

# Selection
ZEBRA_MIN_DIRECTIONAL_CONFIDENCE: int = 65
ZEBRA_SELECT_TOP_N: int = 5             # Top 5 candidates daily
```

### 5.9 Signal Publisher Registration

**Update `signal_publisher/__init__.py`:**

```python
# Zebra signals
from .zebra import (
    ZebraEntrySignal,
    ZebraExitSignal,
    publish_zebra_entry_signal,
    publish_zebra_exit_signal
)

__all__ = [
    # ... existing ...
    # Zebra
    'ZebraEntrySignal',
    'ZebraExitSignal',
    'publish_zebra_entry_signal',
    'publish_zebra_exit_signal',
]
```

### 5.10 Frontend Channel Subscription

**Update `SignalProvider.tsx`:**
```typescript
const { isConnected, lastSignal } = useSignalSocket({
    channels: [
        'theta_entry', 'theta_puts',
        'calendar_spread', 'diagonal_spread',
        'zebra_entry', 'zebra_exit'  // ← NEW
    ],
    onSignal: handleSignal,
    // ...
});
```

**Update auto-approve settings (`api/settings/auto-approve/route.ts`):**
```typescript
interface AutoApproveSettings {
    enabled: boolean;
    theta: StrategySettings;
    diagonal: StrategySettings;
    zebra: StrategySettings;  // ← NEW
}
```

---

## 6. Phase 2 — ML Signal Engine & Anti-Crowding

**Duration:** Weeks 5–10  
**Goal:** Replace rule-based stock selection with ML-driven directional predictions. Implement anti-crowding intelligence.

### 6.1 New Files

| File | Purpose |
|---|---|
| `src/zebra_spreads/ml_signal_engine.py` | Ensemble model training + inference |
| `src/zebra_spreads/feature_store.py` | Feature vector computation + caching |
| `src/zebra_spreads/anti_crowding.py` | 6 anti-crowding mechanisms |
| `src/zebra_spreads/data_sources.py` | Market data, fundamentals, sentiment feeds |
| `models/zebra_rf_model.pkl` | Trained Random Forest |
| `models/zebra_xgb_model.pkl` | Trained XGBoost |
| `models/zebra_lstm_model.h5` | Trained LSTM |

### 6.2 ML Signal Engine

```python
class ZebraMLSignalEngine:
    """
    Ensemble model for 30-day directional prediction.
    
    Models:
    - Random Forest: Captures non-linear feature interactions
    - XGBoost: Gradient boosting for structured data
    - LSTM: Sequential patterns in price history
    
    Training:
    - Rolling 2-year window
    - Label: forward 30-day return (bucketed: up > 5%, flat ±5%, down < -5%)
    - Retrain weekly
    """
    
    def generate_daily_candidates(self, as_of_date: date) -> List[TradeCandidate]:
        """
        Full pipeline:
        1. Pull eligible universe (universe.py filters)
        2. Compute feature vectors for each symbol (feature_store.py)
        3. Run ensemble prediction → directional_confidence, expected_move_pct
        4. Filter: directional_confidence > 65
        5. Compute liquidity_score, capital_efficiency, anti_crowding_score
        6. Rank by composite score:
           Score = DC × 0.40 + Liquidity × 0.25 + CapEff × 0.20 + AntiCrowd × 0.15
        7. Return top N candidates with rationale
        """
```

### 6.3 Feature Store

**Feature categories per symbol:**

| Category | Features | Data Source |
|---|---|---|
| **Technical** | RSI, MACD, 50/200 SMA crossover, Bollinger position, ATR, volume trend | IB Gateway / market data API |
| **Fundamental** | Earnings surprise history, revenue growth, analyst revisions, PE vs sector | Financial APIs (FMP, Alpha Vantage) |
| **Options** | IV, IVR, IV skew, term structure, ATM spread, OI distribution | Tastytrade chain data |
| **Flow** | Unusual volume vs OI, sweep detection, dark pool flags, put/call ratio | Options flow APIs |
| **Sentiment** | News NLP score, social media momentum, insider trading signals | News APIs, Reddit/X scraping |

### 6.4 Anti-Crowding Module

```python
class AntiCrowdingModule:
    """
    Six mechanisms to avoid crowded ZEBRA trades.
    Used in both candidate ranking AND construction scoring.
    """
    
    def evaluate(self, symbol: str, target_strikes: dict, 
                 target_expiry: date) -> AntiCrowdingResult:
        """
        Returns:
        - anti_crowding_score: 0-100 (100 = uncrowded)
        - crowding_flags: list of detected issues
        - recommended_adjustments: strike/expiry shifts
        """
    
    # Mechanism 1: OI Crowding Detector
    def _check_oi_crowding(self, symbol, strikes, lookback=5):
        """
        If OI at target strike increased > 30% in 5 days
        without corresponding price move → crowded.
        Action: shift long strike 1-2 deeper ITM.
        """
    
    # Mechanism 2: Bid-Ask Spread Anomaly
    def _check_spread_anomaly(self, symbol, strikes, lookback=20):
        """
        If current spread > 1.5σ above 20-day mean → adverse selection.
        Action: delay entry or use different expiry.
        """
    
    # Mechanism 3: Timing Differentiation
    def _check_social_spike(self, symbol):
        """
        NLP monitors YouTube/Reddit/X for ZEBRA-related content spikes.
        If spike detected → delay entries 3-5 trading days.
        """
    
    # Mechanism 4: Strike Diversification
    def _jitter_strikes(self, long_delta_range, short_delta_range):
        """
        Randomize within safe delta bands to avoid textbook combos.
        Optimize for lowest crowding score, not just theoretical optimum.
        """
    
    # Mechanism 5: Unusual Flow Counter-Signal
    def _check_institutional_counter(self, symbol, strikes):
        """
        If institutional sells at ITM strikes while retail chatter rises
        → downgrade directional confidence by 15 points.
        """
    
    # Mechanism 6: Expiration Cycle Rotation
    def _rotate_expiry(self, available_expiries):
        """
        Avoid nearest obvious monthly.
        Prefer 2nd monthly or quarterlies for lower retail overlap.
        """
```

### 6.5 Phase 1 → Phase 2 Transition

During Phase 1 (before ML is ready), use **rule-based** directional scoring:

```python
def rule_based_directional_score(symbol: str) -> float:
    """
    Simplified scoring until ML engine is trained:
    - RSI momentum (20%)
    - 50/200 SMA trend (25%)
    - Volume trend (15%)
    - IV percentile (20%)
    - Sector momentum (20%)
    
    Returns: 0-100 confidence score
    """
```

---

## 7. Phase 3 — Portfolio Risk & Analytics

**Duration:** Weeks 11–14  
**Goal:** Portfolio-level risk controls, performance tracking, and model feedback loop.

### 7.1 Portfolio Risk Engine

**Extend `risk_manager.py` or create `src/zebra_spreads/portfolio_risk.py`:**

```python
class ZebraPortfolioRisk:
    """
    Portfolio-level constraints for ZEBRA positions.
    """
    
    # Position limits
    MAX_CONCURRENT_ZEBRAS: int = 8       # Max open ZEBRA positions
    MAX_CAPITAL_PER_TRADE_PCT: float = 10 # Max 10% of portfolio per ZEBRA
    MAX_SAME_SECTOR: int = 3             # Max 3 ZEBRAs in same GICS sector
    MAX_CORRELATION: float = 0.75        # If corr > 0.75, only 1 ZEBRA allowed
    MAX_PORTFOLIO_DELTA: int = 500       # Total net delta cap (SPY-equivalent)
    
    # VIX Regime Rules
    VIX_REGIMES = {
        "low":    {"max_vix": 15, "max_positions": 8,  "min_dc": 65},
        "medium": {"max_vix": 25, "max_positions": 6,  "min_dc": 65},
        "high":   {"max_vix": 35, "max_positions": 4,  "min_dc": 75},
        "crisis": {"max_vix": 999, "max_positions": 0, "min_dc": 999},
    }
    
    def check_capacity(self, proposed_trade: ZebraStructure) -> Tuple[bool, str]:
        """
        Returns (allowed: bool, reason: str)
        
        Checks in order:
        1. Total position count ≤ MAX for current VIX regime
        2. Capital ≤ MAX_CAPITAL_PER_TRADE_PCT of portfolio
        3. Sector concentration ≤ MAX_SAME_SECTOR
        4. Correlation with existing positions ≤ MAX_CORRELATION
        5. Total portfolio delta ≤ MAX_PORTFOLIO_DELTA
        6. VIX regime directional confidence requirement
        """
    
    def get_portfolio_greeks(self) -> dict:
        """
        Returns aggregate Greeks across all open ZEBRAs:
        - total_delta, total_theta, total_vega
        - sector_breakdown
        - correlation_matrix
        """
```

### 7.2 Analytics & Trade Logging

**Database table: `zebra_trade_log`** (see Schema section)

```python
class ZebraAnalytics:
    """
    Performance tracking and model feedback.
    """
    
    def log_trade(self, trade_log_entry: TradeLogEntry):
        """Persist completed trade with all metrics."""
    
    def get_overview(self) -> dict:
        """
        Returns:
        - win_rate, avg_return, sharpe_ratio, max_drawdown
        - avg_holding_period, total_trades
        - P&L by exit_reason breakdown
        """
    
    def get_model_performance(self) -> dict:
        """
        Directional accuracy by confidence bucket:
        - 60-70, 70-80, 80-90, 90+ buckets
        - Accuracy per VIX regime
        """
    
    def get_anticrowding_impact(self) -> dict:
        """
        Compare returns of crowded vs uncrowded entries:
        - avg_return_crowded, avg_return_uncrowded
        - statistical significance test
        """
```

### 7.3 Frontend Dashboard Widgets

Add to `dashboard/page.tsx`:

```typescript
// ZEBRA Performance Summary Card
<ZebraPerformanceSummary />  // Win rate, Sharpe, active positions

// ZEBRA Position Monitor  
<ZebraPositionTable />  // Open positions with live P&L, Greeks, actions

// ZEBRA Analytics Charts
<ZebraAnalyticsCharts />  // Performance over time, regime analysis
```

---

## 8. Phase 4 — ZEEHBS Hedge & Optimization

**Duration:** Weeks 15+  
**Goal:** Optional portfolio hedging overlay and continuous optimization.

### 8.1 ZEEHBS Module

```python
class ZeehbsHedgeModule:
    """
    ZEEHBS = Zero Extrinsic Hedged Back Spread
    
    Adds synthetic short index hedges when portfolio risk is elevated.
    
    Activation conditions:
    - > 5 concurrent ZEBRAs
    - VIX rising from low base (VIX delta > +3 in 5 days)
    - Major macro event approaching (FOMC, CPI, earnings cluster)
    
    Mechanism:
    - For every 2 ZEBRAs, add 1 synthetic short on SPY/QQQ:
      Sell 1 Call + Buy 1 Put at same strike/expiry
    
    Research backing:
    - Reduced SPY max DD from -23.93% to -9.8%
    - Maintained ~42% return
    """
    
    def evaluate(self, portfolio: List[ZebraPosition]) -> Optional[HedgeProposal]:
        """Check if hedging conditions are met."""
    
    def execute_hedge(self, proposal: HedgeProposal):
        """Submit synthetic short orders via Tastytrade."""
```

### 8.2 Continuous Optimization

- **Weekly model retraining** with latest trade outcomes
- **Feature importance analysis** — drop features with persistent low contribution
- **Alpha decay monitoring** — track if strategy edge is diminishing
- **Threshold tuning** — A/B test different profit target / stop loss levels
- **Backtesting framework** — validate parameter changes on historical data

---

## 9. Database Schema

### 9.1 PostgreSQL Tables

```sql
-- Signals table (extends existing signals table)
-- No new table needed; ZEBRA signals use existing signal storage
-- with strategy = 'zebra' and extended metadata JSON

-- ZEBRA-specific position tracking
CREATE TABLE IF NOT EXISTS zebra_positions (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,  -- 'LONG' or 'SHORT'
    
    -- Structure
    long_strike DECIMAL(10,2) NOT NULL,
    short_strike DECIMAL(10,2) NOT NULL,
    expiry DATE NOT NULL,
    contracts INTEGER DEFAULT 1,
    
    -- Entry data
    entry_debit DECIMAL(10,2) NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    initial_dte INTEGER NOT NULL,
    
    -- Greeks at entry
    net_delta_entry DECIMAL(6,4),
    net_theta_entry DECIMAL(6,4),
    net_extrinsic_entry DECIMAL(10,4),
    
    -- Scoring at entry
    directional_confidence DECIMAL(5,2),
    construction_score DECIMAL(5,2),
    anti_crowding_score DECIMAL(5,2),
    composite_score DECIMAL(5,2),
    
    -- Status tracking
    status VARCHAR(20) DEFAULT 'OPEN',  -- OPEN, CLOSING, CLOSED
    exit_time TIMESTAMP,
    exit_credit DECIMAL(10,2),
    exit_reason VARCHAR(30),  -- PROFIT_TARGET, TIME_EXIT, STOP_LOSS, etc.
    
    -- P&L
    realized_pnl DECIMAL(10,2),
    realized_pnl_pct DECIMAL(6,2),
    max_drawdown_pct DECIMAL(6,2),
    
    -- Execution tracking
    entry_order_id VARCHAR(64),
    exit_order_id VARCHAR(64),
    slippage_bps DECIMAL(6,2),
    
    -- Metadata
    rationale TEXT,
    tags JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_zebra_positions_user ON zebra_positions(user_id);
CREATE INDEX idx_zebra_positions_status ON zebra_positions(status);
CREATE INDEX idx_zebra_positions_symbol ON zebra_positions(symbol);

-- ZEBRA trade log (completed trades for analytics)
CREATE TABLE IF NOT EXISTS zebra_trade_log (
    id SERIAL PRIMARY KEY,
    zebra_id VARCHAR(64) REFERENCES zebra_positions(id),
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP NOT NULL,
    entry_debit DECIMAL(10,2) NOT NULL,
    exit_credit DECIMAL(10,2) NOT NULL,
    
    pnl_abs DECIMAL(10,2) NOT NULL,
    pnl_pct DECIMAL(6,2) NOT NULL,
    max_drawdown_pct DECIMAL(6,2),
    
    exit_reason VARCHAR(30) NOT NULL,
    holding_days INTEGER NOT NULL,
    
    -- ML feedback data
    directional_confidence_entry DECIMAL(5,2),
    realized_30d_move_pct DECIMAL(6,2),
    anti_crowding_score_entry DECIMAL(5,2),
    slippage_bps DECIMAL(6,2),
    
    -- Context
    vix_at_entry DECIMAL(5,2),
    vix_at_exit DECIMAL(5,2),
    sector VARCHAR(30),
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- Anti-crowding metrics history
CREATE TABLE IF NOT EXISTS zebra_crowding_metrics (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    strike DECIMAL(10,2) NOT NULL,
    expiry DATE NOT NULL,
    
    oi_5d_change_pct DECIMAL(6,2),
    spread_zscore DECIMAL(6,2),
    social_spike_detected BOOLEAN DEFAULT FALSE,
    institutional_counter BOOLEAN DEFAULT FALSE,
    
    computed_at TIMESTAMP DEFAULT NOW()
);
```

---

## 10. API Contracts

### 10.1 Backend Python APIs (Internal)

These are function calls within the Python backend, not HTTP endpoints:

| Function | Input | Output |
|---|---|---|
| `universe.get_eligible_symbols()` | `date` | `List[{symbol, adv, atm_spread, oi}]` |
| `feature_store.get_features(symbol)` | `symbol` | Feature vector dict |
| `ml_engine.generate_candidates(date)` | `date` | `List[TradeCandidate]` |
| `construction.construct(symbol, ...)` | Symbol + config | `List[ZebraStructure]` top 3 |
| `anti_crowding.evaluate(symbol, strikes)` | Symbol + strikes | `{score, flags, adjustments}` |
| `lifecycle.evaluate(position)` | `ZebraPosition` | `(Action, reason)` |
| `portfolio_risk.check_capacity(trade)` | `ZebraStructure` | `(bool, reason)` |
| `analytics.log_trade(entry)` | `TradeLogEntry` | None |

### 10.2 Frontend Next.js API Routes

| Route | Method | Purpose |
|---|---|---|
| `/api/signals` | GET | Fetch all signals including ZEBRA (existing) |
| `/api/signals/[id]/approve` | POST | Approve ZEBRA signal (existing, strategy-agnostic) |
| `/api/settings/auto-approve` | GET/PUT | Include `zebra` strategy settings |
| `/api/positions` | GET | Return ZEBRA positions alongside theta/diagonal |
| `/api/tastytrade/account` | GET | Account balance (existing) |
| `/api/activity` | GET | Trade activity log (existing, works automatically) |
| `/api/zebra/analytics` | GET | **(New)** ZEBRA-specific performance metrics |
| `/api/zebra/portfolio` | GET | **(New)** Portfolio risk snapshot |

### 10.3 WebSocket Channels

| Channel | Message Type | When |
|---|---|---|
| `zebra_entry` | ZebraEntrySignal | New ZEBRA opportunity identified |
| `zebra_exit` | ZebraExitSignal | ZEBRA position closed (any reason) |
| `zebra_all` | Either | All ZEBRA-related messages |

---

## 11. Daily Automation Schedule

| Time (ET) | Action | Service |
|---|---|---|
| **07:30** | ML engine runs on full universe → daily candidate scores | `zebra_monitor` |
| **08:00** | Anti-crowding update (OI changes, spread anomalies, social spikes) | `zebra_monitor` |
| **09:45** | Construction engine on top candidates; portfolio capacity check; generate trade proposals | `zebra_monitor` |
| **10:00** | Entry window opens — if auto-approve ON, submit multi-leg orders | `zebra_monitor` + client |
| **10:15** | First lifecycle sweep (manage all open positions) | `zebra_monitor` |
| **11:30** | Entry window closes | — |
| **12:00** | Second lifecycle sweep | `zebra_monitor` |
| **14:00** | Third lifecycle sweep | `zebra_monitor` |
| **15:30** | Pre-close sweep: expiring positions, assignment/dividend risk | `zebra_monitor` |
| **16:15** | Post-close: sync fills, close statuses, log completed trades | `zebra_monitor` |
| **17:00** | Generate daily report, push via TradeMind dashboard/email | `zebra_monitor` |

---

## 12. Testing Strategy

### 12.1 Unit Tests

| Test File | Coverage |
|---|---|
| `test_zebra_construction.py` | Strike optimization, extrinsic calculation, scoring |
| `test_zebra_lifecycle.py` | All 8 decision tree branches |
| `test_zebra_anticrowding.py` | Each of 6 mechanisms independently |
| `test_zebra_portfolio_risk.py` | VIX regimes, sector limits, correlation filter |
| `test_zebra_signal_publisher.py` | Signal serialization, WebSocket broadcast |

### 12.2 Integration Tests

| Test | What It Validates |
|---|---|
| Dry-run order test | Build ZEBRA order → Tastytrade dry-run → validate acceptance |
| Signal-to-UI test | Publish signal → WS → frontend receives → renders correctly |
| Auto-approve test | Signal → client auto-approve → order submitted → status updated |
| Lifecycle loop test | Open position → trigger condition → correct action executed |

### 12.3 Backtesting

- Backtest construction engine on historical options chain data
- Validate lifecycle thresholds (50% profit, 50% time, -40% stop)
- Compare rule-based vs ML-driven stock selection
- Measure anti-crowding impact on simulated returns

---

## 13. Deployment Plan

### 13.1 Backend (EC2)

```bash
# 1. Deploy new code
./deploy.sh  # existing deployment script

# 2. Create systemd service for ZEBRA monitor
sudo cp zebra_monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable zebra-monitor
sudo systemctl start zebra-monitor

# 3. Verify
sudo journalctl -u zebra-monitor -f
```

### 13.2 Frontend (Vercel)

```bash
# Automatic on git push to main
git add .
git commit -m "feat: ZEBRA strategy integration"
git push origin main
# Vercel rebuilds automatically
```

### 13.3 Database Migration

```sql
-- Run via PostgreSQL client or automated migration
-- Tables: zebra_positions, zebra_trade_log, zebra_crowding_metrics
```

---

## 14. Risk & Open Questions

### 14.1 Known Risks

| Risk | Mitigation |
|---|---|
| **3-leg slippage** | Always use complex orders; monitor fill quality; 3% max slippage |
| **Early assignment on short call** | Monitor DTE < 5 and ex-div dates; auto-close |
| **ML model overfitting** | Walk-forward validation; rolling 2-year window; feature importance monitoring |
| **Strategy crowding** | Anti-crowding module is entire Phase 2 priority |
| **Tastytrade API complex order support** | Verify 3-leg complex order syntax during Phase 1 Week 1 |
| **Market data latency** | Use IB Gateway for real-time Greeks; Tastytrade chains as backup |

### 14.2 Open Questions

1. **Bearish ZEBRAs:** Do we support SHORT (put-based) ZEBRAs from Day 1, or start with LONG (call-based) only?
   - **Recommendation:** Start with LONG only in Phase 1; add SHORT in Phase 2.

2. **Capital sizing:** Fixed $X per ZEBRA or percentage of portfolio?
   - **Recommendation:** Percentage-based (10% max per trade, configurable).

3. **ML data sources:** Which paid data APIs for fundamentals, flow, and sentiment?
   - **Recommendation:** Start with free sources (Yahoo Finance, Reddit API); add paid (Alpha Vantage, Quandl) in Phase 2.

4. **Theta monitor coexistence:** Should ZEBRA monitor be a separate service or merged into existing monitor?
   - **Recommendation:** Separate `zebra_monitor.service` for isolation and independent scaling.

5. **Re-centering frequency:** How often can a ZEBRA be re-centered before we give up?
   - **Recommendation:** Max 2 re-centers per position; after that, stop-loss exit.

---

## Summary: File Creation Checklist

### Phase 1 (Core)
- [ ] `src/zebra_spreads/__init__.py`
- [ ] `src/zebra_spreads/construction_engine.py`
- [ ] `src/zebra_spreads/lifecycle_engine.py`
- [ ] `src/zebra_spreads/universe.py`
- [ ] `signal_publisher/zebra.py`
- [ ] `zebra_monitor_continuous.py`
- [ ] `zebra_monitor.service`
- [ ] Update `config.py` with ZEBRA section
- [ ] Update `signal_publisher/__init__.py`
- [ ] Update `tastytrade_client.py` with `build_zebra_order()`
- [ ] Update `trademind-app/src/lib/tastytrade-api.ts` with `executeZebra()`
- [ ] Update `trademind-app/src/lib/strategy-executor.ts` with ZEBRA registration
- [ ] Create `trademind-app/src/components/signals/ZebraSignalCard.tsx`
- [ ] Update `trademind-app/src/components/providers/SignalProvider.tsx` channels
- [ ] Run database migrations

### Phase 2 (ML + Anti-Crowding)
- [ ] `src/zebra_spreads/ml_signal_engine.py`
- [ ] `src/zebra_spreads/feature_store.py`
- [ ] `src/zebra_spreads/anti_crowding.py`
- [ ] `src/zebra_spreads/data_sources.py`
- [ ] ML model training pipeline + saved models

### Phase 3 (Portfolio + Analytics)
- [ ] `src/zebra_spreads/portfolio_risk.py`
- [ ] `src/zebra_spreads/analytics.py`
- [ ] `trademind-app/src/app/api/zebra/analytics/route.ts`
- [ ] Dashboard ZEBRA performance widgets

### Phase 4 (ZEEHBS + Optimization)
- [ ] `src/zebra_spreads/zeehbs_hedge.py`
- [ ] Backtest framework extensions
- [ ] Threshold optimization scripts
