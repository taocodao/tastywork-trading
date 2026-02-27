"""
ML-Enhanced Mean Reversion Signal
=================================
Predicts P(TQQQ bounce > 3% in next 7 days) given an RSI-2 < 10 event.
"""

import logging
import os
from typing import Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    xgb = None
    XGB_AVAILABLE = False


class MeanReversionSignal:
    def __init__(self, model_path: str = "models/tqqq_mean_reversion_xgb.json"):
        self.model_path = model_path
        self._model = None
        self._load_model()

    def _load_model(self):
        if not XGB_AVAILABLE:
            logger.warning("XGBoost not installed. Mean Reversion Signal will use fallback.")
            return
            
        if os.path.exists(self.model_path):
            try:
                self._model = xgb.XGBClassifier()
                self._model.load_model(self.model_path)
                logger.info(f"Loaded Mean Reversion ML model from {self.model_path}")
            except Exception as e:
                logger.error(f"Failed to load Mean Reversion ML model: {e}")
                self._model = None
        else:
            logger.warning(f"Mean Reversion ML model not found at {self.model_path}. Using fallback probability.")

    def build_features(self, df: pd.DataFrame) -> np.ndarray:
        """Extract the exact 15 features needed by the model."""
        if df.empty:
            return np.zeros((1, 15))
            
        latest = df.iloc[-1]
        
        # 15 features per implementation plan
        features = [
            latest.get("rsi_2", 50.0),
            latest.get("rsi2_consec", 0.0),
            latest.get("bb_pct_b", 0.5),
            latest.get("vix_sma_ratio", 1.0),
            latest.get("term_slope", 1.0), # VIX term slope placeholder
            latest.get("vol_ratio", 1.0),
            latest.get("mfi_14", 50.0),
            latest.get("atr_pct", 0.05),
            latest.get("hurst_100", 0.5),
            latest.get("ou_half_life", 14.0),
            latest.get("adx_14", 25.0),
            0.0,  # tqqq_qqq_tracking_error placeholder
            latest.get("days_since_oversold", 20.0),
            latest.get("drawdown_from_high", 0.0),
            latest.get("sma20_slope", 0.0)
        ]
        
        # Replace infs and NaNs securely
        clean_features = []
        for f in features:
            if pd.isna(f) or np.isinf(f):
                clean_features.append(0.0)
            else:
                clean_features.append(float(f))
                
        return np.array(clean_features).reshape(1, -1)

    def predict_bounce_probability(self, df: pd.DataFrame) -> float:
        """Returns P(bounce > 3% in 7 days). Fallback to heuristics if model missing."""
        if self._model is None or df.empty:
            # Fallback heuristic using crash guard principles
            if df.empty: return 0.5
            latest = df.iloc[-1]
            rsi = latest.get("rsi_2", 50)
            if rsi < 5: return 0.65
            if rsi < 10: return 0.55
            return 0.30

        X = self.build_features(df)
        try:
            prob = self._model.predict_proba(X)[0][1] # Probability of class 1
            return float(prob)
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            return 0.5
