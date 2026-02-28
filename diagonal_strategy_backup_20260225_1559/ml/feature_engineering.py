"""
Feature Engineering
===================
Prepares the feature matrix and labels for the XGBoost oscillation predictor.
"""

import pandas as pd
import numpy as np
import logging
from typing import Tuple, Dict, Any, List

from diagonal_strategy.config import OSC_FLAT_THRESHOLD, OSC_LOOKFORWARD_DAYS

logger = logging.getLogger(__name__)

class FeatureEngineer:
    def __init__(self):
        pass

    def create_features_and_labels(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Takes raw merged data from DataLoader, returns (X, y)
        where X is the feature matrix and y are the labels (0: DOWN, 1: FLAT, 2: UP)
        """
        logger.info("Computing bulk TA features for dataset...")
        
        df_ta = df.copy()
        
        # --- Native Pandas Calculations ---
        # RSI
        delta = df_ta['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_ta['RSI_14'] = 100 - (100 / (1 + rs))
        
        gain2 = (delta.where(delta > 0, 0)).rolling(window=2).mean()
        loss2 = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
        rs2 = gain2 / loss2
        df_ta['RSI_2'] = 100 - (100 / (1 + rs2))
        
        # MACD
        ema12 = df_ta['close'].ewm(span=12, adjust=False).mean()
        ema26 = df_ta['close'].ewm(span=26, adjust=False).mean()
        df_ta['MACD_12_26_9'] = ema12 - ema26
        df_ta['MACDs_12_26_9'] = df_ta['MACD_12_26_9'].ewm(span=9, adjust=False).mean()
        df_ta['MACDh_12_26_9'] = df_ta['MACD_12_26_9'] - df_ta['MACDs_12_26_9']
        
        # Bollinger Bands
        df_ta['BBM_20_2.0'] = df_ta['close'].rolling(window=20).mean()
        std20 = df_ta['close'].rolling(window=20).std()
        df_ta['BBU_20_2.0'] = df_ta['BBM_20_2.0'] + (std20 * 2)
        df_ta['BBL_20_2.0'] = df_ta['BBM_20_2.0'] - (std20 * 2)
        
        # ATR (14)
        high_low = df_ta['high'] - df_ta['low']
        high_close = np.abs(df_ta['high'] - df_ta['close'].shift())
        low_close = np.abs(df_ta['low'] - df_ta['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df_ta['ATRr_14'] = tr.rolling(window=14).mean()
        
        # VWAP
        df_ta['VWAP_D'] = (df_ta['close'] * df_ta['volume']).cumsum() / df_ta['volume'].cumsum()
        
        # OBV (vectorized approximation)
        df_ta['OBV'] = (np.sign(df_ta['close'].diff()) * df_ta['volume']).fillna(0).cumsum()
        
        X = pd.DataFrame(index=df_ta.index)
        
        X['rsi_14'] = df_ta.get('RSI_14', 50.0).fillna(50)
        X['rsi_2'] = df_ta.get('RSI_2', 50.0).fillna(50)
        X['rsi_slope_3d'] = (X['rsi_14'] - X['rsi_14'].shift(3)) / 3.0
        
        X['macd_hist'] = df_ta.get('MACDh_12_26_9', 0.0).fillna(0)
        X['macd_cross'] = np.where(df_ta.get('MACD_12_26_9', 0) > df_ta.get('MACDs_12_26_9', 0), 1, -1)
        X['macd_hist_slope'] = X['macd_hist'] - X['macd_hist'].shift(1)
        
        up_bb = df_ta.get('BBU_20_2.0', df_ta['close'])
        low_bb = df_ta.get('BBL_20_2.0', df_ta['close'])
        mid_bb = df_ta.get('BBM_20_2.0', df_ta['close'])
        
        X['bb_position'] = np.where(up_bb > low_bb, (df_ta['close'] - low_bb) / (up_bb - low_bb), 0.5)
        X['bb_width'] = np.where(up_bb > low_bb, (up_bb - low_bb) / mid_bb, 0.0)
        
        X['atr_14'] = df_ta.get('ATRr_14', 0.0).fillna(0)
        X['atr_pct'] = X['atr_14'] / df_ta['close']
        
        X['tqqq_hv_10'] = df_ta['close'].pct_change().rolling(10).std() * np.sqrt(252)
        X['tqqq_hv_5'] = df_ta['close'].pct_change().rolling(5).std() * np.sqrt(252)
        
        vwap = df_ta.get('VWAP_D', df_ta['close'])
        X['vwap_distance'] = np.where(vwap > 0, (df_ta['close'] - vwap) / vwap, 0.0)
        
        vol_ma20 = df_ta['volume'].rolling(20).mean()
        X['volume_ratio'] = df_ta['volume'] / vol_ma20
        
        obv = df_ta.get('OBV', 0.0)
        if isinstance(obv, pd.Series):
            X['obv_slope'] = (obv - obv.shift(5)) / 5.0
        else:
            X['obv_slope'] = 0.0
        
        # Stochastic Oscillator (14,3,3)
        low_14 = df_ta['low'].rolling(14).min()
        high_14 = df_ta['high'].rolling(14).max()
        fast_k = 100 * (df_ta['close'] - low_14) / (high_14 - low_14 + 1e-10)
        df_ta['STOCHk_14_3_3'] = fast_k.rolling(3).mean()
        df_ta['STOCHd_14_3_3'] = df_ta['STOCHk_14_3_3'].rolling(3).mean()
        
        X['stoch_k'] = df_ta['STOCHk_14_3_3'].fillna(50.0)
        X['stoch_d'] = df_ta['STOCHd_14_3_3'].fillna(50.0)
        
        X['vix_level'] = df_ta['vix_level']
        X['vix_roc_5'] = df_ta['vix_roc_5']
        X['iv_rank'] = df_ta['iv_rank']
        X['iv_percentile'] = df_ta['iv_percentile']
        X['term_slope'] = df_ta['term_slope']
        
        ma20 = df_ta['close'].rolling(20).mean()
        ma50 = df_ta['close'].rolling(50).mean()
        
        X['dist_from_20ma'] = (df_ta['close'] - ma20) / df_ta['close']
        X['dist_from_50ma'] = (df_ta['close'] - ma50) / df_ta['close']
        
        # Target variable: TQQQ returns N days ahead
        future_close = df_ta['close'].shift(-OSC_LOOKFORWARD_DAYS)
        f_ret = (future_close - df_ta['close']) / df_ta['close']
        
        conditions = [
            f_ret < -OSC_FLAT_THRESHOLD,
            (f_ret >= -OSC_FLAT_THRESHOLD) & (f_ret <= OSC_FLAT_THRESHOLD),
            f_ret > OSC_FLAT_THRESHOLD
        ]
        choices = [0, 1, 2] # 0: DOWN, 1: FLAT, 2: UP
        
        y = pd.Series(np.select(conditions, choices, default=1), index=df_ta.index, name='label')
        
        valid_idx = X.dropna().index.intersection(y.dropna().index)
        
        # Don't drop the last N days where future return is NaN just yet, 
        # because we might need them for inference. 
        # But for training, we MUST drop them.
        X_train_ready = X.loc[valid_idx]
        y_train_ready = y.loc[valid_idx]
        
        # Ensure we drop rows with NaN labels
        train_valid_idx = y_train_ready[f_ret.loc[valid_idx].notna()].index
        
        return X_train_ready.loc[train_valid_idx], y_train_ready.loc[train_valid_idx]
