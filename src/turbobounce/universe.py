"""
TurboBounce Options: Multi-Ticker Universe Definition
=====================================================

Contains the list of tickers provided by the user.
"""

from dataclasses import dataclass
from typing import List

@dataclass
class TickerConfig:
    symbol: str
    category: str
    is_leveraged_etf: bool = False
    
import pandas as pd

# TurboBounce User-Provided Universe (Essential Base)
base_symbols = [
    "EME", "FN", "LITE", "CRDO", "VRT", "AMAT", "AVGO", "CLS", "LABU", "WDC", "COHR", 
    "BIDU", "ASML", "AGQ", "CIEN", "MU", "VST", "TQQQ", "GLW", "NVDA", "SANM", "ALAB", 
    "CAT", "CEG", "TSM", "BABA", "GEV", "NVT", "AMD", "SNDK", "ANET", "MRVL", "JBL", 
    "APLX", "GOOG", "ARM", "HROW", "NUGT", "MSTR", "TT", "TSLA", "ADI", "AXSM", "NBIS", 
    "JCI", "BA", "QQQ", "NVO", "WPM", "CRWV", "CSCO", "COIN", "OKLO", "AMZN", "GDX", 
    "MELI", "ABBV", "ARKK", "SPXC", "AYI", "AEM", "LMT", "VRTX", "RMBS", "ECL", "AAPL", 
    "ARKW", "LEU", "AEP", "HOOD", "SLB", "ORCL", "META", "SATS", "PLTR", "WAT", "WMT", 
    "COST", "RSP", "QCOM", "CVX", "XOM", "MSFT", "RKLB", "GS", "AVAV", "JPM", "CHRW", 
    "NFLX", "ADBE", "ASTS", "GPOR", "DIS", "KTOS", "VLO", "MA", "V", "RCL", "NET", 
    "LULU", "XYL", "CRM", "AXP", "APP", "SAP", "SHOP", "RDDT", "IBM", "RBRK", "SPOT", 
    "NOW", "CRWD", "ANF", "DUOL", "SNOW", "DASH", "INTU", "MDB", "WDAY", "ZS", "CRCL", 
    "TFX", "VIX"
]

_cached_symbols = None
TURBOBOUNCE_UNIVERSE: List[TickerConfig] = []

def get_turbobounce_symbols() -> List[str]:
    """Returns a flat list of symbols: Base + S&P 500 dynamically fetched."""
    global _cached_symbols
    if _cached_symbols is not None:
        return _cached_symbols

    combined = list(base_symbols)
    try:
        # Dynamically fetch S&P 500
        sp500_table = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        sp500_df = sp500_table[0]
        sp500_tickers = sp500_df['Symbol'].tolist()
        
        # Clean up tickers for yfinance (e.g., BRK.B -> BRK-B)
        sp500_tickers = [sym.replace('.', '-') for sym in sp500_tickers]
        combined.extend(sp500_tickers)
    except Exception as e:
        print(f"Warning: Could not fetch S&P 500 tickers ({e}). Falling back to base list.")
        
    _cached_symbols = list(set(combined)) # Deduplicate
    return _cached_symbols

def init_universe():
    global TURBOBOUNCE_UNIVERSE
    syms = get_turbobounce_symbols()
    TURBOBOUNCE_UNIVERSE = [TickerConfig(sym, "Dynamic Watchlist", sym in ["TQQQ", "LABU", "NUGT", "AGQ"]) for sym in syms]

init_universe()

def get_category_for_symbol(symbol: str) -> str:
    for config in TURBOBOUNCE_UNIVERSE:
        if config.symbol == symbol:
            return config.category
    return "Unknown"
