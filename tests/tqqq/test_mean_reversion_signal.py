import pytest
import pandas as pd
import numpy as np
from src.tqqq.ml.mean_reversion_signal import MeanReversionSignal

def test_build_features_shape():
    signal = MeanReversionSignal(model_path="dummy_nonexistent.json")
    
    df = pd.DataFrame([
        {
            "rsi_2": 8.0,
            "rsi2_consec": 1.0,
            "bb_pct_b": 0.1,
            "vix_sma_ratio": 1.2,
            "term_slope": 1.1,
            "vol_ratio": 1.5,
            "mfi_14": 20.0,
            "atr_pct": 0.08,
            "hurst_100": 0.45,
            "ou_half_life": 10.0,
            "adx_14": 20.0,
            "days_since_oversold": 0.0,
            "drawdown_from_high": -0.15,
            "sma20_slope": -0.5
        }
    ])
    
    features = signal.build_features(df)
    assert features.shape == (1, 15)

def test_fallback_probability():
    signal = MeanReversionSignal(model_path="dummy_nonexistent.json")
    
    df_low = pd.DataFrame([{"rsi_2": 3.0}])
    df_med = pd.DataFrame([{"rsi_2": 8.0}])
    df_high = pd.DataFrame([{"rsi_2": 50.0}])
    
    assert signal.predict_bounce_probability(df_low) == 0.65
    assert signal.predict_bounce_probability(df_med) == 0.55
    assert signal.predict_bounce_probability(df_high) == 0.30

def test_build_features_empty():
    signal = MeanReversionSignal(model_path="dummy_nonexistent.json")
    df = pd.DataFrame()
    
    features = signal.build_features(df)
    assert features.shape == (1, 15)
    assert signal.predict_bounce_probability(df) == 0.50
