"""
VIX Ensemble Predictor
======================
Combines XGBoost + LSTM to forecast the **direction** of VIX over the
next 1–3 days: VIX_RISING | NEUTRAL | VIX_FALLING.

Both models produce directional probabilities; a Bayesian Model Average
(dynamically weighted by rolling validation accuracy) produces the final
confidence-gated decision.
"""

import logging
import os
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# ── Optional heavy imports ─────────────────────────────────────────────────
try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    logger.warning("xgboost not installed. XGBoost branch will be skipped.")
    xgb = None
    XGB_AVAILABLE = False

try:
    import tensorflow as tf
    from tensorflow import keras
    TF_AVAILABLE = True
except ImportError:
    logger.warning("TensorFlow not installed. LSTM branch will be skipped.")
    tf = None
    keras = None
    TF_AVAILABLE = False

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    joblib = None
    JOBLIB_AVAILABLE = False


# ── Output dataclass ───────────────────────────────────────────────────────
@dataclass
class VIXPrediction:
    direction: str            # "VIX_RISING" | "NEUTRAL" | "VIX_FALLING"
    confidence: float         # 0–1
    xgb_prob: float           # raw XGBoost probability (rising)
    lstm_prob: float          # raw LSTM probability (rising)
    ensemble_weight_xgb: float
    ensemble_weight_lstm: float


# ── Constants ──────────────────────────────────────────────────────────────
LABELS       = ["VIX_FALLING", "NEUTRAL", "VIX_RISING"]
XGB_PATH     = "src/tqqq/ml/models/vix_xgb.ubj"
LSTM_PATH    = "src/tqqq/ml/models/vix_lstm.keras"
WEIGHTS_PATH = "src/tqqq/ml/models/ensemble_weights.npy"
LOOKBACK     = 20    # LSTM sequence length (days)
N_FEATURES   = 30   # XGBoost feature count (see _build_xgb_features)
NEUTRAL_BAND = 0.15  # probabilities within ±15% of 0.33 → NEUTRAL


class VIXEnsemblePredictor:
    """
    Two-model ensemble for VIX directional prediction.

    ┌──────────────────────────────────────────────┐
    │  XGBoost (tabular, 30 features)              │  → P(rising) xgb
    │  LSTM (sequence 20 days, 10 features)         │  → P(rising) lstm
    │  Bayesian Model Average (dynamic weights)    │  → final direction
    └──────────────────────────────────────────────┘
    """

    def __init__(self):
        self.xgb_model  = None
        self.lstm_model = None
        self._weights   = np.array([0.55, 0.45])   # [xgb, lstm] initial

        self._try_load_models()

    # ─────────────────────── Public API ──────────────────────────────────

    def predict(self, df: pd.DataFrame) -> VIXPrediction:
        """
        Main prediction entry point.
        ``df`` must contain the raw columns needed by feature builders.
        """
        xgb_p  = self._predict_xgb(df)
        lstm_p = self._predict_lstm(df)

        # Weighted average P(rising)
        w_xgb, w_lstm = self._weights[0], self._weights[1]
        ensemble_p    = w_xgb * xgb_p + w_lstm * lstm_p

        direction, confidence = self._classify(ensemble_p)

        return VIXPrediction(
            direction=direction,
            confidence=confidence,
            xgb_prob=xgb_p,
            lstm_prob=lstm_p,
            ensemble_weight_xgb=float(w_xgb),
            ensemble_weight_lstm=float(w_lstm),
        )

    def fit(self, df: pd.DataFrame, future_days: int = 3) -> None:
        """Train both models on a full historical DataFrame."""
        self._train_xgb(df, future_days)
        self._train_lstm(df, future_days)
        self._calibrate_weights(df, future_days)

    def update_weights(self, xgb_accuracy: float, lstm_accuracy: float) -> None:
        """Bayesian weight update based on out-of-sample rolling accuracy."""
        total = xgb_accuracy + lstm_accuracy
        if total > 0:
            self._weights = np.array([xgb_accuracy / total, lstm_accuracy / total])
            np.save(WEIGHTS_PATH, self._weights)
            logger.info(f"Ensemble weights updated → XGB:{self._weights[0]:.2f} LSTM:{self._weights[1]:.2f}")

    # ─────────────────── Feature Engineering ─────────────────────────────

    @staticmethod
    def build_xgb_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        30 Engineered features for XGBoost.
        Required raw cols: vix, tqqq_close, spy_close, qqq_close (optional).
        """
        d = df.copy()
        v  = d["vix"]

        # VIX levels and momentum
        d["vix_lag1"]      = v.shift(1)
        d["vix_lag2"]      = v.shift(2)
        d["vix_lag3"]      = v.shift(3)
        d["vix_ma5"]       = v.rolling(5).mean()
        d["vix_ma10"]      = v.rolling(10).mean()
        d["vix_ma20"]      = v.rolling(20).mean()
        d["vix_roc1"]      = v.pct_change(1)
        d["vix_roc5"]      = v.pct_change(5)
        d["vix_roc10"]     = v.pct_change(10)
        d["vix_std5"]      = v.rolling(5).std()
        d["vix_std20"]     = v.rolling(20).std()

        # VIX level buckets (ordinal)
        d["vix_regime"]    = pd.cut(
            v, bins=[0, 15, 20, 25, 35, 9999],
            labels=[0, 1, 2, 3, 4]
        ).astype(float)

        # Underlying momentum
        t  = d["tqqq_close"]
        d["tqqq_ret1"]     = t.pct_change(1)
        d["tqqq_ret5"]     = t.pct_change(5)
        d["tqqq_hv5"]      = t.pct_change().rolling(5).std() * np.sqrt(252)
        d["tqqq_hv20"]     = t.pct_change().rolling(20).std() * np.sqrt(252)

        # RSI-like
        delta = t.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        d["tqqq_rsi14"]   = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

        # SPY / QQQ features (if available)
        if "spy_close" in d.columns:
            s = d["spy_close"]
            d["spy_ret1"]  = s.pct_change(1)
            d["spy_ret5"]  = s.pct_change(5)
            d["spy_hv10"]  = s.pct_change().rolling(10).std() * np.sqrt(252)
        else:
            d["spy_ret1"] = d["spy_ret5"] = d["spy_hv10"] = 0.0

        if "qqq_close" in d.columns:
            q = d["qqq_close"]
            d["qqq_ret1"]  = q.pct_change(1)
            d["qqq_ret5"]  = q.pct_change(5)
        else:
            d["qqq_ret1"] = d["qqq_ret5"] = 0.0

        # Calendar features (day-of-week, month)
        if hasattr(d.index, "dayofweek"):
            d["dow"]   = d.index.dayofweek
            d["month"] = d.index.month
        else:
            d["dow"] = d["month"] = 0

        # VIX z-score
        d["vix_zscore"] = (v - v.rolling(60).mean()) / v.rolling(60).std().replace(0, np.nan)

        feature_cols = [
            "vix_lag1","vix_lag2","vix_lag3","vix_ma5","vix_ma10","vix_ma20",
            "vix_roc1","vix_roc5","vix_roc10","vix_std5","vix_std20","vix_regime",
            "tqqq_ret1","tqqq_ret5","tqqq_hv5","tqqq_hv20","tqqq_rsi14",
            "spy_ret1","spy_ret5","spy_hv10","qqq_ret1","qqq_ret5",
            "dow","month","vix_zscore",
        ]
        return d[feature_cols].dropna()

    @staticmethod
    def build_lstm_features(df: pd.DataFrame) -> pd.DataFrame:
        """10 features for the LSTM sequence model."""
        d = df.copy()
        v = d["vix"]
        t = d["tqqq_close"]
        d["vix_norm"]    = (v - v.rolling(60).mean()) / v.rolling(60).std().replace(0, np.nan)
        d["vix_roc1"]    = v.pct_change(1)
        d["vix_roc5"]    = v.pct_change(5)
        d["vix_ma_ratio"]= v / v.rolling(20).mean()
        d["tqqq_ret1"]   = t.pct_change(1)
        d["tqqq_ret5"]   = t.pct_change(5)
        d["tqqq_hv10"]   = t.pct_change().rolling(10).std() * np.sqrt(252)
        if "spy_close" in d.columns:
            d["spy_ret1"] = d["spy_close"].pct_change(1)
        else:
            d["spy_ret1"] = 0.0
        if "vix3m" in d.columns:
            d["term_slope"] = v / d["vix3m"].replace(0, np.nan)
        else:
            d["term_slope"] = 1.0
        d["vix_level"]   = v / 20.0   # normalise around "typical" VIX

        cols = [
            "vix_norm","vix_roc1","vix_roc5","vix_ma_ratio",
            "tqqq_ret1","tqqq_ret5","tqqq_hv10",
            "spy_ret1","term_slope","vix_level"
        ]
        return d[cols].dropna()

    # ─────────────────────── Training ────────────────────────────────────

    def _train_xgb(self, df: pd.DataFrame, future_days: int) -> None:
        if not XGB_AVAILABLE:
            return
        feats = self.build_xgb_features(df)
        label = self._make_labels(df["vix"], feats.index, future_days)
        X, y  = feats.values, label.values
        self.xgb_model = xgb.XGBClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, use_label_encoder=False,
            eval_metric="mlogloss", random_state=42, n_jobs=-1
        )
        self.xgb_model.fit(X, y)
        os.makedirs(os.path.dirname(XGB_PATH), exist_ok=True)
        self.xgb_model.save_model(XGB_PATH)
        logger.info("XGBoost VIX predictor trained and saved.")

    def _train_lstm(self, df: pd.DataFrame, future_days: int) -> None:
        if not TF_AVAILABLE:
            return
        feats = self.build_lstm_features(df)
        label = self._make_labels(df["vix"], feats.index, future_days)
        X_seq, y_seq = self._build_sequences(feats.values, label.values)

        n_feat   = X_seq.shape[2]
        model    = keras.Sequential([
            keras.layers.LSTM(50, return_sequences=True, input_shape=(LOOKBACK, n_feat)),
            keras.layers.Dropout(0.2),
            keras.layers.LSTM(50),
            keras.layers.Dropout(0.2),
            keras.layers.Dense(3, activation="softmax"),
        ])
        model.compile(optimizer="adam", loss="sparse_categorical_crossentropy",
                      metrics=["accuracy"])
        model.fit(X_seq, y_seq, epochs=30, batch_size=32,
                  validation_split=0.1, verbose=0)
        os.makedirs(os.path.dirname(LSTM_PATH), exist_ok=True)
        model.save(LSTM_PATH)
        self.lstm_model = model
        logger.info("LSTM VIX predictor trained and saved.")

    def _calibrate_weights(self, df: pd.DataFrame, future_days: int) -> None:
        """Hold-out last 10% of data to calibrate ensemble weights."""
        n   = len(df)
        val = df.iloc[int(0.9 * n):]
        xgb_acc  = self._eval_xgb(val, future_days)
        lstm_acc = self._eval_lstm(val, future_days)
        self.update_weights(xgb_acc, lstm_acc)

    # ─────────────────────── Inference ───────────────────────────────────

    def _predict_xgb(self, df: pd.DataFrame) -> float:
        """Returns P(rising) from XGBoost, fallback 0.33 if unavailable."""
        if self.xgb_model is None or not XGB_AVAILABLE:
            return 0.33
        feats = self.build_xgb_features(df)
        if feats.empty:
            return 0.33
        proba = self.xgb_model.predict_proba(feats.values[-1:])
        # Class order: [0=FALLING, 1=NEUTRAL, 2=RISING]
        return float(proba[0][2])

    def _predict_lstm(self, df: pd.DataFrame) -> float:
        """Returns P(rising) from LSTM, fallback 0.33 if unavailable."""
        if self.lstm_model is None or not TF_AVAILABLE:
            return 0.33
        feats = self.build_lstm_features(df)
        if len(feats) < LOOKBACK:
            return 0.33
        seq   = feats.values[-LOOKBACK:][np.newaxis, ...]   # (1, 20, n_feat)
        proba = self.lstm_model.predict(seq, verbose=0)
        return float(proba[0][2])

    # ─────────────────────── Helpers ─────────────────────────────────────

    @staticmethod
    def _make_labels(vix: pd.Series, index, future_days: int) -> pd.Series:
        """Create ternary direction label: 0=FALLING, 1=NEUTRAL, 2=RISING."""
        future_vix = vix.shift(-future_days)
        pct_change = (future_vix - vix) / vix
        label      = pd.Series(1, index=vix.index)   # default NEUTRAL
        label[pct_change > 0.05]  = 2    # >5% → RISING
        label[pct_change < -0.05] = 0    # <−5% → FALLING
        return label.loc[index]

    @staticmethod
    def _build_sequences(X: np.ndarray, y: np.ndarray):
        Xs, ys = [], []
        for i in range(LOOKBACK, len(X)):
            Xs.append(X[i - LOOKBACK:i])
            ys.append(y[i])
        return np.array(Xs), np.array(ys)

    @staticmethod
    def _classify(p_rising: float) -> Tuple[str, float]:
        """Convert P(rising) scalar into a direction label + confidence."""
        p_falling = 1.0 - p_rising
        if p_rising > 0.5 + NEUTRAL_BAND:
            return "VIX_RISING", p_rising
        if p_falling > 0.5 + NEUTRAL_BAND:
            return "VIX_FALLING", p_falling
        return "NEUTRAL", max(p_rising, p_falling)

    def _eval_xgb(self, val_df: pd.DataFrame, future_days: int) -> float:
        if self.xgb_model is None or not XGB_AVAILABLE:
            return 0.5
        feats = self.build_xgb_features(val_df)
        label = self._make_labels(val_df["vix"], feats.index, future_days)
        if feats.empty:
            return 0.5
        preds = self.xgb_model.predict(feats.values)
        return float((preds == label.values).mean())

    def _eval_lstm(self, val_df: pd.DataFrame, future_days: int) -> float:
        if self.lstm_model is None or not TF_AVAILABLE:
            return 0.5
        feats = self.build_lstm_features(val_df)
        label = self._make_labels(val_df["vix"], feats.index, future_days)
        if len(feats) < LOOKBACK:
            return 0.5
        X_seq, y_seq = self._build_sequences(feats.values, label.values)
        if len(X_seq) == 0:
            return 0.5
        preds = self.lstm_model.predict(X_seq, verbose=0).argmax(axis=1)
        return float((preds == y_seq).mean())

    def _try_load_models(self) -> None:
        if XGB_AVAILABLE and os.path.exists(XGB_PATH):
            try:
                self.xgb_model = xgb.XGBClassifier()
                self.xgb_model.load_model(XGB_PATH)
                logger.info(f"XGBoost model loaded ← {XGB_PATH}")
            except Exception as exc:
                logger.warning(f"Could not load XGBoost model: {exc}")

        if TF_AVAILABLE and os.path.exists(LSTM_PATH):
            try:
                self.lstm_model = keras.models.load_model(LSTM_PATH)
                logger.info(f"LSTM model loaded ← {LSTM_PATH}")
            except Exception as exc:
                logger.warning(f"Could not load LSTM model: {exc}")

        if os.path.exists(WEIGHTS_PATH):
            try:
                self._weights = np.load(WEIGHTS_PATH)
            except Exception:
                pass
