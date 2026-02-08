# Complete Data Flow: Frontend + Backend Databases

## Current Architecture Discovery

**Frontend (TradeMind on Vercel) Has:**
- ✅ **Upstash Redis** - Currently storing Tastytrade tokens per user
- ✅ **@vercel/postgres** - Installed but NOT USED yet
- ✅ **Next.js API Routes** - Execute trades directly from Vercel

**Backend (EC2) Has:**
- ✅ **PostgreSQL** - signals, user_signal_executions, positions tables

**Current Flow (BROKEN):**
```
Signal Generated (EC2)
  ↓
Signal saved to EC2 PostgreSQL
  ↓
WebSocket broadcast to frontend
  ↓
User clicks "Approve"
  ↓
Frontend API route executes trade (Vercel)
  ↓
Returns orderId to UI
  ↓
❌ NO POSITION CREATED ANYWHERE!
```

---

## Updated Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    BACKEND (EC2 Server)                          │
│                                                                  │
│  PostgreSQL Database                                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  signals (generated signals - GLOBAL)                    │   │
│  │  ├─ id, symbol, strategy, status, data                   │   │
│  │  └─ created_at, expires_at                               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  WebSocket Server (8003) - broadcasts signals                   │
│  API Server (8002) - /api/signals endpoint                      │
│                                                                  │
│  Position Monitor Service (NEW)                                 │
│  ├─ Checks open positions from ALL users                        │
│  ├─ Generates exit signals                                      │
│  └─ Broadcasts via WebSocket                                    │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ↓ WebSocket + REST API
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│              FRONTEND (TradeMind on Vercel)                      │
│                                                                  │
│  ┌────────────────────┐  ┌─────────────────────────────────────┐│
│  │   Upstash Redis    │  │   Vercel Postgres (NEW!)            ││
│  │   ──────────────   │  │   ───────────────────────           ││
│  │   tastytrade:      │  │                                     ││
│  │   {userId}:tokens  │  │   user_positions                    ││
│  │                    │  │   ├─ id (tastytrade order_id)       ││
│  │                    │  │   ├─ user_id                        ││
│  │                    │  │   ├─ signal_id                      ││
│  │                    │  │   ├─ symbol, strike, expiration     ││
│  │                    │  │   ├─ entry_price, contracts         ││
│  │                    │  │   ├─ status (open/closed)           ││
│  │                    │  │   ├─ risk_level                     ││
│  │                    │  │   └─ created_at, updated_at         ││
│  │                    │  │                                     ││
│  │                    │  │   user_settings                     ││
│  │                    │  │   ├─ user_id                        ││
│  │                    │  │   ├─ risk_level                     ││
│  │                    │  │   └─ notifications                  ││
│  └────────────────────┘  └─────────────────────────────────────┘│
│                                                                  │
│  API Routes (Next.js)                                           │
│  ├─ POST /api/signals/[id]/approve  →  Execute + Create Position││
│  ├─ GET /api/positions              →  Get user's positions    ││
│  ├─ PUT /api/settings/risk-level    →  Update risk level       ││
│  └─ POST /api/positions/sync        →  Sync with backend       ││
└──────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: Set Up Vercel Postgres

#### 1.1 Create Database Schema

**File: `src/lib/db/schema.sql`**

```sql
-- User settings
CREATE TABLE IF NOT EXISTS user_settings (
    user_id VARCHAR(128) PRIMARY KEY,
    risk_level VARCHAR(20) DEFAULT 'moderate',
    notifications_enabled BOOLEAN DEFAULT true,
    push_enabled BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- User positions (trades executed by this user)
CREATE TABLE IF NOT EXISTS user_positions (
    id VARCHAR(64) PRIMARY KEY,  -- Tastytrade order_id
    user_id VARCHAR(128) NOT NULL,
    signal_id VARCHAR(36),        -- Reference to backend signal
    
    -- Position details
    symbol VARCHAR(10) NOT NULL,
    strategy VARCHAR(30) DEFAULT 'theta',
    strike DECIMAL(10,2),
    expiration DATE,
    contracts INTEGER DEFAULT 1,
    
    -- Entry details
    entry_price DECIMAL(10,4),
    entry_date TIMESTAMP DEFAULT NOW(),
    capital_required DECIMAL(12,2),
    
    -- Current state (updated by sync)
    current_price DECIMAL(10,4),
    unrealized_pnl DECIMAL(10,2),
    unrealized_pnl_pct DECIMAL(5,2),
    
    -- Risk management
    risk_level VARCHAR(20),
    profit_target_pct DECIMAL(5,2),
    stop_loss_pct DECIMAL(5,2),
    
    -- Status
    status VARCHAR(20) DEFAULT 'open',  -- open, pending_close, closed
    closed_at TIMESTAMP,
    exit_pnl DECIMAL(10,2),
    exit_reason VARCHAR(50),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    INDEX idx_user_positions_user_id (user_id),
    INDEX idx_user_positions_status (status)
);

-- User signal executions (which signals this user acted on)
CREATE TABLE IF NOT EXISTS user_signal_history (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(128) NOT NULL,
    signal_id VARCHAR(36) NOT NULL,
    action VARCHAR(20) NOT NULL,  -- approved, skipped, expired
    position_id VARCHAR(64),       -- If approved, link to position
    created_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(user_id, signal_id)
);
```

#### 1.2 Create Database Client

**File: `src/lib/db/index.ts`**

```typescript
import { sql } from '@vercel/postgres';

// Initialize database tables
export async function initializeDatabase() {
    try {
        await sql`
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id VARCHAR(128) PRIMARY KEY,
                risk_level VARCHAR(20) DEFAULT 'moderate',
                notifications_enabled BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        `;
        
        await sql`
            CREATE TABLE IF NOT EXISTS user_positions (
                id VARCHAR(64) PRIMARY KEY,
                user_id VARCHAR(128) NOT NULL,
                signal_id VARCHAR(36),
                symbol VARCHAR(10) NOT NULL,
                strategy VARCHAR(30) DEFAULT 'theta',
                strike DECIMAL(10,2),
                expiration DATE,
                contracts INTEGER DEFAULT 1,
                entry_price DECIMAL(10,4),
                entry_date TIMESTAMP DEFAULT NOW(),
                capital_required DECIMAL(12,2),
                current_price DECIMAL(10,4),
                unrealized_pnl DECIMAL(10,2),
                risk_level VARCHAR(20),
                status VARCHAR(20) DEFAULT 'open',
                closed_at TIMESTAMP,
                exit_pnl DECIMAL(10,2),
                exit_reason VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        `;
        
        console.log('✅ Database initialized');
    } catch (error) {
        console.error('Database initialization failed:', error);
    }
}

// Position operations
export async function createPosition(data: {
    id: string;
    userId: string;
    signalId?: string;
    symbol: string;
    strike: number;
    expiration: string;
    contracts: number;
    entryPrice: number;
    capitalRequired: number;
    riskLevel: string;
}) {
    return await sql`
        INSERT INTO user_positions (
            id, user_id, signal_id, symbol, strike, expiration,
            contracts, entry_price, capital_required, risk_level, status
        ) VALUES (
            ${data.id}, ${data.userId}, ${data.signalId}, ${data.symbol},
            ${data.strike}, ${data.expiration}, ${data.contracts},
            ${data.entryPrice}, ${data.capitalRequired}, ${data.riskLevel}, 'open'
        )
        RETURNING *
    `;
}

export async function getUserPositions(userId: string, status?: string) {
    if (status) {
        return await sql`
            SELECT * FROM user_positions 
            WHERE user_id = ${userId} AND status = ${status}
            ORDER BY created_at DESC
        `;
    }
    return await sql`
        SELECT * FROM user_positions 
        WHERE user_id = ${userId}
        ORDER BY created_at DESC
    `;
}

export async function updatePositionPrice(
    positionId: string,
    currentPrice: number,
    unrealizedPnl: number
) {
    return await sql`
        UPDATE user_positions 
        SET current_price = ${currentPrice},
            unrealized_pnl = ${unrealizedPnl},
            updated_at = NOW()
        WHERE id = ${positionId}
    `;
}

export async function closePosition(
    positionId: string,
    exitPnl: number,
    exitReason: string
) {
    return await sql`
        UPDATE user_positions 
        SET status = 'closed',
            closed_at = NOW(),
            exit_pnl = ${exitPnl},
            exit_reason = ${exitReason},
            updated_at = NOW()
        WHERE id = ${positionId}
    `;
}

// User settings
export async function getUserSettings(userId: string) {
    const result = await sql`
        SELECT * FROM user_settings WHERE user_id = ${userId}
    `;
    return result.rows[0] || null;
}

export async function setUserRiskLevel(userId: string, riskLevel: string) {
    return await sql`
        INSERT INTO user_settings (user_id, risk_level, updated_at)
        VALUES (${userId}, ${riskLevel}, NOW())
        ON CONFLICT (user_id) 
        DO UPDATE SET risk_level = ${riskLevel}, updated_at = NOW()
    `;
}
```

---

### Phase 2: Update Approve Route to Create Position

**File: `src/app/api/signals/[id]/approve/route.ts`**

Add position creation after trade execution:

```typescript
// Add to imports
import { createPosition, getUserSettings } from '@/lib/db';

// Add after successful trade execution (line ~141):

// ... existing executeCalendarSpread code ...
const result = await executeCalendarSpread(...);

// ✅ NEW: Create position in Vercel Postgres
const userSettings = await getUserSettings(userId);
const riskLevel = userSettings?.risk_level || 'moderate';

await createPosition({
    id: result.orderId,          // Tastytrade order ID
    userId: userId,
    signalId: id,                // Signal ID from URL
    symbol: signalData.symbol,
    strike: signalData.strike,
    expiration: signalData.expiration || signalData.frontExpiry,
    contracts: signalData.contracts || 1,
    entryPrice: signalData.entry_price || signalData.price,
    capitalRequired: signalData.capital_required || signalData.strike * 100,
    riskLevel: riskLevel,
});

console.log(`✅ Position created in database: ${result.orderId}`);

return NextResponse.json({
    status: 'success',
    signal: { id, ...signalData, status: 'executed' },
    orderId: result.orderId,
    positionId: result.orderId,  // Same as orderId
    message: `Trade executed! Order ID: ${result.orderId}`,
});
```

---

### Phase 3: Positions API Endpoint

**File: `src/app/api/positions/route.ts` (NEW)**

```typescript
import { NextResponse } from 'next/server';
import { getUserPositions } from '@/lib/db';
import { cookies } from 'next/headers';

export async function GET(request: Request) {
    try {
        // Get user ID from Privy token
        const cookieStore = await cookies();
        const privyToken = cookieStore.get("privy-token")?.value;
        
        let userId = "default-user";
        if (privyToken) {
            try {
                const payload = privyToken.split(".")[1];
                const decoded = JSON.parse(Buffer.from(payload, "base64").toString());
                userId = decoded.sub || decoded.userId || "default-user";
            } catch (err) {
                console.warn("Could not decode Privy token", err);
            }
        }
        
        // Get status filter from query
        const { searchParams } = new URL(request.url);
        const status = searchParams.get('status') || undefined;
        
        // Fetch positions
        const result = await getUserPositions(userId, status);
        
        return NextResponse.json({
            positions: result.rows,
            count: result.rows.length,
        });
        
    } catch (error) {
        console.error('Positions API error:', error);
        return NextResponse.json(
            { error: 'Failed to fetch positions' },
            { status: 500 }
        );
    }
}
```

---

### Phase 4: Risk Level Settings API

**File: `src/app/api/settings/risk-level/route.ts` (NEW)**

```typescript
import { NextResponse } from 'next/server';
import { getUserSettings, setUserRiskLevel } from '@/lib/db';
import { cookies } from 'next/headers';

// Get current risk level
export async function GET() {
    const userId = await getUserIdFromCookie();
    
    const settings = await getUserSettings(userId);
    
    return NextResponse.json({
        riskLevel: settings?.risk_level || 'moderate',
    });
}

// Update risk level
export async function PUT(request: Request) {
    try {
        const userId = await getUserIdFromCookie();
        const { riskLevel } = await request.json();
        
        // Validate
        const validLevels = ['conservative', 'moderate', 'aggressive'];
        if (!validLevels.includes(riskLevel)) {
            return NextResponse.json(
                { error: 'Invalid risk level' },
                { status: 400 }
            );
        }
        
        await setUserRiskLevel(userId, riskLevel);
        
        // Also notify backend for exit monitoring
        try {
            await fetch(`${process.env.TASTYTRADE_API_URL}/api/user/risk-level`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userId, riskLevel }),
            });
        } catch (backendError) {
            console.warn('Failed to sync risk level to backend:', backendError);
        }
        
        return NextResponse.json({
            success: true,
            riskLevel,
        });
        
    } catch (error) {
        console.error('Risk level update error:', error);
        return NextResponse.json(
            { error: 'Failed to update risk level' },
            { status: 500 }
        );
    }
}

async function getUserIdFromCookie(): Promise<string> {
    const cookieStore = await cookies();
    const privyToken = cookieStore.get("privy-token")?.value;
    
    if (privyToken) {
        try {
            const payload = privyToken.split(".")[1];
            const decoded = JSON.parse(Buffer.from(payload, "base64").toString());
            return decoded.sub || decoded.userId || "default-user";
        } catch {
            // Fall through
        }
    }
    return "default-user";
}
```

---

### Phase 5: Backend Position Monitor with User Risk Levels

**Backend (EC2) needs to:**
1. Know each user's risk level
2. Monitor positions for ALL users
3. Generate exit signals per user's settings
4. Broadcast exit signals to specific users

**File: `src/theta_spreads/position_monitor.py` (EC2)**

```python
"""
Position Monitor - Check all user positions and generate exit signals.
"""

import logging
from src.earnings_intelligence.database import get_session
from sqlalchemy import text
from signal_publisher.theta import ThetaExitSignal, publish_theta_exit_signal
from datetime import datetime, date
import uuid

logger = logging.getLogger(__name__)

# Risk level thresholds
RISK_THRESHOLDS = {
    "conservative": {"profit": 50, "stop": -100, "dte": 7},
    "moderate": {"profit": 65, "stop": -150, "dte": 5},
    "aggressive": {"profit": 75, "stop": -200, "dte": 3},
}


class UserPositionMonitor:
    """Monitor positions and generate personalized exit signals."""
    
    def __init__(self):
        self.session = get_session()
    
    def check_all_users(self):
        """Check positions for all users."""
        logger.info("🔍 Starting position monitoring for all users...")
        
        # Get all open positions with user's risk level
        # This requires backend to know user risk levels (synced from frontend)
        positions = self._get_all_open_positions()
        
        logger.info(f"  Checking {len(positions)} open positions")
        
        exit_signals = []
        
        for position in positions:
            exit_signal = self._check_position(position)
            if exit_signal:
                # Save to database
                self._save_exit_signal(exit_signal)
                
                # Broadcast to WebSocket (will go to user's frontend)
                publish_theta_exit_signal(exit_signal)
                
                exit_signals.append(exit_signal)
                logger.info(f"  📡 Exit signal for {position['user_id']}: {position['symbol']}")
        
        logger.info(f"✅ Generated {len(exit_signals)} exit signals")
        return exit_signals
    
    def _get_all_open_positions(self):
        """Get all open positions from all users."""
        # Query positions table
        result = self.session.execute(text("""
            SELECT p.*, 
                   COALESCE(p.meta_data->>'risk_level', 'moderate') as risk_level
            FROM positions p
            WHERE p.status = 'open'
        """))
        
        positions = []
        for row in result:
            positions.append({
                "id": row.id,
                "user_id": row.user_id,
                "symbol": row.symbol,
                "strike": row.strike,
                "expiration": row.back_expiry,
                "entry_price": abs(row.entry_debit) if row.entry_debit else 0,
                "contracts": row.quantity,
                "risk_level": row.risk_level,
                "created_at": row.created_at,
            })
        
        return positions
    
    def _check_position(self, position):
        """Check if position should be closed."""
        # Get current price (from IB or mock)
        current_price = self._get_current_price(position)
        
        # Get thresholds for user's risk level
        thresholds = RISK_THRESHOLDS.get(
            position["risk_level"], 
            RISK_THRESHOLDS["moderate"]
        )
        
        # Calculate P&L %
        entry = position["entry_price"]
        pnl_pct = ((entry - current_price) / entry) * 100 if entry > 0 else 0
        
        # Calculate DTE
        if position["expiration"]:
            dte = (position["expiration"] - date.today()).days
        else:
            dte = 999
        
        # Check conditions
        exit_reason = None
        
        if pnl_pct >= thresholds["profit"]:
            exit_reason = "profit_target"
        elif pnl_pct <= thresholds["stop"]:
            exit_reason = "stop_loss"
        elif dte <= thresholds["dte"]:
            exit_reason = "time_decay"
        
        if exit_reason:
            pnl = (entry - current_price) * 100 * position["contracts"]
            days_held = (date.today() - position["created_at"].date()).days
            
            return ThetaExitSignal(
                id=str(uuid.uuid4()),
                position_id=position["id"],
                symbol=position["symbol"],
                strike=position["strike"],
                expiration=position["expiration"].isoformat() if position["expiration"] else "",
                exit_price=current_price,
                exit_reason=exit_reason,
                entry_price=entry,
                pnl=pnl,
                pnl_percent=pnl_pct,
                contracts=position["contracts"],
                days_held=days_held,
                created_at=datetime.now(),
                action="BUY_TO_CLOSE",
                status="pending",
                # Add user_id for targeted WebSocket delivery
                user_id=position["user_id"]
            )
        
        return None
    
    def _get_current_price(self, position):
        """Get current option price. TODO: Integrate with IB/Tastytrade."""
        # Mock: Simulate some decay
        return position["entry_price"] * 0.6
    
    def _save_exit_signal(self, signal):
        """Save exit signal to database."""
        from src.earnings_intelligence.database import SignalRepository
        repo = SignalRepository()
        
        data = signal.to_dict()
        data['strategy'] = 'theta'
        data['signal_type'] = 'exit'
        data['target_user_id'] = signal.user_id  # For targeted delivery
        
        repo.save_signal(data)


def run_position_monitor():
    """Entry point for scheduler."""
    monitor = UserPositionMonitor()
    return monitor.check_all_users()
```

---

## Complete Data Flow (Updated)

### 1. Signal Generation (Backend)

```
Scheduler generates theta signal
  ↓
Save to EC2 PostgreSQL (signals table)
  ↓
Broadcast via WebSocket to all connected clients
  ↓
All users see signal in /signals page
```

### 2. User Approves (Frontend)

```
User clicks "Approve" on ThetaSignalCard
  ↓
POST /api/signals/{id}/approve (Vercel API route)
  ↓
Execute trade via Tastytrade API
  ↓
Get order_id from response
  ↓
Save position to Vercel Postgres (user_positions table)
  ↓
Return success to UI
  ↓
User sees "Executed" status
```

### 3. Position Monitoring (Backend)

```
Every 5 minutes during market hours:
  ↓
Query ALL users' positions from EC2 PostgreSQL
  ↓
For each position:
  ├─ Get user's risk level
  ├─ Fetch current option price
  ├─ Check exit conditions
  └─ If exit needed:
       ├─ Save exit signal to database
       └─ Broadcast via WebSocket (targeted to user)
  ↓
User sees exit signal in /signals page
```

### 4. User Closes Position (Frontend)

```
User clicks "Close Position" on exit signal
  ↓
POST /api/signals/{id}/approve (same route, handles BUY_TO_CLOSE)
  ↓
Execute close order via Tastytrade API
  ↓
Update position status in Vercel Postgres
  ↓
Position shows as "Closed" with P&L
```

---

## Database Summary

### Frontend (Vercel)

| Database | What It Stores |
|----------|---------------|
| **Upstash Redis** | Tastytrade OAuth tokens per user |
| **Vercel Postgres** | User positions, settings, signal history |

### Backend (EC2)

| Database | What It Stores |
|----------|---------------|
| **PostgreSQL** | Generated signals (global), position monitoring data |

### Data Relationship

```
EC2: signals (generated by scheduler)
        ↓
    WebSocket broadcast
        ↓
Vercel: User approves → Creates position → Stored in Vercel Postgres
        ↓
EC2: Monitors positions → Generates exit signals
        ↓
    WebSocket broadcast (targeted)
        ↓
Vercel: User closes → Updates Vercel Postgres
```

---

## Files to Create/Modify

### New Files (Frontend)

1. `src/lib/db/index.ts` - Vercel Postgres client
2. `src/lib/db/schema.sql` - Database schema
3. `src/app/api/positions/route.ts` - Positions API
4. `src/app/api/settings/risk-level/route.ts` - Risk settings API

### Modified Files (Frontend)

1. `src/app/api/signals/[id]/approve/route.ts` - Add position creation
2. `src/components/signals/RiskLevelSelector.tsx` - Use new API

### New Files (Backend)

1. `src/theta_spreads/position_monitor.py` - User position monitoring

### Modified Files (Backend)

1. `run_theta_scheduler.py` - Add position monitoring schedule
2. `websocket_server.py` - Add targeted user delivery

---

## Environment Variables Needed

### Vercel (.env)

```bash
# Existing
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...

# NEW: Vercel Postgres
POSTGRES_URL=...
POSTGRES_PRISMA_URL=...
POSTGRES_URL_NON_POOLING=...
POSTGRES_USER=...
POSTGRES_HOST=...
POSTGRES_PASSWORD=...
POSTGRES_DATABASE=...
```

### EC2 (.env)

```bash
# Existing
DATABASE_URL=postgresql://...?sslmode=require

# No changes needed
```

---

## Testing Plan

1. **Initialize Vercel Postgres** via Vercel dashboard
2. **Run schema creation** via API route or script
3. **Test approve flow** - verify position created
4. **Test positions API** - verify positions returned
5. **Test risk level update** - verify saved and synced
6. **Test exit signal** - manually trigger monitoring
7. **Test close flow** - verify position closed

---

## Summary

| Layer | Database | Purpose |
|-------|----------|---------|
| Frontend (Vercel) | Upstash Redis | User tokens |
| Frontend (Vercel) | Vercel Postgres | User positions, settings |
| Backend (EC2) | PostgreSQL | Global signals, monitoring |

**Key Insight:** The frontend (Vercel) already has database capabilities that aren't being used! We just need to:

1. ✅ Configure Vercel Postgres
2. ✅ Create schema
3. ✅ Add position creation to approve route
4. ✅ Create positions/settings API endpoints
5. ✅ Backend monitors and broadcasts exit signals
6. ✅ Frontend displays exit signals and handles closes
