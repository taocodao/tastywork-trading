"""
Regime Classification
=====================
Rule-based market regime detector to condition ML signals.
"""
import pandas as pd
from .config import InstrumentConfig

def classify_regime(df: pd.DataFrame, idx: int, config: InstrumentConfig) -> str:
    """
    Classify the market regime at bar index idx.
    Returns: TRENDING_LOW_VOL, TRENDING_HIGH_VOL, RANGING_LOW_VOL, RANGING_HIGH_VOL, or UNKNOWN
    """
    if idx < 20:
        return "UNKNOWN"
        
    window = df.iloc[max(0, idx-20):idx+1]
    cur = window.iloc[-1]
    
    e1 = cur[f"ema_{config.ema_layers[0]}"]
    e3_layer = config.ema_layers[2] if len(config.ema_layers) > 2 else config.ema_layers[1]
    e3 = cur[f"ema_{e3_layer}"]
    
    # Trend strength based on EMA spread
    price = cur["close"]
    ema_spread_pct = abs(e1 - e3) / price if price > 0 else 0
    
    # Volatility based on rolling standard deviation of returns
    # (Simpler than ATR percentile for a quick proxy)
    returns = window["close"].pct_change().dropna()
    rolling_vol = returns.std()
    
    # Thresholds (could be calibrated per ticker)
    # Using simple absolute thresholds for v1
    is_trending = ema_spread_pct > 0.015  # 1.5% spread between fast/slow EMA
    is_high_vol = rolling_vol > 0.008     # 0.8% std dev per bar
    
    if is_trending and is_high_vol:
        return "TRENDING_HIGH_VOL"
    elif is_trending and not is_high_vol:
        return "TRENDING_LOW_VOL"
    elif not is_trending and is_high_vol:
        return "RANGING_HIGH_VOL"
    else:
        return "RANGING_LOW_VOL"
