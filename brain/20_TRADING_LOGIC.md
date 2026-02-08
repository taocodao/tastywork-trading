# Trading Logic - Theta & Calendar Strategies

## Theta Strategy (Cash-Secured Puts)

### Schedule
- **Morning Analysis**: 9:35 AM ET (market open + 5 min)
- **Position Monitoring**: Every 5 minutes during market hours
- **EOD Report**: 4:00 PM ET

### Entry Criteria
1. Symbol in THETA_UNIVERSE (ETFs only)
2. IV Percentile > threshold (default 30%)
3. Sufficient liquidity (volume, open interest)
4. Portfolio has room (< max positions, < max heat)

### Signal Generation Flow
```
1. theta_monitor_continuous.py runs 24/7
2. At 9:35 AM, calls run_theta_scheduler.py --once
3. Scheduler connects to IB Gateway for market data
4. Fetches option chains for THETA_UNIVERSE symbols
5. Filters puts by:
   - Delta: 0.20-0.30
   - DTE: 30-45 days
   - Premium: >= $1.00
6. Scores each opportunity
7. Generates entry signals
8. Publishes to WebSocket + executes on IB Paper
```

### Exit Criteria
- **Profit Target**: 50% of premium collected
- **Stop Loss**: 2x premium (200% loss)
- **Time Exit**: Close at 7 DTE to avoid gamma risk
- **Assignment Risk**: Close if delta > 0.60

## Calendar Strategy

### Schedule
- **Entry Window**: 3:50 PM ET (near market close)
- **Exit**: When short leg expires or at profit target

### Entry Criteria
1. Symbol in calendar watchlist (SPY, QQQ, IWM)
2. VOSS (Volatility Opportunity Score) threshold met
3. IV term structure favorable (backwardation)

### Spread Construction
- **Short Leg**: 3-5 DTE, ATM strike
- **Long Leg**: 10-14 DTE, same strike
- **Direction**: Based on AI directional predictor

## Dual Execution Model

```
Signal Generated
     │
     ├──→ WebSocket → Users → Approve → Tastytrade (production)
     │
     └──→ IB Paper Trading (validation/testing)
```

Both execution paths run automatically on every signal.

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| CancelledError | IB connection dropped | Retry with backoff |
| TimeoutError | IB Gateway slow | Increase timeout |
| Error 201 | Order rejected | Check buying power |
| Error 10147 | Symbol not found | Verify contract details |
