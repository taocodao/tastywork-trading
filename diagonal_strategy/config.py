"""
Active Diagonal Strategy — Configuration Parameters
===================================================
Contains all tunable hyperparameters for the strategy:
 - Option legs parameters (DTE, delta) parameterized by VIX regime
 - TA signal scoring thresholds
 - ML predictor confidence constraints
 - Backtest setup parameters
"""
from typing import Dict, Any

# =============================================================================
# STRATEGY PARAMETERS (REGIME-KEYED)
# =============================================================================
TQQQ_DIAGONAL_PARAMS: Dict[str, Dict[str, Any]] = {
    'LOW_VOL': {
        'anchor_dte': 60,
        'anchor_delta': -0.25,
        'hedge_dte': 14,
        'hedge_delta': -0.12,
        'max_cycles': 4,
        'anchor_profit_target_pct': 0.50,
        'anchor_stop_loss_mult': 2.0,
        'hedge_close_decay_pct': 0.50,  # close hedge when 50% decayed
        'max_naked_hours': 48,
        'vix_spike_close': 3.0,
    },
    'NORMAL': {
        'anchor_dte': 45,
        'anchor_delta': -0.25,
        'hedge_dte': 14,
        'hedge_delta': -0.10,
        'max_cycles': 3,
        'anchor_profit_target_pct': 0.50,
        'anchor_stop_loss_mult': 2.0,
        'hedge_close_decay_pct': 0.60,
        'max_naked_hours': 36,
        'vix_spike_close': 2.5,
    },
    'HIGH_VOL': {
        'anchor_dte': 45,
        'anchor_delta': -0.25,
        'hedge_dte': 10,
        'hedge_delta': -0.08,
        'max_cycles': 2,
        'anchor_profit_target_pct': 0.40,
        'anchor_stop_loss_mult': 1.5,
        'hedge_close_decay_pct': 0.50,
        'max_naked_hours': 24,
        'vix_spike_close': 2.0,
    },
    # Note: CRISIS falls back to standard Vertical Credit Spreads
}

# =============================================================================
# TECHNICAL ANALYSIS THRESHOLDS
# =============================================================================
TA_RSI_OVERSOLD = 30
TA_RSI_OVERBOUGHT = 70
TA_RSI2_EXTREME = 10
TA_IV_RANK_MIN = 15
TA_BB_OVERSOLD = 0.15

TA_DIP_SCORE_THRESHOLD = 0.45       # minimum to trigger entry
TA_BOUNCE_SCORE_THRESHOLD = 0.55    # minimum to trigger hedge close

# =============================================================================
# ML & PREDICTOR SETTINGS
# =============================================================================
TA_ML_CONFIDENCE_MIN = 0.55         # minimum ML prediction confidence
OSC_FLAT_THRESHOLD = 0.03           # ±3.0% = FLAT for classification labels
OSC_LOOKFORWARD_DAYS = 3            # predict 3-day return horizon
OSC_RETRAIN_WEEKLY = True           # whether to retrain the ML model weekly (live)

# =============================================================================
# GENERAL SETTINGS & PRINCIPAL TIERS
# =============================================================================
PRINCIPAL_TIERS = [
    {'min': 0,      'max_positions': 2, 'risk_pct': 0.020, 'max_contracts': 3},
    {'min': 10000,  'max_positions': 5, 'risk_pct': 0.025, 'max_contracts': 10},
    {'min': 50000,  'max_positions': 5, 'risk_pct': 0.025, 'max_contracts': 15},
    {'min': 100000, 'max_positions': 8, 'risk_pct': 0.025, 'max_contracts': 20},
]

ACCOUNT_VALUE = 25000.0  # Default, can be overridden by runner CLI
COMMISSION_PER_SPREAD = 4.0
RISK_FREE_RATE = 0.05
