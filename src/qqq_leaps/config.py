"""
QQQ LEAPS Strategy — Configuration
====================================
All tunable parameters in one place. Modify here to adjust strategy behavior
without touching any other file.
"""
from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class QQQLeapsConfig:
    # ── Data ─────────────────────────────────────────────────────────────────
    ticker: str = "QQQ"
    vix_ticker: str = "^VIX"
    vix3m_ticker: str = "^VIX3M"
    vix1y_ticker: str = "^VIX1Y"
    rf_ticker: str = "^IRX"

    # ── Entry Gates ───────────────────────────────────────────────────────────
    entry_rsi14_max: float = 35.0          # RSI(14) must be below this (oversold)
    entry_rsi2_max: float = 20.0           # RSI(2) must be below this for strongest signal
    entry_gap_down_min: float = 0.003      # Gap-down >= 0.3%  (was 0.5%; lowered to capture moderate dips)
    entry_ml_confidence_min: float = 0.45  # Layer B gate (0.45 = matches regime-specialist thresholds)
    entry_vix_max: float = 40.0            # No entries above VIX 40 (panic mode)
    entry_sma100_gate: bool = True         # Must be above 100-DMA (primary regime gate)

    # ── Layer A: Regime → LEAPS Parameters ───────────────────────────────────
    delta_bull: float = 0.85               # Aggressive bull regime
    delta_neutral: float = 0.80            # Sideways/neutral
    delta_bear: float = 0.65              # Weak bear (only if entry allowed)
    dte_bull: int = 365                    # 12-month LEAPS in bull
    dte_neutral: int = 540                 # 18-month LEAPS in neutral
    dte_bear: int = 730                    # 24-month LEAPS if somehow entering in bear

    # ── Layer C: Event-Driven Rolling ─────────────────────────────────────────
    roll_trigger_delta_high: float = 0.90  # Signal A: delta drift too high → roll down
    roll_trigger_dte_min: int = 180        # Signal B: < 180 DTE → roll out
    roll_trigger_price_up: float = 0.20    # Signal C: underlying up 20%+ from entry → roll

    # ── Layer D: PMCC Short Call Management (v2 ruleset) ─────────────────────
    pmcc_enabled: bool = True
    # Regime-conditional short call deltas
    pmcc_delta_bull_strong: float = 0.28    # Target delta in BULL_STRONG
    pmcc_delta_bull_moderate: float = 0.23  # Target delta in BULL_MODERATE
    pmcc_delta_defensive: float = 0.15      # Defensive/rolldown target delta
    pmcc_target_delta: float = 0.28         # Default target (backwards compat)
    pmcc_max_delta: float = 0.40            # Hard ceiling — never sell > 0.40 delta
    pmcc_min_delta: float = 0.15            # Hard floor — below this, skip (not worth it)
    pmcc_dte: int = 32                      # 30–35 DTE target (peak theta decay)
    # Exit / profit rules (v2: BCI 20%/10% instead of simple 50%)
    pmcc_profit_target: float = 0.50        # Kept for backwards compat (50% midpoint)
    pmcc_profit_take_early_pct: float = 0.20  # Close at 20% of credit (early in cycle: <10 days)
    pmcc_profit_take_late_pct: float = 0.10   # Close at 10% of credit (late in cycle: >10 days)
    pmcc_early_cycle_days: int = 10          # Threshold between early/late profit-take
    pmcc_gamma_manage_dte: int = 21          # Force management if DTE falls to ≤21
    pmcc_loss_limit_multiple: float = 2.0    # Buy back if price >= 2× credit collected
    pmcc_force_close_gap_pct: float = 0.03   # Close if QQQ within 3% of short strike
    pmcc_roll_delta_trigger: float = 0.40    # Roll if short call delta >= 0.40 (before assignment)
    pmcc_min_leaps_dte: int = 60             # Don't add PMCC if LEAPS has < 60 DTE
    pmcc_min_leaps_age_days: int = 5         # LEAPS must be held ≥ 5 days before PMCC
    pmcc_qqq_recovery_pct: float = 0.02      # QQQ must recover ≥ 2% from LEAPS entry before opening short
    pmcc_min_vix: float = 16.0               # Don't sell calls in crushingly low IV
    pmcc_max_vix: float = 35.0               # Don't sell calls in extreme panic (VIX > 35)
    pmcc_min_premium: float = 0.50           # Min credit per contract ($50 total) to be worthwhile
    pmcc_roll_new_expiry_days: int = 21      # When rolling out, add 21 days to expiry

    # ── Layer E: Drawdown Guard ───────────────────────────────────────────────
    dd_delta_rolldown_trigger: float = 0.65  # LEAPS delta < 0.65 -> roll short call down
    dd_delta_exit_trigger: float = 0.30      # LEAPS delta < 0.30 -> exit
    dd_dte_exit_trigger: int = 60            # Exit if DTE < 60 AND delta < 0.30
    dd_rolldown_target_delta: float = 0.50   # Target short call delta after rolldown

    # ── Layer F: Liquidity Gate ───────────────────────────────────────────────
    min_open_interest: int = 5000
    max_spread_pct: float = 0.015          # Bid-ask / mid < 1.5%
    min_daily_volume_5d: int = 100

    # ── Position Sizing ───────────────────────────────────────────────────────
    max_positions: int = 3
    max_position_pct: float = 0.33         # 33% NAV per slot (3 slots = ~100% deployed)
    max_contracts_hard_cap: int = 5        # Never trade more than 5 LEAPS contracts per position
    cash_reserve_pct: float = 0.05         # 5% cash buffer

    # ── Backtest I/O ──────────────────────────────────────────────────────────
    initial_capital: float = 25_000.0
    commission: float = 1.00              # $1/contract commission

    def slippage_for_vix(self, vix: float, mid_price: float) -> float:
        """Regime-aware half-spread slippage per contract per side."""
        if vix < 18:
            spread_pct = 0.007
        elif vix < 25:
            spread_pct = 0.012
        elif vix < 35:
            spread_pct = 0.020
        else:
            spread_pct = 0.040
        return mid_price * 100 * spread_pct / 2


    # ── IV Scaling (B-S calibration) ──────────────────────────────────────────
    iv_qqq_premium: float = 1.10           # QQQ vol premium (multiplier) over VIX1Y
    iv_scale_short: float = 1.12           # OTM short call IV = VIX × 1.12

    # ── ML Training ───────────────────────────────────────────────────────────
    # Walk-forward: train on `train_months`, test on `test_months`, step `step_months`
    wf_train_months: int = 48              # 4-year training window
    wf_test_months: int = 6               # 6-month OOS test
    wf_step_months: int = 3               # Advance 3 months each window
    wf_embargo_days: int = 5              # Gap between train end and test start
    ml_label_forward_days: int = 30       # "QQQ up ≥ X% in 30 days?"
    ml_label_target_gain: float = 0.04    # 4% gain target for positive label
    ml_min_oos_sharpe: float = 0.50       # Reject model if OOS Sharpe < 0.50
