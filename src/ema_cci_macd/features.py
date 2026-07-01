"""
Feature Engineering
===================
Computes ML feature vectors for candidate setups.
"""
import pandas as pd
from typing import Dict, Any
from .config import InstrumentConfig

def build_feature_vector(df: pd.DataFrame, idx: int, config: InstrumentConfig) -> Dict[str, Any]:
    """
    Build ML features at bar index idx using only data available up to idx.
    """
    if idx < 14:  # Need some lookback for returns/ATR
        return {}
        
    window = df.iloc[:idx+1]
    cur = window.iloc[-1]
    prev3 = window.iloc[-4] if len(window) >= 4 else window.iloc[0]
    
    price = cur["close"]
    e1 = cur[f"ema_{config.ema_layers[0]}"]
    e2 = cur[f"ema_{config.ema_layers[1]}"]
    e3_layer = config.ema_layers[2] if len(config.ema_layers) > 2 else config.ema_layers[1]
    e3 = cur[f"ema_{e3_layer}"]
    
    # 1. Trend Structure (Distance to EMAs)
    dist_e1 = (price - e1) / e1
    dist_e2 = (price - e2) / e2
    dist_e3 = (price - e3) / e3
    
    # 2. EMA Slopes (over last 3 bars)
    e1_prev3 = prev3[f"ema_{config.ema_layers[0]}"]
    e2_prev3 = prev3[f"ema_{config.ema_layers[1]}"]
    e1_slope = (e1 - e1_prev3) / e1_prev3
    e2_slope = (e2 - e2_prev3) / e2_prev3
    
    # EMA stacking
    ema_stack_bullish = 1 if (e1 > e2 > e3) else 0
    ema_stack_bearish = 1 if (e1 < e2 < e3) else 0
    
    # 3. Momentum Context
    cci_now = cur["cci"]
    cci_min_5 = window["cci"].iloc[-5:].min()
    cci_max_5 = window["cci"].iloc[-5:].max()
    
    macd_now = cur["macd_hist"]
    macd_prev3 = prev3["macd_hist"]
    macd_slope = macd_now - macd_prev3
    
    # 4. Price Action & Volatility
    ret_1 = (price - window.iloc[-2]["close"]) / window.iloc[-2]["close"]
    ret_3 = (price - prev3["close"]) / prev3["close"]
    
    high_low_range = (cur["high"] - cur["low"]) / price
    
    features = {
        "dist_e1": round(dist_e1, 5),
        "dist_e2": round(dist_e2, 5),
        "dist_e3": round(dist_e3, 5),
        "e1_slope": round(e1_slope, 5),
        "e2_slope": round(e2_slope, 5),
        "stack_bull": ema_stack_bullish,
        "stack_bear": ema_stack_bearish,
        "cci_now": round(cci_now, 2),
        "cci_min_5": round(cci_min_5, 2),
        "cci_max_5": round(cci_max_5, 2),
        "macd_now": round(macd_now, 4),
        "macd_slope": round(macd_slope, 4),
        "ret_1": round(ret_1, 4),
        "ret_3": round(ret_3, 4),
        "hl_range": round(high_low_range, 4)
    }
    
    # Optional: ATR if calculated in indicators
    if "atr" in cur:
        features["atr_pct"] = round(cur["atr"] / price, 4)
        
    return features
