"""
ML Training Pipeline
====================
Generates datasets of SignalCandidates, labels them based on 
target-before-stop, and trains an ML model.
"""
import pandas as pd
import numpy as np
import logging
from typing import Tuple, List, Any
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from .config import InstrumentConfig
from .features import build_feature_vector
from .regime import classify_regime
from .signal_engine import evaluate_signal
from .types import SignalCandidate

logger = logging.getLogger(__name__)

def generate_candidate_dataset(df: pd.DataFrame, config: InstrumentConfig,
                               horizon_bars: int = 12, reward_multiple: float = 1.5) -> pd.DataFrame:
    """
    Replay historical bars, evaluate signals, compute features, and label outcomes.
    """
    warmup = max(config.ema_layers) + config.cci_lookback + 5
    candidates = []
    
    for i in range(warmup, len(df) - horizon_bars):
        window = df.iloc[:i + 1]
        
        # 1. Deterministic rules
        candidate = evaluate_signal(window, config.symbol, config.timeframe, 
                                    config.ema_layers, config.proximity_pct, config.cci_lookback)
        if candidate is None:
            continue
            
        # 2. Features & Regime
        candidate.features = build_feature_vector(window, i, config)
        candidate.regime = classify_regime(window, i, config)
        
        if not candidate.features:
            continue
            
        # 3. Labeling (did it reach target before stop within horizon?)
        risk = abs(candidate.entry_price - candidate.stop_loss)
        if risk == 0:
            continue
            
        target = candidate.entry_price + (risk * reward_multiple) if candidate.direction == "BUY" \
                 else candidate.entry_price - (risk * reward_multiple)
                 
        future_window = df.iloc[i+1 : i+1+horizon_bars]
        
        label = 0 # 0 = failed, 1 = success
        
        for _, bar in future_window.iterrows():
            high, low = bar["high"], bar["low"]
            
            if candidate.direction == "BUY":
                if low <= candidate.stop_loss:
                    break # hit stop first
                if high >= target:
                    label = 1
                    break # hit target first
            else: # SELL
                if high >= candidate.stop_loss:
                    break # hit stop first
                if low <= target:
                    label = 1
                    break # hit target first
                    
        # Flatten candidate + features for training
        row = candidate.to_dict()
        row.update(candidate.features)
        row["label"] = label
        del row["features"] # remove nested dict
        
        candidates.append(row)
        
    return pd.DataFrame(candidates)


def train_signal_model(df: pd.DataFrame, model_type: str = "xgboost") -> Tuple[Any, dict, list]:
    """
    Train an ML model on candidate setups.
    Returns: (trained_model, metrics, feature_cols)
    """
    if df.empty or len(df) < 20:
        logger.warning("Not enough candidates to train model.")
        return None, {}, []
        
    # Exclude non-feature columns
    exclude_cols = ['symbol', 'timeframe', 'direction', 'timestamp', 
                    'entry_price', 'stop_loss', 'ema1_value', 'ema2_value', 'ema3_value', 
                    'cci_value', 'macd_hist', 'regime', 'publish_decision', 'label']
                    
    # One-hot encode regime if present
    if 'regime' in df.columns:
        df = pd.get_dummies(df, columns=['regime'], drop_first=False)
        exclude_cols.remove('regime') # already removed by get_dummies
        
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    X = df[feature_cols].astype(float)
    y = df['label']
    
    # Train test split (time-aware, simple 80/20 for basic implementation)
    # V2 should use walk-forward validation
    split_idx = int(len(df) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    if len(np.unique(y_train)) < 2:
        logger.warning("Only one class present in training data. Cannot train.")
        return None, {}, []
        
    if model_type == "xgboost":
        model = xgb.XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.05, 
                                  use_label_encoder=False, eval_metric='logloss')
    else:
        model = RandomForestClassifier(n_estimators=100, max_depth=3, random_state=42)
        
    model.fit(X_train, y_train)
    
    # Metrics
    if len(X_test) > 0 and len(np.unique(y_test)) > 1:
        y_pred = model.predict(X_test)
        y_prob = model.predict_proba(X_test)[:, 1]
        
        metrics = {
            "precision": round(precision_score(y_test, y_pred, zero_division=0), 3),
            "recall": round(recall_score(y_test, y_pred, zero_division=0), 3),
            "roc_auc": round(roc_auc_score(y_test, y_prob), 3),
            "train_size": len(X_train),
            "test_size": len(X_test)
        }
    else:
        metrics = {"status": "Not enough test data for metrics"}
        
    return model, metrics, feature_cols
