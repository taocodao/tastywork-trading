"""
QQQ LEAPS ML-Optimized Strategy
================================
All 6 ML layers (A-F) from the risk mitigation plan, integrated into a
single production-ready strategy module.
"""
from .config import QQQLeapsConfig
from .scanner import run_qqq_leaps_scan

__all__ = ["QQQLeapsConfig", "run_qqq_leaps_scan"]
