"""
Reinforcement Learning Optimizer for Theta Strategy
===================================================
Uses Stable-Baselines3 PPO to learn optimal exit decisions per symbol.

The RL agent learns when to exit positions by observing:
- Current P&L
- Days held
- IV changes
- Delta movement
- Breach status

And choosing optimal exit timing to maximize returns.
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import date, timedelta
import logging

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    from stable_baselines3.common.callbacks import BaseCallback
except ImportError:
    print("Installing stable-baselines3...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "stable-baselines3[extra]"])
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    from stable_baselines3.common.callbacks import BaseCallback

logger = logging.getLogger(__name__)


@dataclass
class TradeSnapshot:
    """Single observation of a trade at a point in time."""
    dte: int
    days_held: int
    current_pnl_pct: float  # P&L as % of capital required
    iv_change_pct: float  # IV change from entry
    delta_change: float  # Delta change from entry
    breach_days: int  # Consecutive breach days
    vix_level: float
    week_number: int  # 1, 2, 3, or 4+
    symbol_id: int  # 0=SPY, 1=QQQ, 2=IWM
    
    # Exit occurred (for training only)
    exited: bool = False
    exit_action: int = 0  # 0=didn't exit, 1=profit, 2=defensive, 3=dte
    final_pnl_pct: float = 0.0


class ThetaTradeEnv(gym.Env):
    """
    OpenAI Gym environment for Theta strategy exit optimization.
    
    The agent observes trade state and decides whether to exit.
    Reward is based on final P&L and timing efficiency.
    """
    metadata = {'render.modes': ['human']}
    
    def __init__(self, trade_data: List[List[TradeSnapshot]], symbol: str = "QQQ"):
        """
        Initialize RL environment.
        
        Args:
            trade_data: List of trade sequences (each trade is list of snapshots)
            symbol: Symbol this model is for (SPY, QQQ, IWM)
        """
        super(ThetaTradeEnv, self).__init__()
        
        self.symbol = symbol
        self.trade_data = trade_data
        self.current_trade_idx = 0
        self.current_step = 0
        self.current_trade: List[TradeSnapshot] = []
        
        # State space: [dte, days_held, pnl_pct, iv_change, delta_change, 
        #                breach_days, vix, week, symbol_id]
        self.observation_space = spaces.Box(
            low=np.array([0, 0, -1.0, -1.0, -1.0, 0, 0, 1, 0], dtype=np.float32),
            high=np.array([35, 35, 2.0, 2.0, 1.0, 10, 100, 4, 2], dtype=np.float32),
            dtype=np.float32
        )
        
        # Action space: 0=HOLD, 1=EXIT
        self.action_space = spaces.Discrete(2)
        
        self.done = False
        self.total_reward = 0
    
    def reset(self, seed=None, options=None) -> Tuple[np.ndarray, dict]:
        """Start a new trade episode."""
        if seed is not None:
            np.random.seed(seed)
            
        # Pick random trade from dataset
        self.current_trade_idx = np.random.randint(0, len(self.trade_data))
        self.current_trade = self.trade_data[self.current_trade_idx]
        self.current_step = 0
        self.done = False
        self.total_reward = 0
        
        return self._get_observation(), {}
    
    def _get_observation(self) -> np.ndarray:
        """Get current state observation."""
        if self.current_step >= len(self.current_trade):
            # End of trade - return terminal state
            snapshot = self.current_trade[-1]
        else:
            snapshot = self.current_trade[self.current_step]
        
        return np.array([
            snapshot.dte,
            snapshot.days_held,
            snapshot.current_pnl_pct,
            snapshot.iv_change_pct,
            snapshot.delta_change,
            snapshot.breach_days,
            snapshot.vix_level,
            snapshot.week_number,
            snapshot.symbol_id
        ], dtype=np.float32)
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Execute one timestep.
        
        Args:
            action: 0=HOLD, 1=EXIT
            
        Returns:
            observation, reward, done, info
        """
        snapshot = self.current_trade[self.current_step]
        
        reward = 0
        info = {}
        
        if action == 1:  # EXIT
            # Agent chose to exit
            final_pnl = snapshot.current_pnl_pct
            
            # Reward is the P&L achieved
            reward = final_pnl
            
            # Bonus for exiting quickly with profit
            if final_pnl > 0:
                time_bonus = 0.1 * (1 - snapshot.days_held / 35)  # Earlier = better
                reward += time_bonus
            
            # Penalty for exiting at a loss when could have recovered
            if final_pnl < 0 and snapshot.dte > 7:
                reward -= 0.05  # Small penalty for premature defensive close
            
            self.done = True
            info['exit_type'] = 'agent_decision'
            info['final_pnl'] = final_pnl
            info['days_held'] = snapshot.days_held
            
        else:  # HOLD
            # Agent chose to hold
            self.current_step += 1
            
            # Small penalty for holding (encourages efficient exits)
            reward = -0.001
            
            # Check if trade naturally ended
            if self.current_step >= len(self.current_trade):
                # Trade expired - use actual final P&L
                final_snapshot = self.current_trade[-1]
                reward = final_snapshot.final_pnl_pct - 0.05  # Penalty for holding to expiration
                self.done = True
                info['exit_type'] = 'expiration'
                info['final_pnl'] = final_snapshot.final_pnl_pct
                info['days_held'] = final_snapshot.days_held
        
        obs = self._get_observation()
        self.total_reward += reward
        
        return obs, reward, self.done, info
    
    def render(self, mode='human'):
        """Render current state (for debugging)."""
        snapshot = self.current_trade[self.current_step]
        print(f"Day {snapshot.days_held}, DTE {snapshot.dte}, "
              f"P&L: {snapshot.current_pnl_pct:.2%}, "
              f"Breach: {snapshot.breach_days}")


class ThetaRLOptimizer:
    """
    Manages RL model training and inference for Theta exits.
    """
    
    def __init__(self, symbol: str = "QQQ"):
        self.symbol = symbol
        self.model: Optional[PPO] = None
        self.env: Optional[ThetaTradeEnv] = None
    
    def prepare_training_data(self, backtest_results: List) -> List[List[TradeSnapshot]]:
        """
        Convert backtest trade history into training sequences.
        
        Args:
            backtest_results: List of TrailingExitTrade objects
            
        Returns:
            List of trade snapshot sequences
        """
        trade_sequences = []
        
        symbol_id_map = {"SPY": 0, "QQQ": 1, "IWM": 2}
        symbol_id = symbol_id_map.get(self.symbol, 1)
        
        for trade in backtest_results:
            if trade.symbol != self.symbol:
                continue
            
            # Simulate daily progression of trade
            sequence = []
            
            for day in range(trade.hold_days + 1):
                dte = trade.dte_entry - day
                current_pnl_pct = (
                    (trade.premium_collected - trade.premium_paid) * 100 / 
                    (trade.strike * 100)
                )
                
                # Simulate progression (linear for now - could be more sophisticated)
                progress = day / max(trade.hold_days, 1)
                partial_pnl = current_pnl_pct * progress
                
                week = min((day // 7) + 1, 4)
                
                snapshot = TradeSnapshot(
                    dte=dte,
                    days_held=day,
                    current_pnl_pct=partial_pnl,
                    iv_change_pct=0.0,  # Would need historical IV data
                    delta_change=0.0,   # Would need historical delta
                    breach_days=trade.breach_days if day == trade.hold_days else 0,
                    vix_level=20.0,  # Would need historical VIX
                    week_number=week,
                    symbol_id=symbol_id,
                    exited=(day == trade.hold_days),
                    final_pnl_pct=current_pnl_pct
                )
                
                sequence.append(snapshot)
            
            trade_sequences.append(sequence)
        
        return trade_sequences
    
    def train(
        self, 
        training_data: List[List[TradeSnapshot]], 
        total_timesteps: int = 100000,
        model_save_path: str = "models/theta_rl_model"
    ):
        """
        Train PPO model on historical trade data.
        
        Args:
            training_data: Trade snapshot sequences
            total_timesteps: Training iterations
            model_save_path: Where to save trained model
        """
        logger.info(f"Training RL model for {self.symbol} on {len(training_data)} trades")
        
        # Create environment
        self.env = ThetaTradeEnv(training_data, symbol=self.symbol)
        vec_env = DummyVecEnv([lambda: self.env])
        
        # Create PPO model
        self.model = PPO(
            "MlpPolicy",
            vec_env,
            learning_rate=0.0003,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            verbose=1,
            tensorboard_log=f"./tensorboard/{self.symbol}/"
        )
        
        # Train
        logger.info(f"Starting training for {total_timesteps} timesteps...")
        self.model.learn(total_timesteps=total_timesteps)
        
        # Save model
        self.model.save(f"{model_save_path}_{self.symbol}")
        logger.info(f"Model saved to {model_save_path}_{self.symbol}")
    
    def load_model(self, model_path: str):
        """Load pre-trained model."""
        self.model = PPO.load(model_path)
        logger.info(f"Loaded model from {model_path}")
    
    def predict_exit(self, observation: np.ndarray) -> Tuple[int, float]:
        """
        Predict whether to exit trade.
        
        Args:
            observation: Current trade state [dte, days_held, pnl_pct, ...]
            
        Returns:
            (action, confidence) - action: 0=HOLD, 1=EXIT
        """
        if self.model is None:
            raise ValueError("Model not loaded. Call load_model() or train() first.")
        
        action, _states = self.model.predict(observation, deterministic=True)
        
        # Get action probabilities for confidence
        obs_tensor = observation.reshape(1, -1)
        try:
            action_probs = self.model.policy.get_distribution(obs_tensor).distribution.probs
            confidence = float(action_probs[0][action])
        except:
            confidence = 0.8  # Default if can't get probs
        
        return int(action), confidence
    
    def should_exit_trade(
        self,
        dte: int,
        days_held: int,
        current_pnl_pct: float,
        iv_change_pct: float = 0.0,
        delta_change: float = 0.0,
        breach_days: int = 0,
        vix_level: float = 20.0
    ) -> Tuple[bool, float]:
        """
        High-level API: Should we exit this trade?
        
        Returns:
            (should_exit, confidence)
        """
        week = min((days_held // 7) + 1, 4)
        symbol_id_map = {"SPY": 0, "QQQ": 1, "IWM": 2}
        symbol_id = symbol_id_map.get(self.symbol, 1)
        
        observation = np.array([
            dte, days_held, current_pnl_pct, iv_change_pct, delta_change,
            breach_days, vix_level, week, symbol_id
        ], dtype=np.float32)
        
        action, confidence = self.predict_exit(observation)
        
        return (action == 1), confidence


# =============================================================================
# TRAINING UTILITIES
# =============================================================================

def train_all_symbols(backtest_results: List, output_dir: str = "models"):
    """
    Train RL models for all symbols (SPY, QQQ, IWM).
    
    Args:
        backtest_results: Historical trades from backtest
        output_dir: Where to save models
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    for symbol in ["SPY", "QQQ", "IWM"]:
        logger.info(f"\n{'='*80}")
        logger.info(f"Training model for {symbol}")
        logger.info(f"{'='*80}\n")
        
        optimizer = ThetaRLOptimizer(symbol=symbol)
        
        # Filter trades for this symbol
        symbol_trades = [t for t in backtest_results if t.symbol == symbol]
        
        if len(symbol_trades) < 20:
            logger.warning(f"Not enough trades for {symbol} ({len(symbol_trades)}), skipping")
            continue
        
        # Prepare training data
        training_data = optimizer.prepare_training_data(symbol_trades)
        
        # Train model
        optimizer.train(
            training_data, 
            total_timesteps=50000,  # Adjust based on data size
            model_save_path=f"{output_dir}/theta_rl"
        )
        
        logger.info(f"✅ {symbol} model training complete\n")


if __name__ == "__main__":
    # Example: Load backtest results and train
    print("Theta RL Optimizer - Training Module")
    print("=" * 80)
    print("\nTo train models, run:")
    print("  from backtest_trailing_exits import run_risk_comparison_backtest")
    print("  results = run_risk_comparison_backtest()")
    print("  from src.theta_spreads.rl_optimizer import train_all_symbols")
    print("  train_all_symbols(results['MEDIUM'])")  # Use MEDIUM risk trades
