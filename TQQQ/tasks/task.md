# Unified TQQQ Strategy — 3-Layer Implementation

## Deep Performance Evaluation
- [x] Review all backup backtest scripts and results
- [x] Compare TQQQ strategies and identify best approach
- [x] Perplexity validation of return expectations
- [x] Write comprehensive strategy evaluation

## Implementation Plan
- [x] Design 3-layer architecture (Theta + Swing + Dynamic Sizing)
- [x] Map existing components for reuse
- [x] Get user approval on unified plan

## Implementation (Phases 4-5 Backend)
- [x] Step 1: `order_manager.py` — Add call spread methods
- [x] Step 2: `signal_publisher/tqqq.py` — Add call spread signals
- [x] Step 3: `position_tracker.py` — Support all position types + pools
- [x] Step 4: `tqqq_risk_manager.py` — Capital pool budgeting
- [x] Step 5: `data_pipeline.py` — Support call chain fetching
- [x] Step 6: `config.py` — Unified parameters
- [x] Step 7: `run_tqqq_scheduler.py` — Wire all 3 layers

## Verification
- [x] Run Scenario B backtest (confirm 98.3% baseline)
- [x] Phase 1: Fix import verification test
- [x] Phase 2: Create `tqqq_3layer_backtest.py` (all 3 layers)
- [x] Phase 3: Unit tests for CrashGuard and SwingExitEngine
- [x] Integration test: scheduler generates theta + swing signals
- [x] Paper trading verification (ready to enable in config)

## Backtest Refinement 
- [ ] Implement fixed position sizing for layer 2
- [ ] Add 7-day cooldown between entries
- [ ] Use RSI cross-under trigger instead of level trigger
- [ ] Model Black-Scholes pricing for the diagonal spread
- [ ] Add randomized/filtered CrashGuard rejection
- [ ] Enforce Max 1 concurrent swing trade
