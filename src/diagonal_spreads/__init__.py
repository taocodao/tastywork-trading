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

__all__ = [
    'DiagonalSpreadSignalGenerator',
    'DiagonalSpreadSignal',
    'DiagonalSpreadSelector',
    'DiagonalSpreadSetup',
    'DiagonalStopManager',
]
