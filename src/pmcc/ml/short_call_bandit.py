import logging
import numpy as np
from typing import Dict, List, Optional
import os
import joblib

logger = logging.getLogger(__name__)

class PMCCShortCallBandit:
    """
    LinUCB (Linear Upper Confidence Bound) Contextual Bandit.
    
    Learns to select the optimal Short Call "Arm" based on the current 15-dim market context.
    
    Arms:
    0: Low delta (0.15-0.20)
    1: Medium delta (0.20-0.25)
    2: Medium-High delta (0.25-0.30)
    3: High delta (0.30-0.35)
    4: ATM (0.40) - Bearish override
    5: Skip cycle (No trade)
    --- Dual-Core CSP Arms ---
    6: CSP Conservative (-0.15)
    7: CSP Standard (-0.20)
    8: CSP Moderate (-0.25)
    9: CSP Aggressive (-0.30)
    """
    
    MODEL_FILE = os.path.join(os.path.dirname(__file__), 'short_call_bandit.joblib')
    
    def __init__(self, n_arms: int = 10, n_features: int = 15, alpha: float = 0.5):
        self.n_arms = n_arms
        self.n_features = n_features
        self.alpha = alpha  # Exploration parameter (higher = explore more)
        
        # Initialize LinUCB matrices
        # A saves context covariance. b saves context*reward.
        self.A = [np.identity(n_features) for _ in range(n_arms)]
        self.b = [np.zeros((n_features, 1)) for _ in range(n_arms)]
        
        self.is_trained = False
        self._load_model()
        
    def _load_model(self):
        """Loads LinUCB matrices from disk."""
        if os.path.exists(self.MODEL_FILE):
            try:
                data = joblib.load(self.MODEL_FILE)
                self.A = data['A']
                self.b = data['b']
                self.is_trained = True
                logger.info(f"Loaded LinUCB Bandit Model from {self.MODEL_FILE}")
            except Exception as e:
                logger.error(f"Failed to load Bandit model: {e}")

    def _save_model(self):
        """Saves LinUCB matrices to disk."""
        try:
            joblib.dump({
                'A': self.A,
                'b': self.b
            }, self.MODEL_FILE)
            logger.info(f"Saved LinUCB Bandit Model to {self.MODEL_FILE}")
        except Exception as e:
            logger.error(f"Failed to save Bandit model: {e}")

    def _extract_context(self, pmcc_features: Dict) -> np.ndarray:
        """
        Maps the 15-dim feature dictionary to a numpy column vector.
        """
        keys = [
            'iv_rank', 'rsi_14', 'macd_signal', 'volume_ratio', 'atr_pct', 'bb_pct_b',
            'resistance_proximity', 'trend_label_enc', 'composite_score', 
            'regime_LOW_VOL', 'regime_NORMAL', 'regime_HIGH_VOL', 'regime_CRISIS',
            'days_since_last_roll', 'leaps_dte_normalized'
        ]
        
        # Extract features, filling missing with 0.0
        vec = [pmcc_features.get(k, 0.0) for k in keys]
        
        # Ensure it's a 15x1 column vector
        return np.array(vec, dtype=np.float64).reshape(-1, 1)

    def predict(self, pmcc_features: Dict, available_arms: List[int] = None) -> Dict[str, Any]:
        """
        Calculate the UCB scores for each arm given the context, and select the best one.
        
        Returns:
            Dict containing the selected arm index and the confidence scores.
        """
        if not available_arms:
            available_arms = list(range(self.n_arms))
            
        context = self._extract_context(pmcc_features)
        
        ucb_scores = {}
        expected_rewards = {}
        
        for arm in available_arms:
            A_inv = np.linalg.inv(self.A[arm])
            theta = A_inv.dot(self.b[arm])
            
            # Expected reward for this arm
            expected_reward = theta.T.dot(context)[0][0]
            expected_rewards[arm] = float(expected_reward)
            
            # Confidence bound (exploration term)
            confidence_bound = self.alpha * np.sqrt(context.T.dot(A_inv).dot(context))[0][0]
            
            # Upper Confidence Bound
            ucb_scores[arm] = float(expected_reward + confidence_bound)
            
        # Select arm with highest UCB score
        best_arm = max(ucb_scores.items(), key=lambda x: x[1])[0]
        
        # We also want a "confidence" metric to pass to the gating layer.
        # LinUCB doesn't output traditional probabilities, but we can normalize the expected rewards
        # or just use the spread between the top 2 as a proxy for certainty.
        sorted_scores = sorted(expected_rewards.values(), reverse=True)
        confidence = 0.5
        if len(sorted_scores) >= 2 and sorted_scores[0] > 0:
            # Spread pct between top choice and 2nd best choice
            spread = (sorted_scores[0] - sorted_scores[1]) / abs(sorted_scores[0])
            confidence = min(0.99, 0.5 + (spread * 0.5)) # Bound between 0.5 and 0.99
            
        return {
            "selected_arm": best_arm,
            "confidence": confidence,
            "ucb_scores": ucb_scores,
            "expected_rewards": expected_rewards
        }

    def update(self, arm: int, pmcc_features: Dict, cycle_pnl: float, entry_cost: float):
        """
        Online learning update. After a cycle finishes, feed the reward back into the bandit.
        
        Reward definition: cycle_pnl / entry_cost (normalized percentage return)
                           If entry_cost is 0, just use straight PnL or a generic reward.
        """
        context = self._extract_context(pmcc_features)
        
        # Calculate Reward
        if entry_cost > 0:
            reward = cycle_pnl / entry_cost
        else:
            reward = cycle_pnl / 100.0 # fallback normalization
            
        # Update LinUCB matrices for the chosen arm
        self.A[arm] += context.dot(context.T)
        self.b[arm] += reward * context
        
        self.is_trained = True
        self._save_model()
        
        logger.info(f"Bandit Online Update: Arm {arm} received Reward {reward:.4f}")

    def map_arm_to_delta(self, arm_idx: int) -> Optional[float]:
        """
        Utility mapping the selected arm index to a target delta value.
        Positive values for Calls (PMCC), Negative values for Puts (CSP).
        """
        mapping = {
            # PMCC Short Call Arms
            0: 0.18, # Low
            1: 0.23, # Med
            2: 0.28, # Med-High
            3: 0.33, # High
            4: 0.40, # ATM bearish override
            5: None, # Skip
            # CSP Short Put Arms
            6: -0.15, # Conservative
            7: -0.20, # Standard
            8: -0.25, # Moderate
            9: -0.30  # Aggressive
        }
        return mapping.get(arm_idx, 0.25)
