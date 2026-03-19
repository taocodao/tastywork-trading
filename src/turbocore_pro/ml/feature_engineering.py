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
        
    # -- 5. Fakeout Volume Features --
    if 'qqq_volume' in fdf.columns:
        vol_5d = fdf['qqq_volume'].rolling(5).mean()
        vol_20d = fdf['qqq_volume'].rolling(20).mean()
        # Scale handling
        log_vol_ratio = np.log(vol_5d / vol_20d.replace(0, np.nan))
        fdf['vol_ratio'] = log_vol_ratio.rolling(252).rank(pct=True).fillna(0.5)
    else:
        fdf['vol_ratio'] = 0.5
        
    return fdf

def label_crossover_outcomes(df: pd.DataFrame, forward_days: int = 63, tp_mult: float = 3.0, sl_mult: float = 1.5) -> pd.DataFrame:
    """
    Labels historical Bull Crossovers using Triple Barrier Method (Meta-Labeling).
    Barriers are dynamically set using recent macro volatility.
    1 = Hit Take-Profit (Upper barrier) before Stop-Loss or Time-out
    0 = Hit Stop-Loss (Lower barrier) or Timed out (Vertical barrier)
    """
    fdf = df.copy()
    fdf['target_profitable'] = np.nan
    
    # Approximate macro volatility with 60-day rolling std of returns
    ret_std = fdf['tqqq_close'].pct_change().rolling(60).std()
    
    # Only evaluate days with an active BULL crossover trigger
    # Specifically, the day the 5 EMA crosses above the 30 EMA
    fdf['bull_cross_trigger'] = (fdf['tqqq_bull_cross'] == True) & (fdf['tqqq_bull_cross'].shift(1) == False)
    
    for idx_loc in range(len(fdf)):
        idx = fdf.index[idx_loc]
        if fdf.loc[idx, 'bull_cross_trigger']:
            # Look ahead forward_days (Vertical Barrier)
            end_loc = min(idx_loc + forward_days, len(fdf) - 1)
            future_slice = fdf.iloc[idx_loc+1 : end_loc+1]
            
            if len(future_slice) < 5:
                # Not enough future data to label accurately
                continue
                
            entry_price = fdf.loc[idx, 'tqqq_close']
            daily_vol = ret_std.loc[idx]
            
            # Dynamic horizontal barriers based on path volatility estimate
            if pd.isna(daily_vol) or daily_vol == 0:
                upper_barrier = entry_price * 1.06
                lower_barrier = entry_price * 0.96
            else:
                path_vol = daily_vol * np.sqrt(forward_days)
                upper_barrier = entry_price * (1 + (path_vol * tp_mult))
                lower_barrier = entry_price * (1 - (path_vol * sl_mult))
                
            hit_tp = False
            
            for f_idx, row in future_slice.iterrows():
                if row['tqqq_close'] >= upper_barrier:
                    hit_tp = True
                    break
                if row['tqqq_close'] <= lower_barrier:
                    hit_tp = False
                    break
            
            # Label 1 if it achieved the upper barrier first
            fdf.loc[idx, 'target_profitable'] = 1 if hit_tp else 0
            
    return fdf
