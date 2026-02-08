# Backend Design - tastywork-trading-1

## Overview
Python backend for options trading automation, signals, and broker integrations.

## Key Services

### 1. Theta Monitor (`theta_monitor_continuous.py`)
- Runs 24/7 as daemon
- Triggers scheduled actions at specific times
- Manages the main event loop

### 2. Theta Scheduler (`run_theta_scheduler.py`)
- Morning analysis at 9:35 AM
- Scans THETA_UNIVERSE for opportunities
- Generates and publishes signals
- Places IB paper trades

### 3. Calendar Scheduler (`run_calendar_scheduler.py`)
- Entry window at 3:50 PM
- Uses AI for direction prediction
- Constructs calendar spreads

### 4. WebSocket Server (`websocket_server.py`)
- Port 8003
- Broadcasts signals in real-time
- Channels: `theta_entry`, `theta_exit`, `calendar_spread`

### 5. Tasty API Server (`tasty_api_server.py`)
- Port 8002
- REST API for frontend
- Handles signal approval, positions, accounts

## Data Models

### Signal
```python
{
    "id": "uuid",
    "symbol": "SPY",
    "strategy": "theta" | "calendar",
    "action": "SELL_TO_OPEN" | "BUY_TO_CLOSE",
    "strike": 500.0,
    "expiration": "2026-03-15",
    "premium": 2.50,
    "confidence": 0.85,
    "timestamp": "2026-02-05T09:35:00Z"
}
```

### Position
```python
{
    "symbol": "SPY",
    "option_symbol": "SPY260315P00500000",
    "entry_price": 2.50,
    "current_price": 1.25,
    "pnl": 125.00,
    "pnl_pct": 50.0,
    "status": "open" | "closed"
}
```

## Integration Points

| Service | Protocol | Purpose |
|---------|----------|---------|
| IB Gateway | TCP/4004 | Market data, Greeks |
| Tastytrade | HTTPS | Order execution |
| Redis | TCP/6379 | Signal caching |
| Frontend | WebSocket | Real-time updates |
