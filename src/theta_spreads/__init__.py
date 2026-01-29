"""
Theta Cash-Secured Put Selling Strategy
========================================

Automated cash-secured put selling strategy implementing the professional
time-based exit approach for maximum capital efficiency.

Key Features:
- Daily symbol selection using 5-factor scoring (50+ → 12 best)
- 30-delta put identification with confidence scoring (0-100)
- Time-based profit targets (50%/60%/75%/90% by week)
- Real-time position monitoring and capital redeployment
- Integration with IB Gateway for market data
"""

from .symbol_selector import SymbolSelector, SymbolScore
from .options_analyzer import OptionsAnalyzer, PutScore
from .signal_generator import ThetaSignalGenerator, ThetaEntrySignal, ThetaExitSignal
from .portfolio_manager import ThetaPortfolioManager, ThetaPosition
from .scheduler import ThetaScheduler, create_default_scheduler

__all__ = [
    "SymbolSelector",
    "SymbolScore",
    "OptionsAnalyzer",
    "PutScore",
    "ThetaSignalGenerator",
    "ThetaEntrySignal",
    "ThetaExitSignal",
    "ThetaPortfolioManager",
    "ThetaPosition",
    "ThetaScheduler",
    "create_default_scheduler",
]

__version__ = "1.0.0"

