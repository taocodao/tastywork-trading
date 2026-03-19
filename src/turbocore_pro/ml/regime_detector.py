import logging
import numpy as np
import pandas as pd
from typing import Dict, Optional
import joblib
import os

try:
    from hmmlearn.hmm import GaussianHMM
    HMMLEARN_AVAILABLE = True
except ImportError:
    HMMLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)

class TurboCoreRegimeDetector:
    """
    Hidden Markov Model (HMM) specifically tuned for the TQQQ TurboCore strategy.
    
    Identifies latent states mapping to:
    BULL, SIDEWAYS, BEAR
    
    Observable Features:
    - QQQ 20-day historically rolling volatility
    - VIX daily closing level
    
    This sits in Layer 2, outputting an ML regime that dictates the Fractional Kelly 
    dynamic allocation in the downstream pipeline. It also honors the Layer 1 
    SMA200 (-3% buffer) hard exit gate.
    """
    
    MODEL_FILE = os.path.join(os.path.dirname(__file__), 'turbocore_hmm.joblib')
    
    def __init__(self):
        self.model: Optional[GaussianHMM] = None
        self.is_trained = False
        self.state_mapping: Dict[int, str] = {}
        
        if not HMMLEARN_AVAILABLE:
            logger.warning("hmmlearn is not installed. TurboCoreRegimeDetector will degrade.")
            return
            
        self._load_model()
        
    def _load_model(self):
        if os.path.exists(self.MODEL_FILE):
            try:
                data = joblib.load(self.MODEL_FILE)
                self.model = data['model']
                self.state_mapping = data['mapping']
                self.is_trained = True
                logger.debug(f"Loaded HMM TurboCore Model from {self.MODEL_FILE}")
            except Exception as e:
                logger.error(f"Failed to load HMM model: {e}")
                
    def _save_model(self):
        if self.model and self.is_trained:
            try:
                joblib.dump({
                    'model': self.model,
                    'mapping': self.state_mapping
                }, self.MODEL_FILE)
            except Exception as e:
                logger.error(f"Failed to save HMM model: {e}")

    def _extract_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Expects Master DataFrame containing `qqq_vol_20d` and `vix_close` 
        from data_pipeline.py
        """
        features_df = df[['qqq_vol_20d', 'vix_close']].dropna()
        return features_df.values
        
    def fit(self, df: pd.DataFrame):
        if not HMMLEARN_AVAILABLE:
            logger.error("Cannot fit: hmmlearn missing.")
            return
            
        X = self._extract_features(df)
        if len(X) < 100:
            logger.error("Not enough data to train HMM.")
            return
            
        logger.info(f"Training TurboCore HMM on {len(X)} samples")
        
        # 3 states mapping to BULL, SIDEWAYS, BEAR
        self.model = GaussianHMM(n_components=3, covariance_type="diag", n_iter=1000, random_state=42)
        self.model.fit(X)
        
        # Mapping logic:
        # VIX and Volatility are generally lower in BULL markets and higher in BEAR markets.
        # We sum the normalized means of both features for each state.
        
        # Normalize means for relative comparison
        means = self.model.means_
        norm_means = means / means.max(axis=0)
        state_scores = np.sum(norm_means, axis=1)
        
        sorted_indices = np.argsort(state_scores)
        
        # Lowest vol/vix -> BULL
        # Mid vol/vix -> SIDEWAYS
        # High vol/vix -> BEAR
        self.state_mapping = {
            sorted_indices[0]: "BULL",
            sorted_indices[1]: "SIDEWAYS",
            sorted_indices[2]: "BEAR"
        }
        
        self.is_trained = True
        self._save_model()
        logger.info(f"HMM Training complete. State Mapping: {self.state_mapping}")
        
    def predict_regimes(self, master_df: pd.DataFrame) -> pd.DataFrame:
        """
        Appends the ML predicted regime to the dataframe. 
        Also combines it with the base SMA200 Gate.
        """
        df = master_df.copy()
        
        if not self.is_trained or not HMMLEARN_AVAILABLE or len(df) == 0:
            logger.warning("HMM not trained or unavailable, defaulting ML regime to SIDEWAYS")
            df['ml_regime'] = "SIDEWAYS"
            df['final_regime'] = "SIDEWAYS"
            return df
            
        # Predict hidden states (requires filling NAs for the series length)
        # For dates with missing VIX or Vol (e.g. first 20 days), we pad or default.
        df['ml_regime'] = "SIDEWAYS" # Default safe state
        
        # Only predict on valid feature rows to maintain array sizing
        valid_idx = df[['qqq_vol_20d', 'vix_close']].dropna().index
        if len(valid_idx) > 0:
            X = df.loc[valid_idx, ['qqq_vol_20d', 'vix_close']].values
            hidden_states = self.model.predict(X)
            
            # Map numeric states back to string labels
            state_labels = [self.state_mapping[state] for state in hidden_states]
            df.loc[valid_idx, 'ml_regime'] = state_labels
            
        # The Final Layer: Overlay the SMA200 Gate
        # If SMA200 dictates a hard exit (Risk-Off), it overrides the HMM.
        final_regimes = []
        for idx, row in df.iterrows():
            if row.get('qqq_below_sma200_sell', False):
                final_regimes.append("BEAR_SMA_FORCED")
            else:
                final_regimes.append(row['ml_regime'])
                
        df['final_regime'] = final_regimes
        return df

if __name__ == "__main__":
    from src.tqqq_turbocore.data_pipeline import TurboCoreDataPipeline
    logging.basicConfig(level=logging.INFO)
    pipeline = TurboCoreDataPipeline()
    pipeline.fetch_data("5y")
    df = pipeline.prepare_core_features()
    
    detector = TurboCoreRegimeDetector()
    detector.fit(df)
    
    df_merged = detector.predict_regimes(df)
    print("Recent Regimes:")
    print(df_merged[['qqq_close', 'vix_close', 'qqq_below_sma200_sell', 'ml_regime', 'final_regime']].tail(10))
