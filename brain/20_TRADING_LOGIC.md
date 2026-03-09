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

## TQQQ TurboCore Strategy

### Core Logic
TurboCore is a dynamic asset allocation strategy that rebalances daily between **TQQQ (3x), QLD (2x), QQQ (1x), and SGOV (Cash)** based on a combination of technical gates and Machine Learning regimes.

- **Primary Trend Gate**: SMA200 (Risk-On if Price > SMA200).
- **ML Regimes**: BULL, BEAR, SIDEWAYS (calculated via HMM and XGBoost signal scoring).

### Strategic Enhancements (Researched Mar 2026)
The following safety and performance enhancements were implemented in the `_enhanced` laboratory branch and verified via backtesting:

1.  **ATH Drawdown Context**: Uses drawdown from All-Time High (ATH) as a feature to distinguish between "temporary pullbacks" and "deep crashes."
2.  **High-Volume Reversal (Distribution Days)**: Spots institutional selling near ATH (Price near ATH + High Volume + Bearish Candle) as an early warning signal.
3.  **T+1 Execution Delay**: Enforces a 1-day cooling-off period after a "sell" or "reduce risk" signal before allowing a new "buy," preventing choppy whipsaws.
4.  **Momentum Slope Confirmation**: Require the 20-day SMA slope to be positive before transitioning from a Bearish to a Bullish state.
5.  **Deep-Crash Aggressive Allocation**: Threshold-based buying (e.g., QQQ Drawdown > 30% from ATH) triggers aggressive TQQQ exposure (up to 80%) regardless of standard trend gates, provided ML confidence is high.
6.  **10% Strategic Reserve**: Maintains a permanent 10% SGOV allocation that is only deployed during extreme "Deep-Crash" scenarios.

### Reversion Status (Mar 09, 2026)
The production codebase currently uses the **Stable Baseline** version. The enhancements are documented and preserved in the research branch but are not currently live-trading to minimize variance before market open.
