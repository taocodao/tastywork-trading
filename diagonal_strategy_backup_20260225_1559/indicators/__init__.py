"""
ML Indicators for TQQQ Diagonal Strategy
==========================================
Ported from IB-program-trading/src/ai_signal_generator.py and
IB-program-trading/src/trend_speed.py — zero extra dependencies (numpy + pandas only).
"""
from .ml_indicators import (
    calculate_atr,
    kmeans_cluster_1d,
    calculate_adaptive_supertrend,
    calculate_optimal_rsi,
    calculate_ml_mfi,
    SuperTrendResult,
    RSIResult,
    MFIResult,
    TrendDirection,
    VolatilityLevel,
)
from .trend_speed import TrendSpeedAnalyzer, ExitStage, TrendSpeedResult

__all__ = [
    'calculate_atr',
    'kmeans_cluster_1d',
    'calculate_adaptive_supertrend',
    'calculate_optimal_rsi',
    'calculate_ml_mfi',
    'SuperTrendResult',
    'RSIResult',
    'MFIResult',
    'TrendDirection',
    'VolatilityLevel',
    'TrendSpeedAnalyzer',
    'ExitStage',
    'TrendSpeedResult',
]
