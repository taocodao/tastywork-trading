"""
TurboBounce Options: Multi-Ticker Data Provider
===============================================

Provides pre-market daily data (RSI, Bollinger Bands, Volume, Moving Averages)
plus options IV rank for the ~47 ticker universe.
Used to feed the Scanner.
"""

import logging
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class MultiTickerDataProvider:
    """Fetches end-of-day/pre-market technicals + options info for the universe."""

    def __init__(self, ib_client=None):
        self.ib_client = ib_client  # Optional: For live options data if connected
        
        # Cache to prevent hammering Yahoo Finance during the scan loop
        self._tech_cache: Dict[str, Dict[str, Any]] = {}

    def fetch_batch_data(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetches technicals for a batch of symbols via yfinance.
        Returns a dict mapping symbol -> metrics dict.
        """
        logger.info(f"Fetching batch technicals for {len(symbols)} symbols...")
        results = {}
        
        try:
            # Download 200 days of history for SMA-200 calculation
            df_history = yf.download(symbols, period="200d", group_by="ticker", auto_adjust=True, progress=False)
            
            for sym in symbols:
                try:
                    # yfinance returns MultiIndex columns when downloading multiple tickers
                    df = df_history[sym] if len(symbols) > 1 else df_history
                    
                    if df.empty or len(df) < 5:
                        logger.warning(f"Insufficient history for {sym}")
                        continue
                        
                    metrics = self._calculate_technicals(df)
                    
                    # Add mock IV info (if IB client not available, or outside market hours)
                    # In a full live environment, IV Rank comes from Tastytrade or IB APIs
                    metrics['iv_rank'] = np.random.uniform(20.0, 80.0) # Placeholder
                    metrics['bid_ask_spread'] = 0.05 if metrics['avg_volume'] > 5000000 else 0.15
                    
                    results[sym] = metrics
                    self._tech_cache[sym] = metrics
                    
                except Exception as e:
                    logger.error(f"Error processing {sym}: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Batch yfinance download failed: {str(e)}")
            
        return results

    def _calculate_technicals(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculates RSI-2, Bollinger Bands, Moving Averages, etc."""
        close = df['Close']
        volume = df['Volume']
        
        # 3-Day Return
        ret_3d = (close.iloc[-1] / close.iloc[-4] - 1.0) if len(close) >= 4 else 0.0
        
        # RSI-2
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=2).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
        rs = gain / loss
        rsi_2 = 100 - (100 / (1 + rs))
        current_rsi_2 = rsi_2.iloc[-1] if not pd.isna(rsi_2.iloc[-1]) else 50.0
        
        # 200 SMA
        sma_200 = close.rolling(window=200).mean().iloc[-1] if len(close) >= 200 else close.iloc[-1]
        dist_sma = (close.iloc[-1] - sma_200) / sma_200 if sma_200 > 0 else 0.0
        
        # Bollinger Bands (20, 2)
        sma_20 = close.rolling(window=20).mean()
        std_20 = close.rolling(window=20).std()
        upper_bb = sma_20 + (std_20 * 2)
        lower_bb = sma_20 - (std_20 * 2)
        
        current_close = close.iloc[-1]
        current_lower = lower_bb.iloc[-1]
        current_upper = upper_bb.iloc[-1]
        
        # Bollinger %B: (Price - Lower) / (Upper - Lower)
        # < 0 means price is below lower band
        bb_width = current_upper - current_lower
        pct_b = (current_close - current_lower) / bb_width if bb_width > 0 else 0.5
        
        # Volume info
        avg_vol = volume.rolling(window=20).mean().iloc[-1] if len(volume) >= 20 else volume.iloc[-1]
        vol_ratio = (volume.iloc[-1] / avg_vol) if avg_vol > 0 else 1.0
        
        # Calculate Historical Volatility (20-day annualized) to proxy IV Rank
        log_rets = np.log(close / close.shift(1))
        hv_20 = log_rets.rolling(window=20).std() * np.sqrt(252) * 100
        current_hv = hv_20.iloc[-1] if len(hv_20) > 0 and not pd.isna(hv_20.iloc[-1]) else 0.0
        hv_min = hv_20.min() if len(hv_20) > 0 else 0.0
        hv_max = hv_20.max() if len(hv_20) > 0 else 0.0
        
        # Proxy IV Rank (HV Rank)
        if hv_max > hv_min:
            proxy_iv_rank = ((current_hv - hv_min) / (hv_max - hv_min)) * 100
        else:
            proxy_iv_rank = 50.0
            
        return {
            "close": float(current_close),
            "rsi_2": float(current_rsi_2),
            "ret_3d": float(ret_3d),
            "sma_200": float(sma_200),
            "dist_sma_200": float(dist_sma),
            "pct_b": float(pct_b),
            "volume": float(volume.iloc[-1]),
            "avg_volume": float(avg_vol),
            "vol_ratio": float(vol_ratio),
            "iv_rank": float(proxy_iv_rank),  # Using HV Rank as proxy for live
            "bid_ask_spread": 0.05 if float(avg_vol) > 5000000 else 0.15
        }
