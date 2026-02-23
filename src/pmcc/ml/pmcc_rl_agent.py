import logging
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

from src.diagonal_spreads.diagonal_rl_optimizer import (
    DiagonalTradeEnv, 
    DiagonalTradeSnapshot, 
    DiagonalRLOptimizer,
    DiagonalAction,
    SB3_AVAILABLE
)

logger = logging.getLogger(__name__)

if SB3_AVAILABLE:
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    from stable_baselines3.common.callbacks import EvalCallback
    from gymnasium import spaces

@dataclass
class PMCCSnapshot(DiagonalTradeSnapshot):
    """
    Extends the 20-feature DiagonalTradeSnapshot into a 28-feature PMCC state.
    """
    leaps_current_delta: float = 0.80
    cumulative_premium_collected_pct: float = 0.0 # pct of initial leaps debit
    cycle_count: int = 1
    assignment_risk_score: float = 0.0
    bci_headroom: float = 0.10 # (Short Strike - Break Even) / Stock Price
    width_pct: float = 0.20 # (Short Strike - Long Strike) / Long Strike
    long_leg_pnl_pct: float = 0.0
    extrinsic_ratio: float = 0.10


class PMCCManagementEnv(DiagonalTradeEnv):
    """
    PPO RL Environment specifically tuned for the Poor Man's Covered Call.
    
    Increases observation space to 28 features to give the agent full context
    over the LEAPS leg profitability and the cumulative premium scaling.
    
    Adjusts the reward function to penalize assignment and heavily reward 
    risk-free cycle rolls.
    """
    def __init__(self, trade_data: List[List[PMCCSnapshot]], symbol: str = "SPY", max_rolls: int = 12):
        super().__init__(trade_data=trade_data, symbol=symbol, max_rolls=max_rolls)
        
        # Extend Observation Space from 20 -> 28
        low = list(self.observation_space.low)
        high = list(self.observation_space.high)
        
        # Add bounds for the new 8 features
        low.extend([0.0, -2.0, 0, 0.0, -1.0, 0.0, -2.0, 0.0])
        high.extend([1.0, 5.0, 50, 1.0, 1.0, 2.0, 5.0, 1.0])
        
        self.observation_space = spaces.Box(
            low=np.array(low, dtype=np.float32),
            high=np.array(high, dtype=np.float32),
            dtype=np.float32
        )

    def _get_observation(self) -> np.ndarray:
        """Get current 28-dim state observation."""
        base_obs = super()._get_observation()
        
        snapshot: PMCCSnapshot = self.current_trade[min(self.current_step, len(self.current_trade)-1)]
        
        # Append the 8 PMCC-specific features
        pmcc_features = np.array([
            snapshot.leaps_current_delta,
            snapshot.cumulative_premium_collected_pct,
            snapshot.cycle_count,
            snapshot.assignment_risk_score,
            snapshot.bci_headroom,
            snapshot.width_pct,
            snapshot.long_leg_pnl_pct,
            snapshot.extrinsic_ratio
        ], dtype=np.float32)
        
        return np.concatenate((base_obs, pmcc_features))

    def _calculate_exit_reward(self, snapshot: PMCCSnapshot, final_pnl: float) -> float:
        """
        Calculate reward for choosing EXIT action.
        """
        # Base reward inherited from DiagonalEnv calculates time efficiency
        reward = super()._calculate_exit_reward(snapshot, final_pnl)
        
        # PMCC Specifics
        # 1. Penalty if choosing to exit when BCI is still strong and we could have kept selling calls
        if snapshot.bci_headroom > 0.05 and snapshot.long_dte > 90 and snapshot.current_pnl_pct > 0:
            reward -= 0.10
            
        # 2. Bonus if exiting when LEAPS DTE drops below 90 (strategic exit)
        if snapshot.long_dte <= 90 and final_pnl > 0:
            reward += 0.20
            
        return reward
        
    def _calculate_roll_reward(self, snapshot: PMCCSnapshot) -> float:
        """
        Calculate reward for choosing ROLL action.
        """
        reward = super()._calculate_roll_reward(snapshot)
        
        # 1. Bonus for credit-only rolls
        if snapshot.roll_credit_estimate > 0:
            reward += 0.30
            
        # 2. Heavy Penalty for assignment risk (rolling deep ITM short calls late)
        if snapshot.assignment_risk_score > 0.8:
            reward -= 2.0
            
        return reward


class PMCCRLOptimizer(DiagonalRLOptimizer):
    """
    Orchestrates the PPO agent for PMCC specifically.
    """
    def __init__(self, symbol: str = "SPY"):
        super().__init__(symbol=symbol)

    def train(self, training_data: List[List[PMCCSnapshot]], **kwargs):
        """Train PPO specifically using the PMCC Environment."""
        if not SB3_AVAILABLE:
            logger.error("stable-baselines3 not installed. Cannot train PPO.")
            return
            
        logger.info(f"Training PMCC PPO Agent on {len(training_data)} historical cycle records...")
        
        self.env = PMCCManagementEnv(training_data, symbol=self.symbol)
        vec_env = DummyVecEnv([lambda: self.env])
        
        # Using more robust hyperparameters for the complex 28-dim space
        self.model = PPO(
            "MlpPolicy",
            vec_env,
            learning_rate=3e-4,  
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,
            verbose=0
        )
        
        self.model.learn(total_timesteps=kwargs.get('total_timesteps', 100000))
        logger.info("PMCC PPO Training Complete.")

    def should_roll_or_exit(
        self,
        snapshot: PMCCSnapshot,
        use_rule_based_fallback: bool = True
    ) -> Tuple[DiagonalAction, float, str]:
        """
        High-level Inference API: Should we hold, roll, or exit this PMCC?
        We accept the full PMCCSnapshot dataclass directly to avoid massive arg lists.
        """
        if self.model is None:
            if use_rule_based_fallback:
                action, reason = self.rule_based.decide(snapshot)
                return action, 0.7, f"Rule-based fallback: {reason}"
            return DiagonalAction.HOLD, 0.5, "Default: hold (model not loaded)"
            
        # Construct the 28-dimensional array observation
        symbol_id = self.get_symbol_id(self.symbol)
        
        observation = np.array([
            snapshot.short_dte, snapshot.long_dte, snapshot.days_held,
            snapshot.current_pnl_pct, snapshot.short_leg_pnl_pct, snapshot.long_leg_pnl_pct,
            snapshot.iv_rank, snapshot.iv_change_pct, snapshot.term_structure_diff, snapshot.iv_skew,
            snapshot.position_delta, snapshot.theta_per_day, snapshot.vega_exposure,
            snapshot.breach_days, snapshot.vix_level, snapshot.underlying_move_pct,
            symbol_id, snapshot.short_theta_decay_pct, snapshot.roll_credit_estimate, snapshot.days_since_last_roll,
            # PMCC Extensions (8)
            snapshot.leaps_current_delta, snapshot.cumulative_premium_collected_pct,
            snapshot.cycle_count, snapshot.assignment_risk_score,
            snapshot.bci_headroom, snapshot.width_pct,
            snapshot.long_leg_pnl_pct, snapshot.extrinsic_ratio
        ], dtype=np.float32)
        
        try:
            action, confidence = self.predict_action(observation)
            return action, confidence, "PPO RL agent optimal prediction"
        except Exception as e:
            logger.warning(f"PMCC RL prediction failed: {e}")
            if use_rule_based_fallback:
                action, reason = self.rule_based.decide(snapshot)
                return action, 0.7, f"Fallback: {reason}"
            return DiagonalAction.HOLD, 0.5, "Default: hold"
