# ZEBRA Strategy Implementation

This directory contains the core implementation of the ZEBRA (Zero Extrinsic Back Ratio) strategy, including ML optimization and advanced backtesting engines.

## Key Components

### Core Execution
- **`monitor.py`**: Main service loop. Runs continuously to scan for opportunities and manage positions.
  - Run via: `python3 -m src.zebra.monitor` from the project root.
- **`client.py`**: Extends `TastytradeClient` with ZEBRA-specific order logic.
- **`construction_engine.py`**: Logic to identify optimal strike/expiry combinations.
- **`lifecycle_engine.py`**: Decision tree for managing open positions.

### Analysis & Optimization (New)
- **`ml_optimizer.py`**: Bayesian parameter optimization using `scikit-optimize`. Finds the best Profit Target, Stop Loss, and Trailing Stop settings.
  - Run via: `python -m src.zebra.ml_optimizer`
- **`backtest_engine.py`**: Enhanced walk-forward portfolio backtester. Simulates realistic trading with position sizing and advanced exits.
  - Run via: `python -m src.zebra.backtest_engine`
- **`exit_engine.py`**: Advanced exit strategies logic (Trailing Stop, ATR Stop, Momentum Exit).
- **`security_scorer.py`**: Multi-factor scoring engine (Trend, Momentum, Volatility, Volume).
- **`entry_timing.py`**: Regime-aware entry timing using ATR as a volatility proxy.

### Legacy / Reference
- **`backtest.py`**: Original simple backtester (kept for baseline comparison).
- **`research.py`**: Live AI selection tool leveraging Perplexity API.

## Usage Guide

### 1. Optimize Strategy Parameters
Run the ML optimizer to find the best parameters for the current market regime:
```bash
python -m src.zebra.ml_optimizer
```
*Output: Recommended Profit Target, Stop Loss, Trailing Stop %*

### 2. Run Enhanced Backtest
Simulate portfolio performance using the advanced engine:
```bash
python -m src.zebra.backtest_engine
```
*Output: Win Rate, Sharpe Ratio, Detailed Trade Log*

### 3. Live Trading Monitor
Start the continuous monitor for live trading:
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 -m src.zebra.monitor
```

## Configuration
Settings are managed in `config.py` (ZEBRA section), but the optimization process can override these dynamically during backtesting.
