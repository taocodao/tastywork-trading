#!/usr/bin/env python3
"""
HMM Semantic Validation Test
==============================
Diagnoses whether the current 3-state HMM is producing semantically valid 
regime labels by comparing state-conditional QQQ returns and VIX levels
against known ground truth expectations.

Expected for a valid 3-state HMM on QQQ 2019-2026:
  BULL state:     > 60% of days,  Ann. QQQ return > +15%, Avg VIX < 18
  SIDEWAYS state: 5-15% of days,  Ann. QQQ return -5% to +10%, VIX 18-25
  BEAR state:     15-25% of days, Ann. QQQ return < -10%, VIX > 22

If SIDEWAYS occupies > 30% of days → HMM is degenerate (confirmed broken).

Run from: d:\Projects\tastywork-trading-1\
  python validate_hmm_semantics.py
"""

import sys, warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

print("=" * 65)
print("  TurboCore Pro — HMM Semantic Validation Test")
print("=" * 65)

# ── Download data ────────────────────────────────────────────────
print("\n[1] Downloading QQQ, VIX, VIX3M data (2019-2026)...")
qqq = yf.download("QQQ", start="2017-01-01", end="2026-03-20",
                  auto_adjust=True, progress=False)["Close"].squeeze()
vix = yf.download("^VIX", start="2017-01-01", end="2026-03-20",
                  progress=False)["Close"].squeeze()
vix3m = yf.download("^VIX3M", start="2017-01-01", end="2026-03-20",
                    progress=False)["Close"].squeeze()
tqqq = yf.download("TQQQ", start="2017-01-01", end="2026-03-20",
                   auto_adjust=True, progress=False)["Close"].squeeze()

qqq   = qqq.dropna()
tqqq  = tqqq.reindex(qqq.index).ffill()
vix   = vix.reindex(qqq.index).ffill().fillna(20.0)
vix3m = vix3m.reindex(qqq.index).ffill().fillna(21.0)

# ── Run regime detector (production version) ─────────────────────
print("[2] Running TurboCoreRegimeDetector on full history...")
try:
    from src.turbocore_pro.ml.regime_detector import TurboCoreRegimeDetector
    from src.turbocore_pro.data_pipeline import TurboCoreDataPipeline

    pipeline = TurboCoreDataPipeline()
    pipeline.data['QQQ']   = pd.DataFrame({'Close': qqq, 'Open': qqq, 'High': qqq, 'Low': qqq, 'Volume': 0})
    pipeline.data['TQQQ']  = pd.DataFrame({'Close': tqqq, 'Open': tqqq, 'High': tqqq, 'Low': tqqq, 'Volume': 0})
    pipeline.data['^VIX']  = pd.DataFrame({'Close': vix})
    pipeline.data['^VIX3M']= pd.DataFrame({'Close': vix3m})
    master = pipeline.prepare_core_features(fetch_fred=False)

    detector = TurboCoreRegimeDetector()
    result_df = detector.predict_regimes(master)
    
    # Map regime names
    if 'final_regime' in result_df.columns:
        regimes = result_df['final_regime']
    elif 'hmm_state' in result_df.columns:
        regimes = result_df['hmm_state']
    else:
        regimes = result_df.iloc[:, -1]

except Exception as e:
    print(f"  RegimeDetector failed: {e}")
    print("  Falling back to raw hmmlearn directly...")
    
    # ── Fallback: run HMM directly from file if saved ────────────
    from sklearn.preprocessing import StandardScaler
    
    qqq_ret   = np.log(qqq / qqq.shift(1))
    qqq_vol   = qqq_ret.rolling(20).std() * np.sqrt(252)
    qqq_10d   = qqq.pct_change(10)
    vts       = (vix3m - vix) / vix.replace(0, np.nan)
    
    feats = pd.DataFrame({
        'qqq_ret':  qqq_ret,
        'qqq_vol':  qqq_vol,
        'qqq_10d':  qqq_10d,
        'vix':      vix,
        'vts':      vts,
    }).dropna()
    
    from hmmlearn.hmm import GaussianHMM
    scaler = StandardScaler()
    X = scaler.fit_transform(feats)
    
    model = GaussianHMM(n_components=3, covariance_type='full',
                        n_iter=200, random_state=42)
    model.fit(X)
    states = model.predict(X)
    
    # Map states to regime names by ordering means (low vol = bull)
    state_means = model.means_[:, 1]  # vol feature
    order = np.argsort(state_means)   # ascending vol: BULL, SIDEWAYS, BEAR
    state_map = {order[0]: 'BULL', order[1]: 'SIDEWAYS', order[2]: 'BEAR'}
    
    regimes = pd.Series([state_map[s] for s in states], index=feats.index)

# ── Align to the backtest window only ───────────────────────────
start_date = "2019-01-01"
regimes_bt = regimes.loc[start_date:]
qqq_bt     = qqq.loc[start_date:]
vix_bt     = vix.loc[start_date:]
qqq_ret_bt = np.log(qqq_bt / qqq_bt.shift(1))

# ── State occupancy ──────────────────────────────────────────────
print("\n[3] STATE OCCUPANCY (Backtest window 2019-2026):")
print("-" * 65)
total_days = len(regimes_bt.dropna())
state_counts = regimes_bt.value_counts()
for state, count in state_counts.items():
    pct = count / total_days * 100
    flag = ""
    if state == "SIDEWAYS" and pct > 30:
        flag = "  ← 🔴 DEGENERATE (expected 5-15%)"
    elif state == "BULL" and pct < 40:
        flag = "  ← 🔴 TOO LOW (expected 60-70%)"
    elif state == "BEAR" and pct > 35:
        flag = "  ← 🔴 TOO HIGH (expected 15-25%)"
    print(f"  {state:<20} {count:>5d} days  ({pct:5.1f}%){flag}")

# ── State-conditional QQQ returns ───────────────────────────────
print("\n[4] STATE-CONDITIONAL QQQ METRICS:")
print("-" * 65)
print(f"  {'State':<20} {'Ann.Return':>12} {'Avg VIX':>10} {'Win%':>8} {'Verdict'}")
print(f"  {'-'*20} {'-'*12} {'-'*10} {'-'*8} {'-'*15}")

for state in ["BULL", "SIDEWAYS", "BEAR"]:
    if state not in regimes_bt.values:
        continue
    mask = regimes_bt == state
    mask = mask.reindex(qqq_ret_bt.index).fillna(False)
    
    ann_ret  = qqq_ret_bt[mask].mean() * 252
    avg_vix  = vix_bt.reindex(qqq_ret_bt.index)[mask].mean()
    win_pct  = (qqq_ret_bt[mask] > 0).mean() * 100
    
    # Verdict
    if state == "BULL":
        verdict = "✅ OK" if ann_ret > 0.15 else "🔴 BROKEN"
    elif state == "SIDEWAYS":
        verdict = "✅ OK" if (ann_ret > -0.10 and ann_ret < 0.15) else "🔴 BROKEN"
    else:  # BEAR
        verdict = "✅ OK" if ann_ret < 0.00 else "🔴 BROKEN"
    
    print(f"  {state:<20} {ann_ret:>+11.1%} {avg_vix:>10.1f} {win_pct:>7.1f}% {verdict}")

# ── Annual QQQ returns as ground truth ──────────────────────────
print("\n[5] QQQ ANNUAL RETURNS (ground truth for HMM validation):")
print("-" * 65)
qqq_annual = qqq_bt.resample('Y').last().pct_change().dropna()
for year, ret in qqq_annual.items():
    print(f"  {year.year}: {ret:+.1%}")

# ── Top diagnosis ─────────────────────────────────────────────────
print("\n[6] DIAGNOSIS:")
print("-" * 65)
sideways_pct = state_counts.get("SIDEWAYS", 0) / total_days * 100
bull_pct     = state_counts.get("BULL", 0)     / total_days * 100

if sideways_pct > 35:
    print(f"  🔴 CRITICAL: SIDEWAYS = {sideways_pct:.1f}% — HMM is DEGENERATE.")
    print(f"     Expected: 5-15%. SIDEWAYS absorbed the bull-market center.")
    print(f"     FIX: Rebuild with 2-state HMM or re-initialize transmat.")
elif sideways_pct > 20:
    print(f"  🟡 WARNING: SIDEWAYS = {sideways_pct:.1f}% — HMM is marginal.")
    print(f"     Expected: 5-15%. Partial misclassification likely.")
else:
    print(f"  ✅ OK: SIDEWAYS = {sideways_pct:.1f}% — within expected range.")

if bull_pct < 45:
    print(f"  🔴 CRITICAL: BULL = {bull_pct:.1f}% — too low for 2019-2026 bull market.")
    print(f"     Expected: 60-70% given QQQ's +188% total return over this period.")

print("\n" + "=" * 65)
print("  Validation complete. Review findings above before changing")
print("  any allocation parameters.")
print("=" * 65)
