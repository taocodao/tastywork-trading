
"""
DVO Regime Classifier
=====================
Determines the market regime for Deep Value Overlay timing.
Combines ZEBRA's Volatility-based detection with Trend (SMA200) analysis.

Regimes:
- CRISIS: High Vol + Downtrend (No new entries)
- EARLY_RECOVERY: Vol stabilizing + Deep Value available
- UPTREND: Low/Normal Vol + Uptrend (Ideal for DVO)
- LATE_CYCLE: Low Vol + Extended Trend (Risk of pullback)
"""

import logging
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Reuse ZEBRA detector logic
from ..zebra.regime_detector import RegimeDetector

logger = logging.getLogger(__name__)

class DvorRegimeClassifier:
    def __init__(self):
        self.base_detector = RegimeDetector()
        self.market_data = None
        
    def fetch_market_data(self):
        """Fetch SPY data for Vol + Trend analysis."""
        try:
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
            
            # Fetch for base detector
            self.base_detector.fetch_spy_data(start_date, end_date)
            
            # Reuse the data from base detector if possible, or fetch own
            if self.base_detector.spy_data is not None:
                df = self.base_detector.spy_data.copy()
            else:
                df = yf.download('SPY', start=start_date, end=end_date, progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                     df = df.xs('SPY', axis=1, level=1) if 'SPY' in df.columns.get_level_values(1) else df.droplevel(1, axis=1)

            # Calculate SMAs
            df['SMA50'] = df['Close'].rolling(50).mean()
            df['SMA200'] = df['Close'].rolling(200).mean()
            
            # Distances
            df['Dist_SMA200'] = (df['Close'] - df['SMA200']) / df['SMA200']
            
            self.market_data = df
            return True
        except Exception as e:
            logger.error(f"Failed to fetch market data for DVO regime: {e}")
            return False

    def get_regime(self):
        """
        Determine current DVO regime.
        Returns: (regime_tag: str, reasoning: str)
        """
        if self.market_data is None or self.market_data.empty:
            return "UPTREND", "Default (No Data)"
            
        latest = self.market_data.iloc[-1]
        date = latest.name
        
        # 1. Base Volatility Regime
        vol_label, _ = self.base_detector.get_regime(date)
        
        # 2. Trend Context
        price = latest['Close']
        sma200 = latest['SMA200']
        dist_sma200 = latest['Dist_SMA200']
        
        is_uptrend = price > sma200
        is_extended = dist_sma200 > 0.15 # 15% above SMA200 = Stretched
        
        # 3. Classification Logic
        
        # CRISIS: Base says CRISIS or simple logic checks
        if vol_label == 'CRISIS':
            return "CRISIS", f"High Volatility ({vol_label})"
            
        if not is_uptrend and vol_label == 'HIGH_VOL':
            return "CRISIS", "Downtrend + High Vol"

        # EARLY RECOVERY: Downtrend but Vol Normalizing
        if not is_uptrend and vol_label in ['NORMAL', 'LOW_VOL']:
            return "EARLY_RECOVERY", "Price below SMA200 but Vol stable"
            
        # LATE CYCLE: Extended Uptrend + Low Vol (Complacency)
        if is_uptrend and is_extended and vol_label == 'LOW_VOL':
            return "LATE_CYCLE", "Extended >15% above SMA200 + Low Vol"
            
        # UPTREND: Standard
        if is_uptrend:
            return "UPTREND", "Price > SMA200 + Normal Vol"
            
        return "UPTREND", "Fallback"
