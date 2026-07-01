"""
Indicator Engine — EMA, CCI, MACD Histogram
=============================================
Pure functions that compute all three indicators on an OHLCV DataFrame
using pandas-ta. No side effects, fully testable.

Indicator stack:
  - EMA (multi-period): Trend direction + dynamic support/resistance
  - CCI (Commodity Channel Index): Deviation from statistical average
  - MACD Histogram: Trend strength confirmation filter
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)

# Try pandas-ta first; fall back to manual computation if unavailable
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    logger.warning("pandas-ta not installed. Using manual indicator computation.")


def compute_indicators(df: pd.DataFrame, ema_layers: list,
                       cci_period: int = 20,
                       macd_fast: int = 12, macd_slow: int = 26,
                       macd_signal: int = 9) -> pd.DataFrame:
    """
    Add EMA columns, CCI, and MACD histogram to the DataFrame.

    Args:
        df:          OHLCV DataFrame (columns: open, high, low, close, volume)
        ema_layers:  List of EMA periods, e.g. [40, 120, 350]
        cci_period:  CCI lookback period (typically 14 or 20)
        macd_fast:   MACD fast EMA period (default 12)
        macd_slow:   MACD slow EMA period (default 26)
        macd_signal: MACD signal line period (default 9)

    Returns:
        Same DataFrame with added columns:
          ema_{period} for each period in ema_layers
          cci
          macd_hist
    """
    df = df.copy()

    if PANDAS_TA_AVAILABLE:
        return _compute_with_pandas_ta(df, ema_layers, cci_period,
                                        macd_fast, macd_slow, macd_signal)
    else:
        return _compute_manual(df, ema_layers, cci_period,
                               macd_fast, macd_slow, macd_signal)


def _compute_with_pandas_ta(df, ema_layers, cci_period,
                             macd_fast, macd_slow, macd_signal):
    """Compute indicators using pandas-ta library."""
    # EMA layers
    for period in ema_layers:
        col_name = f"ema_{period}"
        df[col_name] = ta.ema(df["close"], length=period)

    # CCI
    df["cci"] = ta.cci(df["high"], df["low"], df["close"], length=cci_period)

    # MACD — pandas-ta returns a DataFrame with 3 columns
    macd_df = ta.macd(df["close"], fast=macd_fast, slow=macd_slow,
                      signal=macd_signal)
    if macd_df is not None:
        hist_col = f"MACDh_{macd_fast}_{macd_slow}_{macd_signal}"
        if hist_col in macd_df.columns:
            df["macd_hist"] = macd_df[hist_col]
        else:
            # Fallback: take the third column (histogram)
            df["macd_hist"] = macd_df.iloc[:, 2]
    else:
        df["macd_hist"] = 0.0

    # Drop warmup NaN rows (longest EMA determines warmup)
    df.dropna(subset=[f"ema_{max(ema_layers)}"], inplace=True)

    return df


def _compute_manual(df, ema_layers, cci_period,
                     macd_fast, macd_slow, macd_signal):
    """Manual indicator computation when pandas-ta is not available."""
    # EMA layers
    for period in ema_layers:
        df[f"ema_{period}"] = df["close"].ewm(span=period, adjust=False).mean()

    # CCI (manual)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    tp_sma = typical_price.rolling(window=cci_period).mean()
    tp_mad = typical_price.rolling(window=cci_period).apply(
        lambda x: abs(x - x.mean()).mean(), raw=True
    )
    df["cci"] = (typical_price - tp_sma) / (0.015 * tp_mad)

    # MACD histogram (manual)
    ema_fast = df["close"].ewm(span=macd_fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=macd_slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=macd_signal, adjust=False).mean()
    df["macd_hist"] = macd_line - signal_line

    df.dropna(subset=[f"ema_{max(ema_layers)}"], inplace=True)

    return df
