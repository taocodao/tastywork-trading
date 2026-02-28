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
    # ── LOW_VOL: EC2 DTE/delta + balanced risk management ──
    'LOW_VOL': {
        'anchor_dte': 30,                   # EC2: faster premium turnover
        'anchor_delta': -0.295,             # EC2: slightly more premium
        'hedge_dte': 12,
        'hedge_delta': -0.056,
        'max_cycles': 5,
        'anchor_profit_target_pct': 0.60,   # balanced (EC2: 0.67, old: 0.45)
        'anchor_stop_loss_mult': 1.8,       # relaxed from EC2's 1.3 — works across regimes
        'hedge_close_decay_pct': 0.40,      # keep fast hedge cycling
        'hedge_max_hold_days': 14,
        'max_naked_hours': 31,              # EC2: tighter naked exposure
        'vix_spike_close': 3.0,
    },
    # ── NORMAL: EC2 DTE/delta + balanced risk management ──
    'NORMAL': {
        'anchor_dte': 61,                   # EC2: longer anchor = more theta capture
        'anchor_delta': -0.258,
        'hedge_dte': 7,                     # EC2: short hedge = faster rotation + cheaper
        'hedge_delta': -0.065,
        'max_cycles': 4,
        'anchor_profit_target_pct': 0.55,   # EC2 was 0.62, balanced
        'anchor_stop_loss_mult': 1.8,       # EC2 was 1.06 (too tight for combined regime test)
        'hedge_close_decay_pct': 0.43,      # EC2 value
        'hedge_max_hold_days': 14,
        'max_naked_hours': 14,              # EC2: re-hedge faster
        'vix_spike_close': 2.5,
    },
    # ── HIGH_VOL: EC2 DTE/delta + balanced risk management ──
    'HIGH_VOL': {
        'anchor_dte': 33,                   # EC2: shorter anchor in volatile conditions
        'anchor_delta': -0.292,
        'hedge_dte': 8,
        'hedge_delta': -0.076,
        'max_cycles': 2,
        'anchor_profit_target_pct': 0.50,   # balanced
        'anchor_stop_loss_mult': 2.5,       # EC2: 3.11 — reduced to avoid runaway losses
        'hedge_close_decay_pct': 0.44,      # EC2 value
        'hedge_max_hold_days': 14,
        'max_naked_hours': 48,              # balanced (EC2: 52, old: 24)
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

TA_DIP_SCORE_THRESHOLD = 0.45       # entry threshold
TA_BOUNCE_SCORE_THRESHOLD = 0.50    # hedge exit threshold (was 0.55 — faster exits)
TA_VIX_SPIKE_ENTRY_BONUS = 3.0      # if VIX rises > this pts in 1 day, lower entry threshold by 5%

# =============================================================================
# ML & PREDICTOR SETTINGS
# =============================================================================
TA_ML_CONFIDENCE_MIN = 0.55         # minimum ML prediction confidence
OSC_FLAT_THRESHOLD = 0.03           # ±3.0% = FLAT for classification labels
OSC_LOOKFORWARD_DAYS = 3            # predict 3-day return horizon
OSC_RETRAIN_WEEKLY = True           # whether to retrain the ML model weekly (live)

# =============================================================================
# ML SIGNAL ENHANCER (IB ML Indicators Integration)
# =============================================================================
ML_ENHANCER_ENABLED        = True   # Master toggle — False → pure rule-based scoring
ML_SUPERTREND_ENABLED      = True   # K-Means adaptive SuperTrend
ML_RSI_ENABLED             = True   # ML Optimal RSI + divergence detection
ML_MFI_ENABLED             = True   # ML Money Flow Index with dynamic thresholds
ML_TREND_SPEED_ENABLED     = True   # TrendSpeed 4-stage exit framework
ML_MAX_BOOST               = 0.15   # Maximum ML can add OR subtract from a base score

# Indicator-level parameters
ML_RSI_PERIODS             = [7, 14, 21, 28]   # periods tested by ML Optimal RSI
ML_SUPERTREND_ATR_PERIOD   = 10                # ATR window for SuperTrend
ML_SUPERTREND_TRAINING_BARS = 300              # K-Means training window (bars)
ML_MFI_PERIOD              = 14                # MFI rolling window

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
