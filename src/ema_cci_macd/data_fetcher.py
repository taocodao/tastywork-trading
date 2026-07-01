"""
Data Fetcher — Swappable Market Data Interface
=================================================
Provides OHLCV candle data for the signal engine.

Default implementation uses yfinance (free, no API key).
Interface is designed so Alpaca or IB Gateway can be swapped in
by implementing the same fetch_ohlcv() signature.
"""

import logging
from typing import Protocol, Optional
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# yfinance interval → period mapping (how far back we can go)
_PERIOD_MAP = {
    "1m":  "5d",
    "5m":  "60d",
    "15m": "60d",
    "60m": "730d",
    "1h":  "730d",
    "1d":  "10y",
}

# Normalize user-facing timeframe to yfinance interval
_INTERVAL_MAP = {
    "1m":  "1m",
    "5m":  "5m",
    "15m": "15m",
    "1h":  "60m",
    "4h":  "60m",   # yfinance doesn't support 4h, use 1h
    "1d":  "1d",
}


class DataFetcher(Protocol):
    """Interface for market data providers."""
    def fetch_ohlcv(self, symbol: str, timeframe: str,
                    lookback: int = 500,
                    start: Optional[str] = None,
                    end: Optional[str] = None) -> pd.DataFrame:
        ...


class YFinanceFetcher:
    """
    Default data fetcher using yfinance (free tier).

    Returns a DataFrame with lowercase columns: open, high, low, close, volume.
    Index is DatetimeIndex.
    """

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1d",
                    lookback: int = 500,
                    start: Optional[str] = None,
                    end: Optional[str] = None) -> pd.DataFrame:
        """
        Fetch OHLCV data.

        Args:
            symbol:    Ticker symbol (e.g., "QQQ", "SPY", "BTC-USD")
            timeframe: Candle interval ("1m","5m","15m","1h","1d")
            lookback:  Number of bars (ignored if start/end provided)
            start:     Start date "YYYY-MM-DD" (optional, for backtesting)
            end:       End date "YYYY-MM-DD" (optional, for backtesting)

        Returns:
            DataFrame with columns: open, high, low, close, volume
        """
        interval = _INTERVAL_MAP.get(timeframe, "1d")

        try:
            if start and end:
                # Backtest mode: fetch exact date range
                df = yf.download(
                    symbol, start=start, end=end,
                    interval=interval, progress=False, auto_adjust=True
                )
            else:
                # Live mode: fetch by period
                period = _PERIOD_MAP.get(interval, "2y")
                df = yf.download(
                    symbol, period=period,
                    interval=interval, progress=False, auto_adjust=True
                )
        except Exception as e:
            logger.error(f"yfinance download failed for {symbol}: {e}")
            return pd.DataFrame()

        if df.empty:
            logger.warning(f"No data returned for {symbol} ({timeframe})")
            return df

        # Normalize column names to lowercase
        # Handle MultiIndex columns from yfinance (when single ticker)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        df.columns = [c.lower() for c in df.columns]

        # Ensure required columns exist
        required = ["open", "high", "low", "close"]
        for col in required:
            if col not in df.columns:
                logger.error(f"Missing column '{col}' in {symbol} data")
                return pd.DataFrame()

        df.dropna(subset=["close"], inplace=True)
        return df
