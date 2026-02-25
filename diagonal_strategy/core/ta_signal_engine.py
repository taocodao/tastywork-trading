"""
Technical Analysis Signal Engine
================================
Computes 25+ TA features from TQQQ OHLCV + VIX data.
Generates dip and bounce scores (0.0 to 1.0) based on rule-based heuristics
(Phase 1) or ML predictions (Phase 2).
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
import logging

from diagonal_strategy.config import (
    TA_RSI_OVERSOLD, TA_RSI_OVERBOUGHT, TA_RSI2_EXTREME,
    TA_IV_RANK_MIN, TA_BB_OVERSOLD
)

logger = logging.getLogger(__name__)

class TASignalEngine:
    def __init__(self, ml_model=None):
        self.ml_model = ml_model  # If None, uses rule-based scoring

    def compute_features(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute features for the LAST available row using standard pandas.
        """
        df = market_data.get('tqqq_bars')
        if df is None or df.empty or len(df) < 50:
            logger.warning("Insufficient TQQQ bars. Need at least 50 periods.")
            return {}

        df = df.copy()

        # Calculate Indicators manually to avoid pandas-ta dependency
        # RSI 14 & 2
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI_14'] = 100 - (100 / (1 + rs))
        
        gain2 = (delta.where(delta > 0, 0)).rolling(window=2).mean()
        loss2 = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
        rs2 = gain2 / loss2
        df['RSI_2'] = 100 - (100 / (1 + rs2))

        # MACD (12, 26, 9)
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD_12_26_9'] = ema12 - ema26
        df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=9, adjust=False).mean()
        df['MACDh_12_26_9'] = df['MACD_12_26_9'] - df['MACDs_12_26_9']

        # Bollinger Bands (20, 2)
        df['BBM_20_2.0'] = df['close'].rolling(window=20).mean()
        std20 = df['close'].rolling(window=20).std()
        df['BBU_20_2.0'] = df['BBM_20_2.0'] + (std20 * 2)
        df['BBL_20_2.0'] = df['BBM_20_2.0'] - (std20 * 2)

        # ATR (14)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['ATRr_14'] = tr.rolling(window=14).mean()
        
        # VWAP (simplified moving VWAP for the block, usually VWAP resets daily)
        df['VWAP_D'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()
        
        # OBV (simplified)
        obv = [0]
        for i in range(1, len(df)):
            if df['close'].iloc[i] > df['close'].iloc[i-1]:
                obv.append(obv[-1] + df['volume'].iloc[i])
            elif df['close'].iloc[i] < df['close'].iloc[i-1]:
                obv.append(obv[-1] - df['volume'].iloc[i])
            else:
                obv.append(obv[-1])
        df['OBV'] = obv

        last = df.iloc[-1]
        
        features = {}
        
        # Momentum
        features['rsi_14'] = last.get('RSI_14', 50.0)
        features['rsi_2'] = last.get('RSI_2', 50.0)
        
        # slope = (current - N_ago) / N
        rsi14_3_ago = df['RSI_14'].iloc[-4] if len(df) >= 4 else features['rsi_14']
        features['rsi_slope_3d'] = (features['rsi_14'] - rsi14_3_ago) / 3.0
        
        features['macd_hist'] = last.get('MACDh_12_26_9', 0.0)
        macd_line = last.get('MACD_12_26_9', 0.0)
        macd_signal = last.get('MACDs_12_26_9', 0.0)
        features['macd_cross'] = 1 if macd_line > macd_signal else -1
        
        macd_hist_1_ago = df['MACDh_12_26_9'].iloc[-2] if len(df) >= 2 else 0.0
        features['macd_hist_slope'] = features['macd_hist'] - macd_hist_1_ago

        # Volatility
        upper_bb = last.get('BBU_20_2.0', last['close'])
        lower_bb = last.get('BBL_20_2.0', last['close'])
        mid_bb = last.get('BBM_20_2.0', last['close'])
        
        if upper_bb > lower_bb:
            features['bb_position'] = (last['close'] - lower_bb) / (upper_bb - lower_bb)
            features['bb_width'] = (upper_bb - lower_bb) / mid_bb
        else:
            features['bb_position'] = 0.5
            features['bb_width'] = 0.0
            
        features['atr_14'] = last.get('ATRr_14', 0.0)
        features['atr_pct'] = features['atr_14'] / last['close'] if last['close'] > 0 else 0.0
        
        # TQQQ HV (Historical Volatility)
        returns = df['close'].pct_change().dropna()
        features['tqqq_hv_10'] = returns.tail(10).std() * np.sqrt(252) if len(returns) >= 10 else 0.0
        features['tqqq_hv_5'] = returns.tail(5).std() * np.sqrt(252) if len(returns) >= 5 else 0.0
        
        # Volume/Flow
        vwap_val = last.get('VWAP_D', last['close'])
        features['vwap_distance'] = (last['close'] - vwap_val) / vwap_val if vwap_val > 0 else 0.0
        
        vol_ma20 = df['volume'].tail(20).mean()
        features['volume_ratio'] = last['volume'] / vol_ma20 if vol_ma20 > 0 else 1.0
        
        obv_val = last.get('OBV', 0.0)
        obv_5_ago = df['OBV'].iloc[-6] if len(df) >= 6 else obv_val
        features['obv_slope'] = (obv_val - obv_5_ago) / 5.0

        features['stoch_k'] = last.get('STOCHk_14_3_3', 50.0)
        features['stoch_d'] = last.get('STOCHd_14_3_3', 50.0)
        
        # VIX Context
        features['vix_level'] = market_data.get('vix_level', 20.0)
        features['vix_roc_5'] = market_data.get('vix_roc_5', 0.0)
        features['iv_rank'] = market_data.get('iv_rank', 50.0)
        features['iv_percentile'] = market_data.get('iv_percentile', 50.0)
        features['term_slope'] = market_data.get('term_slope', 0.0)

        # Structure
        ma20 = df['close'].tail(20).mean()
        ma50 = df['close'].tail(50).mean()
        features['dist_from_20ma'] = (last['close'] - ma20) / last['close'] if last['close'] > 0 else 0.0
        features['dist_from_50ma'] = (last['close'] - ma50) / last['close'] if last['close'] > 0 else 0.0

        return features

    def dip_score(self, features: Dict[str, Any]) -> float:
        """
        Returns 0.0-1.0 score indicating strength of current dip.
        > 0.70 = strong dip, favorable for opening diagonal.
        """
        if self.ml_model:
            return self.ml_model.predict_dip_probability(features)
        return self._rule_based_dip_score(features)

    def bounce_score(self, features: Dict[str, Any]) -> float:
        """
        Returns 0.0-1.0 score indicating strength of current bounce.
        > 0.70 = strong bounce, favorable for closing hedge.
        """
        if self.ml_model:
            return self.ml_model.predict_bounce_probability(features)
        return self._rule_based_bounce_score(features)

    def _rule_based_dip_score(self, f: Dict[str, Any]) -> float:
        score = 0.30
        
        # RSI components (broader ranges)
        rsi14 = f.get('rsi_14', 50)
        if rsi14 < 25: score += 0.20
        elif rsi14 < 35: score += 0.15
        elif rsi14 < 45: score += 0.08
        
        rsi2 = f.get('rsi_2', 50)
        if rsi2 < 10: score += 0.12
        elif rsi2 < 20: score += 0.08
        elif rsi2 < 30: score += 0.04
        
        if f.get('rsi_slope_3d', 0) > 0: score += 0.05
        
        # Stochastic
        stoch_k = f.get('stoch_k', 50)
        stoch_d = f.get('stoch_d', 50)
        if stoch_k < 20 and stoch_d < 20: score += 0.10
        elif stoch_k < 30: score += 0.05
        
        # MACD (any positive momentum helps)
        if f.get('macd_cross', 0) == 1 and f.get('macd_hist_slope', 0) > 0: score += 0.12
        elif f.get('macd_hist_slope', 0) > 0: score += 0.08
        elif f.get('macd_cross', 0) == 1: score += 0.05
        
        # Bollinger Bands (broader ranges)
        bb = f.get('bb_position', 0.5)
        if bb < 0.10: score += 0.15
        elif bb < 0.25: score += 0.10
        elif bb < 0.40: score += 0.05
        
        # Price below moving averages = dip
        dist20 = f.get('dist_from_20ma', 0)
        if dist20 < -0.03: score += 0.10
        elif dist20 < -0.01: score += 0.05
        
        # Volume spike on dip = capitulation
        if f.get('volume_ratio', 1) > 1.5: score += 0.05
        elif f.get('volume_ratio', 1) > 1.2: score += 0.03
        
        # IV context (rich premium helps entry)
        iv = f.get('iv_rank', 50)
        if iv > 40: score += 0.08
        elif iv > 25: score += 0.04
        elif iv < 10: score -= 0.05
        
        # VIX rising = fear
        if f.get('vix_roc_5', 0) > 0.10: score += 0.05
        elif f.get('vix_roc_5', 0) > 0.03: score += 0.03
        
        return max(0.0, min(1.0, float(score)))

    def _rule_based_bounce_score(self, f: Dict[str, Any]) -> float:
        score = 0.30
        
        # RSI recovering
        rsi14 = f.get('rsi_14', 50)
        if rsi14 > 55: score += 0.15
        elif rsi14 > 45: score += 0.10
        elif rsi14 > 38: score += 0.05
        
        if f.get('rsi_slope_3d', 0) > 1: score += 0.08
        if f.get('rsi_2', 50) > 70: score += 0.10
        elif f.get('rsi_2', 50) > 50: score += 0.05
        
        # Stochastic Bounce
        stoch_k = f.get('stoch_k', 50)
        if stoch_k > 80: score += 0.10
        elif stoch_k > 50: score += 0.05
        
        # MACD positive momentum
        if f.get('macd_hist', 0) > 0 and f.get('macd_hist_slope', 0) > 0: score += 0.12
        elif f.get('macd_hist', 0) > 0: score += 0.06
        
        # Price above VWAP
        if f.get('vwap_distance', 0) > 0: score += 0.08
        
        # BB normalizing
        bb = f.get('bb_position', 0.5)
        if bb > 0.60: score += 0.08
        elif bb > 0.45: score += 0.04
        
        # Price above MAs
        if f.get('dist_from_20ma', 0) > 0.01: score += 0.08
        
        # VIX declining
        if f.get('vix_roc_5', 0) < -0.05: score += 0.08
        elif f.get('vix_roc_5', 0) < -0.02: score += 0.04
        
        return max(0.0, min(1.0, float(score)))
