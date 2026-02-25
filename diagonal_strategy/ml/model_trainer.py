"""
Model Trainer
=============
Trains the XGBoost oscillation predictor using validation scoring.
Saves the best model for live inference.
"""

from xgboost import XGBClassifier
import pandas as pd
import numpy as np
import logging
import os
from sklearn.metrics import accuracy_score, classification_report

logger = logging.getLogger(__name__)

class ModelTrainer:
    def __init__(self, model_dir: str = "diagonal_strategy/ml/models"):
        self.model_dir = model_dir
        os.makedirs(self.model_dir, exist_ok=True)
        
    def train(self, X: pd.DataFrame, y: pd.Series) -> XGBClassifier:
        """
        Trains an XGBoost multiclass model on the full dataset.
        For demonstration, uses a standard train/test split.
        """
        logger.info(f"Training XGBoost model on {len(X)} samples...")
        
        split_idx = int(len(X) * 0.8)
        X_train, y_train = X.iloc[:split_idx], y.iloc[:split_idx]
        X_test, y_test = X.iloc[split_idx:], y.iloc[split_idx:]
        
        # Compute sample weights to counteract class imbalance (UP dominates)
        from sklearn.utils.class_weight import compute_sample_weight
        sample_weights = compute_sample_weight('balanced', y_train)
        
        model = XGBClassifier(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective='multi:softprob',
            num_class=3,
            eval_metric='mlogloss',
            early_stopping_rounds=30,
            random_state=42
        )
        
        # We need to drop any columns that XGBoost cannot handle natively, 
        # but our X should consist purely of floats.
        model.fit(
            X_train, y_train,
            sample_weight=sample_weights,
            eval_set=[(X_test, y_test)],
            verbose=False
        )
        
        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        logger.info(f"Validation Accuracy: {acc:.2%}")
        report = classification_report(y_test, preds, target_names=['DOWN', 'FLAT', 'UP'], zero_division=0)
        logger.info(f"\n{report}")
        
        # Re-train on full dataset for production
        logger.info("Refitting on full dataset for production...")
        best_n = model.best_iteration if hasattr(model, 'best_iteration') and model.best_iteration else 300
        final_model = XGBClassifier(
            n_estimators=best_n,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective='multi:softprob',
            num_class=3,
            random_state=42
        )
        final_model.fit(X, y)
        
        model_path = os.path.join(self.model_dir, "xgb_oscillator.json")
        final_model.save_model(model_path)
        logger.info(f"Saved production model to {model_path}")
        
        return final_model
