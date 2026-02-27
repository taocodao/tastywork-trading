import logging
import asyncio
from typing import Optional, Dict
import pandas as pd
import ta

logger = logging.getLogger(__name__)

class TQQQIntradayFetcher:
    """
    Fetches intraday 5-min OHLCV bars from IB Gateway and computes technical features.
    
    Uses the centralized IBMarketDataHub to share the connection with other strategies.
    Automatically merges with daily context (Hurst, OU, SMA distance) if provided.
    """
    
    def __init__(self, hub=None):
        self._hub = hub
        self._connected = False
        
        # We can run independent of hub for backtesting
        if hub is not None:
            self._use_hub = True
            logger.info("TQQQIntradayFetcher initialized with shared IB hub")
        else:
            self._use_hub = False
            from ib_insync import IB
            self.ib = IB()
            logger.warning("TQQQIntradayFetcher initialized without hub (direct connection mode)")

    @property
    def client(self):
        """Get the active IB client."""
        if self._use_hub:
            return self._hub.data_client
        return self.ib

    def connect(self, host="127.0.0.1", port=4004, client_id=3005) -> bool:
        """Connect to IB Gateway."""
        if self._use_hub:
            return self._hub.connect_data()
            
        try:
            if not self.ib.isConnected():
                logger.info(f"Connecting to IB Gateway at {host}:{port}...")
                self.ib.connect(host, port, clientId=client_id, timeout=10)
                self._connected = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IB: {e}")
            self._connected = False
            return False

    def fetch_bars(self, symbol: str = "TQQQ", duration: str = "2 D", bar_size: str = "5 mins") -> Optional[pd.DataFrame]:
        """
        Fetch intraday bars via IB reqHistoricalData.
        
        Args:
            symbol: Stock symbol
            duration: Duration string (e.g., "2 D", "1 W", "1 M")
            bar_size: Bar size string (e.g., "5 mins", "15 mins")
            
        Returns:
            DataFrame with OHLCV data or None if failed
        """
        if (self._use_hub and not self._hub.is_connected()[0]) or (not self._use_hub and not self.client.isConnected()):
            if not self.connect():
                logger.error("Cannot fetch bars - no IB connection")
                return None

        try:
            from ib_insync import Stock, util
            
            contract = Stock(symbol, 'SMART', 'USD')
            self.client.qualifyContracts(contract)
            
            # Fetch data (synchronous via ib_insync)
            logger.debug(f"Requesting {duration} of {bar_size} bars for {symbol}...")
            
            bars = self.client.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
            
            if not bars:
                logger.warning(f"No {bar_size} bars returned for {symbol}")
                return None
                
            # Convert to DataFrame
            df = util.df(bars)
            df.rename(columns={'date': 'timestamp'}, inplace=True)
            df.set_index('timestamp', inplace=True)
            
            logger.info(f"Fetched {len(df)} {bar_size} bars for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching intraday bars for {symbol}: {e}")
            return None

    def compute_intraday_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add purely intraday technical features to the DataFrame.
        """
        if df is None or df.empty or len(df) < 20: # Need enough for BB and RSI
            return df
            
        df_feats = df.copy()
        
        # 1. Intraday RSI (Fast)
        df_feats['rsi_2'] = ta.momentum.RSIIndicator(df_feats['close'], window=2).rsi()
        df_feats['rsi_14'] = ta.momentum.RSIIndicator(df_feats['close'], window=14).rsi()
        
        # 2. Intraday Bollinger Bands (for quick exhaustion detection)
        # 20 periods on 5-min = 100 minutes (approx 1.5 hours)
        bb = ta.volatility.BollingerBands(df_feats['close'], window=20, window_dev=2.0)
        
        df_feats['bb_lower'] = bb.bollinger_lband()
        df_feats['bb_upper'] = bb.bollinger_hband()
        
        # Manual %B calculation: (Price - Lower) / (Upper - Lower)
        range_diff = df_feats['bb_upper'] - df_feats['bb_lower']
        range_diff = range_diff.replace(0, 0.0001)  # Avoid division by zero
        df_feats['bb_pct_b'] = (df_feats['close'] - df_feats['bb_lower']) / range_diff

        # 3. Volume capitulation
        # Ratio of current bar volume to 20-bar moving average volume
        df_feats['vol_sma_20'] = df_feats['volume'].rolling(window=20).mean()
        df_feats['vol_sma_20'] = df_feats['vol_sma_20'].replace(0, 1) # Prevent div 0
        df_feats['vol_ratio'] = df_feats['volume'] / df_feats['vol_sma_20']
        
        return df_feats

    def merge_daily_context(self, intraday_df: pd.DataFrame, daily_context: Dict) -> pd.DataFrame:
        """
        Merge slower daily regime metrics onto fast intraday bars.
        
        Args:
            intraday_df: DataFrame of 5-min bars
            daily_context: Dictionary of latest daily metrics (e.g., from TQQQDataPipeline)
                Expected keys: 'hurst_exponent', 'ou_half_life', 'dist_from_200_sma', 'vix_ratio'
        """
        if intraday_df is None or intraday_df.empty:
            return intraday_df
            
        df = intraday_df.copy()
        
        # Forward fill the daily context across all intraday bars
        for key, value in daily_context.items():
            df[key] = value
            
        return df
