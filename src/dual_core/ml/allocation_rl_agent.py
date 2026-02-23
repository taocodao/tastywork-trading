"""
PPO Allocation Agent
====================

A Reinforcement Learning agent that learns the optimal capital split 
between CSP and PMCC given current market conditions.

State Space: 15 dimensions (VIX, Regimes, P&L, Greeks)
Action Space: 5 discrete allocation profiles
"""

import logging
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Dict, Tuple, List, Optional
import os
import sys

# Optional dependency imports handled safely
try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import EvalCallback
except ImportError:
    PPO = None

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from src.pmcc.ml.confidence_gate import ConfidenceGatedDecisionMaker
from src.dual_core.allocator import AllocationPlan

logger = logging.getLogger(__name__)

# Action Mappings
# [CSP%, PMCC%, Cash%]
ALLOCATION_PROFILES = {
    0: (0.55, 0.10, 0.35), # CSP Heavy
    1: (0.40, 0.20, 0.40), # Defensive
    2: (0.40, 0.25, 0.35), # Balanced (Default target)
    3: (0.30, 0.35, 0.35), # PMCC Heavy
    4: (0.25, 0.40, 0.35)  # Max Growth
}

class AllocationEnv(gym.Env):
    """
    Gym environment for simulating Dual-Core capital allocation.
    Used for training the PPO agent on historical data.
    """
    def __init__(self, historical_data: List[Dict]):
        super().__init__()
        self.data_series = historical_data
        self.current_step = 0
        self.max_steps = len(historical_data) - 1
        
        # Action Space: 5 discrete profiles
        self.action_space = spaces.Discrete(5)
        
        # Obs Space: 15 continuous variables (plus 2 optional LSTM boosters)
        # Using 17 to accommodate the LSTM IV Router dimensions from Phase 4.2
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(17,), dtype=np.float32
        )
        
        # Tracking state
        self.current_allocation_idx = 2 # Start balanced
        self.days_since_rebalance = 0

    def reset(self, seed=None, options=None) -> Tuple[np.ndarray, Dict]:
        super().reset(seed=seed)
        self.current_step = 0
        self.current_allocation_idx = 2
        self.days_since_rebalance = 0
        return self._get_observation(), {}

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        # Calculate churn (penalty for changing too often)
        churn_penalty = 0.0
        if action != self.current_allocation_idx:
            if self.days_since_rebalance < 10:
                churn_penalty = 0.05 # Heavy penalty for flipping constantly
            elif self.days_since_rebalance < 20:
                churn_penalty = 0.02
            self.days_since_rebalance = 0
        else:
            self.days_since_rebalance += 1
            
        self.current_allocation_idx = action
        
        # Advance state
        self.current_step += 1
        done = self.current_step >= self.max_steps
        
        # Calculate Reward (Mocked logic for placeholder)
        # In reality, this calculates portfolio P&L based on the weights chosen
        # applied to the next N days of forward returns for CSP vs PMCC indices.
        mock_sharpe = np.random.normal(1.0, 0.2) 
        mock_drawdown = np.random.uniform(0, 0.1)
        
        reward = (mock_sharpe * 0.5) + ((1.0 - mock_drawdown) * 0.2) - churn_penalty
        
        info = {
            "allocation": ALLOCATION_PROFILES[action],
            "churn_penalty": churn_penalty
        }
        
        return self._get_observation(), reward, done, False, info

    def _get_observation(self) -> np.ndarray:
        data = self.data_series[self.current_step]
        obs = np.array([
            data.get('vix', 20.0),
            data.get('vix_5d_pct', 0.0),
            data.get('prob_low_vol', 0.25),
            data.get('prob_normal', 0.50),
            data.get('prob_high_vol', 0.20),
            data.get('prob_crisis', 0.05),
            data.get('csp_30d_pnl', 0.0),
            data.get('pmcc_30d_pnl', 0.0),
            data.get('portfolio_net_delta', 0.1),
            data.get('portfolio_theta_pct', 0.001),
            data.get('cash_reserve_pct', 0.35),
            data.get('spy_20d_ret', 0.0),
            data.get('spy_rsi', 50.0),
            data.get('term_structure_slope', 2.0),
            self.days_since_rebalance,
            # LSTM Route Boosters (0 by default if unrouted)
            data.get('lstm_csp_boost', 0.0),
            data.get('lstm_pmcc_boost', 0.0)
        ], dtype=np.float32)
        return obs


class AllocationRLAgent:
    """
    Wrapper for the Stable-Baselines3 PPO Model.
    Provides inference interface for DualCoreAllocator.
    """
    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.gate = ConfidenceGatedDecisionMaker(confidence_threshold=0.65)
        
        if model_path and PPO is not None:
             self.load(model_path)
             
    def load(self, model_path: str):
        try:
            if os.path.exists(model_path):
                 self.model = PPO.load(model_path)
                 logger.info(f"Loaded Allocation PPO model from {model_path}")
            else:
                 logger.warning(f"Allocation PPO model not found at {model_path}")
        except Exception as e:
            logger.error(f"Failed to load PPO model: {e}")
            
    def train(self, historical_data: List[Dict], total_timesteps: int = 200000, save_path: str = "allocation_ppo"):
        if PPO is None:
            logger.error("stable_baselines3 not installed.")
            return
            
        env = AllocationEnv(historical_data)
        logger.info("Initializing PPO Training...")
        self.model = PPO("MlpPolicy", env, verbose=1, learning_rate=0.0003, n_steps=2048)
        
        # Assuming early stopping and eval callbacks are setup
        self.model.learn(total_timesteps=total_timesteps, progress_bar=True)
        self.model.save(save_path)
        logger.info(f"Training complete. Saved to {save_path}")

    def predict_allocation(
        self, 
        vix: float, 
        regime: str, 
        portfolio_state: Dict,
        routing_signal: Optional[Dict] = None
    ) -> Tuple[AllocationPlan, float]:
        """
        Inference method called by DualCoreAllocator.
        Returns the AllocationPlan and the confidence score.
        """
        if self.model is None:
            raise ValueError("Model not loaded.")
            
        # 1. Build observation vector
        # Note: In production, values are extracted accurately from state
        obs = np.zeros(17, dtype=np.float32)
        obs[0] = vix
        # ... Populate obs 1-14 from portfolio_state ...
        obs[14] = portfolio_state.get('days_since_rebalance', 0)
        
        # Incorporate Phase 4.2 LSTM Routing Bias
        if routing_signal:
            obs[15] = routing_signal.get('csp_weight_boost', 0.0)
            obs[16] = routing_signal.get('pmcc_weight_boost', 0.0)
            
        # 2. Get prediction and Action Probabilities (for confidence)
        try:
            # We need the action probability distribution
            if hasattr(self.model.policy, "get_distribution"):
                import torch
                obs_tensor = torch.tensor(obs).unsqueeze(0)
                dist = self.model.policy.get_distribution(obs_tensor)
                probs = torch.softmax(dist.distribution.logits, dim=1).detach().numpy()[0]
                
                action = np.argmax(probs)
                confidence = float(probs[action])
            else:
                # Fallback if policy doesn't expose distribution easily
                action, _ = self.model.predict(obs, deterministic=True)
                action = int(action)
                confidence = 1.0 # Cannot gauge 
                
        except Exception as e:
            logger.error(f"PPO prediction failed: {e}")
            raise
            
        # 3. Create Plan
        csp, pmcc, cash = ALLOCATION_PROFILES[action]
        
        plan = AllocationPlan(
            csp_conservative_pct=csp * 0.7, # Rough split of the CSP bucket
            csp_aggressive_pct=csp * 0.3,
            pmcc_moderate_pct=pmcc,
            cash_reserve_pct=cash,
            tail_hedge_pct=0.02, # Fixed costs
            money_market_pct=0.03,
            is_ml_driven=True,
            confidence=confidence
        )
        
        return plan, confidence
