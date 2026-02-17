import pandas as pd
import numpy as np
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from xgboost import XGBClassifier
    from sklearn.model_selection import TimeSeriesSplit, cross_val_score
    from sklearn.metrics import accuracy_score, precision_score
    XGBOOST_AVAILABLE = True
except ImportError:
    logger.warning("XGBoost or Scikit-Learn not installed. ML Filter disabled.")
    XGBOOST_AVAILABLE = False

class FeatureExtractor:
    @staticmethod
    def extract(row, df, date):
        """
        Extract ML features from a single row of market data.
        Assumes df has history up to 'date'.
        """
        try:
            # Technicals
            rsi = row.get('RSI', 50)
            drop_pct = row.get('Drop_Pct', 0)
            sma50_dist = (row['Close'] - row.get('SMA50', row['Close'])) / row['Close']
            atr_pct = (row.get('ATR', 0) / row['Close']) * 100
            
            # Volume
            vol_spike = row.get('Vol_Spike', 1.0)
            
            # Momentum / Oscillators (Need history if not pre-calc)
            # We assume these columns are pre-calculated in dataframe or we calculate on fly
            # For simplicity, we'll use what's available or simple derived values
            
            # Derived
            close = row['Close']
            prev_close = df.shift(1).loc[date]['Close'] if date in df.index else close
            roc_1d = (close - prev_close) / prev_close
            
            # --- NEW FEATURES (Phase 8) ---
            # 1. SMA200 Distance (Long Trend)
            sma200 = row.get('SMA200', row['Close']) # calculated in backtester
            sma200_dist = (close - sma200) / sma200
            
            # 2. Bollinger Band Position
            # BB Calculation on the fly if not present
            if 'BB_Upper' not in row:
                # Rolling calculation might be expensive here if not pre-calc.
                # Use simple approx or rely on backtester pre-calc. 
                # Backtester doesn't pre-calc BB. Let's calc from recent history in DF.
                # We need historical closes.
                window = 20
                if len(df) >= window:
                     # Get last 20 rows ending at date
                     # Handle if date index match
                     if date in df.index:
                         idx = df.index.get_loc(date)
                         recent = df.iloc[max(0, idx-window+1):idx+1]
                     else:
                         recent = df.tail(window)
                     
                     ma = recent['Close'].mean()
                     std = recent['Close'].std()
                     upper = ma + 2*std
                     lower = ma - 2*std
                     
                     bb_pos = (close - lower) / (upper - lower) if (upper-lower) > 0 else 0.5
                else:
                    bb_pos = 0.5
            else:
                bb_pos = (close - row['BB_Lower']) / (row['BB_Upper'] - row['BB_Lower'])

            # 3. ATR Rank (Percentile vs 60d)
            if 'ATR' in df.columns:
                 # Current ATR vs last 60d ATRs
                 if date in df.index:
                     idx = df.index.get_loc(date)
                     # Look at prev 60 days
                     history = df['ATR'].iloc[max(0, idx-60):idx+1]
                     rank = history.rank(pct=True).iloc[-1]
                 else:
                     rank = 0.5
            else:
                rank = 0.5

            # Day of Week / Month
            dt = pd.to_datetime(date)
            dow = dt.dayofweek
            month = dt.month
            
            return {
                'RSI': rsi,
                'Drop_Pct': drop_pct,
                'SMA50_Dist': sma50_dist,
                'SMA200_Dist': sma200_dist,
                'ATR_Pct': atr_pct,
                'ATR_Rank': rank,
                'BB_Pos': bb_pos,
                'Vol_Spike': vol_spike,
                'ROC_1d': roc_1d,
                'DOW': dow,
                'Month': month
            }
        except Exception as e:
            logger.error(f"Error extracting features for {date}: {e}")
            return None

class ZebraMLFilter:
    def __init__(self, confidence_threshold=0.65):
        self.model = None
        self.threshold = confidence_threshold
        if XGBOOST_AVAILABLE:
            self.model = XGBClassifier(
                n_estimators=100,         # Increased from 50 (Phase 8)
                learning_rate=0.05,       # Slower learning
                max_depth=4,              # Slightly deeper
                min_child_weight=3,       # Reduce overfitting
                subsample=0.8,            # Regularization
                colsample_bytree=0.8,     # Regularization
                eval_metric='logloss',
                use_label_encoder=False,
                n_jobs=1,
                verbosity=0
            )
            
    def train(self, trades_df):
        """
        Train the model on historical trade results.
        trades_df must contain: 'features' (dict) and 'outcome' (1=Win, 0=Loss)
        """
        if not XGBOOST_AVAILABLE or trades_df.empty:
            return False
            
        # Prepare Data
        # Filter out corrupted features
        trades_df = trades_df.dropna(subset=['outcome'])
        if trades_df.empty: return False

        X = pd.DataFrame(trades_df['features'].tolist())
        y = trades_df['outcome']
        
        # Simple fillna for safety
        X = X.fillna(0)
        
        # Time Series Split Validation
        tscv = TimeSeriesSplit(n_splits=3)
        try:
            scores = cross_val_score(self.model, X, y, cv=tscv, scoring='precision', n_jobs=1)
            logger.info(f"ML Model CV Precision: {scores.mean():.2f} (Scores: {scores})")
        except Exception as e:
            logger.warning(f"CV Failed: {e}")
        
        # Fit on all data
        self.model.fit(X, y)
        
        # Log Feature Importance
        try:
            imps = self.model.feature_importances_
            feats = X.columns
            sorted_idx = np.argsort(imps)[::-1]
            logger.info("Top Features: " + ", ".join([f"{feats[i]}: {imps[i]:.3f}" for i in sorted_idx[:5]]))
        except: pass
        
        return True
        
    def predict(self, feature_dict):
        """
        Return confidence probability of a WIN.
        """
        if not XGBOOST_AVAILABLE or not self.model:
            return 0.5 # Neutral if no model
            
        X = pd.DataFrame([feature_dict])
        X = X.fillna(0) # alignment
        try:
            # Predict Proba returns [prob_0, prob_1]
            prob_win = self.model.predict_proba(X)[0][1] 
            return prob_win
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return 0.5

    def should_trade(self, feature_dict):
        prob = self.predict(feature_dict)
        return prob >= self.threshold, prob

    def save_model(self, filepath="zebra_ml_model.joblib"):
        """Save the trained model to disk."""
        if not self.model:
            logger.warning("No model to save.")
            return False
        try:
            import joblib
            joblib.dump(self.model, filepath)
            logger.info(f"Model saved to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
            return False

    def load_model(self, filepath="zebra_ml_model.joblib"):
        """Load a trained model from disk."""
        try:
            import joblib
            import os
            if not os.path.exists(filepath):
                logger.warning(f"Model file not found: {filepath}")
                return False
                
            self.model = joblib.load(filepath)
            logger.info(f"Model loaded from {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
