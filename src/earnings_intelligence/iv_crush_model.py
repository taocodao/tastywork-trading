"""
ML IV Crush Predictor Model.
Random Forest classifier for predicting IV crush magnitude after earnings.
"""

import os
import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Check for scikit-learn availability
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score, train_test_split
    from sklearn.metrics import classification_report, f1_score, confusion_matrix
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available. Install with: pip install scikit-learn")

from .features import FeatureVector, IVCrushClass, FeatureEngineer


class IVCrushPredictor:
    """
    Machine Learning model for predicting IV crush after earnings.
    
    Uses Random Forest classifier with 4 classes:
    - NORMAL: Expected 10-20% IV decline
    - SEVERE: Unexpected >30% IV decline (dangerous for calendar spreads)
    - EXPANSION: IV increases (rare, good for calendars)
    - NO_CRUSH: <5% IV change
    """

    MODEL_VERSION = "v1.0"
    MODEL_DIR = Path(__file__).parent / "models"
    MODEL_FILE = "iv_crush_rf_v1.pkl"
    SCALER_FILE = "iv_crush_scaler_v1.pkl"

    # Class labels
    CLASSES = [
        IVCrushClass.NORMAL,
        IVCrushClass.SEVERE,
        IVCrushClass.EXPANSION,
        IVCrushClass.NO_CRUSH
    ]

    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize the IV Crush Predictor.
        
        Args:
            model_path: Optional path to pre-trained model file
        """
        self.model = None
        self.scaler = None
        self.feature_engineer = FeatureEngineer()
        self.is_trained = False
        
        # Try to load existing model
        if model_path:
            self.load_model(model_path)
        else:
            self._try_load_default_model()

    def _try_load_default_model(self):
        """Try to load the default model if it exists."""
        model_path = self.MODEL_DIR / self.MODEL_FILE
        if model_path.exists():
            try:
                self.load_model(str(model_path))
            except Exception as e:
                logger.warning(f"Failed to load default model: {e}")

    def predict(
        self,
        earnings_context: Dict[str, Any],
        technical_data: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Predict IV crush for upcoming earnings.
        
        Args:
            earnings_context: Data from Perplexity API
            technical_data: Technical indicators (optional)
            market_data: Market context like VIX (optional)
        
        Returns:
            Dictionary with prediction results:
            - predicted_class: NORMAL, SEVERE, EXPANSION, NO_CRUSH
            - confidence: 0-100 score
            - class_probabilities: Dict of class -> probability
            - predicted_crush_pct: Estimated crush percentage
        """
        # Extract features
        features = self.feature_engineer.extract_features(
            earnings_context,
            technical_data,
            market_data
        )
        
        # If model not trained, use heuristics
        if not self.is_trained or self.model is None:
            return self._heuristic_prediction(features, earnings_context)
        
        try:
            # Prepare feature array
            X = np.array([features.to_array()])
            
            # Scale features
            if self.scaler:
                X = self.scaler.transform(X)
            
            # Get prediction and probabilities
            predicted_class = self.model.predict(X)[0]
            probabilities = self.model.predict_proba(X)[0]
            
            # Map probabilities to actual model classes (not hardcoded CLASSES)
            model_classes = self.model.classes_
            class_probs = {
                model_classes[i]: float(probabilities[i])
                for i in range(len(model_classes))
            }
            
            # Confidence is the probability of predicted class
            confidence = max(probabilities) * 100
            
            # Estimate crush percentage based on class
            predicted_crush_pct = self._estimate_crush_pct(predicted_class, class_probs)
            
            return {
                "predicted_class": predicted_class,
                "confidence": round(confidence, 1),
                "class_probabilities": class_probs,
                "predicted_crush_pct": round(predicted_crush_pct, 1),
                "features_used": features.to_dict(),
                "model_version": self.MODEL_VERSION
            }

            
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return self._heuristic_prediction(features, earnings_context)

    def _heuristic_prediction(
        self,
        features: FeatureVector,
        earnings_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fallback heuristic prediction when model not available.
        Uses simple rules based on key features.
        """
        crush_prob = earnings_context.get("crush_probability", 0.5)
        days = features.days_to_earnings
        iv_rank = features.iv_rank_bucket
        
        # Simple heuristic rules
        if days <= 3:
            # Very close to earnings = high risk
            if crush_prob >= 0.7 or iv_rank >= 2:
                predicted_class = IVCrushClass.SEVERE
                confidence = 70
            else:
                predicted_class = IVCrushClass.NORMAL
                confidence = 60
        elif days <= 7:
            if crush_prob >= 0.6:
                predicted_class = IVCrushClass.NORMAL
                confidence = 65
            else:
                predicted_class = IVCrushClass.NO_CRUSH
                confidence = 55
        else:
            predicted_class = IVCrushClass.NO_CRUSH
            confidence = 50
        
        # Estimate crush percentage
        crush_pct = -15.0 if predicted_class == IVCrushClass.NORMAL else \
                   -35.0 if predicted_class == IVCrushClass.SEVERE else \
                   5.0 if predicted_class == IVCrushClass.EXPANSION else -2.0
        
        return {
            "predicted_class": predicted_class,
            "confidence": confidence,
            "class_probabilities": {predicted_class: confidence / 100},
            "predicted_crush_pct": crush_pct,
            "features_used": features.to_dict(),
            "model_version": "heuristic",
            "note": "Using heuristic fallback - model not trained"
        }

    def _estimate_crush_pct(self, predicted_class: str, probs: Dict[str, float]) -> float:
        """Estimate crush percentage based on prediction."""
        # Base estimates for each class
        class_estimates = {
            IVCrushClass.NORMAL: -15.0,
            IVCrushClass.SEVERE: -35.0,
            IVCrushClass.EXPANSION: 10.0,
            IVCrushClass.NO_CRUSH: -2.0
        }
        
        # Weighted average based on probabilities
        weighted_sum = sum(
            class_estimates.get(cls, 0) * prob
            for cls, prob in probs.items()
        )
        
        return weighted_sum

    def train(
        self,
        training_data: List[Tuple[FeatureVector, str]],
        test_size: float = 0.2,
        n_estimators: int = 100,
        max_depth: int = 10
    ) -> Dict[str, Any]:
        """
        Train the Random Forest model.
        
        Args:
            training_data: List of (FeatureVector, label) tuples
            test_size: Fraction of data for testing
            n_estimators: Number of trees in forest
            max_depth: Maximum tree depth
        
        Returns:
            Training results with metrics
        """
        if not SKLEARN_AVAILABLE:
            raise ImportError("scikit-learn required for training. Install with: pip install scikit-learn")
        
        if len(training_data) < 50:
            logger.warning(f"Small training set ({len(training_data)} samples). Model may overfit.")
        
        # Prepare data
        X = np.array([f.to_array() for f, _ in training_data])
        y = np.array([label for _, label in training_data])
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
            class_weight="balanced"  # Handle class imbalance
        )
        
        self.model.fit(X_train_scaled, y_train)
        self.is_trained = True
        
        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        f1 = f1_score(y_test, y_pred, average="weighted")
        
        # Cross-validation
        cv_scores = cross_val_score(self.model, X_train_scaled, y_train, cv=5, scoring="f1_weighted")
        
        # Feature importance
        feature_importance = dict(zip(
            FeatureVector.feature_names(),
            self.model.feature_importances_
        ))
        
        results = {
            "f1_score": round(f1, 3),
            "cv_mean": round(cv_scores.mean(), 3),
            "cv_std": round(cv_scores.std(), 3),
            "training_samples": len(X_train),
            "test_samples": len(X_test),
            "feature_importance": dict(sorted(
                feature_importance.items(),
                key=lambda x: x[1],
                reverse=True
            )),
            "classification_report": classification_report(y_test, y_pred, output_dict=True),
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
            "model_version": self.MODEL_VERSION,
            "trained_at": datetime.now().isoformat()
        }
        
        logger.info(f"Model trained. F1-score: {f1:.3f}, CV mean: {cv_scores.mean():.3f}")
        
        return results

    def save_model(self, path: Optional[str] = None):
        """Save trained model to disk."""
        if not self.is_trained:
            raise ValueError("Model not trained yet")
        
        # Ensure model directory exists
        self.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        
        model_path = Path(path) if path else self.MODEL_DIR / self.MODEL_FILE
        scaler_path = model_path.parent / self.SCALER_FILE
        
        with open(model_path, "wb") as f:
            pickle.dump(self.model, f)
        
        if self.scaler:
            with open(scaler_path, "wb") as f:
                pickle.dump(self.scaler, f)
        
        logger.info(f"Model saved to {model_path}")

    def load_model(self, path: str):
        """Load trained model from disk."""
        model_path = Path(path)
        scaler_path = model_path.parent / self.SCALER_FILE
        
        with open(model_path, "rb") as f:
            self.model = pickle.load(f)
        
        if scaler_path.exists():
            with open(scaler_path, "rb") as f:
                self.scaler = pickle.load(f)
        
        self.is_trained = True
        logger.info(f"Model loaded from {model_path}")

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance ranking."""
        if not self.is_trained or self.model is None:
            return {}
        
        return dict(zip(
            FeatureVector.feature_names(),
            self.model.feature_importances_
        ))


# Singleton instance for convenience
_predictor_instance = None


def get_predictor() -> IVCrushPredictor:
    """Get or create singleton predictor instance."""
    global _predictor_instance
    if _predictor_instance is None:
        _predictor_instance = IVCrushPredictor()
    return _predictor_instance
