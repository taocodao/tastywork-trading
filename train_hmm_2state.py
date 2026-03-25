#!/usr/bin/env python3
"""
TurboCore Pro — 2-State HMM Trainer
======================================
Replaces the degenerate 3-state HMM with a validated 2-state (BULL/BEAR)
Gaussian HMM using semantically anchored initialization.

Why 2 states:
  - 3-state HMM is pathologically degenerate: SIDEWAYS = 48.7% of days
    (expected 5-10%), absorbing misclassified bull-market days
  - 2-state model has 4 transmat params vs 9 → more reliable estimation
    on ~1800 observations
  - Academic consensus: Hamilton (1989) and successors use 2-state for
    equity regime trading. "Intermediate" states lack economic analog.
  - XGBoost confidence replaces the discriminatory function of SIDEWAYS:
    low-confidence BULL tier = what SIDEWAYS was attempting to capture

Architecture after this fix:
  2-State HMM → BULL or BEAR hard gate
  XGBoost confidence → continuous modulation within BULL
    > 0.65  → full LEAPS (60%)
    0.45-0.65 → reduced LEAPS (30-40%)
    < 0.45  → QQQ-only (no leverage)

Run:
  python train_hmm_2state.py

Saves to:
  src/turbocore_pro/ml/turbocore_hmm_2state.joblib
  src/turbocore_pro/ml/turbocore_hmm_2state_scaler.joblib
"""

import sys, warnings, logging
import numpy as np
import pandas as pd
import yfinance as yf
import joblib
from pathlib import Path
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("HMM2State")

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

MODEL_FILE  = ROOT / "src/turbocore_pro/ml/turbocore_hmm_2state.joblib"
SCALER_FILE = ROOT / "src/turbocore_pro/ml/turbocore_hmm_2state_scaler.joblib"

try:
    from hmmlearn.hmm import GaussianHMM
except ImportError:
    log.error("hmmlearn not installed. Run: pip install hmmlearn")
    sys.exit(1)


# ── Download data ────────────────────────────────────────────────
log.info("Downloading market data (2017-2026)...")
qqq   = yf.download("QQQ",   start="2017-01-01", end="2026-03-20", auto_adjust=True,  progress=False)["Close"].squeeze()
tqqq  = yf.download("TQQQ",  start="2017-01-01", end="2026-03-20", auto_adjust=True,  progress=False)["Close"].squeeze()
vix   = yf.download("^VIX",  start="2017-01-01", end="2026-03-20", progress=False)["Close"].squeeze()
vix3m = yf.download("^VIX3M",start="2017-01-01", end="2026-03-20", progress=False)["Close"].squeeze()

qqq   = qqq.dropna()
tqqq  = tqqq.reindex(qqq.index).ffill()
vix   = vix.reindex(qqq.index).ffill().fillna(20.0)
vix3m = vix3m.reindex(qqq.index).ffill().fillna(21.0)

# ── Build features ────────────────────────────────────────────────
log.info("Engineering HMM features...")
qqq_log_ret  = np.log(qqq / qqq.shift(1))
qqq_vol_20d  = qqq_log_ret.rolling(20).std() * np.sqrt(252)
qqq_10d_ret  = np.log(qqq / qqq.shift(10))
vix_term_slope = vix3m - vix   # Positive = contango (calm), negative = backwardation (stress)

features = pd.DataFrame({
    'qqq_vol_20d':     qqq_vol_20d,
    'vix_close':       vix,
    'qqq_10d_return':  qqq_10d_ret,
    'vix_term_slope':  vix_term_slope,
}).dropna()

log.info("Feature matrix: %d rows x %d cols", len(features), features.shape[1])

# ── Scale features ────────────────────────────────────────────────
scaler  = StandardScaler()
X_all   = scaler.fit_transform(features.values)

# Training window: use all available data (2017 onward) for maximum estimation reliability
# Walk-forward inference will use the saved model on growing windows
X_train = X_all
log.info("Training on %d samples (full history)...", len(X_train))


# ── Build and fit 2-state HMM ─────────────────────────────────────
# Semantically anchored transmat: equity regimes are persistent
#   BULL: avg regime length ~4-12 months → 1/(1-0.97) = 33 days avg
#   BEAR: avg bear market ~2-4 months    → 1/(1-0.95) = 20 days avg
model = GaussianHMM(
    n_components    = 2,
    covariance_type = 'full',
    n_iter          = 300,
    tol             = 1e-5,
    init_params     = 'mc',    # Only random-init means and covars — NOT transmat
    params          = 'stmc',  # Learn all during EM
    random_state    = 42,
)

# Semantically anchored transmat (overrides init_params='mc' for transmat)
model.transmat_ = np.array([
    [0.97, 0.03],   # BULL: 97% stays bull (33-day avg regime length)
    [0.05, 0.95],   # BEAR: 95% stays bear (20-day avg — bears are shorter)
])

# Semantic mean initialization (z-score space, so ~1 std deviation apart)
# State 0 = BULL:  positive momentum, low vol, low VIX, contango VTS
# State 1 = BEAR:  negative momentum, high vol, high VIX, backwardation VTS
# Feature order: [qqq_vol_20d, vix_close, qqq_10d_return, vix_term_slope]
model.means_ = np.array([
    [-0.70, -0.70,  0.60,  0.30],   # BULL: low vol/VIX, positive momentum, contango
    [ 0.80,  0.80, -0.60, -0.40],   # BEAR: high vol/VIX, negative momentum, backwardation
])

model.fit(X_train)
log.info("HMM training complete. Converged: %s", model.monitor_.converged)

# ── Map states semantically (by qqq_10d_return mean, feature index 2) ────────
# State with HIGHER mean qqq_10d_return = BULL
# State with LOWER  mean qqq_10d_return = BEAR
# Using single feature (momentum) is more reliable than summing all features
momentum_means = model.means_[:, 2]  # qqq_10d_return column
bull_state = int(np.argmax(momentum_means))
bear_state = int(np.argmin(momentum_means))

state_mapping = {bull_state: 'BULL', bear_state: 'BEAR'}
log.info("State mapping (by momentum): %s", state_mapping)
log.info("Learned means (qqq_10d_return col): state0=%.3f, state1=%.3f",
         momentum_means[0], momentum_means[1])

# ── Log learned transmat ──────────────────────────────────────────
log.info("Learned transmat diagonal: BULL=%.3f, BEAR=%.3f",
         model.transmat_[bull_state, bull_state],
         model.transmat_[bear_state, bear_state])

# ── Semantic validation ───────────────────────────────────────────
log.info("")
log.info("=" * 60)
log.info("  SEMANTIC VALIDATION (2019-2026 backtest window)")
log.info("=" * 60)

# Slice to backtest window
bt_mask    = features.index >= "2019-01-01"
X_bt       = X_all[bt_mask]
dates_bt   = features.index[bt_mask]
qqq_bt     = qqq.reindex(dates_bt)
vix_bt     = vix.reindex(dates_bt)
qqq_1d_ret = qqq_bt.pct_change()

# Use predict_proba for posterior smoothing (not hard Viterbi)
all_probs   = model.predict_proba(X_all)
probs_bt    = all_probs[bt_mask]
hard_states = np.argmax(probs_bt, axis=1)
labels      = np.array([state_mapping[s] for s in hard_states])

# Print occupancy and return validation
total = len(labels)
for state_name in ['BULL', 'BEAR']:
    mask      = labels == state_name
    count     = mask.sum()
    pct       = count / total * 100
    ann_ret   = qqq_1d_ret[mask].mean() * 252 if mask.sum() > 0 else 0
    avg_vix   = vix_bt[mask].mean() if mask.sum() > 0 else 0

    if state_name == 'BULL':
        verdict = "✅" if (ann_ret > 0.12 and pct > 50) else "🔴 FAILED VALIDATION"
    else:
        verdict = "✅" if (ann_ret < 0.05 and pct < 40) else "🔴 FAILED VALIDATION"

    log.info("  %s: %d days (%.1f%%) | Ann.QQQ=%.1f%% | Avg VIX=%.1f %s",
             state_name, count, pct, ann_ret * 100, avg_vix, verdict)

log.info("=" * 60)

# ── Check if model passes validation ─────────────────────────────
bull_mask     = labels == 'BULL'
bull_pct      = bull_mask.sum() / total * 100
bull_ann_ret  = qqq_1d_ret[bull_mask].mean() * 252 if bull_mask.sum() > 0 else 0

if bull_pct < 50 or bull_ann_ret < 0.10:
    log.error("MODEL FAILED SEMANTIC VALIDATION — not saving.")
    log.error("  BULL occupancy = %.1f%% (need > 50%%)", bull_pct)
    log.error("  BULL ann. QQQ return = %.1f%% (need > 10%%)", bull_ann_ret * 100)
    log.error("  Try rerunning — Baum-Welch may have hit different local optimum.")
    sys.exit(1)

# ── Save model ────────────────────────────────────────────────────
joblib.dump({'model': model, 'mapping': state_mapping, 'n_states': 2}, MODEL_FILE)
joblib.dump(scaler, SCALER_FILE)
log.info("2-state HMM saved to: %s", MODEL_FILE)
log.info("Scaler saved to:      %s", SCALER_FILE)
log.info("")
log.info("Next step: update regime_detector.py to load and use")
log.info("  turbocore_hmm_2state.joblib with posterior probability blending.")
