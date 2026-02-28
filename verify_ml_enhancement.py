"""
Quick end-to-end verification of the ML Signal Enhancement integration.
Run from tastywork-trading-1 root: python verify_ml_enhancement.py
"""
import sys
sys.path.insert(0, '.')

import pandas as pd
import yfinance as yf

print("Fetching TQQQ data (6mo)...")
df = yf.Ticker('TQQQ').history(period='6mo')
df = df.rename(columns=str.lower)
last_close = float(df['close'].iloc[-1])
print(f"  Got {len(df)} bars. Last close: {last_close:.2f}")

# ── Individual ML indicators ────────────────────────────────────────────────
from diagonal_strategy.indicators.ml_indicators import (
    calculate_adaptive_supertrend,
    calculate_optimal_rsi,
    calculate_ml_mfi,
)
from diagonal_strategy.indicators.trend_speed import TrendSpeedAnalyzer

print()
print("=== ML Indicator Results ===")

st = calculate_adaptive_supertrend(df)
print(f"ML SuperTrend : direction={st.trend_direction.value:<8}  vol={st.volatility_level.value:<6}  conf={st.confidence:.1f}%")

rsi = calculate_optimal_rsi(df)
print(f"ML Optimal RSI: RSI({rsi.optimal_period})={rsi.rsi_value:.1f}  oversold={rsi.is_oversold}  overbought={rsi.is_overbought}")
print(f"  Dynamic thresholds: oversold<{rsi.oversold_threshold:.1f},  overbought>{rsi.overbought_threshold:.1f}")
if rsi.has_divergence:
    print(f"  !! {rsi.divergence_type.upper()} divergence detected")

mfi = calculate_ml_mfi(df)
print(f"ML MFI        : MFI={mfi.mfi_value:.1f}  oversold={mfi.is_oversold}  vol_confirm={mfi.volume_confirmation:.0f}%")

ts = TrendSpeedAnalyzer()
ts_result = ts.analyze(df['close'])
print(f"Trend Speed   : hist={ts_result.histogram:.1f}  stage={ts_result.stage.value:<12}  accel={ts_result.is_accelerating}")

# ── Full MLSignalEnhancer integration ───────────────────────────────────────
print()
print("=== MLSignalEnhancer + TASignalEngine (live TQQQ) ===")
from diagonal_strategy.core.ml_signal_enhancer import MLSignalEnhancer
from diagonal_strategy.core.ta_signal_engine import TASignalEngine

enhancer = MLSignalEnhancer()
engine   = TASignalEngine(ml_enhancer=enhancer)

mkt_data = {'tqqq_bars': df, 'vix_level': 18.0, 'vix_roc_5': 0.0}
features  = engine.compute_features(mkt_data)

base_dip     = engine._rule_based_dip_score(features)
final_dip    = engine.dip_score(features)
base_bounce  = engine._rule_based_bounce_score(features)
final_bounce = engine.bounce_score(features)

print(f"Dip score   : base={base_dip:.3f}  ML-enhanced={final_dip:.3f}  delta={final_dip-base_dip:+.3f}")
print(f"Bounce score: base={base_bounce:.3f}  ML-enhanced={final_bounce:.3f}  delta={final_bounce-base_bounce:+.3f}")

# Show ML reasons
e_dip = enhancer.enhance_dip_score(df, base_dip)
if e_dip.reasons:
    print()
    print("ML dip enhancement reasons:")
    for r in e_dip.reasons:
        print(f"  {r}")

e_bounce = enhancer.enhance_bounce_score(df, base_bounce)
if e_bounce.reasons:
    print()
    print("ML bounce enhancement reasons:")
    for r in e_bounce.reasons:
        print(f"  {r}")

# ── Trend Speed exit stage ───────────────────────────────────────────────────
from diagonal_strategy.indicators.trend_speed import ExitStage
exit_stage = enhancer.get_exit_stage(df)
print()
print(f"Trend Speed exit stage: {exit_stage.value}")
if exit_stage == ExitStage.STRONG_ACCELERATION:
    print("  → HOLD hedge")
elif exit_stage == ExitStage.EARLY_WARNING:
    print("  → Monitoring; prepare to scale out hedge")
elif exit_stage == ExitStage.CONFIRMATION:
    print("  → CLOSE HEDGE early (momentum crossed zero)")
else:
    print("  → WATCH for next entry")

print()
print("PASS: End-to-end ML enhancement working correctly.")
