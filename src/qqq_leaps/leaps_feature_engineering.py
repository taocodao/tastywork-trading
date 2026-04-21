"""
QQQ LEAPS — Feature Engineering
=================================
Builds the full feature matrix used by Layers A (regime) and B (entry classifier).
Extends TurboCore Pro's existing pipeline with QQQ-LEAPS-specific features.
"""
import math
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def build_leaps_features(
    qqq_close: pd.Series,
    qqq_open: pd.Series,
    vix: pd.Series,
    vix3m: pd.Series,
    rf: pd.Series,
) -> pd.DataFrame:
    """
    Computes the complete feature matrix for QQQ LEAPS entry classification.

    Args:
        qqq_close:  QQQ daily close prices (pd.Series, DatetimeIndex)
        qqq_open:   QQQ daily open prices
        vix:        VIX close prices, aligned to qqq_close.index
        vix3m:      VIX3M close prices
        rf:         Risk-free rate (^IRX / 100), aligned

    Returns:
        pd.DataFrame with one row per trading day and all feature columns.
    """
    master = pd.DataFrame(index=qqq_close.index)
    master["qqq_close"] = qqq_close
    master["qqq_open"] = qqq_open
    master["vix"] = vix
    master["vix3m"] = vix3m.fillna(vix * 1.05)    # Fallback if VIX3M unavailable
    master["rf"] = rf.fillna(0.045)

    # ── Trend / SMA Regime ────────────────────────────────────────────────────
    master["sma_50"]  = qqq_close.rolling(50).mean()
    master["sma_100"] = qqq_close.rolling(100).mean()
    master["sma_200"] = qqq_close.rolling(200).mean()

    master["above_sma50"]  = (qqq_close > master["sma_50"]).astype(float)
    master["above_sma100"] = (qqq_close > master["sma_100"]).astype(float)
    master["above_sma200"] = (qqq_close > master["sma_200"]).astype(float)

    master["dist_sma50"]  = (qqq_close - master["sma_50"])  / master["sma_50"]
    master["dist_sma100"] = (qqq_close - master["sma_100"]) / master["sma_100"]
    master["dist_sma200"] = (qqq_close - master["sma_200"]) / master["sma_200"]

    # ── RSIs ─────────────────────────────────────────────────────────────────
    def _rsi(series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    master["rsi_2"]  = _rsi(qqq_close, 2)
    master["rsi_5"]  = _rsi(qqq_close, 5)
    master["rsi_14"] = _rsi(qqq_close, 14)
    master["rsi_30"] = _rsi(qqq_close, 30)

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    sma_20 = qqq_close.rolling(20).mean()
    std_20 = qqq_close.rolling(20).std()
    upper_bb = sma_20 + 2 * std_20
    lower_bb = sma_20 - 2 * std_20
    bb_width = (upper_bb - lower_bb).replace(0, np.nan)
    master["pct_b"] = (qqq_close - lower_bb) / bb_width
    master["bb_width_pct"] = bb_width / sma_20

    # ── Returns / Momentum ────────────────────────────────────────────────────
    master["ret_1d"]  = qqq_close.pct_change(1)
    master["ret_3d"]  = qqq_close.pct_change(3)
    master["ret_5d"]  = qqq_close.pct_change(5)
    master["ret_10d"] = qqq_close.pct_change(10)
    master["ret_21d"] = qqq_close.pct_change(21)
    master["ret_63d"] = qqq_close.pct_change(63)

    # Gap detection (open vs prior close)
    master["gap_pct"]      = (qqq_open - qqq_close.shift(1)) / qqq_close.shift(1)
    master["is_gap_down"]  = (master["gap_pct"] <= -0.005).astype(float)
    master["is_gap_down2"] = (master["gap_pct"] <= -0.020).astype(float)

    # ── Volatility / IV ───────────────────────────────────────────────────────
    log_ret = np.log(qqq_close / qqq_close.shift(1))
    master["hv_10"]  = log_ret.rolling(10).std()  * math.sqrt(252) * 100
    master["hv_20"]  = log_ret.rolling(20).std()  * math.sqrt(252) * 100
    master["hv_60"]  = log_ret.rolling(60).std()  * math.sqrt(252) * 100
    master["hv_120"] = log_ret.rolling(120).std() * math.sqrt(252) * 100

    # Proxy IV rank: percentile of HV20 over trailing 252 days
    hv_min_52w = master["hv_20"].rolling(252).min()
    hv_max_52w = master["hv_20"].rolling(252).max()
    denom = (hv_max_52w - hv_min_52w).replace(0, np.nan)
    master["iv_rank"] = ((master["hv_20"] - hv_min_52w) / denom * 100).clip(0, 100).fillna(50)

    # ── VIX Features ─────────────────────────────────────────────────────────
    master["vix_pct_rank"]   = master["vix"].rolling(252).rank(pct=True)  # VIX percentile
    master["vix_sma_50"]     = master["vix"].rolling(50).mean()
    master["vix_rel_50"]     = master["vix"] / master["vix_sma_50"]       # VIX relative to 50-DMA
    master["vix_term_slope"] = (master["vix3m"] - master["vix"]) / master["vix"]  # Contango(+) vs Backwardation(-)
    master["put_call_proxy"] = 1.0 / (master["vix_term_slope"].clip(-0.5, 0.5) + 1.0)  # Fear proxy

    # VIX 5-day change (acceleration of fear)
    master["vix_5d_change"] = master["vix"].pct_change(5)

    # VVIX proxy: realized vol-of-VIX (no separate VVIX ticker needed)
    vix_log_ret = np.log(vix / vix.shift(1))
    master["vvix_proxy"] = vix_log_ret.rolling(10).std() * math.sqrt(252) * 100

    # ── ATH Drawdown ──────────────────────────────────────────────────────────
    ath = qqq_close.cummax()
    master["ath_drawdown"] = (qqq_close - ath) / ath   # Negative = below ATH
    master["qqq_52w_low"] = qqq_close.rolling(252).min()

    # ── Regime Classification (rule-based, pre-ML) ────────────────────────────
    def _classify_regime(row: pd.Series) -> str:
        if not row["above_sma100"]:
            return "BEAR"
        if row["above_sma200"] and row["vix"] < 25:
            return "BULL_STRONG"
        if row["above_sma100"] and row["vix"] < 35:
            return "BULL_MODERATE"
        return "CHOPPY"

    master = master.dropna(subset=["sma_200"])
    master["rule_regime"] = master.apply(_classify_regime, axis=1)

    # ── HMM Regime Probability (Layer A) ─────────────────────────────────────
    master["hmm_p_bull"] = _load_hmm_regime(master)

    return master


def _load_hmm_regime(master: pd.DataFrame) -> pd.Series:
    """
    Loads the existing TurboCore 2-state HMM and computes bull probability.
    Falls back to rule-based regime signal if HMM unavailable.
    """
    import os, sys
    from pathlib import Path

    hmm_path   = Path(__file__).parent.parent / "turbocore_pro/ml/turbocore_hmm_2state.joblib"
    scaler_path= Path(__file__).parent.parent / "turbocore_pro/ml/turbocore_hmm_2state_scaler.joblib"

    fallback = (master["rule_regime"].isin(["BULL_STRONG", "BULL_MODERATE"])).astype(float) * 0.8 + 0.1

    if not (hmm_path.exists() and scaler_path.exists()):
        logger.warning("TurboCore HMM not found — using rule-based regime fallback.")
        return fallback

    try:
        import joblib
        hmm_data   = joblib.load(hmm_path)
        hmm_model  = hmm_data.get("model")
        hmm_map    = hmm_data.get("mapping", {0: "BULL", 1: "BEAR"})
        scaler     = joblib.load(scaler_path)

        # Build HMM feature matrix (must match turbocore_hmm_2state training)
        log_ret   = np.log(master["qqq_close"] / master["qqq_close"].shift(1))
        hv20      = log_ret.rolling(20).std() * math.sqrt(252)
        qqq_10d   = np.log(master["qqq_close"] / master["qqq_close"].shift(10))
        vts       = master["vix3m"] - master["vix"]

        hmm_feats = pd.DataFrame({
            "qqq_vol_20d":    hv20,
            "vix_close":      master["vix"],
            "qqq_10d_return": qqq_10d,
            "vix_term_slope": vts,
        }, index=master.index).dropna()

        X = scaler.transform(hmm_feats.values)
        probs = hmm_model.predict_proba(X)

        bull_col = [k for k, v in hmm_map.items() if v == "BULL"]
        bull_col = bull_col[0] if bull_col else 0

        p_bull = pd.Series(probs[:, bull_col], index=hmm_feats.index)
        return p_bull.reindex(master.index).ffill().fillna(0.5)

    except Exception as e:
        logger.warning(f"HMM load/predict failed: {e} — using fallback.")
        return fallback


def add_forward_labels(
    master: pd.DataFrame,
    forward_days: int = 30,
    target_gain: float = 0.04,
) -> pd.DataFrame:
    """
    Adds binary label: 1 if QQQ closes >= target_gain% above entry within
    `forward_days` trading days, 0 otherwise.

    Used for Layer B (entry classifier) training.
    NOTE: This function introduces look-ahead — use only on the TRAINING slice.
    """
    closes = master["qqq_close"].values
    n = len(closes)
    labels = np.full(n, np.nan)

    for i in range(n - forward_days):
        entry_price = closes[i]
        target      = entry_price * (1 + target_gain)
        future      = closes[i + 1 : i + 1 + forward_days]
        labels[i]   = 1.0 if np.any(future >= target) else 0.0

    out = master.copy()
    out["label_bounce"] = labels
    return out
