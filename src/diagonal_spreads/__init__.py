"""
Diagonal Spreads Module
=======================

Combines Vertical Spread direction prediction with Calendar Spread DTE selection
to create diagonal spreads (Poor Man's Covered Call/Put).

Structure:
- Direction prediction from vertical_spreads.direction_predictor
- DTE selection from calendar_spreads.dte_selector
- Custom strike selection for diagonal setup
"""

from .signal_generator import DiagonalSpreadSignalGenerator, DiagonalSpreadSignal
from .spread_selector import DiagonalSpreadSelector, DiagonalSpreadSetup
from .stop_manager import DiagonalStopManager

# Edge 1: Circuit Breaker (VIX-VXV Term Structure)
from .circuit_breaker import (
    TermStructureCircuitBreaker,
    TermStructureStatus,
    TermStructureRegime,
    check_term_structure_circuit_breaker
)

# Edge 2: Multi-Asset Rotation (ETF Universe + Liquidity Screening)
from .etf_universe import (
    ETFUniverse,
    SecurityConfig,
    UniverseTier,
    get_etf_universe
)
from .liquidity_screener import (
    LiquidityScreener,
    LiquidityResult,
    UniverseScanner
)

# Edge 3: ML Roll Timing (Diagonal RL Optimizer)
# Optional import - only needed for ML-based roll timing
try:
    from .diagonal_rl_optimizer import (
        DiagonalRLOptimizer,
        DiagonalTradeEnv,
        DiagonalTradeSnapshot,
        DiagonalAction,
        RuleBasedRollDecider,
        walk_forward_train
    )
    _HAS_RL_OPTIMIZER = True
except Exception as e:
    # RL optimizer requires stable-baselines3, which is optional
    _HAS_RL_OPTIMIZER = False
    # Define dummy classes so __all__ doesn't break
    DiagonalRLOptimizer = None
    DiagonalTradeEnv = None
    DiagonalTradeSnapshot = None
    DiagonalAction = None
    RuleBasedRollDecider = None
    walk_forward_train = None

__all__ = [
    # Core signal generation
    'DiagonalSpreadSignalGenerator',
    'DiagonalSpreadSignal',
    'DiagonalSpreadSelector',
    'DiagonalSpreadSetup',
    'DiagonalStopManager',
    
    # Edge 1: Circuit Breaker
    'TermStructureCircuitBreaker',
    'TermStructureStatus',
    'TermStructureRegime',
    'check_term_structure_circuit_breaker',
    
    # Edge 2: Multi-Asset Rotation
    'ETFUniverse',
    'SecurityConfig',
    'UniverseTier',
    'get_etf_universe',
    'LiquidityScreener',
    'LiquidityResult',
    'UniverseScanner',
    
    # Edge 3: ML Roll Timing
    'DiagonalRLOptimizer',
    'DiagonalTradeEnv',
    'DiagonalTradeSnapshot',
    'DiagonalAction',
    'RuleBasedRollDecider',
    'walk_forward_train',
]
