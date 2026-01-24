# QUICK REFERENCE: EARNINGS AI IMPLEMENTATION 
## One-Pager for Antigravity Team

---

## THE PROBLEM
Current IB System: **Directional options trading** (calls/puts) based on RSI + AI signals
- **Gap:** No earnings awareness
- **Risk:** Calendar spreads lose 100% when earnings trigger IV crush
- **Opportunity:** Add earnings intelligence to improve win rate 75% → 85%+

---

## THE SOLUTION: 4-COMPONENT SYSTEM

### Component 1: Earnings Calendar Ingestion (`src/earnings_calendar.py`)
```
┌─────────────────────────────────┐
│  Fetch Earnings Dates           │
│  - Alpha Vantage (primary)      │
│  - Yahoo Finance (fallback)     │
│  - SEC EDGAR (precision)        │
│                                 │
│  Cache in PostgreSQL:           │
│  - announcement_date            │
│  - expected_move (historical)   │
│  - iv_rank_5y                   │
│  - previous_beat_miss           │
│                                 │
│  Update: Every hour (sync job)  │
└─────────────────────────────────┘
```

**Time to build:** 1 week

---

### Component 2: IV Crush ML Model (`src/iv_crush_predictor.py`)
```
Input (54 features):
├─ Technical: RSI, MACD, Bollinger Bands
├─ Volatility: IV, IV rank, IV percentile, VIX
├─ Earnings: Days to earnings, surprise magnitude
├─ Price: Beta, 20y volatility
└─ Market: Sector momentum, VIX

                    ↓

Random Forest Classifier (500 trees, depth 15)
Training: 45,000+ earnings events (5+ years)

                    ↓

Output (Confidence 0-100):
├─ IV Crush Magnitude (-10% to -50%)
├─ Crush Timing (0-2 hours post-announcement)
├─ Probability (0-100%)
└─ Expected Move vs Historical Move
```

**Performance Target:** 
- F1-Score: >0.82
- Accuracy: 78-85% within ±5% of actual crush
- Training time: 2-3 hours on modern CPU

**Time to build:** 2 weeks

---

### Component 3: Strategy Router (`src/earnings_strategy_router.py`)
```
Signal Input (Calendar Spread)
        │
        ├─ Days to Earnings < 7?
        │
        ├─ YES → Consult IV Predictor
        │        │
        │        ├─ Crush Prob > 70%?
        │        │  ├─ YES → ❌ REJECT (skip trade)
        │        │  └─ NO → ✅ APPROVE
        │        │
        │        └─ Expected Move < Historical Move?
        │           ├─ YES → Calendar favorable
        │           └─ NO → Consider REVERSE CALENDAR
        │
        └─ NO → ✅ APPROVE (earnings impact minimal)

Decision Matrix:
╔════════════════════════════════════════╗
║ Days | Crush Prob | Action             ║
╠════════════════════════════════════════╣
║ 1-3  | >70%       | ❌ REJECT          ║
║ 1-3  | 50-70%     | ⚠️ REDUCE 50%      ║
║ 1-3  | <50%       | ✅ APPROVE         ║
║ 4-7  | >80%       | ❌ REJECT          ║
║ 4-7  | 60-80%     | ⚠️ REDUCE 30%      ║
║ 4-7  | <60%       | ✅ APPROVE         ║
║ >7   | Any        | ✅ APPROVE         ║
╚════════════════════════════════════════╝
```

**Time to build:** 1 week

---

### Component 4: Enhanced Risk Manager (`src/earnings_risk_manager.py`)
```
Existing Formula:
Stop_Distance = k × Beta × VIX

NEW Earnings-Aware Formula:
Stop_Distance = k × Beta × VIX × Earnings_Vol_Factor

Where:
Earnings_Vol_Factor = {
    1.5 if 1 day before earnings
    1.3 if 2-3 days before
    1.1 if 4-7 days before
    1.0 if >7 days from earnings
}

Example:
AAPL: Beta 1.3, VIX 18, k 0.8, 3 days to earnings
Normal: 0.8 × 1.3 × 18 = 18.72%
With earnings: 0.8 × 1.3 × 18 × 1.3 = 24.34% (30% wider)
```

**Time to build:** 1 week

---

## ALTERNATIVE STRATEGIES

**When calendar spread is rejected:**

### Strategy A: Reverse Calendar Spread
```
Normal:  SELL short-term call, BUY long-term call (loses on IV crush)
Reverse: BUY short-term call, SELL long-term call (profits on IV crush)

Win rate: 55-65%
Risk: Defined (max loss = position value)
Best for: 1-2 days before earnings
```

### Strategy B: Long Straddle
```
When: Expected Move > Historical Move by >15%
Action: BUY ATM Call + BUY ATM Put (same strike, same expiry)

Win rate: 60-70%
Risk: Premium paid (defined)
Best for: Uncertain direction but expecting big move
```

### Strategy C: Skip Trade
```
When: IV Crush >75% AND Days < 2
Action: Wait for next signal

Rationale: Better to miss 1 trade than lose 50% on one
Avg 4-6 signals/month, can skip 1-2
```

---

## IMPLEMENTATION ROADMAP

```
┌─ Week 1-2: DATABASE & API ─────────────────────┐
│ ✓ Create earnings_calendar table               │
│ ✓ Build API client (Alpha Vantage, Yahoo, SEC) │
│ ✓ Setup hourly sync cron job                   │
│ ✓ Data validation framework                    │
└────────────────────────────────────────────────┘

┌─ Week 3-4: ML MODEL ──────────────────────────┐
│ ✓ Feature engineering (54 dimensions)          │
│ ✓ Load 5+ years historical earnings data       │
│ ✓ Train Random Forest model                    │
│ ✓ Backtest on historical earnings             │
│ ✓ Achieve F1-score >0.82                       │
└────────────────────────────────────────────────┘

┌─ Week 5-6: INTEGRATION ───────────────────────┐
│ ✓ Modify trading_system.py (add earnings check)│
│ ✓ Implement strategy router                    │
│ ✓ Update risk manager                          │
│ ✓ Integrate with signal generators             │
│ ✓ Dashboard updates                            │
└────────────────────────────────────────────────┘

┌─ Week 7-8: TESTING & DEPLOYMENT ─────────────┐
│ ✓ Unit tests (95% coverage)                    │
│ ✓ Integration tests                            │
│ ✓ Paper trading (2+ weeks)                     │
│ ✓ Production deployment                        │
│ ✓ Monitoring & alerts setup                    │
└────────────────────────────────────────────────┘
```

---

## KEY METRICS

**Performance Targets:**

| Metric | Target | Impact |
|--------|--------|--------|
| **Prediction Accuracy** | 78-85% within ±5% | Core model quality |
| **IV Crush Detection** | >90% | Avoid big losses |
| **False Positives** | <15% | Don't skip valid trades |
| **Win Rate Improvement** | 75% → 83%+ | +8% absolute |
| **Sharpe Ratio** | >1.8x | Risk-adjusted return |
| **Major Losses Avoided** | 10-15 trades/year | Save $2k-5k/year |

---

## CRITICAL SUCCESS FACTORS

1. **Real Earnings Data**
   - Must have accurate announcement dates
   - Use API priority: SEC > Alpha Vantage > Yahoo
   - Validate against official company calendars

2. **ML Model Quality**
   - Train on actual earnings outcomes (not simulated)
   - Validate F1-score >0.82 before production
   - Monthly retraining as new earnings data arrives

3. **Integration with Existing System**
   - Minimal changes to trading_system.py
   - Respect existing risk manager logic
   - Add earnings as "override layer" (not replacement)

4. **User Communication**
   - Show users WHY trades are rejected (earnings info)
   - Explain alternative strategies (reverse calendar, straddle)
   - Build confidence in model predictions

---

## DATABASE SCHEMA (PostgreSQL)

```sql
CREATE TABLE earnings_calendar (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    announcement_date TIMESTAMP NOT NULL,
    expected_move FLOAT,
    historical_move FLOAT,
    iv_rank_5y FLOAT,
    previous_beat_miss VARCHAR(10),
    previous_surprise FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, announcement_date)
);

CREATE TABLE iv_crush_predictions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    prediction_date TIMESTAMP,
    days_to_earnings INT,
    predicted_crush_pct FLOAT,
    crush_probability FLOAT,
    confidence_score FLOAT,
    model_version VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE earnings_trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10),
    trade_date TIMESTAMP,
    days_to_earnings INT,
    strategy_type VARCHAR(30),
    decision_reason VARCHAR(255),
    actual_crush FLOAT,
    position_outcome FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## DEPENDENCIES (Python)

```
Core ML:
├─ scikit-learn>=1.0  (Random Forest)
├─ xgboost>=1.5      (Gradient Boosting)
├─ tensorflow>=2.8   (Optional: Neural Net)
└─ joblib>=1.0       (Model serialization)

Data:
├─ pandas>=1.3
├─ numpy>=1.20
├─ psycopg2>=2.9     (PostgreSQL)
└─ requests>=2.28    (API calls)

APIs:
├─ alpha_vantage
├─ yfinance
└─ sec-edgar

Testing:
├─ pytest>=7.0
├─ pytest-cov>=4.0
└─ hypothesis>=6.0   (Property-based testing)
```

---

## QUESTIONS FOR ANTIGRAVITY

1. **Database:** PostgreSQL, MongoDB, or other?
2. **Model Serving:** TensorFlow Serving, triton, or custom?
3. **Deployment:** AWS Lambda, GCP, Kubernetes?
4. **ML Framework:** scikit-learn/XGBoost (recommended) or TensorFlow?
5. **Timeline:** Can deliver in 6-8 weeks?
6. **Budget:** Any constraints on API costs?

---

## SUCCESS CRITERIA (EXIT CONDITIONS)

✅ **Go-Live Requirements:**
1. F1-score ≥0.82 on historical earnings
2. Win rate ≥80% in paper trading (50+ trades)
3. <5% false positive rate (avoid good trades)
4. Sharpe ratio >1.5 in backtesting
5. All unit/integration tests passing
6. Dashboard displaying earnings info
7. 2+ weeks successful paper trading
8. Monitoring & alerts functional

**If any criterion not met → Fix before going live**

---

**READY FOR DEVELOPMENT SPRINT**

Next Step: Antigravity Sprint Planning (Estimate: 8 weeks)

