import pandas as pd
import yfinance as yf
import numpy as np
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class TurboCoreDataPipeline:
    def __init__(self, tickers: List[str] = ['QQQ', 'TQQQ', 'SQQQ', 'QLD', 'SGOV', '^VIX', 'TLT', 'DX-Y.NYB']):
        self.tickers = tickers
        self.data: Dict[str, pd.DataFrame] = {}
        
    def fetch_data(self, period: str = "10y") -> Dict[str, pd.DataFrame]:
        logger.info(f"Fetching {period} data for {self.tickers}")
        for ticker in self.tickers:
            try:
                df = yf.download(ticker, period=period, progress=False)
                if df.empty:
                    logger.warning(f"No data fetched for {ticker}")
                    continue
                
                # Handle multi-index columns from yfinance >= 0.2.0
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.droplevel(1)
                
                if 'Close' in df.columns:
                    df = df.dropna(subset=['Close'])
                    self.data[ticker] = df
                else:
                    logger.warning(f"No Close price found for {ticker}")
                    
            except Exception as e:
                logger.error(f"Error fetching data for {ticker}: {e}")
                
        return self.data
        
    def prepare_core_features(self) -> pd.DataFrame:
        """
        Prepares the QQQ and TQQQ base features for the EMA and SMA macro gate.
        Returns a master dataframe indexed by Date.
        """
        if 'QQQ' not in self.data or 'TQQQ' not in self.data:
            raise ValueError("QQQ and TQQQ data required for core features")
            
        qqq_df = self.data['QQQ'].copy()
        tqqq_df = self.data['TQQQ'].copy()
        
        master = pd.DataFrame(index=qqq_df.index)
        master['qqq_close'] = qqq_df['Close']
        master['tqqq_close'] = tqqq_df['Close'].reindex(master.index).ffill()
        
        if '^VIX' in self.data:
            master['vix_close'] = self.data['^VIX']['Close'].reindex(master.index).ffill()
        else:
            master['vix_close'] = np.nan
            
        # 1. 5/30 EMA on TQQQ for the micro signal
        master['tqqq_ema_5'] = master['tqqq_close'].ewm(span=5, adjust=False).mean()
        master['tqqq_ema_30'] = master['tqqq_close'].ewm(span=30, adjust=False).mean()
        
        # 2. 200 SMA on QQQ for the macro gate
        master['qqq_sma_200'] = master['qqq_close'].rolling(window=200).mean()
        
        # Core flags
        # Golden cross occurs when EMA 5 > EMA 30
        master['tqqq_bull_cross'] = master['tqqq_ema_5'] > master['tqqq_ema_30']
        
        # Macro gates (+5% / -3% hysteresis)
        master['qqq_above_sma200_buy'] = master['qqq_close'] > (master['qqq_sma_200'] * 1.05)
        master['qqq_below_sma200_sell'] = master['qqq_close'] < (master['qqq_sma_200'] * 0.97)
        
        # Features for Regime detection
        master['qqq_log_return'] = np.log(master['qqq_close'] / master['qqq_close'].shift(1))
        master['qqq_vol_20d'] = master['qqq_log_return'].rolling(window=20).std()
        
        return master.dropna()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pipeline = TurboCoreDataPipeline()
    pipeline.fetch_data("2y")
    master_df = pipeline.prepare_core_features()
    print("Master DataFrame tail:")
    print(master_df[['qqq_close', 'tqqq_close', 'vix_close', 'tqqq_ema_5', 'tqqq_ema_30', 'qqq_sma_200', 'tqqq_bull_cross']].tail())
