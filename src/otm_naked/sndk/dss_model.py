"""
SNDK Dynamic Directional Strangle (DDS) - XGBoost DSS Model
===========================================================
Trains a 3-class XGBoost model to predict 3-day forward return probabilities.
DSS Score = P(UP) - P(DOWN)
"""
import logging
import pandas as pd
import numpy as np
import joblib
from pathlib import Path
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
try:
    import xgboost as xgb
except ImportError:
    xgb = None

logger = logging.getLogger(__name__)

class DSSModel:
    def __init__(self, model_dir="models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.model_dir / "sndk_dds_xgboost.joblib"
        self.scaler_path = self.model_dir / "sndk_dds_scaler.joblib"
        
        self.model = None
        self.scaler = None
        self.is_loaded = False
        
        # 18 Features for DDS
        self.feature_cols = [
            "daily_move_pct", "gap_pct", "daily_range_pct", "atr_14", "roc_5d", "vwap_dev", # Momentum
            "iv_est", "iv_hv_spread", "ivr", "hv_ratio", "iv_change",                       # Volatility
            "put_call_ratio", "net_portfolio_delta", "strike_distance_pct", "days_since_large_move", # Options/Position
            "spy_5d_return", "sndk_spy_corr_20d", "sndk_vs_smh"                             # Market Structure
        ]
        
    def load_model(self) -> bool:
        """Loads trained model and scaler if available."""
        if not xgb:
            logger.error("XGBoost not installed. Please pip install xgboost.")
            return False
            
        if self.model_path.exists() and self.scaler_path.exists():
            try:
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                self.is_loaded = True
                logger.info("Successfully loaded XGBoost DDS model.")
                return True
            except Exception as e:
                logger.error(f"Failed to load DDS model: {e}")
        return False
        
    def predict_dss(self, current_features: pd.Series) -> float:
        """Returns the Directional Signal Score [-1.0, 1.0]."""
        if not self.is_loaded:
            logger.warning("Model not loaded. Cannot predict DSS.")
            return 0.0
            
        try:
            # Build feature array in correct order
            X = []
            for col in self.feature_cols:
                val = current_features.get(col, 0.0)
                # Handle NaNs
                if pd.isna(val): val = 0.0
                X.append(val)
                
            X_arr = np.array(X).reshape(1, -1)
            X_scaled = self.scaler.transform(X_arr)
            
            # Predict probabilities (3 classes: 0=DOWN, 1=SIDEWAYS, 2=UP)
            probs = self.model.predict_proba(X_scaled)[0]
            
            p_down = probs[0]
            p_up = probs[2]
            
            # DSS = P(UP) - P(DOWN)
            dss = float(p_up - p_down)
            return dss
            
        except Exception as e:
            logger.error(f"Error predicting DSS: {e}")
            return 0.0

    def train_model(self, df: pd.DataFrame):
        """
        Train the XGBoost model using historical feature DataFrame.
        Expected to be called offline or on a schedule.
        """
        if not xgb:
            raise ImportError("XGBoost required for training.")
            
        logger.info("Preparing data for XGBoost training...")
        
        # 1. Create Target Label (3-day forward return class)
        # Shift close backwards to get future returns
        future_return = df["close"].shift(-3) / df["close"] - 1.0
        future_return *= 100
        
        # Classes: 0 (DOWN <= -2%), 1 (SIDEWAYS -2% to 2%), 2 (UP >= 2%)
        conditions = [
            future_return <= -2.0,
            future_return >= 2.0
        ]
        choices = [0, 2]
        df["target"] = np.select(conditions, choices, default=1)
        
        # Drop rows where target is NaN (the last 3 days)
        df_clean = df.dropna(subset=["target"] + self.feature_cols)
        
        X = df_clean[self.feature_cols].values
        y = df_clean["target"].values
        
        # Walk-forward split
        tscv = TimeSeriesSplit(n_splits=5, gap=5)
        
        self.scaler = StandardScaler()
        self.model = xgb.XGBClassifier(
            objective='multi:softprob',
            num_class=3,
            n_estimators=100,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42
        )
        
        # Train on full dataset
        logger.info(f"Training on {len(X)} samples with {len(self.feature_cols)} features...")
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        
        # Save
        joblib.dump(self.model, self.model_path)
        joblib.dump(self.scaler, self.scaler_path)
        self.is_loaded = True
        logger.info("Training complete. Model and scaler saved.")
