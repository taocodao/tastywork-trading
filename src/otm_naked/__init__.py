"""
OTM Naked Options Selling Strategy
====================================
ML-Optimized Deep Out-of-the-Money naked options selling strategy.

Architecture:
  - Universe Screener   : Pre-selected 35 liquid mega-caps + ETFs
  - Signal Engine       : 52W high/low proximity + RSI + IV composite
  - Entry Classifier    : XGBoost 2-stage win probability filter
  - Strike Selector     : Delta-based put/call strike selection via BS
  - Risk Manager        : 1% per-position, 2x credit stop-loss
  - Position Monitor    : Intra-trade exit triggers
  - Backtest Engine     : Walk-forward + Monte Carlo

Usage:
    from src.otm_naked.scanner import OTMNakedScanner
    scanner = OTMNakedScanner()
    signals = scanner.run_daily_scan()
"""
from .config import OTMNakedConfig, OTM_NAKED_UNIVERSE, OTM_NAKED_SECTORS

__version__ = "1.0.0"
__all__ = ["OTMNakedConfig", "OTM_NAKED_UNIVERSE", "OTM_NAKED_SECTORS"]
