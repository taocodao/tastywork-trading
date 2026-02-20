# PMCC Machine Learning Optimization Supplement
## Comprehensive AI/ML Enhancement for Automated Poor Man's Covered Call

***

## Overview: Why ML for PMCC Parameter Optimization

The base PMCC implementation plan defines static parameters (LEAPS delta 0.80, short call delta 0.20–0.30, 30–45 DTE, etc.) that work as reasonable defaults. However, these parameters are **not optimal across all market conditions**. Academic research demonstrates that machine learning models—particularly ensemble methods, LSTM networks, and reinforcement learning—can significantly outperform static parameters by adapting to regime shifts, volatility clustering, and dynamic support/resistance levels.[^1][^2][^3]

This supplement adds five ML modules to the existing PMCC system:

| Module | ML Technique | PMCC Parameters Optimized |
|--------|-------------|--------------------------|
| **A. Bayesian Parameter Optimization** | Optuna/Gaussian Process | All 13+ static parameters simultaneously |
| **B. Market Regime Detection** | Hidden Markov Model + Ensemble Voting | Short call delta, DTE, profit target, stop loss |
| **C. IV Forecasting & LEAPS Timing** | GARCH + LSTM/ConvLSTM | LEAPS entry timing, IV Rank entry threshold |
| **D. Adaptive Short Call Selection** | Contextual Bandit (LinUCB) | Short call strike, delta, DTE per cycle |
| **E. Position Management RL Agent** | PPO (Proximal Policy Optimization) | Roll timing, profit target, stop loss adjustment |

***

## Module A: Bayesian Parameter Optimization with Optuna

### A.1 Problem Statement

The PMCC strategy has 13+ interacting parameters. Grid search across all combinations would require millions of backtests. Bayesian optimization finds near-optimal configurations in 200–500 iterations by intelligently sampling the parameter space.[^4][^5]

### A.2 Architecture

```
┌──────────────────────────────────────┐
│         Optuna Study Manager          │
│  (Tree-Parzen Estimator Sampler)      │
├──────────────────────────────────────┤
│                                       │
│  Trial N:                             │
│  ┌───────────────┐                    │
│  │ Sample Params  │                    │
│  └──────┬────────┘                    │
│         ▼                             │
│  ┌───────────────┐                    │
│  │ PMCC Backtester│◄── Historical     │
│  │ (vectorbt or  │    Options Data    │
│  │  custom)       │                    │
│  └──────┬────────┘                    │
│         ▼                             │
│  ┌───────────────┐                    │
│  │ Evaluate       │                    │
│  │ Sharpe + ROC   │                    │
│  └──────┬────────┘                    │
│         ▼                             │
│  Update Surrogate Model               │
│  → Select Trial N+1                   │
└──────────────────────────────────────┘
```

### A.3 Search Space Definition

```python
import optuna

def objective(trial):
    """
    Optuna objective function for PMCC parameter optimization.
    Each trial runs a full backtest with sampled parameters.
    """
    
    # === LEAPS Parameters ===
    leaps_delta = trial.suggest_float('leaps_delta', 0.70, 0.90, step=0.05)
    leaps_min_dte = trial.suggest_int('leaps_min_dte', 270, 730, step=30)
    leaps_roll_trigger_dte = trial.suggest_int('leaps_roll_trigger_dte', 60, 180, step=15)
    leaps_max_extrinsic_ratio = trial.suggest_float('leaps_max_extrinsic_ratio', 0.15, 0.35, step=0.05)
    
    # === Short Call Parameters ===
    short_delta_min = trial.suggest_float('short_delta_min', 0.10, 0.20, step=0.05)
    short_delta_max = trial.suggest_float('short_delta_max', 0.25, 0.45, step=0.05)
    short_dte_target = trial.suggest_int('short_dte_target', 21, 60, step=7)
    use_resistance = trial.suggest_categorical('use_resistance', [True, False])
    resistance_proximity_pct = trial.suggest_float('resistance_proximity_pct', 0.01, 0.05, step=0.005)
    
    # === Management Parameters ===
    profit_target_pct = trial.suggest_float('profit_target_pct', 0.30, 0.80, step=0.05)
    stop_loss_pct = trial.suggest_float('stop_loss_pct', -2.0, -0.50, step=0.25)
    roll_trigger_delta = trial.suggest_float('roll_trigger_delta', 0.40, 0.60, step=0.05)
    
    # === Portfolio Parameters ===
    max_positions = trial.suggest_int('max_positions', 4, 12, step=1)
    max_capital_pct = trial.suggest_float('max_capital_pct', 0.40, 0.80, step=0.05)
    iv_rank_entry_threshold = trial.suggest_float('iv_rank_entry_threshold', 15, 50, step=5)
    
    # === Entry Timing Parameters ===
    min_premium_pct = trial.suggest_float('min_premium_pct', 0.005, 0.025, step=0.005)
    
    # Run PMCC backtest with these parameters
    params = {
        'leaps_delta': leaps_delta,
        'leaps_min_dte': leaps_min_dte,
        'leaps_roll_trigger_dte': leaps_roll_trigger_dte,
        'leaps_max_extrinsic_ratio': leaps_max_extrinsic_ratio,
        'short_delta_min': short_delta_min,
        'short_delta_max': short_delta_max,
        'short_dte_target': short_dte_target,
        'use_resistance': use_resistance,
        'resistance_proximity_pct': resistance_proximity_pct,
        'profit_target_pct': profit_target_pct,
        'stop_loss_pct': stop_loss_pct,
        'roll_trigger_delta': roll_trigger_delta,
        'max_positions': max_positions,
        'max_capital_pct': max_capital_pct,
        'iv_rank_entry_threshold': iv_rank_entry_threshold,
        'min_premium_pct': min_premium_pct,
    }
    
    results = run_pmcc_backtest(params, start_date='2019-01-01', end_date='2024-12-31')
    
    # Multi-objective: maximize Sharpe AND annualized ROC
    sharpe = results['sharpe_ratio']
    roc = results['annualized_roc']
    max_dd = results['max_drawdown']
    
    # Penalize if max drawdown exceeds threshold
    if max_dd > 0.40:
        return float('-inf')
    
    # Composite score: 60% Sharpe + 30% ROC + 10% Win Rate
    composite = 0.60 * sharpe + 0.30 * (roc / 100) + 0.10 * results['win_rate']
    
    return composite


def run_optimization():
    """
    Run Bayesian optimization with Optuna.
    Uses TPE sampler (Tree-Parzen Estimator) - proven superior
    for trading strategy optimization.
    """
    study = optuna.create_study(
        study_name='pmcc_optimization',
        direction='maximize',
        sampler=optuna.samplers.TPESampler(
            n_startup_trials=50,      # Random exploration first
            multivariate=True,        # Model parameter interactions
            seed=42
        ),
        pruner=optuna.pruners.MedianPruner(
            n_startup_trials=30,
            n_warmup_steps=60         # Don't prune early backtests
        ),
        storage='sqlite:///pmcc_optuna.db'  # Persist results
    )
    
    study.optimize(objective, n_trials=500, n_jobs=4)  # Parallel backtests
    
    print(f"Best params: {study.best_params}")
    print(f"Best value: {study.best_value}")
    
    return study
```

### A.4 Walk-Forward Validation (Anti-Overfitting)

Static optimization on a single period leads to overfitting. Walk-forward optimization (WFO) re-optimizes parameters on rolling windows to ensure robustness:[^6][^7][^8]

```python
def walk_forward_optimization(data, in_sample_months=36, out_sample_months=6):
    """
    Walk-forward optimization to prevent overfitting.
    
    Process:
    1. Optimize on 36-month in-sample window
    2. Test on next 6-month out-of-sample window  
    3. Slide forward 6 months, repeat
    4. Aggregate OOS results for true performance estimate
    """
    results = []
    current_start = data.index.min()
    
    while current_start + timedelta(days=(in_sample_months + out_sample_months) * 30) <= data.index.max():
        
        is_end = current_start + timedelta(days=in_sample_months * 30)
        oos_end = is_end + timedelta(days=out_sample_months * 30)
        
        # In-sample: optimize
        is_data = data[current_start:is_end]
        best_params = run_optuna_on_data(is_data, n_trials=200)
        
        # Out-of-sample: validate with optimized params
        oos_data = data[is_end:oos_end]
        oos_result = run_pmcc_backtest(best_params, data=oos_data)
        
        results.append({
            'period': f"{is_end.strftime('%Y-%m')} to {oos_end.strftime('%Y-%m')}",
            'params': best_params,
            'oos_sharpe': oos_result['sharpe_ratio'],
            'oos_roc': oos_result['annualized_roc'],
            'oos_win_rate': oos_result['win_rate'],
        })
        
        current_start += timedelta(days=out_sample_months * 30)
    
    # Analyze parameter stability across windows
    param_stability = analyze_parameter_stability(results)
    
    return results, param_stability


def analyze_parameter_stability(wfo_results):
    """
    Check if optimized parameters are stable across windows.
    Stable parameters = robust strategy; unstable = overfitting risk.
    """
    import pandas as pd
    
    params_df = pd.DataFrame([r['params'] for r in wfo_results])
    
    stability_report = {}
    for col in params_df.columns:
        stability_report[col] = {
            'mean': params_df[col].mean(),
            'std': params_df[col].std(),
            'cv': params_df[col].std() / params_df[col].mean(),  # Coefficient of variation
            'stable': params_df[col].std() / params_df[col].mean() < 0.20  # CV < 20% = stable
        }
    
    return stability_report
```

### A.5 Expected Output

After running 500 trials with walk-forward validation, the system produces:

- **Optimized parameter set** per regime (bull, bear, sideways)
- **Stability report** showing which parameters are robust vs. sensitive
- **Sharpe improvement** estimate vs. static defaults (research shows Bayesian optimization typically improves Sharpe by 15–40% over manual parameter selection)[^5]

***

## Module B: Market Regime Detection (HMM + Ensemble)

### B.1 Rationale

The PMCC video explicitly states: sell differently based on market trend. Rather than simple SMA-based trend detection (Module 9 in the base plan), this ML approach uses a Hidden Markov Model to detect latent regime states with probabilistic confidence.[^3][^9][^10]

### B.2 Architecture

```
Market Data → Feature Engineering → HMM Regime Classifier
                                          │
                                          ▼
                                   Regime: {BULL, BEAR, SIDEWAYS, 
                                            HIGH_VOL, LOW_VOL}
                                          │
                                          ▼
                               Parameter Adjustment Table
                                          │
                                          ▼
                               Modified PMCC Parameters
```

### B.3 Implementation

```python
from hmmlearn.hmm import GaussianHMM
import numpy as np
import pandas as pd

class MarketRegimeDetector:
    """
    Hidden Markov Model for detecting market regimes.
    Uses ensemble of HMM + XGBoost for robust classification.
    
    Research shows HMM combined with ensemble methods enhances
    regime classification robustness significantly.
    """
    
    def __init__(self, n_regimes=3):
        self.n_regimes = n_regimes
        self.hmm = GaussianHMM(
            n_components=n_regimes,
            covariance_type='full',
            n_iter=1000,
            random_state=42
        )
        self.regime_labels = {}  # Mapped after training
        self.scaler = None
    
    def engineer_features(self, price_data, vix_data=None):
        """
        Feature engineering for regime detection.
        Multi-factor approach: volatility, returns, momentum, microstructure.
        """
        df = pd.DataFrame()
        
        # Return features
        df['returns_1d'] = price_data['close'].pct_change(1)
        df['returns_5d'] = price_data['close'].pct_change(5)
        df['returns_21d'] = price_data['close'].pct_change(21)
        
        # Volatility features (multiple timeframes)
        df['vol_5d'] = df['returns_1d'].rolling(5).std() * np.sqrt(252)
        df['vol_21d'] = df['returns_1d'].rolling(21).std() * np.sqrt(252)
        df['vol_63d'] = df['returns_1d'].rolling(63).std() * np.sqrt(252)
        df['vol_ratio'] = df['vol_5d'] / df['vol_63d']  # Vol regime indicator
        
        # Momentum features
        df['sma_50_200_ratio'] = (
            price_data['close'].rolling(50).mean() / 
            price_data['close'].rolling(200).mean()
        )
        df['rsi_14'] = self._calculate_rsi(price_data['close'], 14)
        df['macd_signal'] = self._calculate_macd_signal(price_data['close'])
        
        # Skewness and kurtosis (distribution shape)
        df['return_skew_21d'] = df['returns_1d'].rolling(21).skew()
        df['return_kurt_21d'] = df['returns_1d'].rolling(21).kurt()
        
        # Volume features
        df['volume_ratio'] = (
            price_data['volume'].rolling(5).mean() / 
            price_data['volume'].rolling(21).mean()
        )
        
        # VIX integration (if available)
        if vix_data is not None:
            df['vix_level'] = vix_data['close']
            df['vix_change_5d'] = vix_data['close'].pct_change(5)
            df['vix_term_structure'] = vix_data.get('term_structure', 0)
        
        return df.dropna()
    
    def fit(self, features_df):
        """Train HMM on historical features."""
        from sklearn.preprocessing import StandardScaler
        
        self.scaler = StandardScaler()
        X = self.scaler.fit_transform(features_df.values)
        
        self.hmm.fit(X)
        
        # Map regime labels based on mean returns
        regimes = self.hmm.predict(X)
        for regime_id in range(self.n_regimes):
            mask = regimes == regime_id
            mean_return = features_df['returns_21d'][mask].mean()
            mean_vol = features_df['vol_21d'][mask].mean()
            
            # Label regimes by characteristics
            if mean_return > 0.005 and mean_vol < 0.20:
                self.regime_labels[regime_id] = 'BULL_LOW_VOL'
            elif mean_return > 0.005 and mean_vol >= 0.20:
                self.regime_labels[regime_id] = 'BULL_HIGH_VOL'
            elif mean_return < -0.005 and mean_vol >= 0.20:
                self.regime_labels[regime_id] = 'BEAR_HIGH_VOL'
            elif mean_return < -0.005 and mean_vol < 0.20:
                self.regime_labels[regime_id] = 'BEAR_LOW_VOL'
            else:
                self.regime_labels[regime_id] = 'SIDEWAYS'
    
    def predict_regime(self, features_df):
        """Predict current regime with confidence scores."""
        X = self.scaler.transform(features_df.values[-1:])
        
        # Get probability of each regime
        regime_probs = self.hmm.predict_proba(X)
        predicted_regime = self.hmm.predict(X)
        
        return {
            'regime': self.regime_labels.get(predicted_regime, 'UNKNOWN'),
            'regime_id': int(predicted_regime),
            'confidence': float(regime_probs[predicted_regime]),
            'probabilities': {
                self.regime_labels.get(i, f'regime_{i}'): float(p) 
                for i, p in enumerate(regime_probs)
            },
            'transition_risk': self._assess_transition_risk(regime_probs)
        }
    
    def _assess_transition_risk(self, probs):
        """Detect if regime transition is likely (high entropy)."""
        from scipy.stats import entropy
        regime_entropy = entropy(probs)
        max_entropy = np.log(self.n_regimes)
        normalized_entropy = regime_entropy / max_entropy
        
        if normalized_entropy > 0.70:
            return 'HIGH'   # Regime transition likely
        elif normalized_entropy > 0.40:
            return 'MEDIUM' # Uncertain
        return 'LOW'        # Stable regime
```

### B.4 Regime-Adaptive Parameter Mapping

```python
REGIME_PARAMETER_MAP = {
    'BULL_LOW_VOL': {
        'short_delta_target': 0.20,        # Preserve upside
        'short_dte': 30,                   # Standard cycle
        'profit_target_pct': 0.50,         # Standard profit target
        'stop_loss_pct': -1.00,            # Standard stop
        'strike_method': 'RESISTANCE',     # Sell at resistance
        'position_size_multiplier': 1.2,   # Slightly overweight
        'description': 'Ideal PMCC conditions - maximize cycles'
    },
    'BULL_HIGH_VOL': {
        'short_delta_target': 0.25,        # Capture elevated premiums
        'short_dte': 45,                   # Longer DTE for safety
        'profit_target_pct': 0.40,         # Take profits faster
        'stop_loss_pct': -0.75,            # Tighter stop
        'strike_method': 'RESISTANCE',     # Still use resistance
        'position_size_multiplier': 1.0,   # Standard size
        'description': 'Good premiums but volatile - be cautious'
    },
    'BEAR_HIGH_VOL': {
        'short_delta_target': 0.35,        # Aggressive premium collection
        'short_dte': 21,                   # Shorter DTE, faster cycles
        'profit_target_pct': 0.30,         # Quick profits
        'stop_loss_pct': -0.50,            # Very tight stop
        'strike_method': 'ATM_NEAR',       # Sell near ATM per video advice
        'position_size_multiplier': 0.60,  # Reduce size significantly
        'description': 'Defensive mode - maximize premium, minimize exposure'
    },
    'BEAR_LOW_VOL': {
        'short_delta_target': 0.30,        # Moderate premium capture
        'short_dte': 30,                   # Standard
        'profit_target_pct': 0.40,         # Slightly faster exits
        'stop_loss_pct': -0.75,            # Moderate stop
        'strike_method': 'DELTA_FALLBACK', # Low premium environment
        'position_size_multiplier': 0.50,  # Underweight significantly
        'description': 'Consider pausing new entries'
    },
    'SIDEWAYS': {
        'short_delta_target': 0.25,        # Balanced approach
        'short_dte': 30,                   # Standard cycle
        'profit_target_pct': 0.50,         # Standard
        'stop_loss_pct': -1.00,            # Standard
        'strike_method': 'RANGE_TOP',      # Sell at top of range
        'position_size_multiplier': 1.0,   # Standard size
        'description': 'Sweet spot for premium selling'
    }
}


def adjust_parameters_for_regime(base_params, regime_output):
    """
    Dynamically adjust PMCC parameters based on detected regime.
    Blend base (Optuna-optimized) with regime adjustments.
    """
    regime = regime_output['regime']
    confidence = regime_output['confidence']
    transition_risk = regime_output['transition_risk']
    
    regime_params = REGIME_PARAMETER_MAP.get(regime, REGIME_PARAMETER_MAP['SIDEWAYS'])
    
    adjusted = base_params.copy()
    
    # Blend: high confidence = more regime influence; low = more base
    blend_weight = confidence  # 0.0 to 1.0
    
    for key in ['short_delta_target', 'profit_target_pct', 'stop_loss_pct']:
        if key in regime_params and key in base_params:
            adjusted[key] = (
                base_params[key] * (1 - blend_weight) + 
                regime_params[key] * blend_weight
            )
    
    # If transition risk is HIGH, reduce position sizes
    if transition_risk == 'HIGH':
        adjusted['position_size_multiplier'] = min(
            regime_params.get('position_size_multiplier', 1.0), 
            0.70
        )
        adjusted['short_dte'] = max(21, adjusted.get('short_dte', 30) - 7)
    
    adjusted['strike_method'] = regime_params['strike_method']
    adjusted['regime_note'] = regime_params['description']
    
    return adjusted
```

### B.5 Retraining Schedule

- **Weekly**: Refit HMM on rolling 2-year window
- **On VIX spike > 30**: Immediate re-prediction
- **Monthly**: Full walk-forward validation of regime detection accuracy

***

## Module C: IV Forecasting & LEAPS Entry Timing

### C.1 Problem Statement

The base plan specifies "enter LEAPS when IV Rank < 30." ML can do better by forecasting whether IV will decline further (wait) or is at a trough (enter now). Research shows LSTM models outperform GARCH for short-maturity IV forecasting, while GARCH is superior for longer maturities. For LEAPS (long-dated), a hybrid approach is optimal.[^11][^12][^13][^14][^15]

### C.2 Two-Model Architecture

```
┌─────────────────────────────────────────────┐
│          IV Forecasting Pipeline             │
├─────────────────────────────────────────────┤
│                                              │
│  Model 1: GARCH(1,1) / EGARCH               │
│  ├── Forecasts: Realized vol 1-week ahead    │
│  ├── Input: Historical returns               │
│  └── Output: Conditional variance forecast   │
│                                              │
│  Model 2: LSTM Network                       │
│  ├── Forecasts: IV surface 30-day ahead      │
│  ├── Input: IV term structure, Greeks,       │
│  │          volume, VIX, macro features       │
│  └── Output: Predicted IV for target LEAPS   │
│                                              │
│  Ensemble: Weighted average (GARCH 40%,      │
│            LSTM 60% for LEAPS maturities)    │
│                                              │
│  Decision Engine:                            │
│  ├── Predicted IV < Current IV → ENTER NOW   │
│  ├── Predicted IV > Current IV → WAIT        │
│  └── Confidence < 60% → DEFAULT (IV Rank<30) │
└─────────────────────────────────────────────┘
```

### C.3 LSTM IV Forecasting Model

```python
import torch
import torch.nn as nn

class IVForecastLSTM(nn.Module):
    """
    LSTM model for forecasting implied volatility.
    Research shows LSTM captures rapid IV changes better than 
    traditional time series models, with MAPE ~3.5% in-sample.
    ConvLSTM further improves to 8.26% MAPE out-of-sample.
    """
    
    def __init__(self, input_size, hidden_size=128, num_layers=2, 
                 output_horizon=30, dropout=0.2):
        super().__init__()
        
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout
        )
        
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size, 
            num_heads=4,
            batch_first=True
        )
        
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, output_horizon)  # Predict 30 days ahead
        )
    
    def forward(self, x):
        # x shape: (batch, seq_len, features)
        lstm_out, _ = self.lstm(x)
        
        # Self-attention for capturing long-range dependencies
        attn_out, _ = self.attention(lstm_out, lstm_out, lstm_out)
        
        # Use last time step
        out = self.fc(attn_out[:, -1, :])
        return out  # Shape: (batch, 30) — 30-day IV forecast


class IVFeatureEngineer:
    """
    Feature engineering for IV prediction model.
    """
    
    FEATURE_LIST = [
        # IV surface features
        'iv_atm',                    # ATM implied volatility
        'iv_25d_put',               # 25-delta put IV
        'iv_25d_call',              # 25-delta call IV
        'iv_skew',                  # Put-call IV skew
        'iv_term_slope',            # IV term structure slope
        'iv_rank_30d',              # 30-day IV rank
        'iv_percentile_252d',       # 1-year IV percentile
        
        # Realized vol features
        'rv_5d',                    # 5-day realized vol
        'rv_21d',                   # 21-day realized vol
        'rv_iv_spread',             # RV - IV spread (vol risk premium)
        
        # Greeks-derived
        'avg_delta',                # Average delta of target strikes
        'gamma_exposure',           # Market gamma exposure
        'vanna_exposure',           # Vanna (dDelta/dVol)
        
        # Market microstructure
        'option_volume_ratio',      # Put/call volume ratio
        'open_interest_change',     # OI change rate
        
        # Macro features
        'vix_level',                # VIX
        'vix_futures_curve',        # VIX contango/backwardation
        'yield_10y',                # 10-year treasury
        'dxy_change',               # Dollar index change
        
        # Calendar features
        'days_to_fomc',             # Days until next FOMC
        'days_to_earnings',         # Days until earnings
        'day_of_week',              # Intra-week seasonality
        'month_of_year',            # Monthly seasonality
    ]
    
    def build_features(self, options_data, market_data, lookback=60):
        """Build feature matrix with 60-day lookback sequences."""
        features = pd.DataFrame()
        
        for feat in self.FEATURE_LIST:
            if feat in options_data.columns:
                features[feat] = options_data[feat]
            elif feat in market_data.columns:
                features[feat] = market_data[feat]
        
        # Create sequences of shape (n_samples, lookback, n_features)
        sequences = []
        targets = []
        
        for i in range(lookback, len(features) - 30):
            seq = features.iloc[i-lookback:i].values
            target = features['iv_atm'].iloc[i:i+30].values  # 30-day ahead IV
            sequences.append(seq)
            targets.append(target)
        
        return np.array(sequences), np.array(targets)
```

### C.4 LEAPS Entry Signal Generator

```python
class LEAPSEntrySignal:
    """
    Combines IV forecast with technical and fundamental signals
    to generate LEAPS entry timing recommendations.
    """
    
    def generate_signal(self, symbol, iv_forecast, current_iv_rank, regime):
        """
        Decision matrix for LEAPS entry timing.
        
        Returns: {'action': 'ENTER'|'WAIT'|'AVOID', 'confidence': 0-1, 'reason': str}
        """
        predicted_iv_30d = iv_forecast['predicted_iv_30d_ahead']
        current_iv = iv_forecast['current_iv']
        iv_direction = (predicted_iv_30d - current_iv) / current_iv
        model_confidence = iv_forecast['confidence']
        
        # === Decision Rules ===
        
        # Rule 1: Strong entry signal
        if (current_iv_rank < 25 and 
            iv_direction > 0.0 and  # IV expected to rise → LEAPS get more expensive
            model_confidence > 0.65 and
            regime['regime'] in ['BULL_LOW_VOL', 'SIDEWAYS']):
            return {
                'action': 'ENTER',
                'confidence': min(model_confidence, 0.90),
                'reason': f'IV Rank low ({current_iv_rank:.0f}), IV forecast rising, '
                          f'favorable regime ({regime["regime"]})',
                'urgency': 'HIGH'
            }
        
        # Rule 2: Good but not urgent
        if (current_iv_rank < 35 and 
            regime['regime'] not in ['BEAR_HIGH_VOL'] and
            model_confidence > 0.55):
            return {
                'action': 'ENTER',
                'confidence': model_confidence * 0.80,
                'reason': f'Acceptable IV Rank ({current_iv_rank:.0f}), moderate confidence',
                'urgency': 'MEDIUM'
            }
        
        # Rule 3: Wait for better entry
        if iv_direction < -0.05 and model_confidence > 0.60:
            return {
                'action': 'WAIT',
                'confidence': model_confidence,
                'reason': f'IV predicted to drop {iv_direction*100:.1f}% in 30 days — wait',
                'urgency': 'LOW'
            }
        
        # Rule 4: Adverse conditions
        if regime['regime'] == 'BEAR_HIGH_VOL' and current_iv_rank > 60:
            return {
                'action': 'AVOID',
                'confidence': 0.70,
                'reason': 'High IV + bear regime — LEAPS too expensive',
                'urgency': 'NONE'
            }
        
        # Default: use base IV Rank rule
        if current_iv_rank < 30:
            return {'action': 'ENTER', 'confidence': 0.50, 
                    'reason': 'Default IV Rank < 30 rule', 'urgency': 'MEDIUM'}
        
        return {'action': 'WAIT', 'confidence': 0.40, 
                'reason': 'No strong signal — wait', 'urgency': 'LOW'}
```

### C.5 Training Pipeline

- **Data**: 5+ years of historical options chain data (OptionMetrics, Polygon.io, or CBOE DataShop)
- **Training**: Walk-forward with 3-year in-sample, 6-month out-of-sample
- **Retraining**: Monthly, with online updates on daily IV observations
- **Metrics**: MAPE, directional accuracy, profit improvement vs. static IV Rank < 30 rule

***

## Module D: Contextual Bandit for Adaptive Short Call Selection

### D.1 Rationale

Instead of a fixed short call strategy, a **contextual bandit** (LinUCB) learns online which short call parameters perform best given the current market context. This is superior to fully offline optimization because it adapts continuously.[^16][^17][^18]

The "arms" of the bandit are different short call configurations, and the "context" is the current market state.

### D.2 Architecture

```
Context Vector (Market State)
    ├── Current regime (from Module B)
    ├── IV Rank
    ├── Days since last short call
    ├── Current LEAPS P/L
    ├── RSI, MACD, volume ratio
    ├── Resistance level proximity
    ├── Earnings distance
    └── Sector momentum
          │
          ▼
    ┌─────────────────┐
    │   LinUCB Agent    │
    │                   │
    │   Arms:           │
    │   Arm 0: Δ=0.15, DTE=45, Resistance    │
    │   Arm 1: Δ=0.20, DTE=30, Resistance    │
    │   Arm 2: Δ=0.25, DTE=30, Delta         │
    │   Arm 3: Δ=0.30, DTE=45, Delta         │
    │   Arm 4: Δ=0.35, DTE=21, ATM           │
    │   Arm 5: SKIP (don't sell this cycle)   │
    └─────────┬───────┘
              ▼
    Selected Arm → Execute Short Call → Observe Reward
                                              │
                                              ▼
                                     Update LinUCB Parameters
```

### D.3 Implementation

```python
import numpy as np

class PMCCContextualBandit:
    """
    LinUCB contextual bandit for adaptive short call selection.
    
    Each 'arm' represents a different short call configuration.
    The bandit learns which configuration works best in each context.
    
    This approach naturally balances exploration (trying new configurations)
    with exploitation (using proven configurations).
    """
    
    def __init__(self, n_arms=6, context_dim=15, alpha=0.25):
        """
        alpha: Exploration parameter (higher = more exploration).
               Start at 0.25, decay to 0.10 over time.
        """
        self.n_arms = n_arms
        self.context_dim = context_dim
        self.alpha = alpha
        
        # Per-arm parameters
        self.A = [np.eye(context_dim) for _ in range(n_arms)]
        self.b = [np.zeros(context_dim) for _ in range(n_arms)]
        
        # Arm definitions
        self.arms = [
            {'delta': 0.15, 'dte': 45, 'method': 'RESISTANCE', 'name': 'Conservative-Resistance'},
            {'delta': 0.20, 'dte': 30, 'method': 'RESISTANCE', 'name': 'Moderate-Resistance'},
            {'delta': 0.25, 'dte': 30, 'method': 'DELTA',      'name': 'Balanced-Delta'},
            {'delta': 0.30, 'dte': 45, 'method': 'DELTA',      'name': 'Income-Delta'},
            {'delta': 0.35, 'dte': 21, 'method': 'ATM_NEAR',   'name': 'Aggressive-ATM'},
            {'delta': None, 'dte': None, 'method': 'SKIP',      'name': 'Skip-Cycle'},
        ]
        
        self.history = []
    
    def build_context(self, symbol_data, portfolio_state, regime_output):
        """
        Build context vector from current market state.
        """
        context = np.array([
            regime_output['probabilities'].get('BULL_LOW_VOL', 0),
            regime_output['probabilities'].get('BEAR_HIGH_VOL', 0),
            regime_output['probabilities'].get('SIDEWAYS', 0),
            symbol_data['iv_rank'] / 100.0,
            symbol_data['rsi_14'] / 100.0,
            symbol_data['macd_signal_normalized'],
            symbol_data['volume_ratio'],
            symbol_data['resistance_proximity'],    # 0-1, how close to resistance
            symbol_data['support_proximity'],       # 0-1, how close to support
            symbol_data['days_to_earnings'] / 90.0, # Normalized
            symbol_data['sma_50_200_ratio'],
            portfolio_state['current_leaps_pnl_pct'],
            portfolio_state['cycles_completed'] / 12.0,
            symbol_data['atr_pct'],                 # ATR as % of price
            symbol_data['put_call_ratio'],
        ])
        
        return context
    
    def select_arm(self, context):
        """
        LinUCB arm selection with Upper Confidence Bound.
        Balances exploration and exploitation.
        """
        ucb_scores = np.zeros(self.n_arms)
        
        for arm in range(self.n_arms):
            A_inv = np.linalg.inv(self.A[arm])
            theta = A_inv @ self.b[arm]
            
            # UCB score = predicted reward + exploration bonus
            predicted_reward = context @ theta
            exploration_bonus = self.alpha * np.sqrt(context @ A_inv @ context)
            
            ucb_scores[arm] = predicted_reward + exploration_bonus
        
        selected_arm = np.argmax(ucb_scores)
        
        return selected_arm, self.arms[selected_arm], {
            'ucb_scores': ucb_scores.tolist(),
            'exploitation_scores': [
                float(context @ np.linalg.inv(self.A[a]) @ self.b[a]) 
                for a in range(self.n_arms)
            ],
            'confidence': float(ucb_scores[selected_arm] - np.sort(ucb_scores)[-2])
        }
    
    def update(self, arm_index, context, reward):
        """
        Update arm parameters after observing reward.
        
        Reward = normalized P/L of the short call cycle:
            reward = (premium_collected - exit_cost) / leaps_cost
            Positive = profitable cycle, Negative = loss
        """
        self.A[arm_index] += np.outer(context, context)
        self.b[arm_index] += reward * context
        
        self.history.append({
            'arm': arm_index,
            'arm_name': self.arms[arm_index]['name'],
            'context': context.tolist(),
            'reward': reward,
        })
    
    def get_arm_performance(self):
        """Report arm performance statistics."""
        import pandas as pd
        
        df = pd.DataFrame(self.history)
        if df.empty:
            return "No history yet"
        
        report = df.groupby('arm_name').agg(
            count=('reward', 'count'),
            mean_reward=('reward', 'mean'),
            std_reward=('reward', 'std'),
            win_rate=('reward', lambda x: (x > 0).mean()),
            total_reward=('reward', 'sum'),
        ).sort_values('mean_reward', ascending=False)
        
        return report
    
    def decay_exploration(self, min_alpha=0.05, decay_rate=0.995):
        """Gradually reduce exploration over time."""
        self.alpha = max(min_alpha, self.alpha * decay_rate)
```

### D.4 Reward Function Design

```python
def calculate_bandit_reward(cycle_result, leaps_cost):
    """
    Multi-factor reward that captures both P/L and risk-adjusted quality.
    
    Components:
    1. Premium P/L (primary signal)
    2. Risk efficiency (Sharpe-like)
    3. Assignment avoidance bonus
    4. Time efficiency (faster profit = better)
    """
    
    # P/L component (normalized by LEAPS cost)
    pnl_reward = cycle_result['pnl'] / leaps_cost
    
    # Time efficiency: profiting in fewer days is better
    days_held = cycle_result['days_held']
    target_days = cycle_result['target_dte']
    time_efficiency = (target_days - days_held) / target_days if pnl_reward > 0 else 0
    
    # Assignment penalty
    assignment_penalty = -0.50 if cycle_result['was_assigned'] else 0
    
    # Smooth profit bonus (hit profit target vs. stop loss)
    if cycle_result['exit_reason'] == 'PROFIT_TARGET':
        exit_bonus = 0.10
    elif cycle_result['exit_reason'] == 'STOP_LOSS':
        exit_bonus = -0.10
    else:
        exit_bonus = 0
    
    # Combined reward
    reward = (
        0.60 * pnl_reward +
        0.15 * time_efficiency +
        0.15 * exit_bonus +
        0.10 * assignment_penalty
    )
    
    return np.clip(reward, -1.0, 1.0)  # Bound rewards
```

***

## Module E: PPO Reinforcement Learning for Position Management

### E.1 Problem Statement

The rolling and exit decisions (when to close, when to roll, when to accept a loss) are sequential decisions with long-term consequences. PPO—the same algorithm used to train ChatGPT—learns optimal policies through trial and error, making it well-suited for this problem.[^19][^20][^21][^22]

### E.2 RL Environment Definition

```python
import gymnasium as gym
from gymnasium import spaces

class PMCCManagementEnv(gym.Env):
    """
    Gymnasium environment for PMCC position management.
    
    The agent manages an existing PMCC position (LEAPS + short call)
    and decides at each timestep whether to hold, close, roll, or adjust.
    
    State: Current position Greeks, market conditions, P/L
    Action: Hold, Close short, Roll up/out, Roll down/out, Close entire position
    Reward: Risk-adjusted P/L over episode
    """
    
    def __init__(self, historical_data, options_chain_data):
        super().__init__()
        
        self.data = historical_data
        self.options = options_chain_data
        
        # === Observation Space (26 features) ===
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(26,), dtype=np.float32
        )
        
        # === Action Space ===
        self.action_space = spaces.Discrete(6)
        # 0: HOLD - Do nothing
        # 1: CLOSE_SHORT - Buy back short call only (prepare to resell)
        # 2: ROLL_UP_OUT - Roll short call to higher strike + further expiry
        # 3: ROLL_DOWN_IN - Roll short call to lower strike (defensive)
        # 4: CLOSE_ALL - Close entire PMCC position
        # 5: ADD_PROTECTION - Buy protective put (emergency)
        
        self.position = None
        self.step_count = 0
        self.max_steps = 252  # 1 year max
    
    def _get_observation(self):
        """Build state vector from current position and market."""
        market = self.data.iloc[self.current_idx]
        
        obs = np.array([
            # Position state (8 features)
            self.position['leaps_delta'],
            self.position['short_delta'],
            self.position['net_delta'],
            self.position['short_pnl_pct'],        # Short call P/L as % of premium
            self.position['total_pnl_pct'],         # Total PMCC P/L
            self.position['short_dte_remaining'] / 60.0,  # Normalized
            self.position['leaps_dte_remaining'] / 365.0,
            self.position['premium_collected_pct'],  # Cumulative premium / LEAPS cost
            
            # Market features (10 features)
            market['returns_1d'],
            market['returns_5d'],
            market['vol_21d'] / 0.30,               # Normalized
            market['iv_rank'] / 100.0,
            market['rsi_14'] / 100.0,
            market['distance_to_resistance_pct'],
            market['distance_to_support_pct'],
            market['sma_50_200_ratio'],
            market['volume_ratio'],
            market['vix_level'] / 40.0,
            
            # Regime probabilities (3 features)
            market.get('regime_bull_prob', 0.33),
            market.get('regime_bear_prob', 0.33),
            market.get('regime_sideways_prob', 0.34),
            
            # Calendar features (3 features)
            market.get('days_to_earnings', 90) / 90.0,
            market.get('day_of_week', 2) / 4.0,
            market.get('days_to_monthly_opex', 30) / 30.0,
            
            # Risk metrics (2 features)
            self.position.get('max_drawdown_current', 0),
            self.position.get('gamma_risk', 0),
        ], dtype=np.float32)
        
        return obs
    
    def step(self, action):
        """Execute action and return next state, reward, done."""
        
        prev_total_value = self.position['total_value']
        
        # Execute action
        if action == 0:  # HOLD
            pass
        elif action == 1:  # CLOSE_SHORT
            self._close_short_call()
        elif action == 2:  # ROLL_UP_OUT
            self._roll_up_and_out()
        elif action == 3:  # ROLL_DOWN_IN
            self._roll_down_and_in()
        elif action == 4:  # CLOSE_ALL
            self._close_entire_position()
        elif action == 5:  # ADD_PROTECTION
            self._add_protective_put()
        
        # Advance market by 1 day
        self.current_idx += 1
        self.step_count += 1
        self._update_position_values()
        
        # Calculate reward
        reward = self._calculate_reward(action, prev_total_value)
        
        # Check termination conditions
        done = (
            self.step_count >= self.max_steps or
            self.position['status'] == 'CLOSED' or
            self.current_idx >= len(self.data) - 1 or
            self.position['total_pnl_pct'] < -0.50  # 50% max loss
        )
        
        truncated = self.step_count >= self.max_steps
        
        return self._get_observation(), reward, done, truncated, {}
    
    def _calculate_reward(self, action, prev_value):
        """
        Multi-component reward function.
        Encourages: profitable exits, good rolling, risk management
        Penalizes: excessive trading, assignment, large drawdowns
        """
        current_value = self.position['total_value']
        pnl_change = (current_value - prev_value) / self.position['leaps_cost']
        
        # Base reward: P/L change
        reward = pnl_change * 10  # Scale for learning
        
        # Transaction cost penalty
        if action in [1, 2, 3, 5]:  # Any trade action
            reward -= 0.01  # Bid-ask spread + commission
        
        # Bonus: closed short call profitably
        if action == 1 and self.position['short_pnl_pct'] > 0.30:
            reward += 0.05
        
        # Penalty: assignment occurred
        if self.position.get('assigned', False):
            reward -= 0.20
        
        # Penalty: short call went deep ITM without rolling
        if action == 0 and self.position['short_delta'] > 0.60:
            reward -= 0.03  # Should have rolled
        
        # Bonus: good LEAPS management (rolled before too late)
        if self.position['leaps_dte_remaining'] < 90 and action == 4:
            reward += 0.02  # Closed position before LEAPS decay acceleration
        
        # Risk-adjusted: penalize high drawdown
        if self.position['max_drawdown_current'] > 0.25:
            reward -= 0.01 * (self.position['max_drawdown_current'] - 0.25)
        
        return float(reward)


class PPOTrainer:
    """
    Train PPO agent for PMCC management using stable-baselines3.
    """
    
    def train(self, env, total_timesteps=500_000):
        from stable_baselines3 import PPO
        from stable_baselines3.common.callbacks import EvalCallback
        
        model = PPO(
            "MlpPolicy",
            env,
            learning_rate=3e-4,
            n_steps=2048,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,         # Discount factor (long-term focus)
            gae_lambda=0.95,    # GAE lambda
            clip_range=0.2,     # PPO clipping
            ent_coef=0.01,      # Entropy bonus for exploration
            vf_coef=0.5,        # Value function coefficient
            max_grad_norm=0.5,
            policy_kwargs={
                'net_arch': [256, 256, 128],  # 3-layer network
                'activation_fn': torch.nn.ReLU,
            },
            verbose=1,
            tensorboard_log="./pmcc_ppo_logs/"
        )
        
        eval_callback = EvalCallback(
            env,
            best_model_save_path='./pmcc_ppo_best/',
            eval_freq=10000,
            n_eval_episodes=20,
            deterministic=True,
        )
        
        model.learn(
            total_timesteps=total_timesteps,
            callback=eval_callback,
            progress_bar=True
        )
        
        return model
```

### E.3 Training Strategy

1. **Pre-training**: Train on 5 years of historical simulated PMCC positions
2. **Walk-forward validation**: Test on 1-year held-out periods
3. **Paper trading**: Run alongside rule-based system for 8 weeks, compare decisions
4. **Gradual deployment**: Start with PPO making suggestions (human approves), then full autonomy

***

## Module F: ML Pipeline Integration

### F.1 Complete System Flow

```
┌─────────────────────────────────────────────────────────┐
│                  ML-Enhanced PMCC System                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  OFFLINE (Weekly/Monthly):                               │
│  ┌──────────────────────────────────────┐                │
│  │ Module A: Optuna Bayesian Optimization │                │
│  │ → Produces optimized base parameters   │                │
│  │ → Walk-forward validated               │                │
│  └──────────────────────────────────────┘                │
│                                                          │
│  ONLINE (Every 15 min during market hours):              │
│  ┌──────────────────────────────────────┐                │
│  │ Step 1: Module B — Detect Regime      │                │
│  │ Output: Regime + confidence            │                │
│  └──────────────┬───────────────────────┘                │
│                 ▼                                         │
│  ┌──────────────────────────────────────┐                │
│  │ Step 2: Module C — Forecast IV        │                │
│  │ Output: IV direction + LEAPS signal    │                │
│  └──────────────┬───────────────────────┘                │
│                 ▼                                         │
│  ┌──────────────────────────────────────┐                │
│  │ Step 3: Adjust base params for regime │                │
│  │ Base (Optuna) × Regime = Active params │                │
│  └──────────────┬───────────────────────┘                │
│                 ▼                                         │
│  ┌──────────────────────────────────────┐                │
│  │ Step 4: Module D — Bandit selects     │                │
│  │         short call configuration       │                │
│  └──────────────┬───────────────────────┘                │
│                 ▼                                         │
│  ┌──────────────────────────────────────┐                │
│  │ Step 5: Module E — PPO manages        │                │
│  │         existing positions             │                │
│  │         (roll/close/hold decisions)    │                │
│  └──────────────────────────────────────┘                │
│                                                          │
│  FEEDBACK LOOP:                                          │
│  Cycle results → Update Bandit rewards                   │
│  Position outcomes → PPO reward signal                   │
│  Monthly: Retrain IV model, HMM, run new Optuna study    │
└─────────────────────────────────────────────────────────┘
```

### F.2 Confidence-Gated Decision Making

Critical safety feature: ML outputs are **confidence-gated**. Below a threshold, the system falls back to the base rule-based strategy:

```python
class ConfidenceGatedDecisionMaker:
    """
    Gate ML decisions by confidence level.
    Prevents the system from acting on low-confidence predictions.
    """
    
    CONFIDENCE_THRESHOLDS = {
        'regime_detection': 0.60,
        'iv_forecast': 0.55,
        'bandit_selection': 0.40,  # Lower threshold (bandits are adaptive)
        'ppo_action': 0.65,
    }
    
    def decide(self, ml_outputs, rule_based_outputs):
        final_decisions = {}
        
        for module, output in ml_outputs.items():
            threshold = self.CONFIDENCE_THRESHOLDS.get(module, 0.60)
            
            if output['confidence'] >= threshold:
                final_decisions[module] = {
                    'source': 'ML',
                    'decision': output['decision'],
                    'confidence': output['confidence'],
                }
            else:
                final_decisions[module] = {
                    'source': 'RULE_BASED',
                    'decision': rule_based_outputs[module],
                    'confidence': output['confidence'],
                    'reason': f'ML confidence {output["confidence"]:.2f} below '
                              f'threshold {threshold:.2f}'
                }
        
        return final_decisions
```

### F.3 A/B Testing Framework

Run ML-enhanced and rule-based strategies in parallel to measure improvement:

```python
class ABTestFramework:
    """
    Compare ML-enhanced PMCC vs. base rule-based PMCC.
    Run both in parallel on paper trading, measure alpha.
    """
    
    def __init__(self):
        self.ml_trades = []
        self.rule_trades = []
    
    def evaluate(self, lookback_days=90):
        ml_df = pd.DataFrame(self.ml_trades[-lookback_days:])
        rule_df = pd.DataFrame(self.rule_trades[-lookback_days:])
        
        return {
            'ml_sharpe': self._sharpe(ml_df['daily_returns']),
            'rule_sharpe': self._sharpe(rule_df['daily_returns']),
            'ml_total_return': ml_df['cumulative_pnl'].iloc[-1],
            'rule_total_return': rule_df['cumulative_pnl'].iloc[-1],
            'ml_win_rate': (ml_df['cycle_pnl'] > 0).mean(),
            'rule_win_rate': (rule_df['cycle_pnl'] > 0).mean(),
            'ml_max_dd': ml_df['drawdown'].max(),
            'rule_max_dd': rule_df['drawdown'].max(),
            'alpha': (ml_df['daily_returns'].mean() - rule_df['daily_returns'].mean()) * 252,
            'statistical_significance': self._ttest(
                ml_df['daily_returns'], rule_df['daily_returns']
            )
        }
```

***

## Module G: Data Pipeline & Feature Store

### G.1 Required Data Sources

| Data Type | Source | Frequency | Storage |
|-----------|--------|-----------|---------|
| **Historical options chains** | Polygon.io / CBOE DataShop / IB API | Daily | PostgreSQL + Parquet files |
| **Stock OHLCV** | IB API / yfinance | 1-min + daily | TimescaleDB or PostgreSQL |
| **Greeks (live)** | IB API reqMktData | Real-time (15-min samples) | Redis + PostgreSQL |
| **IV surface** | Calculated from options chain | Daily | PostgreSQL |
| **VIX + VIX futures** | CBOE / IB API | Daily | PostgreSQL |
| **Earnings dates** | Alpha Vantage / Polygon.io | Weekly refresh | PostgreSQL |
| **FOMC + macro calendar** | FRED / Federal Reserve | Monthly | PostgreSQL |
| **News sentiment** | FinBERT / NewsAPI | Daily | Redis |

### G.2 Feature Store Schema

```sql
CREATE TABLE ml_feature_store (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    
    -- Price features
    close DECIMAL(10,2),
    returns_1d DECIMAL(8,6),
    returns_5d DECIMAL(8,6),
    returns_21d DECIMAL(8,6),
    
    -- Volatility features
    vol_5d DECIMAL(8,6),
    vol_21d DECIMAL(8,6),
    vol_63d DECIMAL(8,6),
    vol_ratio DECIMAL(8,4),
    
    -- IV features
    iv_atm DECIMAL(8,6),
    iv_rank_30d DECIMAL(6,2),
    iv_percentile_252d DECIMAL(6,2),
    iv_skew DECIMAL(8,6),
    iv_term_slope DECIMAL(8,6),
    
    -- Technical features
    rsi_14 DECIMAL(6,2),
    macd_signal DECIMAL(10,4),
    sma_50_200_ratio DECIMAL(8,4),
    bb_position DECIMAL(6,4),  -- Where price is within Bollinger Bands
    
    -- Resistance/Support
    nearest_resistance DECIMAL(10,2),
    nearest_support DECIMAL(10,2),
    resistance_strength INTEGER,
    
    -- Volume
    volume_ratio DECIMAL(8,4),
    put_call_ratio DECIMAL(8,4),
    
    -- Regime (pre-computed)
    regime_label VARCHAR(20),
    regime_confidence DECIMAL(4,3),
    
    -- Macro
    vix_level DECIMAL(6,2),
    yield_10y DECIMAL(6,4),
    
    UNIQUE (symbol, date)
);

CREATE INDEX idx_feature_store_symbol_date ON ml_feature_store(symbol, date);
```

***

## Implementation Phases (ML Supplement)

### Phase ML-1: Data Foundation (Weeks 1–2)
- Set up historical options data pipeline (Polygon.io or CBOE)
- Build feature store with daily ETL
- Implement feature engineering for all modules
- Collect minimum 3 years of historical data

### Phase ML-2: Bayesian Optimization (Weeks 3–4)
- Build PMCC backtester engine (vectorized for speed)
- Implement Optuna objective function with all 13+ parameters
- Run walk-forward optimization across multiple periods
- Document optimized parameter sets per regime

### Phase ML-3: Regime Detection (Weeks 5–6)
- Train HMM on 5+ years of SPY/QQQ data
- Validate regime labels against known market events
- Build regime-adaptive parameter mapping
- Integrate with base PMCC system

### Phase ML-4: IV Forecasting (Weeks 7–9)
- Train GARCH models per symbol
- Train LSTM/ConvLSTM on IV surface data
- Build ensemble predictor
- Validate LEAPS entry signal improvement vs. static IV Rank

### Phase ML-5: Contextual Bandit (Weeks 10–11)
- Implement LinUCB with 6 arms
- Warm-start with historical PMCC backtest data
- Run parallel with rule-based system for validation
- Implement reward function and online learning loop

### Phase ML-6: PPO Agent (Weeks 12–15)
- Build Gymnasium environment for PMCC management
- Train PPO on historical simulated positions
- Walk-forward validation across multiple market periods
- Paper trade for minimum 8 weeks alongside rules

### Phase ML-7: Integration & A/B Testing (Weeks 16–18)
- Integrate all modules into unified pipeline
- Implement confidence-gated decision making
- Run A/B test (ML vs. rules) on paper trading
- Measure statistical significance of improvement
- Gradual live deployment with position limits

***

## Technology Requirements (ML-Specific)

| Component | Library/Tool | Purpose |
|-----------|-------------|---------|
| **Bayesian Optimization** | Optuna (with TPESampler) | Parameter optimization[^23][^24] |
| **HMM** | hmmlearn | Regime detection[^3][^9] |
| **GARCH** | arch (Python) | Short-term volatility forecasting[^25][^26] |
| **LSTM/ConvLSTM** | PyTorch | IV surface forecasting[^12][^15] |
| **Contextual Bandit** | Custom LinUCB / contextualbandits | Adaptive short call selection[^16][^27] |
| **PPO** | stable-baselines3 | Position management RL[^21][^22] |
| **Feature Engineering** | pandas-ta, TA-Lib | Technical indicators |
| **Backtesting** | vectorbt or custom engine | Strategy simulation |
| **XGBoost** | xgboost | Supplementary predictions[^28] |
| **Experiment Tracking** | MLflow or Weights & Biases | Model versioning, metrics |
| **GPU** | NVIDIA (optional) | LSTM training acceleration |

***

## Risk Guardrails for ML-Enhanced Trading

| Risk | Mitigation |
|------|-----------|
| **Model overfitting** | Walk-forward validation mandatory; parameter stability checks; no model goes live without OOS validation[^6][^8] |
| **Catastrophic ML failure** | Confidence gating: if any ML module confidence < threshold, fall back to rule-based |
| **Regime misclassification** | HMM transition risk flag; reduce position sizes when regime entropy is high |
| **Data poisoning/drift** | Monitor feature distributions daily; alert on statistical drift (KS test) |
| **Black swan events** | Hard-coded circuit breakers override all ML: VIX > 40 → halt new positions; single-day loss > 5% → close all shorts |
| **Training-serving skew** | Feature store ensures same features in training and production |
| **PPO policy degradation** | Monthly re-evaluation against rule-based benchmark; auto-revert if PPO underperforms for 30+ days |

***

## Appendix: Updated Parameter Table (ML-Enhanced)

| Parameter | Static Default | ML Module That Optimizes It | Expected Improvement |
|-----------|---------------|---------------------------|---------------------|
| LEAPS Delta | 0.80 | **A** (Optuna) | Finds per-symbol optimal: 0.75–0.85 |
| LEAPS DTE | 365–730 days | **A** (Optuna) | Optimizes cost vs. theta decay tradeoff |
| LEAPS Roll Trigger | 90 DTE | **A** (Optuna) + **E** (PPO) | PPO learns when rolling is most efficient |
| Short Call Delta | 0.20–0.30 | **B** (Regime) + **D** (Bandit) | Adapts 0.15–0.35 based on regime |
| Short Call DTE | 30–45 days | **A** (Optuna) + **D** (Bandit) | Bandit selects optimal DTE per cycle |
| Profit Target | 50% | **A** (Optuna) + **B** (Regime) + **E** (PPO) | Regime-adjusted: 30–80% |
| Stop Loss | -100% premium | **A** (Optuna) + **B** (Regime) + **E** (PPO) | Regime-adjusted: -50% to -200% |
| Max Positions | 6–8 | **A** (Optuna) | Optimized for portfolio Sharpe |
| Max Capital | 60% | **A** (Optuna) | Risk-adjusted allocation |
| IV Rank Entry | < 30 | **C** (LSTM/GARCH forecast) | Predicts IV direction, not just level |
| Strike Method | Resistance | **D** (Bandit) + **B** (Regime) | Bandit learns when resistance vs. delta is better |
| Roll Decision | Delta > 0.50 | **E** (PPO) | Learns optimal roll timing across 26 state features |
| Assignment Trigger | Delta > 0.50 | **E** (PPO) | Context-aware (earnings, ex-div, momentum) |

---

## References

1. [Covered Call Strategy Using Machine Learning](https://blog.quantinsti.com/covered-call-strategy-machine-learning/) - Covered call strategy can use Machine Learning in several ways to enhance decision-making, optimise ...

2. [CCIQ](https://www.cciq.ai)

3. [A multi-model ensemble-HMM voting framework for market regime ...](https://www.aimspress.com/article/id/69045d2fba35de34708adb5d) - In this paper, we present a framework for detecting market regime shifts using a combination of tree...

4. [Optimizing Trading Strategies with Bayesian Optimization](https://onepagecode.substack.com/p/optimizing-trading-strategies-with-6b1) - Optimizing the parameters of a quantitative trading strategy is a critical step in enhancing its per...

5. [Optimising Supertrend Parameters using Bayesian ...](https://arxiv.org/html/2405.14262v1)

6. [A Key Technique for Reducing Overfitting in Backtests - Runbot](https://runbot.io/understanding-walk-forward-optimization-a-key-technique-for-reducing-overfitting-in-backtests/) - Walk forward optimization is a technique that can help to mitigate the risk of overfitting and impro...

7. [Why we employ walk-forward testing to avoid curve-fitting](https://logical-invest.com/walk-forward-testing-avoid-curve-fitting-backtesting/) - The out-of-sample backtest minimizes the risk of over-fitting, as the data is not previously know to...

8. [Walk-Forward Optimization (WFO) - QuantInsti Blog](https://blog.quantinsti.com/walk-forward-optimization-introduction/) - Traditional backtesting is limited by its static nature and susceptibility to overfitting, making it...

9. [Market Regime using Hidden Markov Model - QuantInsti Blog](https://blog.quantinsti.com/regime-adaptive-trading-python/) - Build a regime-adaptive trading strategy in Python with this hands-on guide. Detect market regimes u...

10. [Why Delta Fails in PMCCs — The Real Strike Strategy - YouTube](https://www.youtube.com/watch?v=q7dHzt9WlpE&vl=en) - 20% Off off Annual Memberships! Join my Patreon: https://www.patreon.com/mylifeoflearning My Options...

11. [985492154237322143-42818](https://www.bohrium.com/paper-details/forecasting-implied-volatilities-of-currency-options-with-machine-learning-techniques-and-econometrics-models/985492154237322143-42818)

12. ["Multi-Step Forecast of the Implied Volatility Surface Using ...](https://openprairie.sdstate.edu/etd/3647/) - Implied volatility is an essential input to price an option. Machine learning architectures have sho...

13. [An Artificial Neural Networks Approach in Estimating ...](https://mlkd.aut.ac.ir/proceedings/2024/paper/1A.2.pdf)

14. [[PDF] Multi-Step Forecast of the Implied Volatility Surface Using ...](https://openprairie.sdstate.edu/cgi/viewcontent.cgi?article=4683&context=etd) - Implied volatility is typically derived through a closed-form formula. Changes in implied volatility...

15. [Multistep forecast of the implied volatility surface using deep learning](https://onlinelibrary.wiley.com/doi/10.1002/fut.22302) - ## Abstract

Modeling implied volatility surface (IVS) is of paramount importance to price and hedge...

16. [Multi-Armed Bandit (MAB) Methods in Trading - DayTrading.com](https://www.daytrading.com/multi-armed-bandit) - Multi-Armed Bandit (MAB) methods can provide us with a mathematically rigorous ways to deal with unc...

17. [Strategy Selection Using Multi-Armed Bandit Algorithms in Financial Markets](https://direct.ewa.pub/proceedings/ace/article/view/15927) - This paper aims to evaluate the effectiveness of Multi-Armed Bandit (MAB) algorithms in choosing the...

18. [Multi-Armed Bandit for Trading Strategy Selection](https://www.linkedin.com/pulse/multi-armed-bandit-trading-strategy-selection-learning-hemanth-kumar-nurrc) - Smart Trading Strategy Selection: How AI Learns to Pick Winners in Real-Time Executive Summary The B...

19. [Deep reinforcement learning for optimal trading with partial information](https://arxiv.org/html/2511.00190v1) - In this paper we study an optimal trading problem, where a trading signal follows an Ornstein–Uhlenb...

20. [Reinforcement Learning for Stock Option Trading](https://arc.cct.ie/cgi/viewcontent.cgi?article=1044&context=ict)

21. ["Reinforcement Learning for Stock Option Trading" by James Garza](https://arc.cct.ie/ict/42/) - Reinforcement learning has recently seen an increase in popularity due to its ability to learn from ...

22. [What is Proximal Policy Optimization (PPO)? - IBM](https://www.ibm.com/think/topics/proximal-policy-optimization) - Proximal policy optimization (PPO) is a deep reinforcement learning algorithm for improving the perf...

23. [Optuna: A hyperparameter optimization framework — Optuna 4.7.0 ...](https://optuna.readthedocs.io) - Optuna is an automatic hyperparameter optimization software framework, particularly designed for mac...

24. [Dashboard](https://optuna.org) - Optuna is an automatic hyperparameter optimization software framework, particularly designed for mac...

25. [Implied GARCH Volatility Forecasting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=299502) - This paper empirically investigates a method to quantify volatility using the information content of...

26. [[PDF] Forecasting implied volatility](https://theses.ubn.ru.nl/bitstreams/0fbc11c8-fec5-4805-ab59-f70d27b7d7ef/download) - The implied volatility is an expectation of the mean variance from now until the moment of expiratio...

27. [Ultimate Guide to Contextual Bandits: From Theory to Python ...](https://findingtheta.com/blog/ultimate-guide-to-contextual-bandits-from-theory-to-python-implementation) - ... contextual-bandits-deep-dive; [1802.00981] Contextual Bandit with Adaptive Feature Extraction - ...

28. [GitHub - devxinvestor/Options: ML Options Pricing Model Using XGBoost And GARCH](https://github.com/devxinvestor/Options) - ML Options Pricing Model Using XGBoost And GARCH. Contribute to devxinvestor/Options development by ...

