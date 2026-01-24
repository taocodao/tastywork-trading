# ANTIGRAVITY_DEV_BRIEF.md
## Vertical Spreads Implementation - Quick Reference for Development

**Date:** January 19, 2026  
**For:** Antigravity Development Team  
**Duration:** 8 weeks  
**Budget:** ~$40K-60K  

---

## MISSION

Add **vertical spread** trading capability to the existing AI Calendar Spread system.

- **What:** Vertical spreads (bull call, bear put, etc.)
- **When:** 7-21 days to expiration (close to expiration)
- **Where:** Tastytrade API (OAuth)
- **Who:** Customers with $2K+ accounts & options approval level 2+
- **Why:** Higher probability of profit, capital efficient, complements calendar spreads

---

## HIGH-LEVEL FLOW

```
Stock Data (Real-Time)
    ↓
Direction Prediction (ML)
├─ RSI mean reversion
├─ Bollinger Bands
├─ Moving averages
└─ Ensemble voting → Direction (BULL/BEAR/NEUTRAL) + Confidence (0-100)
    ↓
[If Confidence > 60 & Direction != NEUTRAL]
    ↓
Strike Selection
├─ Get options chain from Tastytrade
├─ Calculate implied move (Black-Scholes)
├─ Select strikes based on confidence level
└─ Determine contract count based on account size
    ↓
Suitability Check
├─ Account size ≥ $2,000? ✓
├─ Options level ≥ 2? ✓
├─ Max loss ≤ 2% of account? ✓
└─ Can trade? → YES/NO
    ↓
Execute Order (if suitable)
├─ Place multi-leg order to Tastytrade
├─ Log trade to audit trail
├─ Send confirmation to customer
└─ Set up stops
    ↓
Monitor Position
├─ Track P&L
├─ Check exit rules (profit target, stop loss, DTE)
└─ Execute exit when triggered
```

---

## DEVELOPMENT PHASES (8 Weeks)

### Phase 1: ML Direction Predictor (Week 1-2)

**Goal:** Build `VerticalSpreadDirectionPredictor` class

**Key Methods:**
- `calculate_direction_signal(stock_data)` → Main entry point
- `_rsi_signal(rsi)` → Returns 1/0/-1
- `_bollinger_signal(price, bb_upper, bb_mid, bb_lower)` → Returns 1/0/-1
- `_ma_signal(price, sma_20, sma_50, sma_200)` → Returns 1/0/-1
- `_ensemble_vote(signals)` → Combines votes → direction + confidence

**Tests to Pass:**
- Test with oversold stock (RSI < 30) → BULL signal
- Test with overbought stock (RSI > 70) → BEAR signal
- Test with trending stock → Direction matches trend
- Test accuracy on historical data (target: 65-75%)

---

### Phase 2: Strike Selection (Week 3)

**Goal:** Build `VerticalSpreadSelector` class

**Key Methods:**
- `select_spread(stock_data, direction_signal, account_data)` → Main entry
- `_select_bull_call_spread(...)` → Buy lower, sell higher call
- `_select_bear_call_spread(...)` → Sell higher, buy lower call
- `_calculate_implied_move(price, iv, dte)` → Black-Scholes approx
- `_calculate_contracts(max_loss, account_size, risk_tol)` → Sizing logic

**Rules to Implement:**
- Expiration: 7-21 DTE (prefer 14 DTE)
- Strike width: $5 standard (adjust based on price)
- Risk sizing: Max 2% of account per trade
- Confidence-based strike selection:
  - High (75+): Wider spreads (higher risk/reward)
  - Medium (60-75): Standard width
  - Low (<60): Skip

---

### Phase 3: Merge with Existing System (Week 4)

**Goal:** Integrate vertical signals with calendar spread signals

**File:** `combined_signal_generator.py`

```python
class CombinedSignalGenerator:
    def generate_signals(self, stock_data, account_data):
        signals = []
        
        # Calendar spreads (existing)
        cal_sig = self.calendar_gen.generate(stock_data)
        if cal_sig and cal_sig["confidence"] > 60:
            signals.append({"type": "CALENDAR_SPREAD", ...})
        
        # Vertical spreads (new)
        dir_sig = self.vertical_gen.calculate_direction_signal(stock_data)
        if dir_sig["confidence"] > 60:
            vert_spread = self.vertical_selector.select_spread(...)
            signals.append({"type": "VERTICAL_SPREAD", ...})
        
        return signals
```

---

### Phase 4: Execution Layer (Week 5)

**Goal:** Place multi-leg orders to Tastytrade

**Update File:** `order_executor.py`

- Multi-leg order API integration
- OAuth authentication
- Error handling
- Audit trail logging

---

### Phase 5: Risk Management & Suitability (Week 6)

**Files:**
- `suitability_validator.py` - Pre-trade checks
- `vertical_stop_manager.py` - Position exits

**Key Logic:**
- Account minimum: $2,000
- Options level: 2+
- Max loss: 2% of account
- Stop logic: 50% max loss trigger, 75% profit target

---

### Phase 6-7: Testing & Compliance (Week 7-8)

**Unit Tests**
- Direction predictor accuracy
- Strike selection logic
- Suitability validation
- Stop loss calculation

**Integration Tests**
- End-to-end: signal → order → Tastytrade
- API authentication
- Multi-leg order placement

**Paper Trading**
- 14+ days with real market data
- Track: Win rate, avg loss, max loss
- Monitor for errors

---

## CODE STRUCTURE

```
src/
├── direction_predictor.py (300 lines)
├── vertical_spread_selector.py (400 lines)
├── combined_signal_generator.py (100 lines)
├── vertical_stop_manager.py (200 lines)
├── suitability_validator.py (250 lines)
└── order_executor_vertical.py (150 lines)

tests/
├── test_direction_predictor.py (300 lines)
├── test_vertical_selector.py (250 lines)
├── test_suitability.py (150 lines)
├── test_integration.py (200 lines)
└── test_compliance.py (100 lines)
```

**Total Dev:** ~2,000 lines new code, ~1,000 lines tests

---

## SUCCESS CRITERIA

### Technical
- ✅ Win rate: 65-75%
- ✅ Avg profit: $50-100 per trade
- ✅ Max loss hit rate: <2%
- ✅ System uptime: >99.5%
- ✅ API latency: <100ms

### Compliance
- ✅ Zero regulatory complaints
- ✅ 100% suitability validation
- ✅ 100% audit trail completeness
- ✅ Circuit breaker: Never exceeded
- ✅ Zero unintended orders

### Business
- ✅ 30% of existing users adopt
- ✅ 50+ new customers
- ✅ $5K-10K monthly revenue (first month)

---

## KNOWN RISKS & MITIGATIONS

| Risk | Mitigation |
|------|-----------|
| **Implied move calc wrong** | Backtest heavily, manual review |
| **Tastytrade API changes** | Monitor API docs, test after updates |
| **Customer loses money** | Suitability checks, education, stop losses |
| **System places 1000 orders** | Circuit breaker, extensive testing |
| **Options chain unavailable** | Fallback to calendar spreads only |
| **High volatility crushes profits** | May reduce trade frequency automatically |

---

## TIMELINE SUMMARY

```
Week 1-2:  ML Direction Predictor ✓
Week 3:    Strike Selection ✓
Week 4:    System Integration ✓
Week 5:    Execution Layer ✓
Week 6:    Risk Management ✓
Week 7:    Unit & Integration Tests ✓
Week 8:    Compliance Review & Beta Launch ✓
Week 9:    Beta Monitoring
Week 10:   Production Rollout
```

---

**Let's build this!** 🚀
