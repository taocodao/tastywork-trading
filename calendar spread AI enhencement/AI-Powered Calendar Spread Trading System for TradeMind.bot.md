# COMPREHENSIVE IMPLEMENTATION PLAN
## AI-Powered Calendar Spread Trading System for TradeMind.bot

**Prepared For:** Antigravity Development Team  
**Project Owner:** Eric Huang, CEO OmniAgentHub.AI / TradeMind.bot  
**Date:** February 3, 2026  
**Status:** Ready for Development Sprint  
**Estimated Timeline:** 8-10 weeks to production MVP  
**Total Effort:** ~400-500 engineering hours

---

## EXECUTIVE SUMMARY

This document provides a complete, production-ready implementation plan for building an AI-powered calendar spread trading system that integrates with Interactive Brokers. The system will leverage machine learning to optimize entry timing, strike selection, position management, and earnings-aware risk management.

**Business Objective:**
Transform TradeMind.bot from a directional options trader into a sophisticated volatility arbitrage platform capable of generating stable monthly income (15-25% ROI) through systematic calendar spread execution.

**Key Innovation:**
- AI-driven volatility surface prediction using LSTM networks
- Reinforcement learning for strike selection and position adjustment
- Earnings intelligence to avoid IV crush catastrophes
- Automated liquidity filtering for optimal execution
- Dynamic risk management with earnings-aware stop calculations

**Expected Performance Targets:**
- Win rate: 80-87% (vs 75% baseline)
- Monthly ROI: 15-25% on deployed capital
- Sharpe ratio: >1.8x
- Maximum drawdown: <15%
- Catastrophic loss events: <1 per quarter

**Total Investment:**
- Development: 8-10 weeks, ~400-500 hours
- API costs: $500/month ongoing
- Infrastructure: $300/month (AWS/GCP)
- ROI: Break-even at 100 active users within 3-4 months

---

## PART 1: SYSTEM ARCHITECTURE OVERVIEW

### 1.1 High-Level System Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                      MARKET DATA SOURCES                            │
│  ┌───────────────┬──────────────┬─────────────┬──────────────────┐  │
│  │ IB Gateway    │ Alpha Vantage│ Yahoo       │ Polygon.io       │  │
│  │ Real-time     │ Earnings API │ Finance     │ Historical Data  │  │
│  │ Ticks & Greeks│ (Daily sync) │ (Real-time) │ (Backtesting)    │  │
│  └───────────────┴──────────────┴─────────────┴──────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
        │                              │                    │
        ↓ Real-time options data      ↓ Earnings calendar  ↓ Historical
        │                              │                    │
┌───────────────────────────────────────────────────────────────────────┐
│                   AI/ML INTELLIGENCE LAYER                            │
├───────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┬──────────────────┬─────────────────────────┐    │
│  │ LSTM Volatility │ RL Strike        │ Random Forest           │    │
│  │ Surface         │ Selection Agent  │ IV Crush Predictor      │    │
│  │ Forecaster      │                  │                         │    │
│  │                 │                  │                         │    │
│  │ Predicts IV     │ Optimizes strike │ Predicts post-earnings  │    │
│  │ term structure  │ placement using  │ IV collapse (82%+ acc)  │    │
│  │ changes         │ PPO algorithm    │                         │    │
│  └─────────────────┴──────────────────┴─────────────────────────┘    │
└───────────────────────────────────────────────────────────────────────┘
        │                              │                    │
        ↓ ML predictions              ↓ Optimal strikes   ↓ Earnings risk
        │                              │                    │
┌───────────────────────────────────────────────────────────────────────┐
│                   TRADING STRATEGY ENGINE                             │
├───────────────────────────────────────────────────────────────────────┤
│  • Option Selection Algorithm (VOSS: Volume, Open Interest, Spread)   │
│  • DTE Selection (30-45 DTE optimal, IV-adjusted)                    │
│  • Strike Selection (0.50-0.60 delta for calendars)                  │
│  • Earnings Strategy Router (avoid/reverse/reduce)                   │
│  • Position Sizing (Kelly Criterion with ML confidence)              │
│  • Greeks Management (delta-neutral, vega-long bias)                 │
└───────────────────────────────────────────────────────────────────────┘
        │
        ↓ Validated trade signals
        │
┌───────────────────────────────────────────────────────────────────────┐
│              EXECUTION & RISK MANAGEMENT                              │
├───────────────────────────────────────────────────────────────────────┤
│  • IB API Integration (ib_async library)                             │
│  • Multi-leg order execution (atomic calendar spreads)               │
│  • Smart limit pricing (bid-ask spread optimization)                 │
│  • Real-time Greeks monitoring (delta, gamma, theta, vega)           │
│  • Dynamic stop-loss (k × Beta × VIX × Earnings_Factor)              │
│  • Position adjustment triggers (RL-based)                           │
│  • P&L tracking and performance analytics                            │
└───────────────────────────────────────────────────────────────────────┘
        │
        ↓ Order execution
        │
┌───────────────────────────────────────────────────────────────────────┐
│                   INTERACTIVE BROKERS                                 │
│  • TWS Gateway / IB Gateway                                          │
│  • Real-time market data subscriptions                               │
│  • Order routing and execution                                       │
│  • Account management and margin                                     │
└───────────────────────────────────────────────────────────────────────┘
```

### 1.2 Technology Stack

**Backend (Python 3.10+):**
```python
# Core Trading
ib_async>=0.9.86          # IB API integration
pandas>=2.0.0             # Data manipulation
numpy>=1.24.0             # Numerical computing
ta-lib>=0.4.26            # Technical indicators

# Machine Learning
scikit-learn>=1.3.0       # Random Forest, feature engineering
xgboost>=1.7.6            # Gradient boosting
tensorflow>=2.13.0        # LSTM, deep learning
stable-baselines3>=2.1.0  # Reinforcement learning (PPO)
gymnasium>=0.29.0         # RL environment

# Data & APIs
psycopg2-binary>=2.9.7    # PostgreSQL
redis>=5.0.0              # Caching, signal passing
alpha_vantage>=2.3.1      # Earnings calendar
yfinance>=0.2.28          # Yahoo Finance
requests>=2.31.0          # HTTP client

# Infrastructure
fastapi>=0.103.0          # API server
uvicorn>=0.23.0           # ASGI server
celery>=5.3.1             # Task queue
docker>=6.1.3             # Containerization

# Testing
pytest>=7.4.0             # Unit testing
pytest-cov>=4.1.0         # Coverage
pytest-asyncio>=0.21.0    # Async testing
hypothesis>=6.82.0        # Property-based testing
```

**Database:**
- **PostgreSQL 15+** for structured data (trades, positions, earnings)
- **Redis 7+** for real-time signals and caching
- **TimescaleDB** extension for time-series market data

**Infrastructure:**
- **AWS EC2** t3.large (2 vCPU, 8GB RAM) for production
- **AWS RDS** PostgreSQL (db.t3.medium)
- **AWS ElastiCache** Redis
- **Docker** + **Docker Compose** for deployment
- **GitHub Actions** for CI/CD

**Monitoring:**
- **Prometheus** for metrics
- **Grafana** for dashboards
- **Sentry** for error tracking
- **PagerDuty** for alerts

---

## PART 2: DETAILED COMPONENT SPECIFICATIONS

### 2.1 Options Selection System (Foundation Layer)

**File:** `src/options_selection/voss_filter.py`

**Purpose:** Solve the liquidity problem that kills most automated options systems.

**VOSS Framework (Volume, Open Interest, Spread, Strike):**

```python
class VOSSLiquidityFilter:
    """
    Volume + Open Interest + Spread + Strike filtering
    Based on deep research: Options-Selection-Best-Practices-Deep-Research.md
    """
    
    def __init__(self):
        self.criteria = {
            'min_open_interest': 1000,      # Minimum 1,000 contracts
            'preferred_open_interest': 5000, # Prefer 5,000+
            'min_volume': 500,               # Minimum 500 daily volume
            'preferred_volume': 2000,        # Prefer 2,000+
            'max_bid_ask_pct': 0.10,        # 10% max spread
            'preferred_bid_ask_pct': 0.05,  # Prefer 5% spread
            'min_bid_ask_size': 10,          # 10 contracts at bid/ask
            'preferred_bid_ask_size': 50     # Prefer 50+
        }
    
    def filter_options_chain(self, chain: pd.DataFrame) -> pd.DataFrame:
        """
        Apply VOSS filtering to options chain
        Priority: Liquidity FIRST, then expiration, then strike
        
        Returns only options that pass liquidity requirements
        """
        # Step 1: CRITICAL liquidity filters (must pass)
        chain = chain[chain['openInterest'] >= self.criteria['min_open_interest']]
        chain = chain[chain['volume'] >= self.criteria['min_volume']]
        
        # Calculate bid-ask spread percentage
        chain['spread_pct'] = (chain['ask'] - chain['bid']) / chain['ask']
        chain = chain[chain['spread_pct'] <= self.criteria['max_bid_ask_pct']]
        
        # Step 2: Quality scoring (prefer better liquidity)
        chain['liquidity_score'] = (
            (chain['openInterest'] / self.criteria['preferred_open_interest']) * 0.4 +
            (chain['volume'] / self.criteria['preferred_volume']) * 0.3 +
            (1 - chain['spread_pct'] / self.criteria['max_bid_ask_pct']) * 0.3
        )
        
        return chain.sort_values('liquidity_score', ascending=False)
```

**DTE Selection Algorithm:**

```python
class DTESelector:
    """
    Days-to-Expiration selection with IV adjustment
    Based on research: 30-45 DTE optimal, adjusted for volatility regime
    """
    
    def select_optimal_dte(self, 
                          symbol: str,
                          iv_rank: float,
                          strategy: str = 'calendar') -> tuple[int, int]:
        """
        Returns (short_dte, long_dte) based on IV conditions
        
        For calendar spreads:
        - Short leg: 7-14 DTE (captures rapid theta decay)
        - Long leg: 30-45 DTE (preserves value, provides hedge)
        
        IV Adjustment:
        - High IV (>70%): Shorter DTE (faster moves, exit quicker)
        - Normal IV (30-70%): Standard 30-45 DTE
        - Low IV (<30%): Longer DTE (need time for signal)
        """
        if iv_rank > 70:
            # High volatility: use shorter timeframes
            short_dte = 7
            long_dte = 30
        elif iv_rank > 30:
            # Normal volatility: standard window
            short_dte = 10
            long_dte = 40
        else:
            # Low volatility: need more time
            short_dte = 14
            long_dte = 45
        
        return short_dte, long_dte
    
    def find_nearest_expiration(self, 
                               target_dte: int,
                               available_expirations: list) -> datetime:
        """
        Find expiration closest to target DTE from available chain
        """
        today = datetime.now()
        target_date = today + timedelta(days=target_dte)
        
        # Find closest available expiration
        closest = min(available_expirations, 
                     key=lambda x: abs((x - today).days - target_dte))
        
        return closest
```

**Strike Selection (Delta-Based):**

```python
class StrikeSelector:
    """
    Delta-based strike selection for calendar spreads
    Research-backed targets: 0.50-0.60 delta for neutral calendars
    """
    
    def select_calendar_strikes(self,
                               chain: pd.DataFrame,
                               current_price: float,
                               strategy_bias: str = 'neutral') -> float:
        """
        Select optimal strike for calendar spread
        
        For neutral calendars:
        - Target: ATM to slightly OTM (0.45-0.55 delta)
        - Maximize theta differential between expirations
        
        Returns strike price closest to target delta
        """
        if strategy_bias == 'neutral':
            target_delta_min = 0.45
            target_delta_max = 0.55
        elif strategy_bias == 'bullish':
            target_delta_min = 0.55
            target_delta_max = 0.65
        elif strategy_bias == 'bearish':
            # For put calendars
            target_delta_min = -0.55
            target_delta_max = -0.45
        
        # Filter to target delta range
        candidates = chain[
            (chain['delta'].abs() >= target_delta_min) &
            (chain['delta'].abs() <= target_delta_max)
        ]
        
        if candidates.empty:
            # Fallback to ATM
            return self._find_atm_strike(chain, current_price)
        
        # Select strike with highest liquidity score in range
        best = candidates.nlargest(1, 'liquidity_score')
        return best.iloc[0]['strike']
    
    def _find_atm_strike(self, chain: pd.DataFrame, price: float) -> float:
        """Find strike closest to current price"""
        chain['distance'] = abs(chain['strike'] - price)
        return chain.nsmallest(1, 'distance').iloc[0]['strike']
```

---

### 2.2 Machine Learning Components

#### 2.2.1 LSTM Volatility Surface Predictor

**File:** `src/ml_models/volatility_forecaster.py`

**Purpose:** Predict IV term structure changes to identify optimal calendar entry points.

**Architecture:**

```python
import tensorflow as tf
from tensorflow.keras.layers import LSTM, Dense, Dropout, Attention

class VolatilitySurfacePredictor:
    """
    LSTM with attention mechanism for IV surface prediction
    Based on research: arXiv:1912.11059 - Deep Learning for IV Surfaces
    
    Predicts:
    - Near-term IV (7-14 DTE)
    - Long-term IV (30-45 DTE)
    - IV term structure slope
    
    Used to identify:
    - When near-term IV > long-term IV (backwardation) = good calendar entry
    - When IV expected to rise = favorable for vega-long calendars
    """
    
    def build_model(self, sequence_length=30, n_features=12):
        """
        Build LSTM architecture
        
        Input features (12):
        - Historical IV levels (7D, 14D, 30D, 60D expirations)
        - Realized volatility (10D, 20D, 30D)
        - VIX level and term structure
        - Price momentum indicators
        - Volume indicators
        """
        model = tf.keras.Sequential([
            # First LSTM layer with return sequences
            LSTM(128, return_sequences=True, 
                 input_shape=(sequence_length, n_features)),
            Dropout(0.3),
            
            # Attention mechanism
            Attention(),
            
            # Second LSTM layer
            LSTM(64, return_sequences=False),
            Dropout(0.2),
            
            # Dense layers
            Dense(32, activation='relu'),
            Dropout(0.2),
            Dense(16, activation='relu'),
            
            # Output layer (predict 4 values)
            Dense(4, activation='linear')  # [IV_7D, IV_14D, IV_30D, IV_45D]
        ])
        
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae']
        )
        
        return model
    
    def predict_term_structure(self, 
                              symbol: str,
                              lookback_days: int = 30) -> dict:
        """
        Predict IV across expiration dates
        
        Returns:
        {
            'iv_7d': 0.24,      # Predicted 7-day IV
            'iv_14d': 0.26,     # Predicted 14-day IV
            'iv_30d': 0.28,     # Predicted 30-day IV
            'iv_45d': 0.29,     # Predicted 45-day IV
            'slope': 0.015,     # Term structure slope (positive = contango)
            'calendar_favorable': True  # Near-term > long-term?
        }
        """
        # Get historical data
        features = self._prepare_features(symbol, lookback_days)
        
        # Predict future IV levels
        predictions = self.model.predict(features)
        
        iv_7d, iv_14d, iv_30d, iv_45d = predictions[0]
        
        # Calculate term structure slope
        slope = (iv_45d - iv_7d) / 38  # per day
        
        # Calendar favorable if near-term IV > long-term IV
        calendar_favorable = iv_14d > iv_30d
        
        return {
            'iv_7d': float(iv_7d),
            'iv_14d': float(iv_14d),
            'iv_30d': float(iv_30d),
            'iv_45d': float(iv_45d),
            'slope': float(slope),
            'calendar_favorable': bool(calendar_favorable),
            'confidence': self._calculate_confidence(features, predictions)
        }
```

**Training Process:**

```python
class VolatilityTrainer:
    """Train LSTM on historical IV surface data"""
    
    def train(self, 
             historical_data: pd.DataFrame,
             validation_split: float = 0.2,
             epochs: int = 100):
        """
        Train on 5+ years of historical IV data
        
        Data requirements:
        - Daily IV snapshots across multiple expirations
        - Realized volatility calculations
        - VIX and market data
        - Minimum 1,000 symbols × 1,500 days = 1.5M samples
        """
        # Prepare sequences (30-day windows → predict next 4 values)
        X, y = self._create_sequences(historical_data, 
                                      sequence_length=30)
        
        # Split train/validation
        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        # Callbacks
        callbacks = [
            tf.keras.callbacks.EarlyStopping(patience=10, restore_best_weights=True),
            tf.keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=5),
            tf.keras.callbacks.ModelCheckpoint('best_model.h5', save_best_only=True)
        ]
        
        # Train
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=epochs,
            batch_size=256,
            callbacks=callbacks,
            verbose=1
        )
        
        return history
```

#### 2.2.2 Reinforcement Learning Strike Selection Agent

**File:** `src/ml_models/rl_strike_agent.py`

**Purpose:** Learn optimal strike placement through trial and error across market regimes.

**Architecture (PPO - Proximal Policy Optimization):**

```python
from stable_baselines3 import PPO
from gymnasium import Env
import gymnasium as gym

class CalendarSpreadEnv(Env):
    """
    Gymnasium environment for RL agent to learn strike selection
    
    State space (observation):
    - Current price
    - IV rank
    - Days to earnings
    - Historical volatility
    - VIX level
    - Greeks (delta, gamma, vega, theta) for candidate strikes
    - Recent price action (10-day momentum, ATR)
    
    Action space:
    - Strike selection (discrete: -5%, -2.5%, ATM, +2.5%, +5% from current price)
    - Position size multiplier (0.5x, 0.75x, 1.0x, 1.25x, 1.5x)
    
    Reward function:
    - Sharpe ratio of returns over episode
    - Penalty for drawdowns >10%
    - Bonus for win streaks
    - Transaction cost penalties
    """
    
    def __init__(self, historical_data: pd.DataFrame):
        super().__init__()
        
        self.data = historical_data
        self.current_step = 0
        
        # Define observation space (15 features)
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(15,), dtype=np.float32
        )
        
        # Define action space (strike selection + position size)
        self.action_space = gym.spaces.MultiDiscrete([5, 5])  # 5 strikes × 5 sizes
        
        self.reset()
    
    def step(self, action):
        """
        Execute one timestep
        
        Args:
            action: [strike_idx, size_idx]
        
        Returns:
            observation, reward, terminated, truncated, info
        """
        strike_idx, size_idx = action
        
        # Map action to actual strike and size
        strike_offset = [-0.05, -0.025, 0.0, 0.025, 0.05][strike_idx]
        size_multiplier = [0.5, 0.75, 1.0, 1.25, 1.5][size_idx]
        
        # Execute simulated trade
        result = self._simulate_calendar_spread(
            strike_offset=strike_offset,
            size_multiplier=size_multiplier,
            hold_days=7
        )
        
        # Calculate reward (Sharpe ratio - transaction costs)
        reward = result['sharpe_ratio'] - 0.01 * size_multiplier
        
        # Apply penalties
        if result['drawdown'] > 0.10:
            reward -= 5.0  # Penalize large drawdowns
        
        if result['win']:
            self.win_streak += 1
            reward += 0.5 * self.win_streak  # Bonus for streaks
        else:
            self.win_streak = 0
        
        # Move to next step
        self.current_step += 1
        terminated = self.current_step >= len(self.data) - 30
        
        observation = self._get_observation()
        info = {'pnl': result['pnl'], 'win': result['win']}
        
        return observation, reward, terminated, False, info
    
    def reset(self, seed=None, options=None):
        """Reset environment to random starting point"""
        super().reset(seed=seed)
        
        self.current_step = np.random.randint(0, len(self.data) - 100)
        self.win_streak = 0
        self.portfolio_value = 10000.0
        
        return self._get_observation(), {}
    
    def _simulate_calendar_spread(self, strike_offset, size_multiplier, hold_days):
        """
        Simulate calendar spread trade outcome
        Uses historical data to calculate P&L, Greeks evolution
        """
        # Implementation details omitted for brevity
        # Returns {'pnl': float, 'sharpe_ratio': float, 'drawdown': float, 'win': bool}
        pass

class RLStrikeAgent:
    """PPO agent for strike selection"""
    
    def __init__(self):
        self.model = None
    
    def train(self, 
             historical_data: pd.DataFrame,
             total_timesteps: int = 1_000_000):
        """
        Train PPO agent on historical data
        
        Training process:
        - Agent explores different strike selections
        - Learns which strikes maximize risk-adjusted returns
        - Adapts to different market regimes
        - Discovers optimal position sizing
        """
        env = CalendarSpreadEnv(historical_data)
        
        # Build PPO model
        self.model = PPO(
            policy="MlpPolicy",
            env=env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            verbose=1,
            tensorboard_log="./ppo_calendar_tensorboard/"
        )
        
        # Train
        self.model.learn(total_timesteps=total_timesteps)
        
        # Save model
        self.model.save("rl_strike_agent")
    
    def select_strike(self, observation: np.ndarray) -> tuple[float, float]:
        """
        Use trained agent to select optimal strike and position size
        
        Args:
            observation: Current market state (15 features)
        
        Returns:
            (strike_offset, size_multiplier)
        """
        action, _states = self.model.predict(observation, deterministic=True)
        
        strike_idx, size_idx = action
        
        strike_offset = [-0.05, -0.025, 0.0, 0.025, 0.05][strike_idx]
        size_multiplier = [0.5, 0.75, 1.0, 1.25, 1.5][size_idx]
        
        return strike_offset, size_multiplier
```

#### 2.2.3 Earnings IV Crush Predictor

**File:** `src/ml_models/iv_crush_predictor.py`

**Purpose:** Predict post-earnings IV collapse to avoid catastrophic calendar spread losses.

**Architecture (Random Forest Classifier):**

```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, f1_score

class IVCrushPredictor:
    """
    Predict IV crush magnitude after earnings
    
    Based on research from Earnings-AI-Implementation.md:
    - F1-score target: >0.82
    - Accuracy target: 78-85% within ±5%
    - Training data: 45,000+ historical earnings events
    """
    
    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=500,
            max_depth=15,
            min_samples_split=10,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1
        )
        self.feature_names = None
    
    def prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Engineer 54 features for IV crush prediction
        
        Feature categories:
        1. Technical (10): RSI, MACD, Bollinger Bands, ATR, momentum
        2. Volatility (12): Current IV, IV rank, IV percentile, VIX, realized vol
        3. Earnings (10): Days to earnings, expected move, historical move, surprise
        4. Price/Market (8): Beta, 52-week range, sector momentum
        5. Company-specific (14): Previous IV changes, beat/miss history, analyst consensus
        """
        features = pd.DataFrame()
        
        # Technical indicators
        features['rsi_14'] = self._calculate_rsi(data['close'], 14)
        features['macd'] = self._calculate_macd(data['close'])
        features['bb_position'] = self._calculate_bb_position(data['close'])
        features['atr_14'] = self._calculate_atr(data, 14)
        
        # Volatility features
        features['iv_current'] = data['implied_volatility']
        features['iv_rank'] = data['iv_rank']
        features['iv_percentile'] = data['iv_percentile']
        features['vix'] = data['vix']
        features['realized_vol_10d'] = data['close'].pct_change().rolling(10).std() * np.sqrt(252)
        features['realized_vol_20d'] = data['close'].pct_change().rolling(20).std() * np.sqrt(252)
        
        # Earnings-specific
        features['days_to_earnings'] = data['days_to_earnings']
        features['expected_move'] = data['expected_move']
        features['historical_move'] = data['historical_move']
        features['previous_surprise'] = data['eps_surprise']
        features['previous_iv_change'] = data['previous_earnings_iv_change']
        
        # Price/Market
        features['beta'] = data['beta']
        features['sector_momentum'] = data['sector_return_10d']
        
        # ... (additional 35 features omitted for brevity)
        
        self.feature_names = features.columns.tolist()
        return features
    
    def train(self, 
             historical_earnings: pd.DataFrame,
             target_col: str = 'iv_crush_magnitude'):
        """
        Train Random Forest on historical earnings data
        
        Args:
            historical_earnings: DataFrame with features + target
                Target classes:
                0: No crush (<10% IV decline)
                1: Mild crush (10-20% decline)
                2: Moderate crush (20-30% decline)
                3: Severe crush (>30% decline)
        """
        # Prepare features
        X = self.prepare_features(historical_earnings)
        y = historical_earnings[target_col]
        
        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        # Train
        print("Training Random Forest on {} samples...".format(len(X_train)))
        self.model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test)
        f1 = f1_score(y_test, y_pred, average='weighted')
        
        print(classification_report(y_test, y_pred))
        print(f"Weighted F1-Score: {f1:.4f}")
        
        if f1 < 0.82:
            print("⚠️  WARNING: F1-score below target 0.82. Retune hyperparameters.")
        else:
            print("✅ F1-score target achieved!")
        
        # Feature importance
        importance = pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        print("\nTop 10 Most Important Features:")
        print(importance.head(10))
        
        return f1
    
    def predict_crush(self, 
                     symbol: str,
                     days_to_earnings: int) -> dict:
        """
        Predict IV crush for upcoming earnings
        
        Returns:
        {
            'crush_probability': 0.73,      # 73% chance of moderate/severe crush
            'predicted_magnitude': 0.28,    # Expected 28% IV decline
            'confidence': 0.85,             # Model confidence
            'recommendation': 'AVOID'       # AVOID, REDUCE_SIZE, or APPROVE
        }
        """
        # Get current market features
        features = self._get_current_features(symbol)
        
        # Predict
        proba = self.model.predict_proba(features)[0]  # [P(class0), P(class1), P(class2), P(class3)]
        predicted_class = self.model.predict(features)[0]
        
        # Calculate crush probability (moderate + severe)
        crush_probability = proba[2] + proba[3]
        
        # Map class to magnitude
        magnitude_map = {0: 0.05, 1: 0.15, 2: 0.25, 3: 0.40}
        predicted_magnitude = magnitude_map[predicted_class]
        
        # Confidence (max probability)
        confidence = max(proba)
        
        # Recommendation logic
        if days_to_earnings <= 3 and crush_probability > 0.70:
            recommendation = 'AVOID'
        elif days_to_earnings <= 7 and crush_probability > 0.60:
            recommendation = 'REDUCE_SIZE'
        else:
            recommendation = 'APPROVE'
        
        return {
            'crush_probability': float(crush_probability),
            'predicted_magnitude': float(predicted_magnitude),
            'confidence': float(confidence),
            'recommendation': recommendation,
            'days_to_earnings': days_to_earnings
        }
```

---

### 2.3 Earnings Intelligence System

**File:** `src/earnings_intelligence/earnings_calendar.py`

**Purpose:** Maintain up-to-date earnings calendar and sync from multiple sources.

```python
import requests
from datetime import datetime, timedelta
import yfinance as yf

class EarningsCalendarClient:
    """
    Fetch and cache earnings dates from multiple sources
    Priority: SEC EDGAR > Alpha Vantage > Yahoo Finance
    """
    
    def __init__(self, db_connection):
        self.db = db_connection
        self.alpha_vantage_key = os.getenv('ALPHA_VANTAGE_API_KEY')
        self.sync_interval = 3600  # Sync every hour
    
    def sync_earnings_calendar(self, symbols: list[str]):
        """
        Fetch earnings dates for watchlist symbols
        Updates PostgreSQL earnings_calendar table
        """
        for symbol in symbols:
            try:
                # Try SEC EDGAR first (most accurate)
                earnings_date = self._fetch_sec_edgar(symbol)
                
                if not earnings_date:
                    # Fallback to Alpha Vantage
                    earnings_date = self._fetch_alpha_vantage(symbol)
                
                if not earnings_date:
                    # Fallback to Yahoo Finance
                    earnings_date = self._fetch_yahoo(symbol)
                
                if earnings_date:
                    # Calculate expected move from historical data
                    expected_move = self._calculate_expected_move(symbol)
                    
                    # Store in database
                    self._upsert_earnings(symbol, earnings_date, expected_move)
            
            except Exception as e:
                print(f"Error syncing {symbol}: {e}")
    
    def get_days_to_earnings(self, symbol: str) -> int:
        """
        Get days until next earnings announcement
        Returns 999 if no earnings in next 90 days
        """
        query = """
            SELECT announcement_date 
            FROM earnings_calendar 
            WHERE symbol = %s 
            AND announcement_date > NOW()
            ORDER BY announcement_date ASC
            LIMIT 1
        """
        
        result = self.db.execute(query, (symbol,))
        
        if result:
            days = (result[0]['announcement_date'] - datetime.now()).days
            return max(0, days)
        
        return 999  # No earnings scheduled
    
    def _fetch_alpha_vantage(self, symbol: str) -> datetime:
        """Fetch from Alpha Vantage API"""
        url = f"https://www.alphavantage.co/query?function=EARNINGS_CALENDAR&symbol={symbol}&apikey={self.alpha_vantage_key}"
        response = requests.get(url)
        
        # Parse CSV response
        # ... (implementation details)
        
        return earnings_date
    
    def _fetch_yahoo(self, symbol: str) -> datetime:
        """Fetch from Yahoo Finance using yfinance"""
        ticker = yf.Ticker(symbol)
        calendar = ticker.calendar
        
        if calendar and 'Earnings Date' in calendar:
            return calendar['Earnings Date'][0]
        
        return None
    
    def _calculate_expected_move(self, symbol: str) -> float:
        """
        Calculate expected move from option-implied straddle
        or use historical average move
        """
        # Get ATM straddle price
        # expected_move = straddle_price / stock_price
        
        # Or use historical average
        query = """
            SELECT AVG(ABS((close_after - close_before) / close_before)) as avg_move
            FROM historical_earnings
            WHERE symbol = %s
            AND announcement_date > NOW() - INTERVAL '2 years'
        """
        
        result = self.db.execute(query, (symbol,))
        return result[0]['avg_move'] if result else 0.05  # Default 5%
```

**File:** `src/earnings_intelligence/strategy_router.py`

**Purpose:** Route signals based on earnings proximity and IV crush predictions.

```python
class EarningsStrategyRouter:
    """
    Decide whether to approve, reject, or modify calendar spread trades
    based on earnings proximity and IV crush predictions
    """
    
    def __init__(self, 
                 earnings_client: EarningsCalendarClient,
                 iv_predictor: IVCrushPredictor):
        self.earnings_client = earnings_client
        self.iv_predictor = iv_predictor
    
    def decide(self, 
              symbol: str,
              strategy: str = 'calendar') -> dict:
        """
        Make trading decision based on earnings intelligence
        
        Returns:
        {
            'action': 'APPROVE' | 'REJECT' | 'REDUCE_SIZE' | 'REVERSE_CALENDAR',
            'reason': str,
            'size_multiplier': float,
            'alternative_strategy': str or None
        }
        """
        # Check days to earnings
        days_to_earnings = self.earnings_client.get_days_to_earnings(symbol)
        
        # No earnings in next 90 days → approve
        if days_to_earnings > 14:
            return {
                'action': 'APPROVE',
                'reason': 'No earnings within 14 days',
                'size_multiplier': 1.0,
                'alternative_strategy': None
            }
        
        # Earnings within 14 days → consult IV predictor
        prediction = self.iv_predictor.predict_crush(symbol, days_to_earnings)
        
        # Decision matrix based on research (Implementation-QuickRef.md)
        if days_to_earnings <= 3:
            if prediction['crush_probability'] > 0.70:
                return {
                    'action': 'REJECT',
                    'reason': f"High crush risk ({prediction['crush_probability']:.0%}) {days_to_earnings}d before earnings",
                    'size_multiplier': 0.0,
                    'alternative_strategy': None
                }
            elif prediction['crush_probability'] > 0.50:
                return {
                    'action': 'REDUCE_SIZE',
                    'reason': f"Moderate crush risk ({prediction['crush_probability']:.0%})",
                    'size_multiplier': 0.5,
                    'alternative_strategy': None
                }
        
        elif days_to_earnings <= 7:
            if prediction['crush_probability'] > 0.80:
                return {
                    'action': 'REJECT',
                    'reason': f"Very high crush risk ({prediction['crush_probability']:.0%})",
                    'size_multiplier': 0.0,
                    'alternative_strategy': None
                }
            elif prediction['crush_probability'] > 0.60:
                # Consider reverse calendar to profit from crush
                return {
                    'action': 'REVERSE_CALENDAR',
                    'reason': f"High crush expected, reverse calendar favorable",
                    'size_multiplier': 0.7,
                    'alternative_strategy': 'reverse_calendar'
                }
        
        # Default: approve with normal size
        return {
            'action': 'APPROVE',
            'reason': 'Earnings risk acceptable',
            'size_multiplier': 1.0,
            'alternative_strategy': None
        }
```

---

### 2.4 Interactive Brokers Integration

**File:** `src/execution/ib_connector.py`

**Purpose:** Handle all IB API communication, order execution, position management.

```python
from ib_async import IB, Option, Stock, Order, util
import asyncio

class IBConnector:
    """
    Interactive Brokers API integration using ib_async
    Handles connection, market data, order execution, position tracking
    """
    
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id
        self.connected = False
    
    async def connect(self):
        """Connect to IB Gateway/TWS"""
        try:
            await self.ib.connectAsync(self.host, self.port, clientId=self.client_id)
            self.connected = True
            print(f"✅ Connected to IB Gateway at {self.host}:{self.port}")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            self.connected = False
    
    async def get_option_chain(self, 
                               symbol: str,
                               expiration: datetime) -> list:
        """
        Fetch complete option chain for symbol and expiration
        Returns list of Option contracts with Greeks
        """
        # Create stock contract
        stock = Stock(symbol, 'SMART', 'USD')
        await self.ib.qualifyContractsAsync(stock)
        
        # Request option chain
        chains = await self.ib.reqSecDefOptParamsAsync(
            stock.symbol, '', stock.secType, stock.conId
        )
        
        chain = next(c for c in chains if c.exchange == 'SMART')
        
        # Get strikes for target expiration
        exp_str = expiration.strftime('%Y%m%d')
        strikes = [strike for strike in chain.strikes]
        
        # Build option contracts
        contracts = []
        for strike in strikes:
            # Call
            call = Option(symbol, exp_str, strike, 'C', 'SMART')
            # Put
            put = Option(symbol, exp_str, strike, 'P', 'SMART')
            
            contracts.extend([call, put])
        
        # Qualify contracts and get market data
        qualified = await self.ib.qualifyContractsAsync(*contracts)
        
        # Request market data with Greeks
        tickers = await self.ib.reqTickersAsync(*qualified)
        
        return tickers
    
    async def place_calendar_spread(self,
                                   symbol: str,
                                   strike: float,
                                   short_expiration: datetime,
                                   long_expiration: datetime,
                                   quantity: int = 1,
                                   option_type: str = 'C') -> dict:
        """
        Place calendar spread order (2-leg combo)
        
        Args:
            symbol: Underlying symbol
            strike: Strike price for both legs
            short_expiration: Near-term expiration (sell)
            long_expiration: Longer-term expiration (buy)
            quantity: Number of spreads
            option_type: 'C' for calls, 'P' for puts
        
        Returns:
            {
                'order_id': int,
                'status': str,
                'filled_price': float,
                'commission': float
            }
        """
        # Build option contracts
        short_exp_str = short_expiration.strftime('%Y%m%d')
        long_exp_str = long_expiration.strftime('%Y%m%d')
        
        short_option = Option(symbol, short_exp_str, strike, option_type, 'SMART')
        long_option = Option(symbol, long_exp_str, strike, option_type, 'SMART')
        
        # Qualify contracts
        await self.ib.qualifyContractsAsync(short_option, long_option)
        
        # Create combo order (calendar spread)
        combo = Contract()
        combo.symbol = symbol
        combo.secType = 'BAG'
        combo.currency = 'USD'
        combo.exchange = 'SMART'
        
        leg1 = ComboLeg()
        leg1.conId = short_option.conId
        leg1.ratio = 1
        leg1.action = 'SELL'  # Sell short-term
        leg1.exchange = 'SMART'
        
        leg2 = ComboLeg()
        leg2.conId = long_option.conId
        leg2.ratio = 1
        leg2.action = 'BUY'   # Buy long-term
        leg2.exchange = 'SMART'
        
        combo.comboLegs = [leg1, leg2]
        
        # Get current mid-price for limit order
        short_ticker = await self.ib.reqTickersAsync(short_option)
        long_ticker = await self.ib.reqTickersAsync(long_option)
        
        short_mid = (short_ticker[0].bid + short_ticker[0].ask) / 2
        long_mid = (long_ticker[0].bid + long_ticker[0].ask) / 2
        
        # Net debit (pay more for long, receive less for short)
        net_debit = long_mid - short_mid
        
        # Create limit order
        order = Order()
        order.action = 'BUY'  # BUY the spread (net debit)
        order.totalQuantity = quantity
        order.orderType = 'LMT'
        order.lmtPrice = round(net_debit, 2)
        order.tif = 'DAY'
        order.outsideRth = True
        
        # Submit order
        trade = self.ib.placeOrder(combo, order)
        
        # Wait for fill (with timeout)
        timeout = 300  # 5 minutes
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            await asyncio.sleep(1)
            
            if trade.orderStatus.status in ['Filled', 'Cancelled']:
                break
        
        # Return result
        return {
            'order_id': trade.order.orderId,
            'status': trade.orderStatus.status,
            'filled_price': trade.orderStatus.avgFillPrice,
            'commission': trade.orderStatus.commission,
            'fill_time': trade.orderStatus.lastFillTime
        }
    
    async def get_portfolio_greeks(self) -> dict:
        """
        Calculate aggregate Greeks for all open positions
        
        Returns:
        {
            'delta': -0.15,     # Net delta
            'gamma': -0.05,     # Net gamma
            'theta': 12.50,     # Net theta (daily P&L from time decay)
            'vega': 45.30       # Net vega (P&L from 1% IV change)
        }
        """
        positions = self.ib.positions()
        
        total_delta = 0
        total_gamma = 0
        total_theta = 0
        total_vega = 0
        
        for position in positions:
            contract = position.contract
            quantity = position.position
            
            # Get Greeks from market data
            ticker = await self.ib.reqTickersAsync(contract)
            greeks = ticker[0].modelGreeks
            
            if greeks:
                total_delta += greeks.delta * quantity
                total_gamma += greeks.gamma * quantity
                total_theta += greeks.theta * quantity
                total_vega += greeks.vega * quantity
        
        return {
            'delta': total_delta,
            'gamma': total_gamma,
            'theta': total_theta,
            'vega': total_vega
        }
```

---

### 2.5 Risk Management System

**File:** `src/risk_management/position_manager.py`

```python
class PositionManager:
    """
    Manage open positions, calculate stops, trigger adjustments
    """
    
    def __init__(self, db_connection, ib_connector):
        self.db = db_connection
        self.ib = ib_connector
        self.max_portfolio_delta = 25  # Max net delta
        self.max_portfolio_gamma = 10  # Max net gamma
    
    async def calculate_dynamic_stop(self,
                                    symbol: str,
                                    entry_price: float,
                                    days_to_earnings: int) -> float:
        """
        Calculate dynamic stop-loss based on volatility and earnings proximity
        
        Formula: Stop_Distance = k × Beta × VIX × Earnings_Factor
        
        Where:
        - k = aggression factor (0.8 default)
        - Beta = stock beta vs SPY
        - VIX = current VIX level
        - Earnings_Factor = {1.5 if 1d before, 1.3 if 2-3d, 1.1 if 4-7d, 1.0 if >7d}
        """
        # Get market data
        beta = await self._get_beta(symbol)
        vix = await self._get_vix()
        
        # Base stop distance
        k = 0.8  # Aggression factor
        base_stop_distance = k * beta * vix / 100
        
        # Earnings multiplier (from Integration-with-IB-System.md)
        if days_to_earnings <= 1:
            earnings_factor = 1.5
        elif days_to_earnings <= 3:
            earnings_factor = 1.3
        elif days_to_earnings <= 7:
            earnings_factor = 1.1
        else:
            earnings_factor = 1.0
        
        stop_distance = base_stop_distance * earnings_factor
        
        # Calculate stop price
        stop_price = entry_price * (1 - stop_distance)
        
        return stop_price
    
    async def check_position_adjustments(self):
        """
        Monitor all positions and trigger adjustments based on:
        - Greeks exceeding limits
        - Days to expiration
        - P&L thresholds
        - RL agent recommendations
        """
        positions = await self.ib.get_positions()
        
        for position in positions:
            # Check if short leg approaching expiration
            if position.short_dte <= 3:
                # Consider rolling short leg
                await self._roll_short_leg(position)
            
            # Check if price moved significantly
            current_price = await self._get_current_price(position.symbol)
            price_change = abs(current_price - position.strike) / position.strike
            
            if price_change > 0.05:  # 5% away from strike
                # Consider re-centering spread
                await self._recenter_spread(position)
            
            # Check P&L
            pnl_pct = position.unrealized_pnl / position.cost_basis
            
            if pnl_pct > 0.20:  # 20% profit
                # Consider taking profit
                await self._close_position(position, reason="Profit target reached")
            
            elif pnl_pct < -0.50:  # 50% loss (half of max loss)
                # Close to prevent max loss
                await self._close_position(position, reason="Stop loss triggered")
    
    async def _roll_short_leg(self, position):
        """
        Roll short leg to next expiration for additional credit
        """
        # Buy back current short leg
        # Sell new short leg at next weekly expiration
        # Log adjustment
        pass
    
    async def _recenter_spread(self, position):
        """
        Close current spread and open new spread at current price
        """
        # Close existing position
        # Calculate new optimal strike (at current ATM)
        # Open new calendar spread
        # Log adjustment
        pass
```

**File:** `src/risk_management/portfolio_limits.py`

```python
class PortfolioLimits:
    """
    Enforce portfolio-level risk limits
    """
    
    def __init__(self, account_size: float):
        self.account_size = account_size
        
        # Risk limits
        self.max_risk_per_trade = account_size * 0.02      # 2% per trade
        self.max_daily_loss = account_size * 0.03           # 3% daily
        self.max_total_risk = account_size * 0.10          # 10% total
        self.max_concurrent_positions = 5
        
        # Greeks limits
        self.max_net_delta = 25
        self.max_net_gamma = 10
        
        # Track daily P&L
        self.daily_pnl = 0
    
    def check_new_trade(self, 
                       trade_cost: float,
                       position_delta: float,
                       position_gamma: float) -> tuple[bool, str]:
        """
        Check if new trade passes risk limits
        
        Returns (approved, reason)
        """
        # Check position size
        if trade_cost > self.max_risk_per_trade:
            return False, f"Trade cost ${trade_cost} exceeds per-trade limit ${self.max_risk_per_trade}"
        
        # Check daily loss limit
        if self.daily_pnl < 0 and abs(self.daily_pnl) >= self.max_daily_loss:
            return False, f"Daily loss limit ${self.max_daily_loss} reached"
        
        # Check concurrent positions
        current_positions = self._get_open_position_count()
        if current_positions >= self.max_concurrent_positions:
            return False, f"Maximum {self.max_concurrent_positions} concurrent positions reached"
        
        # Check Greeks limits
        current_greeks = self._get_portfolio_greeks()
        new_delta = current_greeks['delta'] + position_delta
        new_gamma = current_greeks['gamma'] + position_gamma
        
        if abs(new_delta) > self.max_net_delta:
            return False, f"Portfolio delta {new_delta} exceeds limit ±{self.max_net_delta}"
        
        if abs(new_gamma) > self.max_net_gamma:
            return False, f"Portfolio gamma {new_gamma} exceeds limit ±{self.max_net_gamma}"
        
        # All checks passed
        return True, "Trade approved"
```

---

## PART 3: DATABASE SCHEMA

**PostgreSQL Schema:**

```sql
-- Earnings calendar
CREATE TABLE earnings_calendar (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    announcement_date TIMESTAMP NOT NULL,
    expected_move FLOAT,
    historical_move FLOAT,
    iv_rank_5y FLOAT,
    previous_beat_miss VARCHAR(10),
    previous_surprise FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(symbol, announcement_date),
    INDEX idx_symbol_date (symbol, announcement_date)
);

-- IV crush predictions
CREATE TABLE iv_crush_predictions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    prediction_date TIMESTAMP NOT NULL,
    days_to_earnings INT,
    predicted_crush_pct FLOAT,
    crush_probability FLOAT,
    confidence_score FLOAT,
    model_version VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_symbol_prediction_date (symbol, prediction_date)
);

-- Trades log
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    strategy_type VARCHAR(30) NOT NULL,  -- 'calendar', 'reverse_calendar', 'diagonal'
    entry_date TIMESTAMP NOT NULL,
    exit_date TIMESTAMP,
    
    -- Position details
    strike FLOAT NOT NULL,
    short_expiration DATE NOT NULL,
    long_expiration DATE NOT NULL,
    option_type CHAR(1) NOT NULL,  -- 'C' or 'P'
    quantity INT NOT NULL,
    
    -- Pricing
    entry_price FLOAT NOT NULL,
    exit_price FLOAT,
    commission FLOAT,
    
    -- P&L
    realized_pnl FLOAT,
    pnl_pct FLOAT,
    
    -- Earnings context
    days_to_earnings_at_entry INT,
    earnings_decision VARCHAR(30),  -- 'APPROVE', 'REJECT', 'REDUCE_SIZE'
    iv_crush_prediction FLOAT,
    
    -- Greeks at entry
    entry_delta FLOAT,
    entry_gamma FLOAT,
    entry_theta FLOAT,
    entry_vega FLOAT,
    
    -- Outcome
    win BOOLEAN,
    close_reason VARCHAR(255),
    
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_symbol_entry (symbol, entry_date),
    INDEX idx_strategy (strategy_type),
    INDEX idx_win (win)
);

-- Positions (current open positions)
CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    strategy_type VARCHAR(30) NOT NULL,
    
    -- IB order details
    ib_order_id BIGINT,
    combo_contract_id BIGINT,
    
    -- Position details
    strike FLOAT NOT NULL,
    short_expiration DATE NOT NULL,
    long_expiration DATE NOT NULL,
    short_dte INT,
    long_dte INT,
    option_type CHAR(1) NOT NULL,
    quantity INT NOT NULL,
    
    -- Pricing
    entry_price FLOAT NOT NULL,
    current_price FLOAT,
    cost_basis FLOAT NOT NULL,
    
    -- P&L
    unrealized_pnl FLOAT,
    pnl_pct FLOAT,
    
    -- Risk management
    stop_loss_price FLOAT,
    take_profit_price FLOAT,
    
    -- Greeks (updated real-time)
    current_delta FLOAT,
    current_gamma FLOAT,
    current_theta FLOAT,
    current_vega FLOAT,
    
    -- Timestamps
    opened_at TIMESTAMP NOT NULL,
    last_updated TIMESTAMP DEFAULT NOW(),
    
    INDEX idx_symbol (symbol),
    INDEX idx_open (opened_at)
);

-- Performance analytics (aggregated)
CREATE TABLE performance_metrics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    
    -- Trading metrics
    total_trades INT,
    winning_trades INT,
    losing_trades INT,
    win_rate FLOAT,
    
    -- P&L
    gross_profit FLOAT,
    gross_loss FLOAT,
    net_pnl FLOAT,
    commissions FLOAT,
    
    -- Risk metrics
    max_drawdown FLOAT,
    sharpe_ratio FLOAT,
    profit_factor FLOAT,
    
    -- Strategy breakdown
    calendar_trades INT,
    calendar_win_rate FLOAT,
    reverse_calendar_trades INT,
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- ML model performance tracking
CREATE TABLE ml_model_performance (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(50) NOT NULL,
    model_version VARCHAR(20) NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    metric_value FLOAT NOT NULL,
    evaluation_date TIMESTAMP NOT NULL,
    
    INDEX idx_model_version (model_name, model_version),
    INDEX idx_eval_date (evaluation_date)
);
```

---

## PART 4: IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Weeks 1-2)

**Goal:** Set up infrastructure, database, basic IB connectivity.

**Deliverables:**
- [ ] PostgreSQL database setup with schema
- [ ] Redis instance for caching
- [ ] IB Gateway connection and authentication
- [ ] Basic options chain fetching
- [ ] VOSS liquidity filtering implementation
- [ ] Unit tests for core utilities

**Team:** 1 backend engineer
**Effort:** 80 hours

---

### Phase 2: Options Selection & Execution (Weeks 3-4)

**Goal:** Implement research-backed option selection and order execution.

**Deliverables:**
- [ ] DTE selection algorithm (IV-adjusted)
- [ ] Strike selection logic (delta-based)
- [ ] Calendar spread order builder
- [ ] IB combo order execution
- [ ] Smart limit pricing
- [ ] Liquidity validation before order
- [ ] Integration tests with IB paper trading

**Team:** 1 backend engineer + 1 QA
**Effort:** 100 hours

---

### Phase 3: Machine Learning Models (Weeks 5-6)

**Goal:** Train and deploy ML models for volatility prediction and earnings intelligence.

**Deliverables:**
- [ ] LSTM volatility surface predictor trained
- [ ] Random Forest IV crush predictor trained (F1 > 0.82)
- [ ] RL strike selection agent trained (1M timesteps)
- [ ] Model serving infrastructure
- [ ] Backtesting framework for validation
- [ ] Model performance monitoring

**Team:** 1 ML engineer + 1 backend engineer
**Effort:** 120 hours

---

### Phase 4: Earnings Intelligence (Week 7)

**Goal:** Integrate earnings calendar and strategy routing.

**Deliverables:**
- [ ] Earnings calendar sync (Alpha Vantage, Yahoo, SEC)
- [ ] Hourly sync cron job
- [ ] Earnings strategy router implementation
- [ ] Integration with IV crush predictor
- [ ] Dashboard showing earnings context
- [ ] Backtesting on historical earnings events

**Team:** 1 backend engineer
**Effort:** 60 hours

---

### Phase 5: Risk Management (Week 8)

**Goal:** Implement dynamic risk management and position monitoring.

**Deliverables:**
- [ ] Dynamic stop-loss calculator (earnings-aware)
- [ ] Portfolio Greeks aggregation
- [ ] Position adjustment triggers
- [ ] Daily loss limits enforcement
- [ ] Real-time P&L tracking
- [ ] Alert system for risk breaches

**Team:** 1 backend engineer
**Effort:** 60 hours

---

### Phase 6: Integration & Testing (Weeks 9-10)

**Goal:** End-to-end integration, paper trading, production prep.

**Deliverables:**
- [ ] Full system integration
- [ ] Paper trading with 50+ trades
- [ ] Performance validation (win rate, Sharpe, drawdown)
- [ ] Load testing (handle 100+ concurrent users)
- [ ] Monitoring dashboards (Grafana)
- [ ] Error tracking (Sentry)
- [ ] Deployment documentation

**Team:** 2 backend engineers + 1 DevOps + 1 QA
**Effort:** 120 hours

---

### Phase 7: Production Launch (Week 11+)

**Goal:** Deploy to production, monitor, iterate.

**Deliverables:**
- [ ] Production deployment on AWS
- [ ] Real-money trading enabled
- [ ] 24/7 monitoring
- [ ] Weekly model retraining
- [ ] User feedback collection
- [ ] Performance reporting

**Team:** 1 backend engineer + 1 DevOps
**Effort:** Ongoing

---

## PART 5: TESTING STRATEGY

### Unit Tests (Target: 90%+ Coverage)

```python
# Example: test_voss_filter.py
def test_liquidity_filtering():
    """Test VOSS filter removes illiquid options"""
    chain = create_mock_chain()
    
    # Add illiquid option
    chain.loc[0, 'openInterest'] = 100  # Below minimum 1,000
    
    filtered = voss_filter.filter_options_chain(chain)
    
    assert len(filtered) < len(chain)
    assert filtered['openInterest'].min() >= 1000

def test_dte_selection_high_iv():
    """Test DTE adjustment for high IV"""
    selector = DTESelector()
    
    short_dte, long_dte = selector.select_optimal_dte(
        symbol='NVDA',
        iv_rank=85.0  # High IV
    )
    
    assert short_dte == 7   # Shorter for high IV
    assert long_dte == 30
```

### Integration Tests

```python
# test_calendar_execution.py
@pytest.mark.integration
async def test_place_calendar_spread_end_to_end():
    """Test full calendar spread execution flow"""
    # 1. Fetch options chain
    chain = await ib.get_option_chain('SPY', expiration=get_next_friday())
    
    # 2. Filter liquidity
    filtered = voss_filter.filter_options_chain(chain)
    assert len(filtered) > 0
    
    # 3. Select strike
    strike = strike_selector.select_calendar_strikes(filtered, 450.0)
    assert strike > 0
    
    # 4. Place order
    result = await ib.place_calendar_spread(
        symbol='SPY',
        strike=strike,
        short_expiration=get_next_friday(),
        long_expiration=get_friday_plus_7()
    )
    
    assert result['status'] in ['Filled', 'Submitted']
```

### Backtesting

```python
# test_backtest_calendar.py
def test_backtest_calendar_strategy():
    """
    Backtest calendar spread strategy on 5 years of data
    Validate performance targets
    """
    results = backtester.run(
        strategy='calendar_spread',
        symbols=['SPY', 'QQQ', 'IWM'],
        start_date='2019-01-01',
        end_date='2024-01-01',
        initial_capital=10000
    )
    
    # Performance targets
    assert results.win_rate >= 0.75
    assert results.sharpe_ratio >= 1.5
    assert results.max_drawdown <= 0.20
    assert results.annual_return >= 0.15
```

---

## PART 6: MONITORING & OPERATIONS

### Key Metrics to Track

**Trading Performance:**
- Win rate (target: 80-87%)
- Average P&L per trade
- Sharpe ratio (target: >1.8)
- Maximum drawdown (target: <15%)
- Profit factor (gross profit / gross loss)

**ML Model Performance:**
- LSTM volatility prediction accuracy
- IV crush prediction F1-score (maintain >0.82)
- RL agent cumulative reward
- Model drift detection

**System Health:**
- IB API connection uptime
- Order execution latency
- Database query performance
- Redis cache hit rate
- Error rate by component

**Risk Metrics:**
- Portfolio net delta
- Portfolio net gamma
- Daily P&L
- Open position count
- Capital utilization

### Alerts Configuration

**Critical (PagerDuty):**
- IB connection lost
- Daily loss limit breached
- Order execution failure
- Database outage
- ML model prediction error >20%

**Warning (Email):**
- Win rate drops below 70%
- Portfolio delta exceeds ±20
- Position holds >14 days
- Slippage >5% of expected

### Grafana Dashboards

**Dashboard 1: Trading Performance**
- Real-time P&L chart
- Win/loss distribution
- Calendar showing earnings
- Open positions table
- Greeks heatmap

**Dashboard 2: ML Models**
- LSTM prediction accuracy over time
- IV crush prediction confidence distribution
- RL agent reward progression
- Feature importance charts
- Model retraining schedule

**Dashboard 3: System Health**
- API latency percentiles
- Database connection pool
- Redis memory usage
- Error rate by service
- Deployment history

---

## PART 7: COST ANALYSIS

### Development Costs

| Phase | Duration | Engineers | Hours | Cost @ $100/hr |
|-------|----------|-----------|-------|----------------|
| Phase 1: Foundation | 2 weeks | 1 backend | 80 | $8,000 |
| Phase 2: Options Selection | 2 weeks | 1 backend + QA | 100 | $10,000 |
| Phase 3: ML Models | 2 weeks | 1 ML + 1 backend | 120 | $12,000 |
| Phase 4: Earnings Intel | 1 week | 1 backend | 60 | $6,000 |
| Phase 5: Risk Mgmt | 1 week | 1 backend | 60 | $6,000 |
| Phase 6: Integration | 2 weeks | 2 backend + DevOps + QA | 120 | $12,000 |
| **Total** | **10 weeks** | - | **540 hours** | **$54,000** |

### Ongoing Costs (Monthly)

| Category | Service | Cost |
|----------|---------|------|
| **APIs** | Alpha Vantage Premium | $50 |
| | Polygon.io (historical data) | $200 |
| | Interactive Brokers market data | $100 |
| **Infrastructure** | AWS EC2 (t3.large production) | $75 |
| | AWS RDS PostgreSQL (db.t3.medium) | $85 |
| | AWS ElastiCache Redis | $50 |
| | AWS S3 + CloudWatch | $30 |
| **Monitoring** | Sentry (error tracking) | $50 |
| | PagerDuty (alerts) | $40 |
| **ML Infrastructure** | GPU training (occasional) | $50 |
| **Total Monthly** | | **$730** |

### Revenue Projections

**Assumptions:**
- Average user account size: $10,000
- Monthly ROI target: 20%
- Platform fee: 20% of profits
- User retention: 80%

**Month 1:** 50 users → $10,000 profit/month → $2,000 revenue  
**Month 3:** 150 users → $30,000 profit/month → $6,000 revenue  
**Month 6:** 400 users → $80,000 profit/month → $16,000 revenue  

**Break-even:** ~Month 4 at 200 active users

---

## PART 8: SUCCESS CRITERIA

### Go-Live Requirements (All Must Pass)

**Trading Performance:**
- [ ] Win rate ≥75% in paper trading (minimum 50 trades)
- [ ] Sharpe ratio ≥1.5
- [ ] Maximum drawdown ≤20%
- [ ] No catastrophic losses (>50% single trade) in paper trading

**ML Model Performance:**
- [ ] LSTM volatility prediction MAE <5%
- [ ] IV crush prediction F1-score ≥0.82
- [ ] RL agent average reward positive over 1,000 episodes
- [ ] Earnings strategy router avoids 90%+ of high-crush events

**System Reliability:**
- [ ] IB connection uptime 99.9%
- [ ] Order execution success rate >98%
- [ ] Database query latency p95 <100ms
- [ ] Zero data loss incidents

**Testing:**
- [ ] Unit test coverage ≥90%
- [ ] All integration tests passing
- [ ] Load test: handle 100 concurrent users
- [ ] Paper trading: 2+ weeks, 50+ trades

**Documentation:**
- [ ] API documentation complete
- [ ] Deployment runbook
- [ ] Incident response playbook
- [ ] User guide for system monitoring

---

## PART 9: RISKS & MITIGATION

### Technical Risks

**Risk:** IB API changes break integration  
**Mitigation:** Version pinning, API wrapper abstraction layer, automated tests

**Risk:** ML models degrade over time (concept drift)  
**Mitigation:** Weekly retraining, performance monitoring, automated rollback

**Risk:** Database performance issues at scale  
**Mitigation:** Read replicas, TimescaleDB for time-series, Redis caching

**Risk:** Race conditions in order execution  
**Mitigation:** Database transactions, idempotency keys, order state machine

### Market Risks

**Risk:** Black swan events cause portfolio wipeout  
**Mitigation:** Portfolio delta/gamma limits, max position size 2%, circuit breakers

**Risk:** Earnings surprises despite ML predictions  
**Mitigation:** Conservative earnings avoidance (70%+ crush prob), position sizing

**Risk:** Liquidity dries up, can't exit positions  
**Mitigation:** VOSS filtering enforced, only trade high-liquidity options

### Operational Risks

**Risk:** Key personnel leave mid-project  
**Mitigation:** Comprehensive documentation, code reviews, knowledge sharing

**Risk:** AWS outage during market hours  
**Mitigation:** Multi-region deployment, manual failover procedures

**Risk:** Cost overruns  
**Mitigation:** Phased rollout, re-evaluate after each phase, kill switches

---

## PART 10: NEXT STEPS

### Immediate Actions (This Week)

1. **Antigravity:** Review this implementation plan, confirm scope and timeline
2. **Eric:** Approve budget and resource allocation
3. **Team:** Set up GitHub repository, project management (Jira/Linear)
4. **DevOps:** Provision AWS accounts, set up development environments
5. **Backend:** Begin Phase 1 (database schema, IB connection)

### Sprint Planning (Week 1)

**Sprint 1 (Weeks 1-2):** Foundation  
**Sprint 2 (Weeks 3-4):** Options Selection & Execution  
**Sprint 3 (Weeks 5-6):** Machine Learning Models  
**Sprint 4 (Week 7):** Earnings Intelligence  
**Sprint 5 (Week 8):** Risk Management  
**Sprint 6 (Weeks 9-10):** Integration & Testing  

### Communication Cadence

**Daily:** Standup (15 min) - blockers, progress, plan  
**Weekly:** Sprint review + planning (90 min)  
**Bi-weekly:** Eric/stakeholder demo (30 min)  
**Monthly:** Performance review, metrics analysis

### Decision Points

**End of Phase 2:** Validate options execution working correctly  
**End of Phase 3:** Validate ML models meet performance targets  
**End of Phase 6:** Go/no-go decision for production launch

---

## CONCLUSION

This implementation plan provides a complete roadmap for building a production-ready, AI-powered calendar spread trading system. The system leverages:

✅ **Research-backed option selection** (VOSS framework, 30-45 DTE, delta-based strikes)  
✅ **Advanced ML models** (LSTM volatility prediction, RL strike selection, Random Forest earnings intelligence)  
✅ **Robust risk management** (earnings-aware stops, portfolio Greeks limits, position adjustment triggers)  
✅ **Production-grade infrastructure** (PostgreSQL, Redis, IB API, monitoring)

**Expected Outcomes:**
- Win rate: 80-87%
- Monthly ROI: 15-25%
- Sharpe ratio: >1.8x
- Maximum drawdown: <15%

**Timeline:** 10 weeks to production launch  
**Total Investment:** ~$55,000 development + $730/month ongoing  
**Break-even:** ~4 months at 200 active users

This system will position TradeMind.bot as a leader in AI-powered options trading for the Gen Z market, with a clear competitive advantage through systematic calendar spread execution and earnings intelligence.

---

**Ready for development sprint. Let's build it.**

**Questions? Concerns? Let's discuss before we kick off.**
