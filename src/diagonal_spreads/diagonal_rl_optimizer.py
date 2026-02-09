"""
Diagonal Spread RL Optimizer: ML-based Roll Timing

Adapts the existing ThetaRLOptimizer for diagonal spreads with:
1. Extended feature set (term structure, roll timing signals)
2. Three-action space (HOLD, EXIT, ROLL)
3. Roll-aware reward function
4. Walk-forward training support

Based on consolidated implementation plan evaluation:
- PPO from Stable-Baselines3
- Walk-forward training to prevent overfitting
- Rule-based baseline for comparison
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
import logging
import json
import os

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    from stable_baselines3.common.callbacks import BaseCallback, EvalCallback
except ImportError:
    print("Installing stable-baselines3...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "stable-baselines3[extra]"])
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    from stable_baselines3.common.callbacks import BaseCallback, EvalCallback

logger = logging.getLogger(__name__)


class DiagonalAction(Enum):
    """Actions for diagonal spread management"""
    HOLD = 0       # Continue holding current position
    EXIT = 1       # Close entire position
    ROLL = 2       # Roll short leg to next expiration


@dataclass
class DiagonalTradeSnapshot:
    """
    Single observation of a diagonal spread at a point in time.
    
    Extended from ThetaTradeSnapshot with diagonal-specific features.
    """
    # Time features
    short_dte: int        # DTE of short leg
    long_dte: int         # DTE of long leg
    days_held: int        # Days since entry
    
    # P&L features
    current_pnl_pct: float      # Current P&L as % of max profit
    short_leg_pnl_pct: float    # P&L from short leg
    long_leg_pnl_pct: float     # P&L from long leg
    
    # Volatility features
    iv_rank: float              # Current IV rank (0-100)
    iv_change_pct: float        # IV change from entry
    term_structure_diff: float  # VIX - VXV (negative = contango)
    iv_skew: float              # Short IV - Long IV
    
    # Greeks
    position_delta: float       # Net delta of position
    theta_per_day: float        # Daily theta decay
    vega_exposure: float        # Vega of position
    
    # Risk features
    breach_days: int            # Consecutive days short strike breached
    vix_level: float            # Current VIX
    underlying_move_pct: float  # Underlying move since entry
    
    # Symbol encoding
    symbol_id: int              # 0=SPY, 1=QQQ, 2=IWM, etc.
    
    # Roll opportunity signals
    short_theta_decay_pct: float   # % of max theta captured
    roll_credit_estimate: float    # Estimated credit from rolling
    days_since_last_roll: int      # Days since last roll (0 if never)
    
    # Training labels (only for training data)
    action_taken: DiagonalAction = DiagonalAction.HOLD
    final_pnl_pct: float = 0.0
    was_profitable: bool = False


@dataclass
class DiagonalRollEvent:
    """Record of a roll event for analysis"""
    roll_date: date
    old_short_expiry: date
    new_short_expiry: date
    roll_credit: float
    underlying_price: float
    iv_at_roll: float
    term_structure_at_roll: float


class DiagonalTradeEnv(gym.Env):
    """
    OpenAI Gym environment for diagonal spread management.
    
    Three actions:
    - HOLD: Continue current position
    - EXIT: Close entire position
    - ROLL: Roll the short leg forward
    
    Reward function considers:
    - Final P&L
    - Time efficiency
    - Roll timing quality
    """
    metadata = {'render_modes': ['human']}
    
    # Feature indices for observation space
    FEATURE_NAMES = [
        'short_dte', 'long_dte', 'days_held',
        'current_pnl_pct', 'short_leg_pnl_pct', 'long_leg_pnl_pct',
        'iv_rank', 'iv_change_pct', 'term_structure_diff', 'iv_skew',
        'position_delta', 'theta_per_day', 'vega_exposure',
        'breach_days', 'vix_level', 'underlying_move_pct',
        'symbol_id',
        'short_theta_decay_pct', 'roll_credit_estimate', 'days_since_last_roll'
    ]
    NUM_FEATURES = 20
    
    def __init__(
        self,
        trade_data: List[List[DiagonalTradeSnapshot]],
        symbol: str = "SPY",
        max_rolls: int = 3
    ):
        """
        Initialize RL environment.
        
        Args:
            trade_data: List of trade sequences (each trade is list of snapshots)
            symbol: Symbol this model is for
            max_rolls: Maximum number of rolls allowed per trade
        """
        super().__init__()
        
        self.symbol = symbol
        self.trade_data = trade_data
        self.max_rolls = max_rolls
        
        self.current_trade_idx = 0
        self.current_step = 0
        self.current_trade: List[DiagonalTradeSnapshot] = []
        self.rolls_used = 0
        
        # Observation space: 20 features
        self.observation_space = spaces.Box(
            low=np.array([
                0, 0, 0,            # DTE, long DTE, days held
                -2.0, -2.0, -2.0,   # P&L percentages
                0, -1.0, -5.0, -0.5,  # IV features
                -1.0, -0.5, -1.0,   # Greeks
                0, 0, -0.5,         # Risk features
                0,                   # Symbol id
                0, -1.0, 0          # Roll features
            ], dtype=np.float32),
            high=np.array([
                45, 180, 180,       # DTE limits
                3.0, 3.0, 3.0,      # P&L limits
                100, 2.0, 5.0, 0.5, # IV limits
                1.0, 0.5, 1.0,      # Greeks limits
                30, 100, 0.5,       # Risk limits
                10,                  # Symbol ids
                1.0, 2.0, 90        # Roll limits
            ], dtype=np.float32),
            dtype=np.float32
        )
        
        # Action space: HOLD, EXIT, ROLL
        self.action_space = spaces.Discrete(3)
        
        self.done = False
        self.total_reward = 0
        self.cumulative_pnl = 0
    
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
        self.cumulative_pnl = 0
        self.rolls_used = 0
        
        return self._get_observation(), {}
    
    def _get_observation(self) -> np.ndarray:
        """Get current state observation."""
        if self.current_step >= len(self.current_trade):
            snapshot = self.current_trade[-1]
        else:
            snapshot = self.current_trade[self.current_step]
        
        return np.array([
            snapshot.short_dte,
            snapshot.long_dte,
            snapshot.days_held,
            snapshot.current_pnl_pct,
            snapshot.short_leg_pnl_pct,
            snapshot.long_leg_pnl_pct,
            snapshot.iv_rank,
            snapshot.iv_change_pct,
            snapshot.term_structure_diff,
            snapshot.iv_skew,
            snapshot.position_delta,
            snapshot.theta_per_day,
            snapshot.vega_exposure,
            snapshot.breach_days,
            snapshot.vix_level,
            snapshot.underlying_move_pct,
            snapshot.symbol_id,
            snapshot.short_theta_decay_pct,
            snapshot.roll_credit_estimate,
            snapshot.days_since_last_roll
        ], dtype=np.float32)
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        Execute one timestep.
        
        Args:
            action: 0=HOLD, 1=EXIT, 2=ROLL
            
        Returns:
            observation, reward, terminated, truncated, info
        """
        snapshot = self.current_trade[self.current_step]
        reward = 0
        info = {}
        truncated = False
        
        if action == DiagonalAction.EXIT.value:
            # Agent chose to exit
            final_pnl = snapshot.current_pnl_pct + self.cumulative_pnl
            reward = self._calculate_exit_reward(snapshot, final_pnl)
            self.done = True
            info['action'] = 'exit'
            info['final_pnl'] = final_pnl
            info['days_held'] = snapshot.days_held
            info['rolls_used'] = self.rolls_used
            
        elif action == DiagonalAction.ROLL.value:
            # Agent chose to roll
            if self.rolls_used >= self.max_rolls:
                # Can't roll anymore - treat as hold with penalty
                reward = -0.05
                info['action'] = 'roll_denied'
                self.current_step += 1
            else:
                roll_reward = self._calculate_roll_reward(snapshot)
                reward = roll_reward
                self.rolls_used += 1
                self.cumulative_pnl += snapshot.roll_credit_estimate
                info['action'] = 'roll'
                info['roll_credit'] = snapshot.roll_credit_estimate
                self.current_step += 1
            
        else:  # HOLD
            # Agent chose to hold
            self.current_step += 1
            reward = -0.001  # Small penalty to encourage action
            info['action'] = 'hold'
        
        # Check if trade naturally ended
        if self.current_step >= len(self.current_trade):
            final_snapshot = self.current_trade[-1]
            final_pnl = final_snapshot.current_pnl_pct + self.cumulative_pnl
            reward = final_pnl - 0.05  # Penalty for holding to expiration
            self.done = True
            info['action'] = 'expiration'
            info['final_pnl'] = final_pnl
        
        obs = self._get_observation()
        self.total_reward += reward
        
        return obs, reward, self.done, truncated, info
    
    def _calculate_exit_reward(self, snapshot: DiagonalTradeSnapshot, final_pnl: float) -> float:
        """Calculate reward for exiting."""
        reward = final_pnl
        
        # Bonus for exiting quickly with profit
        if final_pnl > 0:
            time_efficiency = 1 - (snapshot.days_held / 60)  # Assume 60 day max
            reward += 0.1 * max(0, time_efficiency)
        
        # Penalty for exiting at a loss when could have recovered
        if final_pnl < 0 and snapshot.short_dte > 14:
            reward -= 0.05
        
        # Bonus for exiting in favorable term structure
        if snapshot.term_structure_diff < -0.5:  # Contango
            reward += 0.02
        
        return reward
    
    def _calculate_roll_reward(self, snapshot: DiagonalTradeSnapshot) -> float:
        """Calculate reward for rolling."""
        reward = 0
        
        # Base reward is the roll credit
        reward += snapshot.roll_credit_estimate
        
        # Bonus for rolling when theta is mostly captured
        if snapshot.short_theta_decay_pct > 0.6:
            reward += 0.05
        
        # Penalty for rolling too early
        if snapshot.short_theta_decay_pct < 0.3:
            reward -= 0.05
        
        # Bonus for rolling in contango (favorable term structure)
        if snapshot.term_structure_diff < -0.5:
            reward += 0.03
        
        # Penalty for rolling in backwardation
        if snapshot.term_structure_diff > 0.5:
            reward -= 0.05
        
        return reward
    
    def render(self, mode='human'):
        """Render current state."""
        snapshot = self.current_trade[min(self.current_step, len(self.current_trade)-1)]
        print(f"Day {snapshot.days_held}, Short DTE {snapshot.short_dte}, "
              f"P&L: {snapshot.current_pnl_pct:.2%}, "
              f"Term: {snapshot.term_structure_diff:.2f}, "
              f"Rolls: {self.rolls_used}")


class RuleBasedRollDecider:
    """
    Rule-based baseline for roll timing decisions.
    
    Used as comparison baseline and fallback when RL model unavailable.
    
    Rules:
    1. Roll when short leg has captured 60%+ of theta decay
    2. Roll when short DTE < 7 (regardless of theta)
    3. Don't roll if term structure is in backwardation
    4. Exit if position delta exceeds thresholds
    """
    
    def __init__(
        self,
        theta_capture_threshold: float = 0.60,
        min_dte_to_roll: int = 7,
        max_delta_abs: float = 0.35,
        term_structure_halt_threshold: float = 0.5
    ):
        self.theta_capture_threshold = theta_capture_threshold
        self.min_dte_to_roll = min_dte_to_roll
        self.max_delta_abs = max_delta_abs
        self.term_structure_halt_threshold = term_structure_halt_threshold
    
    def decide(self, snapshot: DiagonalTradeSnapshot) -> Tuple[DiagonalAction, str]:
        """
        Make rule-based decision.
        
        Returns:
            (action, reason)
        """
        # Check for exit conditions first
        if abs(snapshot.position_delta) > self.max_delta_abs:
            return DiagonalAction.EXIT, f"Delta breach: {snapshot.position_delta:.2f}"
        
        if snapshot.breach_days >= 5:
            return DiagonalAction.EXIT, f"Strike breach for {snapshot.breach_days} days"
        
        if snapshot.current_pnl_pct >= 0.50:  # 50% of max profit
            return DiagonalAction.EXIT, f"Profit target reached: {snapshot.current_pnl_pct:.1%}"
        
        # Check for roll conditions
        if snapshot.term_structure_diff > self.term_structure_halt_threshold:
            return DiagonalAction.HOLD, "Backwardation - no roll"
        
        if snapshot.short_dte <= self.min_dte_to_roll:
            return DiagonalAction.ROLL, f"Short DTE ({snapshot.short_dte}) below threshold"
        
        if snapshot.short_theta_decay_pct >= self.theta_capture_threshold:
            return DiagonalAction.ROLL, f"Theta captured: {snapshot.short_theta_decay_pct:.1%}"
        
        # Default: hold
        return DiagonalAction.HOLD, "Continue monitoring"


class DiagonalRLOptimizer:
    """
    Manages RL model training and inference for diagonal spread roll timing.
    
    Extends ThetaRLOptimizer with:
    - Three-action space (HOLD/EXIT/ROLL)
    - Term structure awareness
    - Roll timing optimization
    - Walk-forward training
    """
    
    def __init__(self, symbol: str = "SPY"):
        self.symbol = symbol
        self.model: Optional[PPO] = None
        self.env: Optional[DiagonalTradeEnv] = None
        self.rule_based = RuleBasedRollDecider()
        
        # Symbol ID mapping
        self.symbol_id_map = {
            "SPY": 0, "QQQ": 1, "IWM": 2,
            "TLT": 3, "GLD": 4, "SLV": 5,
            "XLK": 6, "XLF": 7, "XLV": 8,
            "XLE": 9
        }
    
    def get_symbol_id(self, symbol: str) -> int:
        """Get numeric ID for a symbol."""
        return self.symbol_id_map.get(symbol.upper(), 0)
    
    def prepare_training_data(
        self,
        backtest_results: List[Dict[str, Any]],
        term_structure_data: Optional[Dict[date, float]] = None
    ) -> List[List[DiagonalTradeSnapshot]]:
        """
        Convert backtest trade history into training sequences.
        
        Args:
            backtest_results: List of diagonal trade dictionaries
            term_structure_data: Optional dict of date -> VIX-VXV diff
            
        Returns:
            List of trade snapshot sequences
        """
        trade_sequences = []
        symbol_id = self.get_symbol_id(self.symbol)
        
        for trade in backtest_results:
            if trade.get("symbol") != self.symbol:
                continue
            
            sequence = []
            hold_days = trade.get("hold_days", 30)
            
            for day in range(hold_days + 1):
                # Calculate time-based features
                short_dte = trade.get("short_dte_entry", 30) - day
                long_dte = trade.get("long_dte_entry", 60) - day
                
                # Simulate P&L progression
                progress = day / max(hold_days, 1)
                max_pnl = trade.get("max_pnl_pct", 0.5)
                current_pnl = max_pnl * progress * (1 + 0.1 * np.random.randn())
                
                # Get term structure if available
                trade_date = trade.get("entry_date", date.today())
                if isinstance(trade_date, str):
                    from datetime import datetime
                    trade_date = datetime.strptime(trade_date, "%Y-%m-%d").date()
                current_date = trade_date + timedelta(days=day)
                term_diff = 0.0
                if term_structure_data:
                    term_diff = term_structure_data.get(current_date, 0.0)
                
                snapshot = DiagonalTradeSnapshot(
                    short_dte=max(0, short_dte),
                    long_dte=max(0, long_dte),
                    days_held=day,
                    current_pnl_pct=current_pnl,
                    short_leg_pnl_pct=current_pnl * 0.7,
                    long_leg_pnl_pct=current_pnl * 0.3,
                    iv_rank=trade.get("iv_rank", 50),
                    iv_change_pct=0.0,
                    term_structure_diff=term_diff,
                    iv_skew=trade.get("iv_skew", 0.0),
                    position_delta=trade.get("entry_delta", 0.0),
                    theta_per_day=trade.get("theta", 0.02),
                    vega_exposure=trade.get("vega", 0.1),
                    breach_days=0,
                    vix_level=trade.get("vix", 20),
                    underlying_move_pct=0.0,
                    symbol_id=symbol_id,
                    short_theta_decay_pct=min(1.0, progress * 1.2),
                    roll_credit_estimate=trade.get("roll_credit", 0.05),
                    days_since_last_roll=day
                )
                
                sequence.append(snapshot)
            
            if sequence:
                trade_sequences.append(sequence)
        
        return trade_sequences
    
    def train(
        self,
        training_data: List[List[DiagonalTradeSnapshot]],
        validation_data: Optional[List[List[DiagonalTradeSnapshot]]] = None,
        total_timesteps: int = 100000,
        model_save_path: str = "models/diagonal_rl_model"
    ):
        """
        Train PPO model on historical trade data.
        
        Args:
            training_data: Trade snapshot sequences
            validation_data: Optional validation set for early stopping
            total_timesteps: Training iterations
            model_save_path: Where to save trained model
        """
        logger.info(f"Training Diagonal RL model for {self.symbol} on {len(training_data)} trades")
        
        if len(training_data) < 50:
            logger.warning(f"Only {len(training_data)} trades - may overfit")
        
        # Create environment
        self.env = DiagonalTradeEnv(training_data, symbol=self.symbol)
        vec_env = DummyVecEnv([lambda: self.env])
        
        # Callbacks
        callbacks = []
        if validation_data:
            val_env = DiagonalTradeEnv(validation_data, symbol=self.symbol)
            val_vec_env = DummyVecEnv([lambda: val_env])
            callbacks.append(EvalCallback(
                val_vec_env,
                best_model_save_path=f"{model_save_path}_best/",
                eval_freq=5000,
                deterministic=True,
                render=False
            ))
        
        # Create PPO model with conservative hyperparameters
        self.model = PPO(
            "MlpPolicy",
            vec_env,
            learning_rate=0.0001,  # Lower LR for stability
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            ent_coef=0.01,  # Encourage exploration
            verbose=1,
            tensorboard_log=f"./tensorboard/diagonal_{self.symbol}/"
        )
        
        # Train
        logger.info(f"Starting training for {total_timesteps} timesteps...")
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=callbacks if callbacks else None
        )
        
        # Save model
        os.makedirs(os.path.dirname(model_save_path) or ".", exist_ok=True)
        self.model.save(f"{model_save_path}_{self.symbol}")
        logger.info(f"Model saved to {model_save_path}_{self.symbol}")
    
    def load_model(self, model_path: str):
        """Load pre-trained model."""
        self.model = PPO.load(model_path)
        logger.info(f"Loaded model from {model_path}")
    
    def predict_action(self, observation: np.ndarray) -> Tuple[DiagonalAction, float]:
        """
        Predict action for current state.
        
        Args:
            observation: Current trade state (20 features)
            
        Returns:
            (action, confidence)
        """
        if self.model is None:
            raise ValueError("Model not loaded. Call load_model() or train() first.")
        
        action, _states = self.model.predict(observation, deterministic=True)
        
        # Get action probabilities for confidence
        try:
            obs_tensor = observation.reshape(1, -1)
            action_probs = self.model.policy.get_distribution(
                self.model.policy.obs_to_tensor(obs_tensor)[0]
            ).distribution.probs.detach().numpy()
            confidence = float(action_probs[0][action])
        except:
            confidence = 0.8
        
        return DiagonalAction(int(action)), confidence
    
    def should_roll_or_exit(
        self,
        short_dte: int,
        long_dte: int,
        days_held: int,
        current_pnl_pct: float,
        iv_rank: float = 50.0,
        term_structure_diff: float = -0.5,
        position_delta: float = 0.0,
        short_theta_decay_pct: float = 0.5,
        roll_credit_estimate: float = 0.05,
        use_rule_based_fallback: bool = True
    ) -> Tuple[DiagonalAction, float, str]:
        """
        High-level API: Should we hold, roll, or exit this diagonal?
        
        Returns:
            (action, confidence, reason)
        """
        symbol_id = self.get_symbol_id(self.symbol)
        
        observation = np.array([
            short_dte, long_dte, days_held,
            current_pnl_pct, current_pnl_pct * 0.7, current_pnl_pct * 0.3,
            iv_rank, 0.0, term_structure_diff, 0.0,
            position_delta, 0.02, 0.1,
            0, 20.0, 0.0,
            symbol_id,
            short_theta_decay_pct, roll_credit_estimate, days_held
        ], dtype=np.float32)
        
        # Create snapshot for rule-based
        snapshot = DiagonalTradeSnapshot(
            short_dte=short_dte,
            long_dte=long_dte,
            days_held=days_held,
            current_pnl_pct=current_pnl_pct,
            short_leg_pnl_pct=current_pnl_pct * 0.7,
            long_leg_pnl_pct=current_pnl_pct * 0.3,
            iv_rank=iv_rank,
            iv_change_pct=0.0,
            term_structure_diff=term_structure_diff,
            iv_skew=0.0,
            position_delta=position_delta,
            theta_per_day=0.02,
            vega_exposure=0.1,
            breach_days=0,
            vix_level=20.0,
            underlying_move_pct=0.0,
            symbol_id=symbol_id,
            short_theta_decay_pct=short_theta_decay_pct,
            roll_credit_estimate=roll_credit_estimate,
            days_since_last_roll=days_held
        )
        
        if self.model is not None:
            try:
                action, confidence = self.predict_action(observation)
                return action, confidence, "RL model prediction"
            except Exception as e:
                logger.warning(f"RL prediction failed: {e}, using rule-based fallback")
        
        if use_rule_based_fallback:
            action, reason = self.rule_based.decide(snapshot)
            return action, 0.7, f"Rule-based: {reason}"
        
        return DiagonalAction.HOLD, 0.5, "Default: hold"


# =============================================================================
# WALK-FORWARD TRAINING
# =============================================================================

def walk_forward_train(
    all_trades: List[Dict[str, Any]],
    symbol: str = "SPY",
    window_size_days: int = 365,
    step_size_days: int = 90,
    output_dir: str = "models/diagonal_wf"
) -> List[str]:
    """
    Walk-forward training to prevent look-ahead bias.
    
    Trains multiple models on rolling windows and saves each.
    
    Args:
        all_trades: All historical trades with entry dates
        symbol: Symbol to train for
        window_size_days: Training window size
        step_size_days: Step between windows
        output_dir: Output directory
        
    Returns:
        List of model paths
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Sort trades by date
    trades = sorted(
        [t for t in all_trades if t.get("symbol") == symbol],
        key=lambda x: x.get("entry_date", "2020-01-01")
    )
    
    if len(trades) < 50:
        logger.warning(f"Only {len(trades)} trades for {symbol}, insufficient for walk-forward")
        return []
    
    model_paths = []
    optimizer = DiagonalRLOptimizer(symbol=symbol)
    
    # Determine date range
    from datetime import datetime
    start_date = datetime.strptime(trades[0].get("entry_date", "2020-01-01"), "%Y-%m-%d").date()
    end_date = datetime.strptime(trades[-1].get("entry_date", "2024-01-01"), "%Y-%m-%d").date()
    
    current_start = start_date
    window_num = 0
    
    while current_start + timedelta(days=window_size_days) < end_date:
        window_end = current_start + timedelta(days=window_size_days)
        
        # Filter trades for this window
        window_trades = [
            t for t in trades
            if current_start <= datetime.strptime(t.get("entry_date", "2020-01-01"), "%Y-%m-%d").date() < window_end
        ]
        
        if len(window_trades) >= 20:
            logger.info(f"Training window {window_num}: {current_start} to {window_end}, {len(window_trades)} trades")
            
            training_data = optimizer.prepare_training_data(window_trades)
            
            model_path = f"{output_dir}/diagonal_wf_{symbol}_{window_num}"
            optimizer.train(
                training_data,
                total_timesteps=30000,  # Smaller per window
                model_save_path=model_path
            )
            model_paths.append(f"{model_path}_{symbol}")
        
        current_start += timedelta(days=step_size_days)
        window_num += 1
    
    # Save metadata
    metadata = {
        "symbol": symbol,
        "window_size_days": window_size_days,
        "step_size_days": step_size_days,
        "num_windows": window_num,
        "model_paths": model_paths
    }
    with open(f"{output_dir}/metadata_{symbol}.json", "w") as f:
        json.dump(metadata, f, indent=2)
    
    return model_paths


if __name__ == "__main__":
    print("Diagonal Spread RL Optimizer - Roll Timing")
    print("=" * 80)
    print("\nTo train models, use:")
    print("  from src.diagonal_spreads.diagonal_rl_optimizer import DiagonalRLOptimizer")
    print("  optimizer = DiagonalRLOptimizer(symbol='SPY')")
    print("  training_data = optimizer.prepare_training_data(backtest_results)")
    print("  optimizer.train(training_data)")
    print("\nTo use trained model:")
    print("  optimizer.load_model('models/diagonal_rl_model_SPY')")
    print("  action, confidence, reason = optimizer.should_roll_or_exit(...)")
