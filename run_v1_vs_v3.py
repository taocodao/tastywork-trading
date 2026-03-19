"""
V1 vs V3 Backtest Comparison
==============================
Runs two scenarios back-to-back using the same data and engine:

V1 Baseline: Original swing-mode parameters (30-35 DTE, RSI-2 bounce exits, hard 200MA gate)
V3 Rules:    New DTE asymmetry (60-90/21-35), Three Laws exits (profit target, BTC, roll-down)

Usage:
    python run_v1_vs_v3.py
"""

import logging
import json
import copy
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('data/v1_vs_v3_comparison.log'),
    ]
)
logger = logging.getLogger(__name__)

# ─── V1 BASELINE PARAM OVERRIDES ──────────────────────────────────────────────
V1_PARAMS = {
    'NORMAL': {
        'mode': 'SWING',
        'anchor_dte': 35,
        'anchor_delta': -0.40,
        'hedge_dte': 10,
        'hedge_delta': -0.20,
        'max_cycles': 1,
        'anchor_profit_target_pct': 0.50,
        'anchor_stop_loss_mult': 2.0,
        'hedge_close_decay_pct': 0.50,
        'max_naked_hours': 4,
        'vix_spike_close': 2.5,
        'swing_max_hold_days': 7,
    },
    'HIGH_VOL': {
        'mode': 'SWING',
        'anchor_dte': 30,
        'anchor_delta': -0.40,
        'hedge_dte': 7,
        'hedge_delta': -0.22,
        'max_cycles': 1,
        'anchor_profit_target_pct': 0.40,
        'anchor_stop_loss_mult': 1.5,
        'hedge_close_decay_pct': 0.50,
        'max_naked_hours': 4,
        'vix_spike_close': 2.0,
        'swing_max_hold_days': 5,
    },
    'LOW_VOL': {
        'mode': 'SWING',
        'anchor_dte': 35,
        'anchor_delta': -0.38,
        'hedge_dte': 10,
        'hedge_delta': -0.18,
        'max_cycles': 1,
        'anchor_profit_target_pct': 0.50,
        'anchor_stop_loss_mult': 2.0,
        'hedge_close_decay_pct': 0.50,
        'max_naked_hours': 4,
        'vix_spike_close': 3.0,
        'swing_max_hold_days': 7,
    },
}

def run_scenario(engine, label, config, param_override=None):
    logger.info(f"\n{'='*60}")
    logger.info(f"Running: {label}")
    logger.info(f"{'='*60}")

    # Temporarily patch params if needed
    original_params = {}
    if param_override:
        for regime, params in param_override.items():
            original_params[regime] = config.TQQQ_DIAGONAL_PARAMS.get(regime, {}).copy()
            config.TQQQ_DIAGONAL_PARAMS[regime] = params

    # Also patch law thresholds for V1
    if param_override:
        config._v1_law1_dte = getattr(config, 'V3_LAW1_FORCE_CLOSE_DTE', 7)
        config._v1_law1_hdg = getattr(config, 'V3_LAW1_HEDGE_REPLACE_DTE', 7)
        config._v1_law3_btc = getattr(config, 'V3_LAW3_SHORT_BTC_PCT', 0.75)
        config._v1_law2_roll = getattr(config, 'V3_LAW2_ROLL_TRIGGER_PCT', -0.90)
        config.V3_LAW1_FORCE_CLOSE_DTE   = 7      # Same for V1 (use DTE)
        config.V3_LAW1_HEDGE_REPLACE_DTE = 0      # Disable long put replacement for V1
        config.V3_LAW3_SHORT_BTC_PCT     = 2.0    # Disable Law 3 BTC for V1 (pure DTE exits)
        config.V3_LAW2_ROLL_TRIGGER_PCT  = -99.0  # Disable roll-down for V1

    metrics = engine.run_scenario()

    # Restore
    if param_override:
        for regime, orig in original_params.items():
            config.TQQQ_DIAGONAL_PARAMS[regime] = orig
        config.V3_LAW1_FORCE_CLOSE_DTE   = config._v1_law1_dte
        config.V3_LAW1_HEDGE_REPLACE_DTE = config._v1_law1_hdg
        config.V3_LAW3_SHORT_BTC_PCT     = config._v1_law3_btc
        config.V3_LAW2_ROLL_TRIGGER_PCT  = config._v1_law2_roll

    logger.info(f"\nResult [{label}]:")
    logger.info(f"  Total Return   : {metrics['total_return']:+.2%}")
    logger.info(f"  Max Drawdown   : {metrics['max_drawdown']:.2%}")
    logger.info(f"  Sharpe Ratio   : {metrics['sharpe']:.3f}")
    logger.info(f"  Total Trades   : {metrics['trades']}")

    # Win rate from trade history
    trades = engine.trades_history
    opens  = [t for t in trades if t['action'] == 'OPEN']
    closes = [t for t in trades if t['action'] in ('CLOSE_ANCHOR', 'CLOSE_ALL')]
    logger.info(f"  Open signals   : {len(opens)}")

    os.makedirs('data', exist_ok=True)
    fname = f"data/{label.replace(' ', '_').lower()}_trades.json"
    with open(fname, 'w') as f:
        json.dump(trades, f, indent=2, default=str)
    logger.info(f"  Saved trades   : {fname}")

    return metrics

def main():
    from diagonal_strategy.backtest.data_loader import DiagonalDataLoader
    from diagonal_strategy.core.ta_signal_engine import TASignalEngine
    from diagonal_strategy.ml.oscillation_predictor import OscillationPredictor
    from diagonal_strategy.core.risk_manager import DiagonalRiskManager
    from diagonal_strategy.backtest.engine import BacktestEngine
    import diagonal_strategy.config as config

    PRINCIPAL = 5000
    config.ACCOUNT_VALUE = PRINCIPAL

    loader = DiagonalDataLoader()
    df = loader.load_historical_data("2019-01-01", use_cache=True)
    if df is None or df.empty:
        logger.error("Failed to load data. Exiting.")
        return

    osc = OscillationPredictor("diagonal_strategy/ml/models/xgb_oscillator.json")
    ta  = TASignalEngine(ml_model=osc)
    rx  = DiagonalRiskManager(config.ACCOUNT_VALUE)

    engine = BacktestEngine(df, config, ta, rx, osc)

    # ── V1 Baseline ──────────────────────────────────────────────────────────
    v1 = run_scenario(engine, "V1 Baseline (30-35DTE swing exits)", config, param_override=V1_PARAMS)

    # Re-init engine state for V3 run
    engine2 = BacktestEngine(df, config, ta, DiagonalRiskManager(config.ACCOUNT_VALUE), osc)
    # ── V3 Rules ─────────────────────────────────────────────────────────────
    v3 = run_scenario(engine2, "V3 Rules (60-75DTE Three Laws)", config)

    # ── Final Comparison ─────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("COMPARISON SUMMARY")
    print("="*60)
    print(f"{'Metric':<20} {'V1 Baseline':>14} {'V3 Rules':>14} {'Chg':>10}")
    print("-"*60)
    metrics = ['total_return', 'max_drawdown', 'sharpe', 'trades']
    labels  = ['Total Return', 'Max Drawdown', 'Sharpe', 'Trades']
    for key, lbl in zip(metrics, labels):
        v1v = v1[key]; v3v = v3[key]
        if key in ('total_return', 'max_drawdown'):
            print(f"{lbl:<20} {v1v:>+13.2%} {v3v:>+13.2%} {(v3v-v1v):>+9.2%}")
        else:
            print(f"{lbl:<20} {v1v:>14.3f} {v3v:>14.3f} {(v3v-v1v):>+9.3f}")
    print("="*60)

    results = {'v1': v1, 'v3': v3}
    with open('data/v1_vs_v3_comparison.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print("\nSaved comparison to data/v1_vs_v3_comparison.json")

if __name__ == "__main__":
    main()
