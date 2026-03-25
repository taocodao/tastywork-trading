import yfinance as yf
import pandas as pd
import numpy as np
import logging

log = logging.getLogger("DataFeatures")

def build_feature_set(start_date, end_date):
    log.info("Downloading market data (%s -> %s)...", start_date, end_date)
    
    qqq   = yf.download('QQQ',   start=start_date, end=end_date, progress=False)
    qqqm  = yf.download('QQQM',  start=start_date, end=end_date, progress=False)
    tqqq  = yf.download('TQQQ',  start=start_date, end=end_date, progress=False)
    sqqq  = yf.download('SQQQ',  start=start_date, end=end_date, progress=False)
    vix   = yf.download('^VIX',  start=start_date, end=end_date, progress=False)
    vix3m = yf.download('^VIX3M',start=start_date, end=end_date, progress=False)
    vix9d = yf.download('^VIX9D',start=start_date, end=end_date, progress=False)
    vvix  = yf.download('^VVIX', start=start_date, end=end_date, progress=False)
    irx   = yf.download('^IRX',  start=start_date, end=end_date, progress=False)
    
    def squeeze(df):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        return df

    qqq   = squeeze(qqq)
    qqqm  = squeeze(qqqm)
    tqqq  = squeeze(tqqq)
    sqqq  = squeeze(sqqq)
    vix   = squeeze(vix)
    vix3m = squeeze(vix3m)
    vix9d = squeeze(vix9d)
    vvix  = squeeze(vvix)
    irx   = squeeze(irx)

    log.info("Building features...")
    df = pd.DataFrame(index=qqq.index)
    
    # Prices
    df['qqq_close']  = qqq['Close']
    df['qqq_low']    = qqq['Low']
    df['qqqm_close'] = qqqm['Close'].reindex(df.index).ffill()
    df['qqqm_low']   = qqqm['Low'].reindex(df.index).ffill()
    
    # Backfill QQQM values using QQQ proxy for dates before QQQM existed (inception ~2020)
    if df['qqqm_close'].isna().any():
        ratio_c = df['qqqm_close'].dropna().iloc[0] / df['qqq_close'].loc[df['qqqm_close'].dropna().index[0]]
        df['qqqm_close'] = df['qqqm_close'].fillna(df['qqq_close'] * ratio_c)
        
        # safely handle qqmm_low
        if df['qqq_low'].notna().any():
            df['qqqm_low'] = df['qqqm_low'].fillna(df['qqq_low'] * ratio_c)
        else:
            df['qqqm_low'] = df['qqqm_close']
        
    df['qqq_open']   = qqq['Open']
    df['tqqq_close'] = tqqq['Close'].reindex(df.index).ffill()
    df['sqqq_close'] = sqqq['Close'].reindex(df.index).ffill()
    
    # VIX terms
    df['vix']   = vix['Close'].reindex(df.index).ffill().fillna(20.0)
    df['vix3m'] = vix3m['Close'].reindex(df.index).ffill().fillna(21.0)
    df['vix9d'] = vix9d['Close'].reindex(df.index).ffill().fillna(19.0)
    df['vvix']  = vvix['Close'].reindex(df.index).ffill().fillna(100.0)
    df['rf']    = (irx['Close'] / 100).reindex(df.index).ffill().fillna(0.045)
    
    # Term structure
    df['vix_vix3m_ratio']  = df['vix'] / df['vix3m']
    df['is_backwardation'] = df['vix_vix3m_ratio'] >= 1.0
    df['vix9d_vix_ratio']  = df['vix9d'] / df['vix']
    
    # IVP 252-day
    df['ivp_252'] = df['vix'].rolling(252).apply(
        lambda x: (x[:-1] < x[-1]).sum() / 251 * 100, raw=True
    ).fillna(50.0)
    
    # SMAs & EMAs
    df['sma_50']  = df['qqq_close'].rolling(50).mean()
    df['sma_100'] = df['qqq_close'].rolling(100).mean()
    df['sma_200'] = df['qqq_close'].rolling(200).mean()
    df['ema_20']  = df['qqqm_close'].ewm(span=20, adjust=False).mean()
    
    df['above_sma100'] = df['qqq_close'] > df['sma_100']
    df['above_sma200'] = df['qqq_close'] > df['sma_200']
    df['above_sma200_3d'] = df['above_sma200'].rolling(3).sum() == 3
    df['below_sma200'] = df['qqq_close'] < df['sma_200']
    df['below_sma200_3d'] = df['below_sma200'].rolling(3).sum() == 3
    
    # Gaps
    df['qqq_gap_pct']   = (df['qqq_open'] - df['qqq_close'].shift(1)) / df['qqq_close'].shift(1)
    df['gap_down_1pct'] = df['qqq_gap_pct'] <= -0.01
    df['gap_down_2pct'] = df['qqq_gap_pct'] <= -0.02
    
    # TQQQ volatility
    df['tqqq_ret_1d'] = df['tqqq_close'].pct_change(1)
    df['tqqq_hv20']   = df['tqqq_ret_1d'].rolling(20).std() * np.sqrt(252)
    df['tqqq_hv20']   = df['tqqq_hv20'].fillna(0.50)
    
    # IV Calibration (from pricing rules)
    df['tqqq_iv_atm'] = df[['tqqq_hv20', 'vix']].apply(
        lambda r: max(r['tqqq_hv20'] * 1.20, r['vix'] / 100 * 3.0), axis=1
    )
    df['tqqq_iv_10d'] = (df['tqqq_iv_atm'] * 1.30).clip(upper=3.0, lower=0.10)
    df['qqq_iv_leaps'] = df['vix'] / 100 * 1.10
    df['qqq_short_iv'] = df['vix'] / 100 * 1.08
    df['vix_call_iv']  = df['vvix'] / 100
    
    # Momentum
    for n in [1, 5, 10, 21]:
        df[f'qqq_ret_{n}d'] = df['qqq_close'].pct_change(n)
        
    df['vvix_10d_chg'] = df['vvix'].pct_change(10).fillna(0)
    
    # RSI(14)
    delta = df['qqq_close'].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df['rsi_14'] = 100 - (100 / (1 + rs))
    
    # Drop rows without 200 sma
    return df.dropna(subset=['sma_200']).copy()
