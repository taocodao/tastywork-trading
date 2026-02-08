"""
Earnings Intelligence Module.
Provides ML-powered IV crush prediction and earnings-aware trading decisions.
"""

from .client import PerplexityClient
from .router import EarningsStrategyRouter, RoutingDecision, AlternativeStrategy
from .features import FeatureVector, FeatureEngineer, IVCrushClass
from .iv_crush_model import IVCrushPredictor, get_predictor
from .scanner import EarningsScanner, EarningsOpportunity
from .database import (
    Signal,
    SignalRepository,
    Position,
    UserSignalExecution,
    EarningsRepository,
    PredictionRepository,
    init_db,
    get_db,
    get_session,
)

__all__ = [
    # Client
    "PerplexityClient",
    
    # Router
    "EarningsStrategyRouter",
    "RoutingDecision",
    "AlternativeStrategy",
    
    # Features
    "FeatureVector",
    "FeatureEngineer",
    "IVCrushClass",
    
    # Model
    "IVCrushPredictor",
    "get_predictor",
    
    # Scanner
    "EarningsScanner",
    "EarningsOpportunity",
    
    # Database
    "Signal",
    "SignalRepository",
    "Position",
    "UserSignalExecution",
    "EarningsRepository",
    "PredictionRepository",
    "init_db",
    "get_db",
    "get_session",
]
