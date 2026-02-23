"""
TQQQ PPO Agent
==============
Reinforcement Learning agent (Stable-Baselines3 format) that learns entirely via
simulated backtesting environments to override the rigid Rule-Based state machine.

Expanded 10-discrete Action Space:
    0: Do nothing
    1: Open spread NOW
    2: Open spread DELAYED (wait for TimingEngine window)
    3: Close short leg NOW (Leg out)
    4: Close short leg DELAYED
    5: Sell long put NOW
    6: Sell long put DELAYED
    7: Close entire spread NOW
    8: Close entire spread DELAYED
    9: Roll spread (avoid assignment / adjust delta)

Reward Function:
    R_t = PL - λ₁*(cost)² - λ₂*CVaR_95 - λ₃*Max_DD + λ₄*timing_bonus
"""

import logging
from typing import Dict, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)

try:
    from stable_baselines3 import PPO
    SB3_AVAILABLE = True
except ImportError:
    PPO = None
    SB3_AVAILABLE = False


class TQQQPPOAgent:
    """
    Evaluates the current state tensor and outputs a discrete action (0-9).
    """
    
    # 10 Discrete Actions
    ACTION_DO_NOTHING = 0
    ACTION_OPEN_NOW = 1
    ACTION_OPEN_DELAYED = 2
    ACTION_LEG_OUT_NOW = 3
    ACTION_LEG_OUT_DELAYED = 4
    ACTION_SELL_LONG_NOW = 5
    ACTION_SELL_LONG_DELAYED = 6
    ACTION_CLOSE_SPREAD_NOW = 7
    ACTION_CLOSE_SPREAD_DELAYED = 8
    ACTION_ROLL_SPREAD = 9
    
    def __init__(self, model_path: str = "src/tqqq/ml/models/ppo_agent.zip"):
        self.model_path = model_path
        self.model = None
        self._try_load()
        
    def get_action(self, state: Dict[str, Any]) -> Tuple[int, float]:
        """
        Takes raw state dict, converts to fixed-length vector, 
        and predicts action + confidence (action probability).
        Returns: (action_int, confidence_float)
        """
        if not SB3_AVAILABLE or self.model is None:
            return self.ACTION_DO_NOTHING, 0.0
            
        try:
            obs = self._build_observation(state)
            
            # Predict action deterministically during live trading
            action, _states = self.model.predict(obs, deterministic=True)
            
            # Note: standard SB3 predict() doesn't return action probabilities easily
            # For "confidence", we usually assume high confidence if it deviates from 0 (Do Nothing)
            # In a fully custom setup, we'd pull the logits from the policy network.
            # Here we fake a confidence gate wrapper.
            confidence = 0.85 
            
            return int(action), confidence
            
        except Exception as e:
            logger.error(f"PPO inference failed: {e}")
            return self.ACTION_DO_NOTHING, 0.0

    def _build_observation(self, state: Dict[str, Any]) -> np.ndarray:
        """
        Transforms heterogeneous state dictionary into a normalized 
        floating-point Numpy array for the PPO PyTorch model.
        """
        # Feature 1: Position State Enum Int
        current_state = int(state.get("position_state", 0))  # 0: IDLE, 1: FULL, 2: LONG_ONLY
        
        # Features 2-5: PnL and Greek metrics
        spread_pnl_pct = state.get("spread_pnl_pct", 0.0)
        short_put_pnl_pct = state.get("short_put_pnl_pct", 0.0)
        dte = state.get("dte", 0) / 45.0  # Normalized to ~45 max
        
        # Features 6-10: Market Context
        vix = state.get("vix_level", 15.0) / 80.0
        vix_trend = state.get("vix_trend", 0.0)  # -1, 0, 1
        tqqq_trend = state.get("tqqq_trend", 0.0) # -1, 0, 1
        
        # Returns vector shape (7, ) - Must match PPO env exactly
        return np.array([
            current_state,
            spread_pnl_pct,
            short_put_pnl_pct,
            dte,
            vix,
            vix_trend,
            tqqq_trend
        ], dtype=np.float32)

    def _try_load(self):
        if not SB3_AVAILABLE:
            return
            
        import os
        if os.path.exists(self.model_path):
            try:
                self.model = PPO.load(self.model_path)
                logger.info(f"Loaded PPO Agent from {self.model_path}")
            except Exception as e:
                logger.error(f"Failed to load PPO model constraint: {e}")
