# TradeMind.bot - Architecture Overview

## System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Vercel)                           │
│  trademind-app/                                                     │
│  ├── Next.js 14 (App Router)                                        │
│  ├── /signals - Real-time signal cards                              │
│  ├── /positions - Position tracking                                 │
│  ├── /dashboard - Gamified stats                                    │
│  └── WebSocket client → ws.trademind.bot                            │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      EC2 SERVER (34.235.119.67)                     │
├─────────────────────────────────────────────────────────────────────┤
│  tastywork-trading-1/                                               │
│  ├── theta_monitor_continuous.py  ← 24/7 scheduler daemon           │
│  ├── run_theta_scheduler.py       ← Morning analysis @ 9:35 AM     │
│  ├── run_calendar_scheduler.py    ← Calendar spreads @ 3:50 PM     │
│  ├── websocket_server.py          ← Port 8003 (signals)            │
│  ├── tasty_api_server.py          ← Port 8002 (API)                │
│  └── ib_order_executor.py         ← IB paper trading               │
├─────────────────────────────────────────────────────────────────────┤
│  Docker Containers:                                                  │
│  ├── ib-gateway (Port 4004) - IB Gateway for market data            │
│  └── redis (Port 6379) - Signal caching                             │
└─────────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│   Interactive Brokers   │     │       Tastytrade        │
│   (Market Data + Paper) │     │    (Order Execution)    │
│   Port 4004             │     │    OAuth API            │
└─────────────────────────┘     └─────────────────────────┘
```

## Data Flow

### Signal Generation
```
1. Scheduler runs at scheduled time
2. Connect to IB Gateway for market data
3. Analyze symbols from THETA_UNIVERSE
4. Score opportunities using:
   - IV percentile
   - Technical indicators
   - Risk parameters
5. Generate signals for qualified puts
6. Publish to WebSocket (users) + Execute on IB Paper
```

### Order Execution (Target Allocation Sync)
```
1. User sees Signal Card (General Tier) showing Target % Allocations.
2. User clicks "Approve" (Advanced Tier) or Auto-Sync triggers.
3. Execution Engine Queries Account State:
   - Live Tastytrade API → Net Liquidating Value & Current Positions.
   - OR Shadow Ledger → User-managed Virtual Balance.
4. Delta Calculation:
   - Target Value = Net_Liq * Target_% (from Signal).
   - Delta Gap = Target Value - Current Holdings.
5. Order Composition: 
   - Converts Delta $ into integer Shares using live market quotes.
6. Execution:
   - Submits Limit Orders to Tastytrade API.
   - Notification sent to user with trade details.
```

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `theta_monitor_continuous.py` | EC2 | 24/7 daemon, calls scheduler |
| `run_theta_scheduler.py` | EC2 | Analysis + signal generation |
| `ib_data_provider.py` | Backend | Fetch data from IB Gateway |
| `ib_order_executor.py` | Backend | Place orders on IB Paper |
| `websocket_server.py` | EC2 | Real-time signal broadcasting |
| `SignalProvider.tsx` | Frontend | WebSocket subscription |
| `SignalCard.tsx` | Frontend | Signal display + approval |

## Configuration

### Critical Files
- `config.py` - All trading parameters, API endpoints
- `.env` - Secrets (Tastytrade creds, API keys)
- `THETA_UNIVERSE` - List of tradeable symbols (ETFs only)

### Ports
| Port | Service |
|------|---------|
| 4004 | IB Gateway (Docker) |
| 6379 | Redis |
| 8002 | Tasty API Server |
| 8003 | WebSocket Server |
| 8000 | IB-program-trading API (Docker) |
