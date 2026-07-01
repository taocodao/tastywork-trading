"""
RegimeBase Dynamic Ladder Strategy - Configuration
==========================================
Extends the base OTMNakedConfig with RegimeBase-specific defaults.
"""
from dataclasses import dataclass, field
from src.otm_naked.config import OTMNakedConfig

@dataclass
class RegimeBaseLadderConfig(OTMNakedConfig):
    # Base overrides
    universe: list = field(default_factory=lambda: ["RegimeBase"])
    initial_capital: float = 500_000.0
    
    # Entry triggers (RegimeBase specific)
    entry_trigger_pct: float = 5.0     # Min daily move %
    ivr_min: float = 65.0              # Min IV Rank (0-100 scale)
    ml_confidence_min: float = 0.62    # XGBoost threshold
    
    # Ladder structure
    max_rungs_per_side: int = 3
    initial_delta: float = 0.20
    ladder_delta_step: float = 0.05    # Each rung farther OTM
    min_naked_delta: float = 0.15      # Minimum delta to avoid wide bid-ask spreads
    
    # DTE targets
    dte_target: int = 60               # Base DTE (can be overridden by IV regime)
    
    # Roll & Exit triggers
    delta_breach_threshold: float = 0.35
    dte_roll_threshold: int = 21       # Roll/close when DTE <= 21
    profit_take_pct_short: float = 0.25  # For DTE <= 21 (fast decay)
    profit_dte_threshold: int = 25       # Crossover point
    
    # Risk
    max_portfolio_delta: float = 0.45
    position_size_pct: float = 0.01    # 1% per rung
    stop_loss_credit_mult: float = 2.0 # Stop at 2x credit received
    
    # Macro filter
    macro_filter_spy_pct: float = 3.0
    
    # Naked to spread conversion
    # Spread only when ML confidence is LOW (< 0.55); naked when >= 0.65
    spread_conversion_conf_low: float = 0.50
    spread_conversion_conf_high: float = 0.65
    spread_wing_pct: float = 0.15      # Wing 15% farther OTM
    
    # Regime thresholds
    adx_no_trade_threshold: float = 40.0
    adx_trend_threshold: float = 25.0
    slope_trend_threshold: float = 0.20  # % per day
    hurst_no_trade_threshold: float = 0.65
    
    # Regime-specific deltas
    delta_trending: float = 0.15   # Conservative in trends
    delta_sideways: float = 0.20   # Normal in sideways
