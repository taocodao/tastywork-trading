import pandas as pd
import numpy as np

def generate_technical_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Appends momentum, volatility, and trend features to the master dataframe
    to feed into the XGBoost Signal Scorer.
    
    Expects qqq_close, tqqq_close, vix_close
    """
    if 'tqqq_close' not in df.columns:
        return df
        
    fdf = df.copy()
    close_s = fdf['tqqq_close']
    
    # -- 1. Momentum: RSI (14) --
    delta = close_s.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    fdf['tqqq_rsi_14'] = 100 - (100 / (1 + rs))
    
    # -- 2. Trend: MACD (12, 26, 9) --
    ema12 = close_s.ewm(span=12, adjust=False).mean()
    ema26 = close_s.ewm(span=26, adjust=False).mean()
    fdf['tqqq_macd'] = ema12 - ema26
    fdf['tqqq_macd_signal'] = fdf['tqqq_macd'].ewm(span=9, adjust=False).mean()
    fdf['tqqq_macd_hist'] = fdf['tqqq_macd'] - fdf['tqqq_macd_signal']
    
    # -- 3. Volatility: Bollinger Bands (20, 2) width --
    sma20 = close_s.rolling(window=20).mean()
    std20 = close_s.rolling(window=20).std()
    upper_band = sma20 + (std20 * 2)
    lower_band = sma20 - (std20 * 2)
    fdf['tqqq_bb_width'] = (upper_band - lower_band) / sma20
    
    # -- 4. Relative VIX --
    if 'vix_close' in fdf.columns:
        vix_sma50 = fdf['vix_close'].rolling(50).mean()
        fdf['vix_rel_50'] = fdf['vix_close'] / vix_sma50
        
    return fdf

def label_crossover_outcomes(df: pd.DataFrame, forward_days: int = 20, threshold_pct: float = 0.05) -> pd.DataFrame:
    """
    Labels historical Bull Crossovers (Buy Signals) as 1 (Profitable) or 0 (Unprofitable).
    A signal is profitable if TQQQ appreciates by `threshold_pct` 
    within `forward_days` after the signal fires.
    """
    fdf = df.copy()
    fdf['target_profitable'] = np.nan
    
    # Only evaluate days with an active BULL crossover trigger
    # Specifically, the day the 5 EMA crosses above the 30 EMA
    fdf['bull_cross_trigger'] = (fdf['tqqq_bull_cross'] == True) & (fdf['tqqq_bull_cross'].shift(1) == False)
    
    trigger_indices = fdf[fdf['bull_cross_trigger']].index
    
    for idx_loc in range(len(fdf)):
        idx = fdf.index[idx_loc]
        if fdf.loc[idx, 'bull_cross_trigger']:
            # Look ahead forward_days
            end_loc = min(idx_loc + forward_days, len(fdf) - 1)
            future_slice = fdf.iloc[idx_loc+1 : end_loc+1]
            
            if len(future_slice) < 5:
                # Not enough future data to label accurately
                continue
                
            entry_price = fdf.loc[idx, 'tqqq_close']
            max_future_price = future_slice['tqqq_close'].max()
            
            gain_pct = (max_future_price - entry_price) / entry_price
            
            # Label 1 if it achieved the threshold gain
            fdf.loc[idx, 'target_profitable'] = 1 if gain_pct >= threshold_pct else 0
            
    return fdf
