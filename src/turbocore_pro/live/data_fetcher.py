"""
Data Fetcher — fetches VIX9D/VIX3M from CBOE and merges with IBKR hourly bars.

The Phase 3 features (VIX9D, VIX3M, breadth divergence) give +1.70pp CAGR
but aren't available from IBKR's hourly data feed. This module fetches them
from CBOE's website and aligns to the QQQ RTH bar grid.

Fallback: if CBOE is blocked, fetches VIX from IBKR as an index.
"""
import logging
import io
from datetime import datetime, timedelta

import pandas as pd
import requests

log = logging.getLogger("turbocore.live.data")

# CBOE daily settle data URLs (free, public, updated daily after close)
CBOE_URLS = {
    "VIX":   "https://cdn.cboe.com/api/global/delayed_quotes/charts/_indices/_VIX.csv",
    "VIX9D": "https://cdn.cboe.com/api/global/delayed_quotes/charts/_indices/_VIX9D.csv",
    "VIX3M": "https://cdn.cboe.com/api/global/delayed_quotes/charts/_indices/_VIX3M.csv",
}

# CBOE alternative: Macrotrends or Yahoo Finance fallbacks
YAHOO_URLS = {
    "VIX":   "https://query1.finance.yahoo.com/v7/finance/download/^VIX?period1={start}&period2={end}&interval=1d&events=history",
    "VIX9D": "https://query1.finance.yahoo.com/v7/finance/download/^VIX9D?period1={start}&period2={end}&interval=1d&events=history",
    "VIX3M": "https://query1.finance.yahoo.com/v7/finance/download/^VIX3M?period1={start}&period2={end}&interval=1d&events=history",
}


def fetch_cboe_index(symbol: str, lookback_days: int = 400) -> pd.DataFrame:
    """
    Fetch a VIX-series index from CBOE as a daily OHLC DataFrame.
    Returns DataFrame indexed by date with columns: open, high, low, close.
    """
    url = CBOE_URLS.get(symbol)
    if not url:
        log.warning(f"No CBOE URL for {symbol}")
        return pd.DataFrame()

    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        })
        resp.raise_for_status()
        # CBOE CSVs have a header line like "Time,..." then data
        df = pd.read_csv(io.StringIO(resp.text), skiprows=1)
        df.columns = [c.strip().lower() for c in df.columns]

        # Find date and close columns
        date_col = "time" if "time" in df.columns else df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.set_index(date_col)

        # Keep last lookback_days
        cutoff = datetime.now() - timedelta(days=lookback_days)
        df = df[df.index >= cutoff]

        log.info(f"Fetched {len(df)} rows of {symbol} from CBOE "
                 f"({df.index[0].date()} to {df.index[-1].date()})")
        return df
    except Exception as e:
        log.error(f"Failed to fetch {symbol} from CBOE: {e}")
        return pd.DataFrame()


def fetch_yahoo_index(symbol: str, lookback_days: int = 400) -> pd.DataFrame:
    """Fetch VIX from Yahoo Finance as fallback when CBOE is blocked."""
    end = int(datetime.now().timestamp())
    start = int((datetime.now() - timedelta(days=lookback_days)).timestamp())
    yahoo_symbol = f"^{symbol}"
    url = f"https://query1.finance.yahoo.com/v7/finance/download/{yahoo_symbol}?period1={start}&period2={end}&interval=1d&events=history"
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = [c.strip().lower() for c in df.columns]
        date_col = "date" if "date" in df.columns else df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.set_index(date_col)
        log.info(f"Fetched {len(df)} rows of {symbol} from Yahoo Finance")
        return df
    except Exception as e:
        log.warning(f"Yahoo Finance fallback failed for {symbol}: {e}")
        return pd.DataFrame()


def fetch_vix_from_ibkr(ibkr_client, lookback_days: int = 400) -> dict[str, pd.DataFrame]:
    """Fetch VIX hourly data from IBKR as an index. Returns dict of DataFrames."""
    result = {}
    if not ibkr_client or not ibkr_client.ib:
        return result
    try:
        from ib_async import Index
        for symbol in ["VIX"]:
            contract = Index(symbol, "CBOE", "USD")
            ibkr_client.ib.qualifyContracts(contract)
            lookback_bars = int(lookback_days * 7)  # approx hourly bars
            # IBKR requires years for durations > 365 days
            duration = "2 Y" if lookback_days > 365 else f"{lookback_days} D"
            bars = ibkr_client.ib.reqHistoricalData(
                contract, endDateTime="",
                durationStr=duration,
                barSizeSetting="1 hour",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
            if bars:
                df_data = [{"datetime": b.date, "close": b.close,
                            "open": b.open, "high": b.high, "low": b.low}
                           for b in bars]
                df = pd.DataFrame(df_data).set_index("datetime")
                result[symbol] = df
                log.info(f"Fetched {len(bars)} VIX bars from IBKR")
    except Exception as e:
        log.warning(f"IBKR VIX fetch failed: {e}")
    return result


def fetch_all_vix_indices(lookback_days: int = 400,
                           ibkr_client=None) -> dict[str, pd.DataFrame]:
    """Fetch VIX, VIX9D, VIX3M. Tries CBOE → Yahoo → IBKR fallback."""
    result = {}
    for symbol in ["VIX", "VIX9D", "VIX3M"]:
        # Try CBOE first
        df = fetch_cboe_index(symbol, lookback_days)
        if df.empty:
            # Try Yahoo Finance
            df = fetch_yahoo_index(symbol, lookback_days)
        if not df.empty:
            result[symbol] = df

    # If VIX still missing, try IBKR
    if "VIX" not in result and ibkr_client:
        ibkr_vix = fetch_vix_from_ibkr(ibkr_client, lookback_days)
        result.update(ibkr_vix)

    if not result:
        log.warning("All VIX data sources failed — signal quality will be degraded")
    return result


def align_vix_to_hourly(vix_daily: pd.DataFrame, qqq_hourly_index: pd.DatetimeIndex) -> pd.Series:
    """
    As-of (backward) fill daily VIX values onto the QQQ hourly bar grid.
    Each hourly bar gets the most recent daily VIX close at or before that timestamp.
    """
    if vix_daily.empty:
        return pd.Series(dtype=float)

    # Use the close column (might be named 'close' or 'vix close' etc.)
    close_col = None
    for c in vix_daily.columns:
        if "close" in c.lower():
            close_col = c
            break
    if close_col is None:
        close_col = vix_daily.columns[-1]

    daily_close = vix_daily[close_col].sort_index()
    # Reindex daily to hourly via as-of join
    hourly_series = daily_close.reindex(qqq_hourly_index, method="ffill")
    return hourly_series


def compute_vix_term_slope(vix: pd.Series, vix3m: pd.Series) -> pd.Series:
    """
    Approximate VIX term structure slope: VIX/VIX3M ratio.
    Values > 1 = backwardation (near-term fear), < 1 = contango (calm).
    """
    # Align both to same index
    combined = pd.concat([vix.rename("vix"), vix3m.rename("vix3m")], axis=1)
    combined = combined.ffill().dropna()
    return combined["vix"] / combined["vix3m"]
