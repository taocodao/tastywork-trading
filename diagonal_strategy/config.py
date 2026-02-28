"""
Active Diagonal Strategy — Configuration Parameters
===================================================
REBUILT v2: Mean-Reversion Swing Trade Mode
Based on Perplexity research (TQQQ Mean Reversion Diagonal.md):
  - Entry: RSI-2 < 10 + price > 200 MA
  - Structure: Sell 30-45 DTE put at -0.40 delta / Buy 7-12 DTE put at -0.20 delta
  - Exit: Close BOTH legs when price > 5-day MA or RSI-2 > 70 (3-7 day hold)
  - Crash guard: 4-layer filter (200 MA → VIX regime → term structure → 20% circuit breaker)
  - No hedge cycling — each trade is a single open/close swing
"""
from typing import Dict, Any

# =============================================================================
# STRATEGY PARAMETERS (REGIME-KEYED)
# Research: higher deltas (-0.40/-0.20) give better directional sensitivity
# =============================================================================
TQQQ_DIAGONAL_PARAMS: Dict[str, Dict[str, Any]] = {
    # ── LOW_VOL: Tight spreads, calm market — best for swing entries ──
    'LOW_VOL': {
        'anchor_dte': 35,               # 30-45 DTE per research
        'anchor_delta': -0.38,          # slightly below -0.40 in calm mkt
        'hedge_dte': 10,                # 7-12 DTE per research
        'hedge_delta': -0.18,           # -0.15 to -0.25 per research
        'max_cycles': 1,                # SWING MODE: no cycling
        'anchor_profit_target_pct': 0.50,
        'anchor_stop_loss_mult': 2.0,   # 2x credit = 1x net loss
        'hedge_close_decay_pct': 0.50,  # unused in swing mode — position closes as unit
        'max_naked_hours': 4,           # very short — re-hedge immediately in swing mode
        'vix_spike_close': 3.0,
        'swing_max_hold_days': 7,       # force close after 7 days regardless
    },
    # ── NORMAL: Core trading regime ──
    'NORMAL': {
        'anchor_dte': 35,
        'anchor_delta': -0.40,          # research: -0.35 to -0.45
        'hedge_dte': 10,
        'hedge_delta': -0.20,           # research: -0.15 to -0.25
        'max_cycles': 1,                # SWING MODE: no cycling
        'anchor_profit_target_pct': 0.50,
        'anchor_stop_loss_mult': 2.0,
        'hedge_close_decay_pct': 0.50,
        'max_naked_hours': 4,
        'vix_spike_close': 2.5,
        'swing_max_hold_days': 7,
    },
    # ── HIGH_VOL: Rich premium but higher risk — smaller size, tighter stops ──
    'HIGH_VOL': {
        'anchor_dte': 30,               # shorter DTE in volatile conditions
        'anchor_delta': -0.40,
        'hedge_dte': 7,
        'hedge_delta': -0.22,           # slightly more protection in high vol
        'max_cycles': 1,                # SWING MODE: no cycling
        'anchor_profit_target_pct': 0.40,  # take profit earlier in high vol
        'anchor_stop_loss_mult': 1.5,   # tighter stop in high vol
        'hedge_close_decay_pct': 0.50,
        'max_naked_hours': 4,
        'vix_spike_close': 2.0,
        'swing_max_hold_days': 5,       # shorter hold in high vol (faster moves)
    },
    # Note: CRISIS (VIX > 32) — no new trades per 4-layer crash guard
}

# =============================================================================
# SWING ENTRY SIGNALS (RSI-2 + 200 MA)
# Research: RSI-2 < 10 + price > 200 MA → 72-77% win rate
# =============================================================================
SWING_ENTRY_RSI2_THRESHOLD = 10         # Primary trigger: RSI-2 below this
SWING_ENTRY_RSI2_AGGRESSIVE = 5         # More aggressive: fewer signals, higher win rate
SWING_ENTRY_USE_VOLUME_CONFIRM = True   # Require volume > 2x 20-day avg (optional)
SWING_ENTRY_VOLUME_MULTIPLIER = 2.0     # Volume capitulation threshold

# =============================================================================
# SWING EXIT SIGNALS
# Research: exit when price > 5-day MA or RSI-2 > 70
# =============================================================================
SWING_EXIT_RSI2_ABOVE = 70              # Close both legs when RSI-2 rises above this
SWING_EXIT_ABOVE_5MA = True             # Close both legs when price > 5-day MA
SWING_EXIT_MAX_HOLD_DAYS = 7           # Force close after N days (from params above)

# =============================================================================
# 4-LAYER CRASH GUARD
# Research: prevents 2022-style repeated false signals
# =============================================================================
# Layer 1: 200 MA Gate (most important — no new trades below 200 MA)
CRASH_GUARD_200MA_ENABLED = True

# Layer 2: VIX regime classification (VIX vs 50-day SMA of VIX)
CRASH_GUARD_VIX_REGIME_ENABLED = True
CRASH_GUARD_VIX_CRISIS_MULT = 1.15     # VIX > 50-SMA * 1.15 = crisis, no trades
CRASH_GUARD_VIX_CAUTION_MULT = 1.0     # VIX > 50-SMA = caution, half size

# Layer 3: VIX term structure (backwardation = fear spike)
CRASH_GUARD_TERM_STRUCTURE_ENABLED = True

# Layer 4: Single-day crash circuit breaker
CRASH_GUARD_DAILY_DROP_PCT = -0.15     # If TQQQ drops > 15% in one day: exit all

# =============================================================================
# LEGACY TA THRESHOLDS (kept for ML enhancer compatibility)
# =============================================================================
TA_RSI_OVERSOLD = 30
TA_RSI_OVERBOUGHT = 70
TA_RSI2_EXTREME = 10
TA_IV_RANK_MIN = 15
TA_BB_OVERSOLD = 0.15

TA_DIP_SCORE_THRESHOLD = 0.45           # legacy — RSI-2 gate now primary
TA_BOUNCE_SCORE_THRESHOLD = 0.50
TA_VIX_SPIKE_ENTRY_BONUS = 3.0

# =============================================================================
# ML & PREDICTOR SETTINGS
# =============================================================================
TA_ML_CONFIDENCE_MIN = 0.55
OSC_FLAT_THRESHOLD = 0.03
OSC_LOOKFORWARD_DAYS = 3
OSC_RETRAIN_WEEKLY = True

ML_ENHANCER_ENABLED        = True
ML_SUPERTREND_ENABLED      = True
ML_RSI_ENABLED             = True
ML_MFI_ENABLED             = True
ML_TREND_SPEED_ENABLED     = True
ML_MAX_BOOST               = 0.15

ML_RSI_PERIODS             = [7, 14, 21, 28]
ML_SUPERTREND_ATR_PERIOD   = 10
ML_SUPERTREND_TRAINING_BARS = 300
ML_MFI_PERIOD              = 14

# =============================================================================
# GENERAL SETTINGS & PRINCIPAL TIERS
# =============================================================================
PRINCIPAL_TIERS = [
    {'min': 0,      'max_positions': 2, 'risk_pct': 0.020, 'max_contracts': 3},
    {'min': 10000,  'max_positions': 5, 'risk_pct': 0.025, 'max_contracts': 10},
    {'min': 50000,  'max_positions': 5, 'risk_pct': 0.025, 'max_contracts': 15},
    {'min': 100000, 'max_positions': 8, 'risk_pct': 0.025, 'max_contracts': 20},
]

ACCOUNT_VALUE = 25000.0
COMMISSION_PER_SPREAD = 4.0
RISK_FREE_RATE = 0.05
