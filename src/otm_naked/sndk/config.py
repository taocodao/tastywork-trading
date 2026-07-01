"""
SNDK Dynamic Ladder Strategy - Configuration
==========================================
Extends the base OTMNakedConfig with SNDK-specific defaults.
"""
from dataclasses import dataclass, field
from src.otm_naked.config import OTMNakedConfig

@dataclass
class SNDKLadderConfig(OTMNakedConfig):
    # Base overrides
    universe: list = field(default_factory=lambda: ["SNDK"])
    initial_capital: float = 500_000.0
    
    # Entry triggers (SNDK specific)
    entry_trigger_pct: float = 5.0     # Min daily move %
    intraday_trigger_pct: float = 2.0  # Min intraday move % for live engine
    ivr_min: float = 65.0              # Min IV Rank (0-100 scale)
    ml_confidence_min: float = 0.62    # XGBoost threshold
    
    # Ladder structure
    max_rungs_per_side: int = 3
    initial_delta: float = 0.20
    ladder_delta_step: float = 0.05    # Each rung farther OTM
    min_naked_delta: float = 0.15      # Minimum delta to avoid wide bid-ask spreads
    
    # DTE targets
    dte_target: int = 60               # Base DTE (can be overridden by IV regime)
    
    # V3: Margin & Risk Management
    nav: float = 245_600.0             # Current paper account NAV
    max_contracts_hard: int = 4        # Absolute ceiling (Reg T)
    max_contracts_pm: int = 6          # Portfolio Margin ceiling
    use_portfolio_margin: bool = False # Set True after PM approved
    margin_per_contract_regt: float = 25_000.0
    margin_per_contract_pm: float = 11_000.0
    min_excess_liquidity: float = 60_000.0
    emergency_close_threshold: float = 30_000.0
    cash_reserve_floor: float = 0.40

    # V3: Rung Spacing (σ multiples of 5-day expected move)
    rung_spacing_sigma_extreme_up: float = 1.00
    rung_spacing_sigma_uptrend: float = 0.75
    rung_spacing_sigma_sideways: float = 0.50

    # V3: Exit Rules
    dte_emergency_close: int = 7
    dte_reduce_profit_target: int = 14
    profit_target_pct_normal: float = 0.50
    profit_target_pct_low_dte: float = 0.35
    favorable_close_fraction: float = 0.20
    
    # Old Roll & Exit triggers (keep for compatibility, but deprecated by V3 rules)
    delta_breach_threshold: float = 0.35
    dte_roll_threshold: int = 21
    profit_take_pct_short: float = 0.25
    profit_dte_threshold: int = 25
    
    # Old Risk (deprecated)
    max_portfolio_delta: float = 0.45
    position_size_pct: float = 0.01
    stop_loss_credit_mult: float = 2.0
    
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
