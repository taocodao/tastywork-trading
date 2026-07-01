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
    "AAPL", "ABBV", "ADBE", "ADI", "AEM", "AEP", "AGQ", "ALAB",
    "AMAT", "AMD", "AMZN", "ANET", "ANF", "APLX", "APP", "ARKK",
    "ARKW", "ARM", "ASML", "ASTS", "AVAV", "AVGO", "AXP", "AXSM",
    "AYI", "BA", "BABA", "BAC", "BIDU", "BLK", "CAT", "CEG",
    "CHRW", "CIEN", "CLS", "COHR", "COIN", "COST", "CRCL", "CRDO",
    "CRM", "CRWD", "CRWV", "CSCO", "CVX", "DASH", "DIA", "DIS",
    "DUOL", "ECL", "EME", "FN", "GDX", "GEV", "GLD", "GLW",
    "GOOG", "GOOGL", "GPOR", "GS", "HOOD", "HROW", "IBM", "INTU",
    "IWM", "JBL", "JCI", "JPM", "KTOS", "LABU", "LEU", "LITE",
    "LMT", "LULU", "MA", "MDB", "MELI", "META", "MRVL", "MSFT",
    "MSTR", "MU", "NBIS", "NET", "NFLX", "NOW", "NUGT", "NVDA",
    "NVO", "NVT", "OKLO", "ORCL", "P", "PLTR", "QCOM", "QQQ",
    "RBRK", "RCL", "RDDT", "RKLB", "RMBS", "RSP", "SANM", "SAP",
    "SATS", "SHOP", "SLB", "SNDK", "SNOW", "SPOT", "SPXC", "TFX",
    "TLT", "TQQQ", "TSLA", "TSM", "TT", "UNH", "V", "VIX",
    "VLO", "VRT", "VRTX", "VST", "WAT", "WDAY", "WDC", "WMT",
    "WPM", "WTI", "XLE", "XOM", "XYL", "ZS",
]

OTM_NAKED_SECTORS: Dict[str, str] = {
    "AAPL": "TECH",  "MSFT": "TECH",  "NVDA": "TECH",  "AMZN": "TECH",
    "GOOGL": "TECH", "META": "TECH",  "TSLA": "TECH",  "AMD": "SEMI",
    "AVGO": "SEMI",  "QCOM": "SEMI",  "MU": "SEMI",    "CRM": "SOFTWARE",
    "ORCL": "SOFTWARE", "ADBE": "SOFTWARE", "JPM": "FINANCE", "GS": "FINANCE",
    "V": "FINANCE",  "MA": "FINANCE", "LLY": "HEALTH", "ABBV": "HEALTH",
    "UNH": "HEALTH", "XOM": "ENERGY", "CVX": "ENERGY", "COST": "CONSUMER",
    "WMT": "CONSUMER", "NFLX": "CONSUMER", "CAT": "INDUSTRIAL", "BA": "INDUSTRIAL",
    "SPY": "ETF",    "QQQ": "ETF",    "IWM": "ETF",    "DIA": "ETF",
    "GLD": "COMMODITY", "TLT": "BOND", "XLE": "ENERGY_ETF",
}

# ===========================================================================
# REGIME -> DELTA TABLE
# ===========================================================================
VIX_LOW    = 15.0
VIX_NORMAL = 25.0
VIX_HIGH   = 35.0

REGIME_DELTA_MAP: Dict[str, Dict[str, float]] = {
    "LOW_VOL": {
        "put_delta":  0.10,
        "call_delta": 0.10,
        "dte":        45,
        "max_positions": 6,
        "stop_mult":  1.8,
    },
    "NORMAL": {
        "put_delta":  0.12,
        "call_delta": 0.12,
        "dte":        45,
        "max_positions": 5,
        "stop_mult":  2.0,
    },
    "HIGH_VOL": {
        "put_delta":  0.15,
        "call_delta": 0.14,
        "dte":        45,
        "max_positions": 4,
        "stop_mult":  2.5,
    },
    "CRISIS": {
        "put_delta":  0.0,
        "call_delta": 0.0,
        "dte":        0,
        "max_positions": 0,
        "stop_mult":  0.0,
    },
}


# ===========================================================================
# STRATEGY PARAMETERS
# ===========================================================================
@dataclass
class OTMNakedConfig:
    # ── Account ───────────────────────────────────────────────────────────────
    initial_capital: float = 50_000.0
    risk_free_rate:  float = 0.045           # 4.5% risk-free (^IRX)

    # ── Universe ──────────────────────────────────────────────────────────────
    universe: List[str] = field(default_factory=lambda: OTM_NAKED_UNIVERSE)
    max_sector_positions: int = 2            # Max 2 positions per sector

    # High-beta position sizing multiplier (0.5x normal size for these names)
    high_beta_symbols: List[str] = field(default_factory=lambda: [
        "MSTR", "ASTS", "OKLO", "PLTR", "LEU", "NUGT", "SOXL", "TQQQ",
    ])
    high_beta_size_mult: float = 0.5         # Reduce position size by 50% for high-beta names

    # ── DTE ───────────────────────────────────────────────────────────────────
    dte_min:    int = 35
    dte_max:    int = 55
    dte_target: int = 45                     # Target 45 DTE for all regimes (standardized)

    # ── Delta targets (overridden by regime table) ────────────────────────────
    put_delta_target:  float = 0.10          # Absolute delta for puts
    call_delta_target: float = 0.10          # Absolute delta for calls
    delta_tolerance:   float = 0.03          # +/- delta tolerance for strike search

    # ── IV filters ────────────────────────────────────────────────────────────
    # NOTE: The HV-based IV rank proxy is a rough approximation. In low-vol years
    # (e.g. 2023) the proxy underestimates actual IV rank since HV-rolling-252 is
    # anchored to the 2022 vol spike. Using 0.10 floor to keep signals flowing.
    min_iv_rank:       float = 0.10          # IV Rank > 10% to enter (was 0.25)
    min_iv_hv_ratio:   float = 0.80          # IV/HV >= 0.80 (was 1.00)

    # ── Liquidity filters ─────────────────────────────────────────────────────
    min_open_interest:      int   = 500
    max_bid_ask_spread_pct: float = 0.15     # Max spread as % of mid
    min_premium:            float = 0.30     # Min credit to collect ($0.30)

    # ── Risk management ───────────────────────────────────────────────────────
    max_risk_per_trade_pct:       float = 0.045  # 4.5% -- Phase 3 (progressive toward quarter-Kelly)
    max_portfolio_heat_pct:       float = 0.40   # 40% notional heat budget (hard cap)
    max_concurrent_positions:     int   = 8      # Position slots (5 Pathway A + 3 Pathway B)
    vix_crisis_threshold:         float = 35.0   # No new trades above VIX 35
    max_drawdown_kill_pct:        float = 0.10   # If NAV drops 10% from peak, activate kill-switch
    max_drawdown_kill_revert_pct: float = 0.03   # Revert to 3% during drawdown (stay in game)

    # ── Stop-loss (spread-aware + IV-adjusted) ────────────────────────────────
    stop_loss_credit_mult:   float = 2.0    # Base: close at 2x credit received (NORMAL regime)
    stop_loss_hv_mult:       float = 2.5    # HIGH_VOL regime stop (2.5x)
    stop_loss_lv_mult:       float = 1.8    # LOW_VOL regime stop (1.8x)
    stop_iv_rank_scale:      float = 1.0    # Per-stock IV rank scaling
    stop_trail_trigger_pct:  float = 0.25   # Start trailing after 25% profit
    stop_trail_step_pct:     float = 0.20   # Trail tightens 20% of entry credit each step
    stop_spread_buffer_mult: float = 1.5    # Stop = raw_stop + 1.5 x half_spread
    stop_check_interval:     int   = 5      # Check stop every N days when healthy
    stop_check_dte_urgent:   int   = 14     # Check daily when DTE <= 14
    stop_check_move_pct:     float = 0.20   # Also check daily if premium moved > 20%

    # ── Profit targets (DTE-graduated per TastyTrade 200K-trade study) ────────
    profit_take_pct:       float = 0.50  # DTE > 21: close at 50% of max credit
    profit_take_pct_21dte: float = 0.70  # 14 < DTE <= 21: close at 70%
    profit_take_pct_14dte: float = 0.80  # 7 < DTE <= 14: close at 80%
    profit_take_pct_7dte:  float = 0.90  # DTE <= 7: close at 90%

    # ── Signal engine ─────────────────────────────────────────────────────────
    # 52W proximity thresholds for CALL signals (overbought)
    call_near_52w_high_pct:  float = 0.10    # Within 10% of 52W high (was 0.15)
    call_above_52w_high_pct: float = 0.10    # Or broken above by 10%
    # 52W proximity thresholds for PUT signals (oversold)
    put_near_52w_low_pct:    float = 0.25    # Within 25% of 52W low (was 0.15)
    put_decline_from_high:   float = 0.08    # Or 8% decline from 52W high

    # RSI thresholds
    rsi_overbought:  float = 65.0            # RSI > 65 -> call signal (was 70)
    rsi_oversold:    float = 35.0            # RSI < 35 -> put signal (was 30)

    # Bollinger Band thresholds
    bb_overbought:   float = 0.90            # %B > 0.90 -> call signal (was 0.95)
    bb_oversold:     float = 0.10            # %B < 0.10 -> put signal (was 0.05)

    # ── ML entry gate ─────────────────────────────────────────────────────────
    ml_confidence_min: float = 0.60          # Minimum XGBoost confidence to enter
    use_ml_gate:       bool  = True          # Can disable for rule-only baseline

    # ── Earnings blackout ─────────────────────────────────────────────────────
    earnings_blackout_days: int = 21         # Skip if earnings within 21 days

    # ── Position monitor ─────────────────────────────────────────────────────
    time_exit_dte:    int   = 21             # Force close at 21 DTE (TastyTrade research)
    delta_breach_pct: float = 0.01           # Close if delta > 1% of strike price
    vix_spike_exit:   float = 10.0           # Close if VIX spikes 10+ pts/day

    # ── Strangle upgrade (disabled) ───────────────────────────────────────────
    strangle_enabled:            bool  = False
    strangle_iv_rank_min:        float = 0.40
    strangle_vix_max:            float = 30.0
    strangle_call_delta_target:  float = 0.10
    strangle_min_call_premium:   float = 0.20

    # ── SGOV / T-bill cash sweep (Phase 1B) ───────────────────────────────────
    # Simulate earning T-bill rate on idle cash not used to cover open positions.
    # SGOV/BIL at ~4.5% annualized; TastyTrade applies ~25-30% margin req on SGOV.
    sgov_sweep_enabled:     bool  = True
    sgov_annual_yield:      float = 0.045    # 4.5% -- approximate 0-3 month T-bill rate
    sgov_margin_buffer_pct: float = 0.30     # Reserve 30% of NAV as margin buffer

    # ── Pathway B: VIX-conditional entry (Phase 2) ───────────────────────────
    # When HILO signal is quiet, allow entries triggered by elevated VIX + RSI.
    # Only fires when Pathway A is silent on a given symbol/day.
    pathway_b_enabled:         bool  = True
    pathway_b_vix_min:         float = 16.0  # VIX >= 16 (broader VRP capture)
    pathway_b_iv_rank_min:     float = 0.30  # IV Rank >= 30%
    pathway_b_rsi_oversold:    float = 35.0  # RSI < 35 for puts
    pathway_b_rsi_overbought:  float = 65.0  # RSI > 65 for calls
    pathway_b_max_slots:       int   = 3     # Max 3 concurrent Pathway B positions
    pathway_b_vix_pause:       float = 35.0  # Pause Pathway B when VIX >= 35
    pathway_b_size_mult:       float = 0.80  # 80% of normal sizing (conservative)

    # ── Phase 3b: Earnings IC Overlay ─────────────────────────────────────────
    # Separate defined-risk sub-strategy. Sells tight iron condors 1 day before
    # earnings to capture IV crush. Max 1% NAV per trade, 5% total allocation.
    # P&L tracked separately from HILO-IV core to preserve strategy isolation.
    earnings_ic_enabled:         bool  = True
    earnings_ic_min_iv_rank:     float = 0.70  # IV Rank >= 70% pre-earnings
    earnings_ic_min_iv_rv_ratio: float = 1.25  # IV must be 1.25x realized vol
    earnings_ic_min_credit:      float = 0.20  # Minimum net credit for full IC
    earnings_ic_max_risk_pct:    float = 0.01  # Max 1% of NAV per earnings IC
    earnings_ic_max_positions:   int   = 3     # Max 3 concurrent earnings IC positions
    earnings_ic_total_alloc_pct: float = 0.05  # Max 5% of NAV in earnings ICs total

    # ── Backtest ──────────────────────────────────────────────────────────────
    backtest_start:          str   = "2018-01-01"
    backtest_end:            str   = "2025-12-31"
    train_window_days:       int   = 504         # ~2 years for ML training
    test_window_days:        int   = 63          # ~3 months per OOS window
    step_days:               int   = 21          # Rolling step size
    commission_per_contract: float = 0.65        # Tastytrade commission


# Module-level default config instance
DEFAULT_CONFIG = OTMNakedConfig()
