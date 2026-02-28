"""
Data Loader (Standalone)
========================
Fetches historical VIX and TQQQ data for ML training and backtesting.
Creates a localized cache.
"""

import os
import logging
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Optional

try:
    import yfinance as yf
except ImportError:
    yf = None

logger = logging.getLogger(__name__)

class DiagonalDataLoader:
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def load_historical_data(self, start_date: str = "2019-01-01", end_date: str = None, use_cache: bool = True) -> Optional[pd.DataFrame]:
        """
        Returns a merged DataFrame of TQQQ OHLCV and VIX close.
        """
        if end_date is None:
            end_date = date.today().isoformat()
            
        cache_file = os.path.join(self.cache_dir, f"tqqq_vix_{start_date}_{end_date}.csv")
        if use_cache and os.path.exists(cache_file):
            logger.info(f"Loading cached data from {cache_file}")
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            df.columns = [c.lower() for c in df.columns]
            # Fill NaN from rolling window warmup
            df['iv_rank'] = df['iv_rank'].fillna(50)
            df['iv_percentile'] = df['iv_percentile'].fillna(50)
            df['vix_roc_5'] = df['vix_roc_5'].fillna(0)
            return df
            
        if not yf:
            logger.error("yfinance is not installed. Cannot fetch data.")
            return None
            
        logger.info(f"Downloading TQQQ and ^VIX from {start_date} to {end_date}")
        
        tqqq = yf.download("TQQQ", start=start_date, end=end_date, progress=False)
        if isinstance(tqqq.columns, pd.MultiIndex):
            tqqq.columns = tqqq.columns.droplevel(1)
            
        tqqq.columns = [c.lower() for c in tqqq.columns]
        if 'close' not in tqqq.columns and 'adj close' in tqqq.columns:
            tqqq = tqqq.rename(columns={'adj close': 'close'})
            
        vix = yf.download("^VIX", start=start_date, end=end_date, progress=False)
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.droplevel(1)
            
        vix_close = vix['Close'].rename('vix_level')
        vix_open = vix['Open'].rename('vix_open')
        vix_high = vix['High'].rename('vix_high')
        vix_low = vix['Low'].rename('vix_low')
        
        df = tqqq.join(vix_close, how='inner')
        df = df.join(vix_open, how='inner')
        df = df.join(vix_high, how='inner')
        df = df.join(vix_low, how='inner')
        
        df['vix_roc_5'] = df['vix_level'].pct_change(5)
        
        vix_rolling = df['vix_level'].rolling(252)
        vix_min = vix_rolling.min()
        vix_max = vix_rolling.max()
        df['iv_rank'] = ((df['vix_level'] - vix_min) / (vix_max - vix_min)) * 100
        
        # IV percentile using rank
        df['iv_percentile'] = df['vix_level'].rolling(252).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1]) * 100
        df['term_slope'] = 0.0 # Placeholder unless fetching VIX3M
        
        df = df.dropna()
        if use_cache:
            df.to_csv(cache_file)
            
        return df
