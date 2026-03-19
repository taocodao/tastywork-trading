import pandas as pd
import numpy as np
import logging
import joblib
import os
from typing import Optional, Dict

try:
    from xgboost import XGBClassifier
    from sklearn.calibration import CalibratedClassifierCV
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from .feature_engineering import generate_technical_features, label_crossover_outcomes

logger = logging.getLogger(__name__)

class TurboCoreSignalScorer:
    """
    XGBoost classifier to score the confidence of 5/30 EMA crossover signals.
    Employs CalibratedClassifierCV (Platt scaling) to output interpretable probabilities.
    """
    
    MODEL_FILE = os.path.join(os.path.dirname(__file__), 'turbocore_xgboost.joblib')
    
    FEATURES = [
        'tqqq_rsi_14', 'tqqq_macd_hist', 'tqqq_bb_width', 
        'qqq_vol_20d', 'vix_close', 'vix_rel_50',
        'vol_ratio', 'vix_term_slope', 'hyg_5d_change'
    ]
    
    def __init__(self):
        self.calibrated_model: Optional[CalibratedClassifierCV] = None
        self.is_trained = False
        
        if not XGBOOST_AVAILABLE:
            logger.warning("xgboost or sklearn missing. Signal scorer degraded.")
            return
            
        self._load_model()
        
    def _load_model(self):
        if os.path.exists(self.MODEL_FILE):
             try:
                 self.calibrated_model = joblib.load(self.MODEL_FILE)
                 self.is_trained = True
                 logger.debug(f"Loaded XGBoost from {self.MODEL_FILE}")
             except Exception as e:
                 logger.error(f"Failed loading XGBoost model: {e}")
                 
    def _save_model(self):
        if self.calibrated_model and self.is_trained:
            try:
                joblib.dump(self.calibrated_model, self.MODEL_FILE)
            except Exception as e:
                 logger.error(f"Failed Saving XGBoost model: {e}")
                 
    def fit(self, df: pd.DataFrame):
        if not XGBOOST_AVAILABLE:
            return
            
        logger.info("Preparing data for XGBoost Score training...")
        
        # 1. Generate features
        fdf = generate_technical_features(df)
        fdf = fdf.dropna(subset=self.FEATURES)
        
        # 2. Label past crossovers with Triple Barrier (Meta-Labeling)
        # We look ahead 63 days for LEAPS. TP is +3x path vol, SL is -1.5x path vol.
        fdf = label_crossover_outcomes(fdf, forward_days=63, tp_mult=3.0, sl_mult=1.5)
        
        # Extract rows that were actually labeled
        labeled_df = fdf.dropna(subset=['target_profitable'])
        
        if len(labeled_df) < 30:
            logger.warning(f"Only {len(labeled_df)} labeled signals found. XGBoost needs > 30. Skipping.")
            return
            
        X = labeled_df[self.FEATURES].values
        y = labeled_df['target_profitable'].values
        
        logger.info(f"Training Calibrated XGBoost on {len(X)} crossover events...")
        
        # Base classifier
        base_xgb = XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42
        )
        
        # Wraps with Sigmoid Platt Scaling
        self.calibrated_model = CalibratedClassifierCV(
            estimator=base_xgb, 
            method='sigmoid', 
            cv=min(5, len(X)//10) # Adjust CV folding for small datasets
        )
        
        self.calibrated_model.fit(X, y)
        self.is_trained = True
        self._save_model()
        logger.info("XGBoost scoring model calibrated and saved.")
        
    def predict_confidence(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Appends the `ml_confidence` metric (0.0 to 1.0) to the dataframe.
        """
        out_df = df.copy()
        out_df['ml_confidence'] = 0.5 # Default uncertainty
        
        if not self.is_trained or not XGBOOST_AVAILABLE:
            return out_df
            
        out_df = generate_technical_features(out_df)
        
        # We only predict confidence where features exist
        valid_idx = out_df.dropna(subset=self.FEATURES).index
        if len(valid_idx) > 0:
            X = out_df.loc[valid_idx, self.FEATURES].values
            
            probs = self.calibrated_model.predict_proba(X)
            # Handle case where model only ever saw 0s or 1s during training (predicts 1 class)
            if probs.shape[1] == 1:
                out_df.loc[valid_idx, 'ml_confidence'] = probs[:, 0]  # Or whatever single probability it yields
            else:
                out_df.loc[valid_idx, 'ml_confidence'] = np.round(probs[:, 1], 3)
            
        return out_df

if __name__ == "__main__":
    from src.tqqq_turbocore.data_pipeline import TurboCoreDataPipeline
    logging.basicConfig(level=logging.INFO)
    pipeline = TurboCoreDataPipeline()
    pipeline.fetch_data("5y")
    df = pipeline.prepare_core_features()
    
    scorer = TurboCoreSignalScorer()
    scorer.fit(df)
    
    scored_df = scorer.predict_confidence(df)
    
    # Show confidence scored on days with active crossover triggers
    crossover_days = scored_df[
        (scored_df['tqqq_bull_cross'] == True) & 
        (scored_df['tqqq_bull_cross'].shift(1) == False)
    ]
    
    print(f"Scored {len(crossover_days)} historical crossovers:")
    print(crossover_days[['tqqq_close', 'ml_confidence']].tail())
