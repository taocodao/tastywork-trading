"""
Oscillation Predictor
=====================
XGBoost classifier that predicts whether TQQQ will be UP, DOWN, or FLAT
over the next 3 days, based on 25+ TA features.
Provides directional probabilities which feed into the ActiveDiagonalManager.
"""

from xgboost import XGBClassifier
import numpy as np
import pandas as pd
from typing import Dict, Any
import logging

from diagonal_strategy.config import (
    OSC_FLAT_THRESHOLD, TA_ML_CONFIDENCE_MIN
)

logger = logging.getLogger(__name__)

class OscillationPredictor:
    def __init__(self, model_path: str = None):
        self.xgb_model = None
        self.model_path = model_path
        self.flat_threshold = OSC_FLAT_THRESHOLD
        self.min_confidence = TA_ML_CONFIDENCE_MIN
        self.directions = ['DOWN', 'FLAT', 'UP']
        self._try_load()

    def _try_load(self):
        if self.model_path:
            try:
                self.xgb_model = XGBClassifier()
                self.xgb_model.load_model(self.model_path)
                logger.info(f"Loaded XGBoost model from {self.model_path}")
            except Exception as e:
                logger.warning(f"Failed to load XGBoost model from {self.model_path}: {e}")
                self.xgb_model = None

    def predict(self, ta_features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Returns a dictionary with directional probabilities and the predicted label.
        If the ML model is not loaded, gracefully falls back to a rule-based inference.
        """
        if not ta_features:
            return self._fallback_prediction({})

        if self.xgb_model is None:
            return self._fallback_prediction(ta_features)

        try:
            # Build feature array in the exact order the model expects
            # For robustness, we convert the dict to a DataFrame with 1 row
            df = pd.DataFrame([ta_features])
            
            # Predict probabilities
            probs = self.xgb_model.predict_proba(df)[0]
            
            down_prob = float(probs[0])
            flat_prob = float(probs[1])
            up_prob   = float(probs[2])
            
            direction_idx = int(np.argmax(probs))
            confidence = float(probs[direction_idx])
            
            return {
                'direction': self.directions[direction_idx],
                'confidence': confidence,
                'up_probability': up_prob,
                'down_probability': down_prob,
                'flat_probability': flat_prob,
                'expected_magnitude': self._estimate_magnitude(ta_features, probs)
            }
        except Exception as e:
            logger.error(f"Oscillation Prediction failed: {e}. Using fallback.")
            return self._fallback_prediction(ta_features)

    def predict_dip_probability(self, ta_features: Dict[str, Any]) -> float:
        """Helper for TASignalEngine: returns the up probability as a proxy for bounce strength."""
        pred = self.predict(ta_features)
        # Higher probability of UP => Higher confidence we are deep in a dip that will bounce
        return pred['up_probability']
        
    def predict_bounce_probability(self, ta_features: Dict[str, Any]) -> float:
        """Helper for TASignalEngine: returns the down probability as a proxy for reversal from overbought."""
        pred = self.predict(ta_features)
        # Higher probability of DOWN => Higher confidence we bounced and will drop
        return pred['down_probability']

    def _estimate_magnitude(self, features: Dict[str, Any], probs: np.ndarray) -> float:
        # Heuristic if regression not available
        base_move = features.get('atr_pct', 0.02)
        if self.directions[np.argmax(probs)] == 'FLAT':
            return 0.0
        return float(base_move * probs[np.argmax(probs)] * 1.5)

    def _fallback_prediction(self, f: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based fallback if ML model is missing."""
        up_score = 0.34
        down_score = 0.32
        # Default to FLAT (1.0 - 0.34 - 0.32 = 0.34) when no strong signal
        # so fallback doesn't continually block entries with 'DOWN'
        
        # RSI
        if f.get('rsi_14', 50) < 30: up_score += 0.15
        elif f.get('rsi_14', 50) > 70: down_score += 0.15
        
        # MACD
        if f.get('macd_cross', 0) == 1: up_score += 0.10
        elif f.get('macd_cross', 0) == -1: down_score += 0.10
        
        # Mean reversion
        dist = f.get('dist_from_20ma', 0)
        if dist < -0.05: up_score += 0.10
        elif dist > 0.05: down_score += 0.10
        
        total = up_score + down_score
        if total > 1.0:
            up_score /= total
            down_score /= total
            
        flat_score = max(0.0, 1.0 - up_score - down_score)
        probs = [down_score, flat_score, up_score] # 0: DOWN, 1: FLAT, 2: UP
        idx = int(np.argmax(probs))
        
        return {
            'direction': self.directions[idx],
            'confidence': float(probs[idx]),
            'up_probability': float(up_score),
            'down_probability': float(down_score),
            'flat_probability': float(flat_score),
            'expected_magnitude': 0.02
        }
