"""
Signal Publisher - Modular Architecture
=========================================
Unified signal publishing for multiple trading strategies.

Supported Strategies:
- Theta (cash-secured puts)
- Calendar Spreads
- Vertical Spreads (future)
"""

# Theta signals
from .theta import (
    ThetaEntrySignal,
    ThetaExitSignal,
    publish_theta_entry_signal,
    publish_theta_exit_signal
)

# Zebra signals
from .zebra import (
    ZebraEntrySignal,
    ZebraExitSignal,
    publish_zebra_entry_signal,
    publish_zebra_exit_signal
)

# DVO signals
from .dvo import (
    DVOEntrySignal,
    DVOExitSignal,
    publish_dvo_entry_signal,
    publish_dvo_exit_signal
)

# Calendar signals
from .calendar import (
    publish_calendar_signal,
    spread_setup_to_signal
)

# PMCC signals
from .pmcc import (
    publish_pmcc_entry_signal,
    publish_pmcc_cycle_signal
)

# TQQQ VIX-Adaptive signals
from .tqqq import (
    TQQQSpreadEntrySignal,
    TQQQLegOutSignal,
    TQQQLongPutSellSignal,
    TQQQDiagonalEntrySignal,
    TQQQDiagonalExitSignal,
    publish_tqqq_entry_signal,
    publish_tqqq_legout_signal,
    publish_tqqq_long_put_signal,
    publish_tqqq_diagonal_entry_signal,
    publish_tqqq_diagonal_exit_signal,
)

# Diagonal signals
from .diagonal import (
    DiagonalEntrySignal,
    publish_diagonal_entry_signal
)

# TurboBounce signals
from .turbobounce import (
    TurboBounceEntrySignal,
    publish_turbobounce_entry_signal
)

# EMA-CCI-MACD signals
from .ema_cci_macd import (
    EMACCIMACDEntrySignal,
    publish_ema_cci_macd_signal
)

# Base classes
from .base import BaseSignal

__all__ = [
    # Theta
    'ThetaEntrySignal',
    'ThetaExitSignal',
    'publish_theta_entry_signal',
    'publish_theta_exit_signal',

    # Zebra
    'ZebraEntrySignal',
    'ZebraExitSignal',
    'publish_zebra_entry_signal',
    'publish_zebra_exit_signal',
    
    # DVO
    'DVOEntrySignal',
    'DVOExitSignal',
    'publish_dvo_entry_signal',
    'publish_dvo_exit_signal',
    
    # Calendar
    'publish_calendar_signal',
    'spread_setup_to_signal',
    
    # PMCC
    'publish_pmcc_entry_signal',
    'publish_pmcc_cycle_signal',
    
    # TQQQ Diagonal
    'TQQQDiagonalEntrySignal',
    'TQQQDiagonalExitSignal',
    'publish_tqqq_diagonal_entry_signal',
    'publish_tqqq_diagonal_exit_signal',
    
    # Diagonal
    'DiagonalEntrySignal',
    'publish_diagonal_entry_signal',
    
    # TurboBounce
    'TurboBounceEntrySignal',
    'publish_turbobounce_entry_signal',
    
    # EMA-CCI-MACD
    'EMACCIMACDEntrySignal',
    'publish_ema_cci_macd_signal',
    
    # Base
    'BaseSignal',
]

__version__ = '2.1.0'
