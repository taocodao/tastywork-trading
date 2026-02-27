import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.tqqq.intraday_data import TQQQIntradayFetcher

@pytest.fixture
def mock_intraday_data():
    """Create a synthetic 5-min OHLCV dataframe for testing."""
    dates = pd.date_range(end=datetime.now(), periods=100, freq='5min')
    
    # Simulate a sudden dip
    close_prices = np.linspace(100, 105, 80).tolist() + np.linspace(105, 90, 20).tolist()
    
    df = pd.DataFrame({
        'open': close_prices,
        'high': [p + 0.5 for p in close_prices],
        'low': [p - 0.5 for p in close_prices],
        'close': close_prices,
        'volume': np.random.randint(1000, 50000, 100)
    }, index=dates)
    
    return df

def test_compute_intraday_features(mock_intraday_data):
    fetcher = TQQQIntradayFetcher()
    
    # Needs at least 20 rows for bollinger bands
    assert len(mock_intraday_data) == 100
    
    df_feats = fetcher.compute_intraday_features(mock_intraday_data)
    
    # Check new columns exist
    assert 'rsi_2' in df_feats.columns
    assert 'rsi_14' in df_feats.columns
    assert 'bb_lower' in df_feats.columns
    assert 'bb_pct_b' in df_feats.columns
    assert 'vol_ratio' in df_feats.columns
    
    # Check RSI-2 behavior on latest row (which is a steep drop)
    latest = df_feats.iloc[-1]
    
    # Should be oversold due to the simulated price crash
    assert not pd.isna(latest['rsi_2'])
    assert latest['rsi_2'] < 30
    
    # Check %B behavior (should be below the lower band due to crash)
    assert not pd.isna(latest['bb_pct_b'])
    assert latest['bb_pct_b'] < 0.5

def test_merge_daily_context(mock_intraday_data):
    fetcher = TQQQIntradayFetcher()
    
    daily_context = {
        'hurst_exponent': 0.42,
        'dist_from_200_sma': -0.15,
        'vix_ratio': 1.15
    }
    
    merged_df = fetcher.merge_daily_context(mock_intraday_data, daily_context)
    
    assert 'hurst_exponent' in merged_df.columns
    assert 'dist_from_200_sma' in merged_df.columns
    
    # Should broadcast to all rows
    assert merged_df['hurst_exponent'].iloc[0] == 0.42
    assert merged_df['hurst_exponent'].iloc[-1] == 0.42
