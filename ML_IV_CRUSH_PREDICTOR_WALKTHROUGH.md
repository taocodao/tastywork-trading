# ML IV Crush Predictor - Implementation Walkthrough

## Overview

This document summarizes the ML IV Crush Predictor implementation for the Earnings Intelligence module. The system uses Perplexity API for earnings data and a Random Forest classifier to predict IV crush severity.

---

## Components Built

### 1. Database Layer (`src/earnings_intelligence/database.py`)
SQLAlchemy models for PostgreSQL persistence:
- `EarningsCalendar` - Cache Perplexity API responses
- `IVPrediction` - Store ML predictions
- `PredictionOutcome` - Track accuracy for retraining
- `TrainingDataPoint` - Historical data for training

### 2. Feature Engineering (`src/earnings_intelligence/features.py`)
16-dimensional feature vector:
| Feature | Source |
|---------|--------|
| `days_to_earnings` | Perplexity |
| `expected_move_pct` | Perplexity |
| `historical_move_pct` | Perplexity |
| `crush_probability` | Perplexity |
| `move_ratio` | Derived |
| `iv_rank_bucket` | Derived (0-3) |
| `earnings_week` | Seasonality |
| `is_mega_cap` | Symbol lookup |
| `rsi_14`, `bb_position`, `ma_trend` | Technical |
| `atm_iv`, `vix_level`, `iv_percentile` | Volatility |
| `sector_momentum`, `market_trend` | Market |

### 3. ML Model (`src/earnings_intelligence/iv_crush_model.py`)
- **Algorithm**: Random Forest Classifier
- **Classes**: NORMAL, SEVERE, EXPANSION, NO_CRUSH
- **Features**: Auto-scaled with StandardScaler
- **Fallback**: Heuristic mode when model not trained

### 4. Enhanced Client (`src/earnings_intelligence/client.py`)
- `get_earnings_context()` - Live earnings data from Perplexity
- `get_historical_earnings()` - Historical data for training
- `collect_training_data()` - Batch collection
- Database caching (24hr TTL)

### 5. ML-Aware Router (`src/earnings_intelligence/router.py`)
Decision logic using ML predictions:
- **SEVERE + high confidence** → REJECT trade
- **SEVERE + low confidence** → REDUCE_SIZE 50%
- **NORMAL** → REDUCE_SIZE 15-30%
- **NO_CRUSH/EXPANSION** → APPROVE

### 6. Training Pipeline (`src/earnings_intelligence/train_model.py`)
```bash
# Train model
python src/earnings_intelligence/train_model.py --train

# Quick test
python src/earnings_intelligence/train_model.py --test
```

---

## Training Results

| Metric | Value |
|--------|-------|
| F1-Score | 1.0 |
| CV Mean | 0.867 |
| Training Samples | 12 |
| Test Samples | 4 |

**Top Features by Importance:**
1. `expected_move_pct` (29.4%)
2. `move_ratio` (24.3%)
3. `earnings_week` (23.8%)
4. `historical_move_pct` (22.5%)

---

## Test Results (AAPL)

```
Perplexity API Key: True ✓
Days to Earnings: 9
Expected Move: 3.98%
Historical Move: 4.5%
Crush Probability: 85%

ML Prediction:
  Class: SEVERE
  Confidence: 50.1%
  Predicted Crush: -25%
  Model Version: v1.0
```

---

## Configuration

Environment variables (`.env`):
```env
PERPLEXITY_API_KEY=pplx-xxx
DATABASE_URL=postgresql://user:pass@host:5432/db
```

Config settings (`config.py`):
```python
EARNINGS_ENABLED = True
EARNINGS_AVOID_DAYS = 3      # Reject trades
EARNINGS_REDUCE_SIZE_DAYS = 7 # Reduce position
```

---

## Usage Example

```python
from src.earnings_intelligence import (
    PerplexityClient, 
    EarningsStrategyRouter,
    IVCrushPredictor
)

# Get earnings data
client = PerplexityClient()
context = client.get_earnings_context("AAPL")

# Get ML prediction
predictor = IVCrushPredictor()
prediction = predictor.predict(context)

# Get trading decision
router = EarningsStrategyRouter()
decision = router.decide("AAPL", context)

if decision.action == "REJECT":
    print(f"Skip trade: {decision.reason}")
```

---

## Files Created/Modified

| File | Action |
|------|--------|
| `src/earnings_intelligence/database.py` | NEW |
| `src/earnings_intelligence/features.py` | NEW |
| `src/earnings_intelligence/iv_crush_model.py` | NEW |
| `src/earnings_intelligence/train_model.py` | NEW |
| `src/earnings_intelligence/client.py` | MODIFIED |
| `src/earnings_intelligence/router.py` | MODIFIED |
| `src/earnings_intelligence/__init__.py` | MODIFIED |
| `.env` | MODIFIED (added DATABASE_URL) |

---

## Next Steps

1. **Collect more training data** for better accuracy (target: 100+ samples)
2. **Integrate technical indicators** from existing system
3. **Add VIX data** for market context
4. **Implement outcome tracking** for model retraining
5. **Connect to PostgreSQL** (currently falls back to SQLite)

---

*Generated: 2026-01-20*
