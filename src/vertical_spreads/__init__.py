"""
Vertical Spreads Module
=======================

Provides vertical spread signal generation and trading capabilities:
- Direction prediction using ML ensemble (RSI, Bollinger Bands, Moving Averages)
- Strike selection based on implied move and confidence
- Suitability validation for customer accounts
- Stop loss and profit target management
"""

from .direction_predictor import VerticalSpreadDirectionPredictor
from .spread_selector import VerticalSpreadSelector
from .signal_generator import VerticalSpreadSignalGenerator
from .stop_manager import VerticalSpreadStopManager
from .suitability import VerticalSpreadSuitabilityValidator

__all__ = [
    'VerticalSpreadDirectionPredictor',
    'VerticalSpreadSelector', 
    'VerticalSpreadSignalGenerator',
    'VerticalSpreadStopManager',
    'VerticalSpreadSuitabilityValidator',
]
