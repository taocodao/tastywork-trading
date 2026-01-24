"""
Calendar Spreads Module
=======================

Provides risk management and position monitoring for calendar spread strategies.
"""

from .stop_manager import CalendarSpreadStopManager, ExitRule, ExitAnalysis
from .position_monitor import PositionMonitor, PositionMonitorService, MonitorConfig

__all__ = [
    'CalendarSpreadStopManager',
    'ExitRule',
    'ExitAnalysis',
    'PositionMonitor',
    'PositionMonitorService',
    'MonitorConfig'
]
