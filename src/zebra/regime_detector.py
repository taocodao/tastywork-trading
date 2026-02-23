import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Regime Thresholds (SPY ATR % of Price)
# LOW: < 1.0% (Grinding higher)
# NORMAL: 1.0% - 2.0% (Standard)
# HIGH: 2.0% - 3.5% (Volatile)
# CRISIS: > 3.5% (Crash mode)

REGIME_PARAMS = {
    'LOW_VOL': {
        'trailing_stop_pct': 0.20,  # Loose trail to ride trend
        'hard_stop_pct': -0.30,
        'time_exit_days': 45,
        'max_positions': 8,
        'allocation': 0.12
    },
    'NORMAL': {
        'trailing_stop_pct': 0.15,  # Standard
        'hard_stop_pct': -0.35,
        'time_exit_days': 25,
        'max_positions': 6,
        'allocation': 0.10
    },
    'HIGH_VOL': {
        'trailing_stop_pct': 0.10,  # Tight trail
        'hard_stop_pct': -0.20,     # Tight hard stop
        'time_exit_days': 10,       # Fast exit
        'max_positions': 4,         # Reduce exposure
        'allocation': 0.08
    },
    'CRISIS': {
        'trailing_stop_pct': 0.05,
        'hard_stop_pct': -0.15,
        'time_exit_days': 5,
        'max_positions': 0,         # NO NEW ENTRIES
        'allocation': 0.0
    }
}

class RegimeDetector:
    def __init__(self, hmm_detector=None):
        self.spy_data = None
        self.hmm_detector = hmm_detector
        
    def set_optimized_params(self, optimized_params):
        """
        Override default REGIME_PARAMS with ML-optimized values.
        """
        global REGIME_PARAMS
        for regime, params in optimized_params.items():
            if regime in REGIME_PARAMS:
                logger.info(f"Updating {regime} params: {params}")
                REGIME_PARAMS[regime].update(params)

    def fetch_spy_data(self, start_date, end_date):
        """Fetch SPY data to determine market regime."""
        try:
            logger.info("Fetching SPY data for regime detection...")
            spy = yf.download('SPY', start=start_date, end=end_date, progress=False)
            
            # Handle MultiIndex if present (yfinance v0.2+)
            if isinstance(spy.columns, pd.MultiIndex):
                spy = spy.xs('SPY', axis=1, level=1) if 'SPY' in spy.columns.get_level_values(1) else spy.droplevel(1, axis=1)

            # Indicators
            spy['ATR'] = self._calc_atr(spy)
            spy['ATR_Pct'] = (spy['ATR'] / spy['Close']) * 100
            
            # Rolling Regime (smooth out noise)
            spy['Regime_ATR'] = spy['ATR_Pct'].rolling(5).mean()
            
            self.spy_data = spy
            return True
        except Exception as e:
            logger.error(f"Error fetching SPY data: {e}")
            return False
            
    def _calc_atr(self, df, period=14):
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        return true_range.rolling(period).mean()

    def get_regime(self, date):
        """
        Return regime label and params for a given date.
        If HMM is available, uses probability-blended params.
        """
        if self.spy_data is None or date not in self.spy_data.index:
            return 'NORMAL', REGIME_PARAMS['NORMAL'] # Default
            
        if self.hmm_detector and self.hmm_detector.is_trained:
            # Optionally pass target_date into the hmm detector if you want strictly point-in-time
            # For backtesting, we truncate the spy_data up to 'date' to avoid lookahead
            historical_slice = self.spy_data.loc[:date]
            label, params = self.hmm_detector.get_blended_regime_params(historical_slice, REGIME_PARAMS)
            return label, params
            
        atr_pct = self.spy_data.loc[date]['Regime_ATR']
        
        if atr_pct < 1.0:
            label = 'LOW_VOL'
        elif atr_pct < 2.0:
            label = 'NORMAL'
        elif atr_pct < 3.5:
            label = 'HIGH_VOL'
        else:
            label = 'CRISIS'
            
        return label, REGIME_PARAMS[label]
