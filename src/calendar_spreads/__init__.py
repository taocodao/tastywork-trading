"""
Calendar Spreads Module
=======================

AI-powered calendar spread trading system with:
- VOSS liquidity filtering
- IV-adjusted DTE selection
- Delta-based strike selection
- Earnings intelligence and IV crush prediction
- Signal generation with confidence scoring
- Position monitoring and risk management

Components:
-----------
**Selection & Filtering:**
- VOSSLiquidityFilter: Filter options for liquidity
- DTESelector: Select optimal DTEs based on IV regime
- CalendarStrikeSelector: Select strikes based on delta/theta

**Earnings Intelligence:**
- EarningsStrategyRouter: Make earnings-aware trading decisions
- IVCrushPredictor: Predict IV crush magnitude
- StrategyDecision: Enum of trading decisions

**Signal Generation:**
- CalendarSignalGenerator: Generate entry signals
- CalendarSpreadSignal: Signal data class

**Position Management:**
- CalendarSpreadStopManager: Stop loss and profit targets
- PositionMonitor: Real-time position monitoring
- PositionMonitorService: Background monitoring service

Usage:
------
```python
from src.calendar_spreads import (
    CalendarSignalGenerator,
    VOSSLiquidityFilter,
    DTESelector,
    CalendarStrikeSelector,
    EarningsStrategyRouter
)

# Create generator with all components
generator = CalendarSignalGenerator()

# Generate signals
signals = generator.generate_signals(
    symbol='SPY',
    stock_price=450.0,
    iv_rank=65.0,
    options_data=chain_data,
    expirations=available_expirations
)

# Process signals
for signal in signals:
    if signal.confidence_score >= 70:
        print(f"Trade: {signal.symbol} ${signal.strike} calendar")
```
"""

# Selection & Filtering
from .voss_filter import (
    VOSSLiquidityFilter,
    VOSSCriteria,
    filter_liquid_options
)

from .dte_selector import (
    DTESelector,
    DTEConfig,
    get_next_weekly_expirations,
    get_next_monthly_expirations
)

from .strike_selector import (
    CalendarStrikeSelector,
    StrikeConfig,
    find_atm_strike,
    get_strike_ladder
)

# Earnings Intelligence
from .earnings_intelligence import (
    EarningsStrategyRouter,
    EarningsRouterConfig,
    EarningsDecision,
    StrategyDecision,
    IVCrushPredictor,
    IVCrushPrediction
)

# Signal Generation
from .signal_generator import (
    CalendarSignalGenerator,
    CalendarSpreadSignal,
    GeneratorConfig
)

# Position Management (existing)
from .stop_manager import CalendarSpreadStopManager, ExitRule, ExitAnalysis
from .position_monitor import PositionMonitor, PositionMonitorService, MonitorConfig

__all__ = [
    # Selection & Filtering
    'VOSSLiquidityFilter',
    'VOSSCriteria',
    'filter_liquid_options',
    'DTESelector',
    'DTEConfig',
    'get_next_weekly_expirations',
    'get_next_monthly_expirations',
    'CalendarStrikeSelector',
    'StrikeConfig',
    'find_atm_strike',
    'get_strike_ladder',
    
    # Earnings Intelligence
    'EarningsStrategyRouter',
    'EarningsRouterConfig',
    'EarningsDecision',
    'StrategyDecision',
    'IVCrushPredictor',
    'IVCrushPrediction',
    
    # Signal Generation
    'CalendarSignalGenerator',
    'CalendarSpreadSignal',
    'GeneratorConfig',
    
    # Position Management
    'CalendarSpreadStopManager',
    'ExitRule',
    'ExitAnalysis',
    'PositionMonitor',
    'PositionMonitorService',
    'MonitorConfig'
]
