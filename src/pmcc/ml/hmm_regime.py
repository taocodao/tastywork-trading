import logging
import numpy as np
import pandas as pd
from datetime import date
from typing import Dict, Optional, Tuple
import joblib
import os

try:
    from hmmlearn.hmm import GaussianHMM
    HMMLEARN_AVAILABLE = True
except ImportError:
    HMMLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)

class HMMRegimeDetector:
    """
    Hidden Markov Model with 4 hidden states mapping to:
    LOW_VOL, NORMAL, HIGH_VOL, CRISIS
    
    Observable features:
    - ATR % (14-day)
    - SPY 20-day realized volatility
    
    Output: probability vector [P(LOW), P(NORMAL), P(HIGH), P(CRISIS)]
    Instead of binary label, enables proportional position sizing.
    """
    
    REGIME_NAMES = ["LOW_VOL", "NORMAL", "HIGH_VOL", "CRISIS"]
    MODEL_FILE = os.path.join(os.path.dirname(__file__), 'hmm_regime_model.joblib')
    
    def __init__(self):
        self.model: Optional[GaussianHMM] = None
        self.is_trained = False
        self.state_mapping: Dict[int, str] = {}
        
        if not HMMLEARN_AVAILABLE:
            logger.warning("hmmlearn is not installed. HMMRegimeDetector will not work.")
            return
            
        self._load_model()
            
    def _load_model(self):
        """Load trained HMM from disk if available."""
        if os.path.exists(self.MODEL_FILE):
            try:
                data = joblib.load(self.MODEL_FILE)
                self.model = data['model']
                self.state_mapping = data['mapping']
                self.is_trained = True
                logger.info(f"Loaded HMM Regime Model from {self.MODEL_FILE}")
            except Exception as e:
                logger.error(f"Failed to load HMM model: {e}")
    
    def _save_model(self):
        """Save trained HMM to disk."""
        if self.model and self.is_trained:
            try:
                joblib.dump({
                    'model': self.model,
                    'mapping': self.state_mapping
                }, self.MODEL_FILE)
                logger.info(f"Saved HMM Regime Model to {self.MODEL_FILE}")
            except Exception as e:
                logger.error(f"Failed to save HMM model: {e}")

    def _extract_features(self, market_data: pd.DataFrame) -> np.ndarray:
        """
        Extract observable features from market data.
        Assumes market_data is SPY daily OHLCV.
        """
        df = market_data.copy()
        
        # 1. ATR %
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        df['ATR_Pct'] = (df['ATR'] / df['Close']) * 100
        
        # 2. Realized Volatility (20-day, annualized)
        df['Log_Ret'] = np.log(df['Close'] / df['Close'].shift(1))
        df['Realized_Vol'] = df['Log_Ret'].rolling(20).std() * np.sqrt(252) * 100
        
        # Drop NAs
        df = df.dropna(subset=['ATR_Pct', 'Realized_Vol'])
        
        return df[['ATR_Pct', 'Realized_Vol']].values

    def fit(self, market_data: pd.DataFrame) -> None:
        """
        Train the HMM on historical market data.
        """
        if not HMMLEARN_AVAILABLE:
            logger.error("Cannot fit HMM: hmmlearn not installed.")
            return
            
        X = self._extract_features(market_data)
        
        if len(X) < 100:
            logger.error("Insufficient data to train HMM (need > 100 rows).")
            return
            
        logger.info(f"Training HMM Regime Detector on {len(X)} samples...")
        
        # 4 states corresponding to our 4 regimes
        self.model = GaussianHMM(n_components=4, covariance_type="diag", n_iter=1000, random_state=42)
        self.model.fit(X)
        
        # We need to map the hidden states (0, 1, 2, 3) to our meaningful labels
        # by looking at the means of the features (ATR and Vol).
        # State with lowest mean Vol/ATR -> LOW_VOL
        # State with highest mean Vol/ATR -> CRISIS
        
        # Get the sum of means for each state (Feature 0: ATR%, Feature 1: Realized Vol)
        state_means = np.sum(self.model.means_, axis=1)
        
        # Sort states by their means
        sorted_states = np.argsort(state_means)
        
        # Map them intuitively
        self.state_mapping = {
            sorted_states[0]: "LOW_VOL",
            sorted_states[1]: "NORMAL",
            sorted_states[2]: "HIGH_VOL",
            sorted_states[3]: "CRISIS"
        }
        
        self.is_trained = True
        self._save_model()
        logger.info(f"HMM Training complete. State Mapping: {self.state_mapping}")

    def predict_regime(self, market_data: pd.DataFrame, target_date: Optional[date] = None) -> Dict[str, float]:
        """
        Predict regime probabilities for the latest date (or target_date) in market_data.
        
        Returns:
            Dict mapping regime names to layout probabilities (0.0 - 1.0)
            e.g., {"NORMAL": 0.85, "HIGH_VOL": 0.15, "LOW_VOL": 0.0, "CRISIS": 0.0}
        """
        default_probs = {"NORMAL": 1.0, "LOW_VOL": 0.0, "HIGH_VOL": 0.0, "CRISIS": 0.0}
        
        if not self.is_trained or self.model is None:
            return default_probs
            
        if target_date:
            # Filter data up to target_date
            if isinstance(market_data.index, pd.DatetimeIndex):
                dt_str = target_date.strftime('%Y-%m-%d')
                if dt_str in market_data.index:
                    market_data = market_data.loc[:dt_str]
        
        X = self._extract_features(market_data)
        if len(X) == 0:
            return default_probs
            
        # Get the last observation
        last_obs = X[-1].reshape(1, -1)
        
        # predict_proba returns the probability of each hidden state given the observation
        # However, for a single observation, standard predict_proba requires the full sequence for forward-backward.
        # Alternatively, we can just look at the emission probabilities for the current single step, 
        # or run the full sequence to get the filtered belief state at the last step.
        
        try:
            # Run the full sequence through the model to get the posterior probabilities
            probs = self.model.predict_proba(X)
            last_probs = probs[-1]  # Probabilities of the 4 states for the most recent timestep
            
            # Map hidden states to labels
            result = {
                "LOW_VOL": 0.0,
                "NORMAL": 0.0,
                "HIGH_VOL": 0.0,
                "CRISIS": 0.0
            }
            
            for state_idx, prob in enumerate(last_probs):
                label = self.state_mapping.get(state_idx, "NORMAL")
                result[label] = float(prob)
                
            return result
        except Exception as e:
            logger.error(f"Failed to predict HMM probabilities: {e}")
            return default_probs

    def get_blended_regime_params(self, market_data: pd.DataFrame, baseline_params: Dict[str, Dict]) -> Tuple[str, Dict]:
        """
        Return the dominant regime label, and a mathematically blended set of parameters
        weighted by the regime probabilities.
        """
        probs = self.predict_regime(market_data)
        
        # Get the dominant regime (highest probability)
        dominant_regime = max(probs.items(), key=lambda x: x[1])[0]
        
        # If the model isn't confident in anything (e.g. all 0), default to NORMAL
        if sum(probs.values()) == 0:
            return "NORMAL", baseline_params.get("NORMAL", {})
            
        # Blend the parameters
        blended = {}
        
        # The fields we care about blending
        numeric_fields = ['trailing_stop_pct', 'hard_stop_pct', 'time_exit_days', 'max_positions', 'allocation']
        
        for field in numeric_fields:
            blended_value = 0.0
            for regime, prob in probs.items():
                if regime in baseline_params and field in baseline_params[regime]:
                    blended_value += (baseline_params[regime][field] * prob)
            
            # Type correction (e.g. max_positions and time_exit_days should be integers)
            if field in ['time_exit_days', 'max_positions']:
                blended[field] = int(round(blended_value))
            else:
                blended[field] = round(blended_value, 4)
                
        return dominant_regime, blended
