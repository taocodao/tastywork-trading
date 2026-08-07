"""
Signal Runner — fetches live data, computes features, loads frozen models,
and produces target allocation using the v3.3 strategy config.

This is the live inference counterpart to the walk-forward backtest's run_fold().
Uses the same feature engineering pipeline (generate_technical_features_v2) and
the same model artifact format (dict with 'model'/'primary' keys).
"""
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

log = logging.getLogger("turbocore.live.signal")

PKG_DIR = Path(__file__).resolve().parent          # src/turbocore_pro/live
REPO_ROOT = Path(__file__).resolve().parents[3]      # repo root
sys.path.insert(0, str(REPO_ROOT))                   # enables `src.turbocore_pro` package imports

# Import the actual feature engineering pipeline
from src.turbocore_pro.ml.feature_engineering_v2 import generate_technical_features_v2  # noqa: E402


class SignalRunner:
    """Computes the target allocation from live market data."""

    def __init__(self, config: dict, repo_root: Path):
        self.config = config
        self.repo_root = repo_root
        # Models ship inside the package: src/turbocore_pro/models/
        self.models_dir = Path(__file__).resolve().parents[1] / "models"
        self._hmm = None        # full dict: {model, mapping, n_states, bars_per_day}
        self._hmm_scaler = None
        self._xgb = None        # full dict: {meta, primary, features}
        self._msgarch = None
        self._prev_tier = "none"  # hysteresis state

    def load_models(self):
        """Load frozen fold-10 model artifacts."""
        strat = self.config["strategy"]
        self._hmm = joblib.load(self.models_dir / strat["hmm_model"])
        self._hmm_scaler = joblib.load(self.models_dir / strat["hmm_scaler"])
        self._xgb = joblib.load(self.models_dir / strat["xgb_model"])
        log.info(f"Loaded HMM: {strat['hmm_model']} (keys: {list(self._hmm.keys())})")
        log.info(f"Loaded XGBoost: {strat['xgb_model']} (keys: {list(self._xgb.keys())})")

        msgarch_path = self.models_dir / strat.get("msgarch_model", "")
        if msgarch_path.exists():
            try:
                self._msgarch = joblib.load(msgarch_path)
                log.info(f"Loaded MS-GARCH: {strat['msgarch_model']}")
            except Exception as e:
                log.warning(f"MS-GARCH load failed: {e}")

    def build_features(self, ibkr_bars: dict[str, pd.DataFrame],
                       vix_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Build the master feature dataframe from live IBKR bars + VIX data.
        Uses generate_technical_features_v2() for all technical indicators.
        """
        qqq = ibkr_bars.get("QQQ")
        if qqq is None or qqq.empty:
            log.error("No QQQ bars received")
            return pd.DataFrame()

        # Build master df with column names matching the pipeline expectations
        master = pd.DataFrame(index=qqq.index)
        master["qqq_close"] = qqq["close"]
        master["qqq_open"] = qqq["open"]
        master["qqq_high"] = qqq["high"]
        master["qqq_low"] = qqq["low"]
        master["qqq_volume"] = qqq["volume"]

        # Join other ETFs
        for sym, prefix in [("TQQQ", "tqqq"), ("QLD", "qld"), ("SGOV", "sgov"), ("HYG", "hyg")]:
            if sym in ibkr_bars and not ibkr_bars[sym].empty:
                df = ibkr_bars[sym]
                master[f"{prefix}_close"] = df["close"].reindex(master.index, method="ffill")
                if "volume" in df.columns:
                    master[f"{prefix}_volume"] = df["volume"].reindex(master.index, method="ffill")

        # VIX data — align to QQQ bar grid
        # vix_data values may be DataFrames (from IBKR/CBOE) or Series (after align_vix_to_hourly)
        if "VIX" in vix_data:
            vix_obj = vix_data["VIX"]
            if isinstance(vix_obj, pd.DataFrame):
                vix_series = vix_obj["close"] if "close" in vix_obj.columns else vix_obj.iloc[:, 0]
            else:
                vix_series = vix_obj  # already a Series
            master["vix_close"] = vix_series.reindex(master.index, method="ffill")
        else:
            log.warning("VIX data unavailable — using synthetic VIX=20.0")
            master["vix_close"] = 20.0

        # Compute basic derived features needed by HMM
        bpd = 6.5  # bars per day (RTH hourly)
        master["qqq_log_return"] = np.log(master["qqq_close"] / master["qqq_close"].shift(1))
        master["qqq_vol_20d"] = (master["qqq_log_return"].rolling(int(20 * bpd))
                                 .std() * np.sqrt(252 * bpd))
        master["qqq_10d_return"] = master["qqq_log_return"].rolling(int(10 * bpd)).sum()
        master["qqq_close_sma200"] = master["qqq_close"].rolling(int(200 * bpd), min_periods=100).mean()
        master["pct_below_sma200"] = (master["qqq_close"] - master["qqq_close_sma200"]) / master["qqq_close_sma200"]

        # VIX ratio (term structure proxy)
        if "vix_close" in master.columns:
            master["vix_ratio"] = 1.0  # neutral default; overwritten if VIX9D/VIX3M available
        if "VIX9D" in vix_data and "VIX3M" in vix_data:
            vix9d = vix_data["VIX9D"]["close"].reindex(master.index, method="ffill")
            vix3m = vix_data["VIX3M"]["close"].reindex(master.index, method="ffill")
            master["vix_ratio"] = vix9d / vix3m

        # HYG 1-day return
        if "hyg_close" in master.columns:
            master["hyg_1d_ret"] = master["hyg_close"].pct_change(int(1 * bpd))

        # Now generate all 26 technical features using the pipeline
        log.info("Generating technical features via generate_technical_features_v2()...")
        master = generate_technical_features_v2(master, bars_per_day=bpd)

        log.info(f"Feature matrix: {master.shape[0]} bars, {master.shape[1]} columns")
        return master

    def compute_signal(self, master: pd.DataFrame) -> dict:
        """
        Run the full signal pipeline on the latest bar:
        HMM regime → XGBoost signal/confidence → allocation target.
        """
        if master.empty or len(master) < 50:
            log.error("Insufficient data for signal computation")
            return {"regime": "BEAR", "signal": 0, "confidence": 0.0,
                    "target_allocation": {"SGOV": 1.0}}

        latest = master.iloc[-1]
        log.info(f"Latest bar: {master.index[-1]}, QQQ close={latest.get('qqq_close', 0):.2f}")

        # ─── HMM Regime Detection ───────────────────────────────────────────
        hmm_model = self._hmm["model"]
        hmm_mapping = self._hmm.get("mapping", {0: "BEAR", 1: "BULL"})
        hmm_bpd = self._hmm.get("bars_per_day", 6.5)

        # HMM uses 4 features: qqq_vol_20d, qqq_10d_return, vix_close, vix_ratio
        hmm_features = ["qqq_vol_20d", "qqq_10d_return", "vix_close", "vix_ratio"]
        feature_window = master[hmm_features].tail(int(130 * hmm_bpd / 6.5)).dropna()

        regime = "BEAR"  # default
        if len(feature_window) >= 50 and self._hmm_scaler is not None:
            try:
                scaled = self._hmm_scaler.transform(feature_window.values)
                raw_states = hmm_model.predict(scaled)
                last_state = int(raw_states[-1])
                regime = hmm_mapping.get(last_state, "BEAR")
                log.info(f"HMM regime: {regime} (raw state={last_state}, mapping={hmm_mapping})")
            except Exception as e:
                log.error(f"HMM prediction failed: {e}")
        else:
            log.warning(f"Insufficient HMM features ({len(feature_window)} rows, need 50+)")

        # ─── XGBoost Signal & Confidence ────────────────────────────────
        # Two-stage model: primary (9 features) → meta (26 features incl. primary_prob)
        # The 'features' key in the model dict is META_FEATURES, not PRIMARY_FEATURES
        PRIMARY_FEATURES = [
            'tqqq_rsi_14', 'tqqq_macd_hist', 'tqqq_bb_width', 'qqq_vol_20d',
            'vix_close', 'vix_rel_50', 'vol_ratio', 'momentum_divergence',
            'fib_retracement',
        ]
        META_FEATURES = self._xgb.get("features", [])

        signal = 1   # default: take the trade
        confidence = 0.5  # default neutral

        primary_model = self._xgb.get("primary")
        meta_model = self._xgb.get("meta")

        if primary_model is not None:
            try:
                # Stage 1: Primary model (9 features)
                primary_vector = []
                primary_missing = []
                for feat in PRIMARY_FEATURES:
                    val = latest.get(feat, 0)
                    if pd.isna(val):
                        val = 0.0
                        primary_missing.append(feat)
                    primary_vector.append(float(val))

                if primary_missing:
                    log.warning(f"Missing {len(primary_missing)}/{len(PRIMARY_FEATURES)} primary features: {primary_missing}")

                primary_proba = primary_model.predict_proba(
                    np.array(primary_vector).reshape(1, -1))[0]
                primary_prob = float(primary_proba[1])
                log.info(f"Primary XGBoost: p_bull={primary_prob:.3f}")

                # Stage 2: Meta model (26 features, includes primary_prob)
                if meta_model is not None and META_FEATURES:
                    meta_vector = []
                    meta_missing = []
                    for feat in META_FEATURES:
                        if feat == 'primary_prob':
                            meta_vector.append(primary_prob)
                        elif feat in master.columns:
                            val = latest.get(feat, 0)
                            if pd.isna(val):
                                val = 0.0
                                meta_missing.append(feat)
                            meta_vector.append(float(val))
                        else:
                            meta_vector.append(0.0)
                            meta_missing.append(feat)

                    if meta_missing:
                        log.warning(f"Missing {len(meta_missing)}/{len(META_FEATURES)} meta features: {meta_missing[:5]}...")

                    meta_proba = meta_model.predict_proba(
                        np.array(meta_vector).reshape(1, -1))[0]
                    confidence = float(meta_proba[1])
                    signal = int(confidence >= 0.30)  # recall-tuned threshold
                    log.info(f"Meta XGBoost: signal={signal}, confidence={confidence:.3f}")
                else:
                    # No meta model — use primary probability directly
                    confidence = primary_prob
                    signal = int(primary_prob >= 0.30)
                    log.info(f"Primary-only: signal={signal}, confidence={confidence:.3f}")
            except Exception as e:
                log.error(f"XGBoost prediction failed: {e}")

        # ─── Target Allocation ───────────────────────────────────────────────
        target = self._compute_allocation(regime, signal, confidence, latest)

        return {
            "regime": regime,
            "signal": signal,
            "confidence": confidence,
            "target_allocation": target,
            "timestamp": str(master.index[-1]),
            "qqq_close": float(latest.get("qqq_close", 0)),
        }

    def _compute_allocation(self, regime: str, signal: int,
                            confidence: float, latest) -> dict:
        """
        Compute target allocation using v3.3 config.
        Returns {symbol: weight} dict.
        """
        strat = self.config["strategy"]
        floor = strat["bull_sgov_floor"]

        if regime == "BULL":
            band = strat.get("hysteresis_band", 0.0)
            hi_thresh = 0.70
            lo_thresh = 0.40

            if band > 0:
                if self._prev_tier == "high":
                    hi_thresh -= band
                    lo_thresh -= band
                elif self._prev_tier == "med":
                    hi_thresh += band
                    lo_thresh -= band
                elif self._prev_tier == "low":
                    hi_thresh += band
                    lo_thresh += band

            if signal == 0:
                tier = "med"
            elif confidence >= hi_thresh:
                tier = "high"
            elif confidence >= lo_thresh:
                tier = "med"
            else:
                tier = "low"

            self._prev_tier = tier

            if tier == "high":
                return {"QLD": 0.50, "TQQQ": 0.35, "QQQ": 0.0, "SGOV": floor}
            elif tier == "med":
                return {"QQQ": 1.0 - floor, "SGOV": floor}
            else:
                return {"QQQ": 0.50, "SGOV": 0.50}
        else:
            # BEAR regime
            if latest.get("pct_below_sma200", 0) < -0.05:
                return {"SGOV": 1.0}  # all cash
            else:
                return {"QQQ": 0.30, "SGOV": 0.70}  # reduced equity
