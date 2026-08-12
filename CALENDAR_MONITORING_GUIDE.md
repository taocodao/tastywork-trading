# Calendar Spread AI Enhancement - User Guide

**Version:** 1.0  
**Date:** February 3, 2026  
**Status:** Implemented

---

## Overview

The Calendar Spread AI Enhancement adds intelligent entry selection, earnings protection, 
and continuous monitoring to the existing calendar spread trading system. This follows 
the same successful pattern as the Theta Sprint implementation.

## What's Been Implemented

### 1. VOSS Liquidity Filter (`src/calendar_spreads/voss_filter.py`)

Filters options for liquidity before trading:
- **Open Interest**: Minimum 1,000 contracts
- **Volume**: Minimum 500 daily
- **Bid-Ask Spread**: Maximum 10%
- **Scoring**: Quality score for prioritization

```python
from src.calendar_spreads import VOSSLiquidityFilter

filter = VOSSLiquidityFilter()
liquid_options = filter.filter_options_chain(raw_chain)
```

### 2. DTE Selector (`src/calendar_spreads/dte_selector.py`)

Selects optimal expiration dates based on IV regime:
- **High IV (>70)**: 7/30 DTE (faster mean reversion)
- **Normal IV (30-70)**: 10/40 DTE (standard)
- **Low IV (<30)**: 14/45 DTE (more time needed)

```python
from src.calendar_spreads import DTESelector

selector = DTESelector()
short_dte, long_dte = selector.select_optimal_dte(iv_rank=65.0)
# Returns: (10, 40) for normal IV
```

### 3. Strike Selector (`src/calendar_spreads/strike_selector.py`)

Delta-based strike selection for maximum theta:
- **Neutral**: 0.45-0.55 delta (ATM)
- **Bullish**: 0.55-0.65 delta
- **Bearish**: -0.45 to -0.55 delta

```python
from src.calendar_spreads import CalendarStrikeSelector

selector = CalendarStrikeSelector()
strike = selector.select_strike(chain, current_price=450.0, strategy_bias='neutral')
```

### 4. Earnings Intelligence (`src/calendar_spreads/earnings_intelligence.py`)

Protects against IV crush around earnings:
- **>14 days to earnings**: APPROVE
- **7-14 days, high crush**: REVERSE_CALENDAR
- **3-7 days, moderate**: REDUCE_SIZE
- **≤3 days, high crush**: REJECT

```python
from src.calendar_spreads import EarningsStrategyRouter, StrategyDecision

router = EarningsStrategyRouter()
decision = router.decide(symbol='AAPL', days_to_earnings=5, current_iv_rank=75.0)

if decision.action == StrategyDecision.REJECT:
    print(f"Skip trade: {decision.reason}")
```

### 5. Signal Generator (`src/calendar_spreads/signal_generator.py`)

Combines all components to generate validated entry signals:

```python
from src.calendar_spreads import CalendarSignalGenerator

generator = CalendarSignalGenerator()
signals = generator.generate_signals(
    symbol='SPY',
    stock_price=450.0,
    iv_rank=65.0,
    options_data=chain_data,
    expirations=available_expirations
)

for signal in signals:
    print(f"{signal.symbol} ${signal.strike} calendar")
    print(f"  Cost: ${signal.net_debit:.2f}")
    print(f"  Theta: ${signal.theta_edge:.2f}/day")
    print(f"  Confidence: {signal.confidence_score:.0f}")
```

### 6. Continuous Monitor (`calendar_monitor_continuous.py`)

24/7 monitoring service:
- **3:50 PM ET**: Entry scan (end-of-day IV)
- **9:35 AM ET**: Exit/adjustment scan
- **Every 5 min**: Position monitoring

---

## Deployment Guide

### Step 1: Sync Files to EC2

```bash
# From local machine
scp -i tradecoin-bot-key.pem \
    calendar_monitor_continuous.py \
    calendar-monitor.service \
    deploy_calendar_monitor.sh \
    ubuntu@ec2-34-203-194-137.compute-1.amazonaws.com:~/tastywork-trading/
```

### Step 2: Deploy Service

```bash
# SSH to EC2
ssh -i tradecoin-bot-key.pem ubuntu@ec2-34-203-194-137.compute-1.amazonaws.com

# Make script executable
chmod +x ~/tastywork-trading/deploy_calendar_monitor.sh

# Run deployment
cd ~/tastywork-trading
./deploy_calendar_monitor.sh
```

### Step 3: Verify Service

```bash
# Check status
sudo systemctl status calendar-monitor

# Watch logs
tail -f ~/tastywork-trading/calendar_monitor.log
```

---

## Configuration

### Generator Configuration

```python
from src.calendar_spreads import CalendarSignalGenerator, GeneratorConfig

config = GeneratorConfig(
    min_confidence_score=60.0,      # Minimum confidence to generate signal
    min_liquidity_score=0.3,        # Minimum liquidity score
    min_theta_edge=0.50,            # Minimum daily theta ($)
    default_profit_target_pct=35.0, # 35% profit target
    default_stop_loss_pct=50.0,     # 50% stop loss
    max_contracts=5,                 # Maximum contracts per trade
    max_risk_per_trade=500.0        # Maximum risk per trade ($)
)

generator = CalendarSignalGenerator(config=config)
```

### Earnings Router Configuration

```python
from src.calendar_spreads import EarningsStrategyRouter, EarningsRouterConfig

config = EarningsRouterConfig(
    safe_days=14,           # No concern if earnings >14 days
    reject_days=3,          # Reject if ≤3 days to earnings with high crush
    reject_crush_prob=0.70, # Threshold for rejection
    reduce_days=7,          # Reduce size if ≤7 days
    reduce_crush_prob=0.50, # Threshold for size reduction
)

router = EarningsStrategyRouter(config=config)
```

---

## Testing

### Unit Tests

```bash
# Run all calendar spread tests
cd ~/tastywork-trading
python -m pytest tests/calendar_spreads/ -v

# Test specific component
python -m pytest tests/calendar_spreads/test_voss_filter.py -v
```

### Manual Testing

```python
# Test signal generation
python -c "
from src.calendar_spreads import CalendarSignalGenerator
gen = CalendarSignalGenerator()
print('Generator initialized successfully')
"

# Test earnings router
python -c "
from src.calendar_spreads import EarningsStrategyRouter
router = EarningsStrategyRouter()
decision = router.decide('SPY', days_to_earnings=5)
print(f'Decision: {decision.action.value} - {decision.reason}')
"
```

---

## Monitoring

### Log Files

| File | Contents |
|------|----------|
| `calendar_monitor.log` | Main service logs |
| `calendar_monitor_error.log` | Error logs only |
| `logs/calendar_spreads.log` | Trade-specific logs |

### Key Metrics to Watch

1. **Signal Generation Rate**: 2-5 signals per day
2. **Confidence Scores**: Target >70
3. **Win Rate**: Target >75%
4. **Theta Capture**: Actual vs expected

### Systemd Commands

```bash
# Status
sudo systemctl status calendar-monitor

# Logs (live)
sudo journalctl -u calendar-monitor -f

# Restart
sudo systemctl restart calendar-monitor

# Stop
sudo systemctl stop calendar-monitor
```

---

## Integration with Existing Systems

### Works With:
- **IB Gateway**: Uses existing IB connection for data and execution
- **Theta Sprint**: Runs alongside (different schedule hours)
- **WebSocket signals**: Publishes to `calendar_spread` channel
- **Position tracker**: Uses existing database

### Position Tracking

Calendar positions are tracked in `calendar_positions.json`:

```json
{
  "positions": [
    {
      "symbol": "SPY",
      "strike": 450.0,
      "short_expiry": "2026-02-07",
      "long_expiry": "2026-02-21",
      "entry_price": 2.50,
      "entry_date": "2026-02-03T15:50:00",
      "quantity": 2,
      "profit_target": 3.375,
      "stop_loss": 1.25
    }
  ]
}
```

---

## Troubleshooting

### Issue: "No liquid options found"

**Cause**: VOSS filter is rejecting all options  
**Solution**: 
1. Check if market is open
2. Verify data provider connection
3. Lower minimum thresholds temporarily for testing

### Issue: "Strike not available in both chains"

**Cause**: Different strikes available at different expirations  
**Solution**: Use common_strikes intersection or widen strike search

### Issue: "Confidence score too low"

**Cause**: One or more components scoring poorly  
**Solution**: Check individual component scores in logs

### Issue: Service keeps restarting

**Cause**: Python errors or connection issues  
**Solution**:
```bash
# Check error log
tail -100 ~/tastywork-trading/calendar_monitor_error.log

# Check systemd status
sudo systemctl status calendar-monitor --no-pager -l
```

---

## Future Enhancements (ML Layer)

The following ML models are planned for future implementation:

1. **LSTM Volatility Forecaster**: Predict IV term structure
2. **RL Strike Agent**: PPO-based strike/size optimization
3. **IV Crush Predictor**: Random Forest F1 >0.82

These will enhance the rule-based system currently in place.

---

## Files Created

```
src/calendar_spreads/
├── voss_filter.py           # VOSS liquidity filtering
├── dte_selector.py          # DTE selection algorithm
├── strike_selector.py       # Strike selection algorithm
├── earnings_intelligence.py # Earnings strategy router
├── signal_generator.py      # Signal generation
├── __init__.py             # Updated exports
├── position_monitor.py     # (existing)
└── stop_manager.py         # (existing)

Root:
├── calendar_monitor_continuous.py  # 24/7 monitoring service
├── calendar-monitor.service        # Systemd service file
├── deploy_calendar_monitor.sh      # Deployment script
└── CALENDAR_MONITORING_GUIDE.md    # This guide

implementation_notes/
└── Calendar_Spread_AI_Implementation_Plan.md  # Detailed plan
```

---

## Support

For issues or questions:
1. Check logs first (`calendar_monitor.log`)
2. Review this guide
3. Consult the implementation plan
