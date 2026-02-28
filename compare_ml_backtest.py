"""
compare_ml_backtest.py
======================
Runs the diagonal strategy backtest TWICE:
  1. Baseline  — TASignalEngine with rule-based dip/bounce scoring only
  2. ML-Enhanced — TASignalEngine with MLSignalEnhancer injected

Prints a side-by-side comparison of all key metrics.

Usage:
    python compare_ml_backtest.py [--start 2021-01-01] [--end 2024-01-01]
                                  [--regime NORMAL]
                                  [--principal 25000]
"""

import argparse
import logging
import json
import sys
import os

logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
sys.path.insert(0, '.')


def build_engine(ml_enhanced: bool, principal: float, start_date: str):
    """Build a BacktestEngine with or without ML enhancement."""
    import diagonal_strategy.config as config
    from diagonal_strategy.core.ta_signal_engine import TASignalEngine
    from diagonal_strategy.ml.oscillation_predictor import OscillationPredictor
    from diagonal_strategy.core.risk_manager import DiagonalRiskManager
    from diagonal_strategy.backtest.data_loader import DiagonalDataLoader
    from diagonal_strategy.backtest.engine import BacktestEngine

    config.ACCOUNT_VALUE = principal

    ml_enhancer = None
    if ml_enhanced:
        try:
            from diagonal_strategy.core.ml_signal_enhancer import MLSignalEnhancer
            ml_enhancer = MLSignalEnhancer()
        except Exception as e:
            print(f"  [WARN] Could not load MLSignalEnhancer: {e}")

    osc_predictor = OscillationPredictor(
        "diagonal_strategy/ml/models/xgb_oscillator.json"
    )
    ta_engine = TASignalEngine(ml_model=None, ml_enhancer=ml_enhancer)
    rx_manager = DiagonalRiskManager(config.ACCOUNT_VALUE)

    loader = DiagonalDataLoader()
    df = loader.load_historical_data(start_date, use_cache=True)
    if df is None or df.empty:
        print("ERROR: Could not load historical data.")
        sys.exit(1)

    return BacktestEngine(df, config, ta_engine, rx_manager, osc_predictor)


def format_metric(val, fmt='pct'):
    if val is None:
        return 'N/A'
    if fmt == 'pct':
        return f"{val*100:+.2f}%"
    if fmt == 'float':
        return f"{val:.3f}"
    if fmt == 'int':
        return f"{int(val)}"
    if fmt == 'dollar':
        return f"${val:,.0f}"
    return str(val)


def compare(baseline: dict, enhanced: dict):
    """Print a formatted comparison table."""
    metrics = [
        ('total_return',      'Total Return',       'pct'),
        ('sharpe',            'Sharpe Ratio',        'float'),
        ('win_rate',          'Win Rate',            'pct'),
        ('max_drawdown',      'Max Drawdown',        'pct'),
        ('avg_trade_pnl',     'Avg Trade P&L',       'dollar'),
        ('total_trades',      'Total Trades',        'int'),
        ('avg_cycles',        'Avg Hedge Cycles',    'float'),
        ('profitable_months', 'Profitable Months',   'pct'),
    ]

    col_w = 22
    print()
    print("=" * 68)
    print(f"  {'METRIC':<25}  {'BASELINE':>{col_w}}  {'ML-ENHANCED':>{col_w}}")
    print("=" * 68)
    for key, label, fmt in metrics:
        b = baseline.get(key)
        e = enhanced.get(key)

        b_str = format_metric(b, fmt)
        e_str = format_metric(e, fmt)

        # Delta indicator
        delta = ''
        if b is not None and e is not None:
            diff = e - b
            if fmt in ('pct', 'float', 'dollar') and diff != 0:
                sign = '▲' if diff > 0 else '▼'
                # For drawdown, lower is better
                if key == 'max_drawdown':
                    sign = '▲' if diff < 0 else '▼'
                if fmt == 'pct':
                    delta = f"  {sign} {abs(diff)*100:.2f}pp"
                elif fmt == 'float':
                    delta = f"  {sign} {abs(diff):.3f}"
                else:
                    delta = f"  {sign} ${abs(diff):,.0f}"

        print(f"  {label:<25}  {b_str:>{col_w}}  {e_str:>{col_w}}{delta}")

    print("=" * 68)
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Backtest: Baseline rule-based vs ML-enhanced diagonal strategy'
    )
    parser.add_argument('--start',     default='2021-01-01', help='Start date (default: 2021-01-01)')
    parser.add_argument('--end',       default='2024-01-01', help='End date   (default: 2024-01-01)')
    parser.add_argument('--regime',    default=None,         help='Regime filter (LOW_VOL, NORMAL, HIGH_VOL)')
    parser.add_argument('--principal', type=float, default=25000.0, help='Account size ($)')
    args = parser.parse_args()

    print(f"\nDiagonal Strategy Backtest Comparison")
    print(f"  Period   : {args.start} → {args.end}")
    print(f"  Regime   : {args.regime or 'ALL (adaptive)'}")
    print(f"  Principal: ${args.principal:,.0f}")

    # ── Run 1: Baseline ─────────────────────────────────────────────────────
    print(f"\n[1/2] Running BASELINE (rule-based scoring)...")
    engine_base = build_engine(ml_enhanced=False, principal=args.principal, start_date=args.start)
    baseline_metrics = engine_base.run_scenario(
        start_date=args.start, end_date=args.end, regime_filter=args.regime
    )
    print(f"  ✓ Baseline complete  — return={baseline_metrics.get('total_return', 0)*100:.2f}%  "
          f"sharpe={baseline_metrics.get('sharpe', 0):.3f}  "
          f"trades={baseline_metrics.get('total_trades', 0)}")

    # ── Run 2: ML-Enhanced ──────────────────────────────────────────────────
    print(f"\n[2/2] Running ML-ENHANCED (ML RSI + SuperTrend + MFI + TrendSpeed)...")
    engine_ml = build_engine(ml_enhanced=True, principal=args.principal, start_date=args.start)
    enhanced_metrics = engine_ml.run_scenario(
        start_date=args.start, end_date=args.end, regime_filter=args.regime
    )
    print(f"  ✓ ML-Enhanced complete — return={enhanced_metrics.get('total_return', 0)*100:.2f}%  "
          f"sharpe={enhanced_metrics.get('sharpe', 0):.3f}  "
          f"trades={enhanced_metrics.get('total_trades', 0)}")

    # ── Comparison table ────────────────────────────────────────────────────
    compare(baseline_metrics, enhanced_metrics)

    # Save results
    os.makedirs('data', exist_ok=True)
    output = {
        'run_params': vars(args),
        'baseline':   baseline_metrics,
        'ml_enhanced': enhanced_metrics,
    }
    with open('data/ml_comparison_results.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print("Results saved to: data/ml_comparison_results.json")


if __name__ == '__main__':
    main()
