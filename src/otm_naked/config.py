"""
OTM Naked Options — Strategy Configuration
============================================
All tunable parameters, universe definition, and regime-delta tables.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# ===========================================================================
# 35-STOCK PRE-SELECTED UNIVERSE
# Sourced from ZEBRA_WATCHLIST + TurboBounce base_symbols + THETA_UNIVERSE
# ===========================================================================
OTM_NAKED_UNIVERSE: List[str] = [
    # ── Technology (8) ──────────────────────────────────────────────────
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
    # ── Semiconductors (3) ──────────────────────────────────────────────
    "AVGO", "QCOM", "MU",
    # ── Software / Cloud (3) ────────────────────────────────────────────
    "CRM", "ORCL", "ADBE",
    # ── Financials (4) ──────────────────────────────────────────────────
    "JPM", "GS", "V", "MA",
    # ── Healthcare (3) ──────────────────────────────────────────────────
    "LLY", "ABBV", "UNH",
    # ── Energy (2) ──────────────────────────────────────────────────────
    "XOM", "CVX",
    # ── Consumer (3) ────────────────────────────────────────────────────
    "COST", "WMT", "NFLX",
    # ── Industrial (2) ──────────────────────────────────────────────────
    "CAT", "BA",
    # ── ETFs (7) ────────────────────────────────────────────────────────
    "SPY", "QQQ", "IWM", "DIA", "GLD", "TLT", "XLE",
]

OTM_NAKED_SECTORS: Dict[str, str] = {
    "AAPL": "TECH",   "MSFT": "TECH",   "NVDA": "TECH",   "AMZN": "TECH",
    "GOOGL": "TECH",  "META": "TECH",   "TSLA": "TECH",   "AMD": "SEMI",
    "AVGO": "SEMI",   "QCOM": "SEMI",   "MU": "SEMI",
    "CRM": "SOFTWARE","ORCL": "SOFTWARE","ADBE": "SOFTWARE",
    "JPM": "FINANCE", "GS": "FINANCE",  "V": "FINANCE",   "MA": "FINANCE",
    "LLY": "HEALTH",  "ABBV": "HEALTH", "UNH": "HEALTH",
    "XOM": "ENERGY",  "CVX": "ENERGY",
    "COST": "CONSUMER","WMT": "CONSUMER","NFLX": "CONSUMER",
    "CAT": "INDUSTRIAL","BA": "INDUSTRIAL",
    "SPY": "ETF",     "QQQ": "ETF",     "IWM": "ETF",     "DIA": "ETF",
    "GLD": "COMMODITY","TLT": "BOND",   "XLE": "ENERGY_ETF",
}

# ===========================================================================
# REGIME → DELTA TABLE  (Section 5.1 of strategy document)
# Naked CALL deltas (positive), naked PUT deltas (positive abs value)
# ===========================================================================
# VIX regime thresholds
VIX_LOW    = 15.0   # VIX < 15 = LOW_VOL
VIX_NORMAL = 25.0   # VIX 15-25 = NORMAL
VIX_HIGH   = 35.0   # VIX 25-35 = HIGH_VOL
                    # VIX > 35 = CRISIS → no new naked positions

REGIME_DELTA_MAP: Dict[str, Dict[str, float]] = {
    "LOW_VOL": {
        "put_delta":  0.10,   # Deeper OTM — vol is low, stay far away
        "call_delta": 0.10,
        "dte":        45,
        "max_positions": 6,
    },
    "NORMAL": {
        "put_delta":  0.12,
        "call_delta": 0.12,
        "dte":        35,
        "max_positions": 5,
    },
    "HIGH_VOL": {
        "put_delta":  0.15,   # Closer to ATM — elevated premium
        "call_delta": 0.14,
        "dte":        21,
        "max_positions": 4,
    },
    "CRISIS": {
        "put_delta":  0.0,    # No new positions in crisis
        "call_delta": 0.0,
        "dte":        0,
        "max_positions": 0,
    },
}


# ===========================================================================
# STRATEGY PARAMETERS
# ===========================================================================
@dataclass
class OTMNakedConfig:
    # ── Account ──────────────────────────────────────────────────────────────
    initial_capital: float = 50_000.0
    risk_free_rate:  float = 0.045           # 4.5% risk-free (^IRX)

    # ── Universe ──────────────────────────────────────────────────────────────
    universe: List[str] = field(default_factory=lambda: OTM_NAKED_UNIVERSE)
    max_sector_positions: int = 3            # Max positions per sector

    # ── DTE ───────────────────────────────────────────────────────────────────
    dte_min: int = 21
    dte_max: int = 45
    dte_target: int = 35                     # Default target DTE

    # ── Delta targets (overridden by regime table) ────────────────────────────
    put_delta_target:  float = 0.10          # Absolute delta for puts
    call_delta_target: float = 0.10          # Absolute delta for calls
    delta_tolerance:   float = 0.03          # ±delta tolerance for strike search

    # ── IV filters ────────────────────────────────────────────────────────────
    min_iv_rank:       float = 0.25          # IV Rank > 25% to enter
    min_iv_hv_ratio:   float = 1.00          # IV/HV >= 1.00 (premium selling edge)

    # ── Liquidity filters ─────────────────────────────────────────────────────
    min_open_interest: int   = 500
    max_bid_ask_spread_pct: float = 0.15     # Max spread as % of mid
    min_premium:       float = 0.30          # Min credit to collect ($0.30)

    # ── Risk management ───────────────────────────────────────────────────────
    max_risk_per_trade_pct: float = 0.01     # 1% of capital per trade
    max_portfolio_heat_pct: float = 0.05     # 5% total naked exposure
    stop_loss_credit_mult:  float = 2.0      # Close at 2x credit received
    profit_take_pct:        float = 0.50     # Close at 50% of max credit
    max_concurrent_positions: int = 5
    vix_crisis_threshold:   float = 35.0     # No new trades above VIX 35

    # ── Signal engine ─────────────────────────────────────────────────────────
    # 52W proximity thresholds for CALL signals (overbought)
    call_near_52w_high_pct: float = 0.15     # Within 15% of 52W high
    call_above_52w_high_pct: float = 0.10    # Or broken above by 10%
    # 52W proximity thresholds for PUT signals (oversold)
    put_near_52w_low_pct:   float = 0.15     # Within 15% of 52W low
    put_decline_from_high:  float = 0.15     # Or 15% decline from 52W high

    # RSI thresholds
    rsi_overbought:  float = 70.0            # RSI > 70 → call signal
    rsi_oversold:    float = 30.0            # RSI < 30 → put signal

    # Bollinger Band thresholds
    bb_overbought:   float = 0.95            # %B > 0.95 → call signal
    bb_oversold:     float = 0.05            # %B < 0.05 → put signal

    # ── ML entry gate ─────────────────────────────────────────────────────────
    ml_confidence_min: float = 0.60          # Minimum XGBoost confidence to enter
    use_ml_gate:       bool  = True          # Can disable for rule-only baseline

    # ── Earnings blackout ─────────────────────────────────────────────────────
    earnings_blackout_days: int = 21         # Skip if earnings within 21 days

    # ── Position monitor ─────────────────────────────────────────────────────
    time_exit_dte: int = 7                   # Force close at 7 DTE
    delta_breach_pct: float = 0.01           # Close if delta > 1% of strike price
    vix_spike_exit: float = 10.0             # Close if VIX spikes 10+ pts/day

    # ── Backtest ──────────────────────────────────────────────────────────────
    backtest_start: str = "2018-01-01"
    backtest_end:   str = "2025-12-31"
    train_window_days: int = 504             # ~2 years for ML training
    test_window_days:  int = 63              # ~3 months per OOS window
    step_days:         int = 21              # Rolling step size
    commission_per_contract: float = 0.65   # Tastytrade commission


# Module-level default config instance
DEFAULT_CONFIG = OTMNakedConfig()
