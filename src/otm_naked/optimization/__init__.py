"""
OTM Naked Options — Monte Carlo Optimization Framework
========================================================
Phases:
  1. sbb_generator.py   — Stationary Block Bootstrap path generator
  2. fast_simulator.py  — Vectorized NumPy backtesting engine
  3. stress_tester.py   — Heston + Jump-Diffusion synthetic crisis paths
  4. optuna_study.py    — Bayesian Optimization (Sortino, max drawdown)
  5. validation.py      — Deflated Sharpe Ratio + Walk-Forward reporting
"""
