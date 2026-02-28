"""
TurboBounce Options: Multi-Ticker Universe Definition
=====================================================

Contains the list of ~47 high-beta/liquid tickers categorized by sector,
primarily sourced from the D watch.csv and core ETFs.
"""

from dataclasses import dataclass
from typing import List, Dict

@dataclass
class TickerConfig:
    symbol: str
    category: str
    is_leveraged_etf: bool = False
    
# TurboBounce Multi-Ticker Universe (~47 symbols)
# TQQQ is included here so it can compete in the "Unified" mode.
TURBOBOUNCE_UNIVERSE = [
    # 3x Leveraged ETFs
    TickerConfig("TQQQ", "3x Leveraged", True),
    TickerConfig("SOXL", "3x Leveraged", True),
    TickerConfig("LABU", "3x Leveraged", True),
    
    # Mega-cap Tech
    TickerConfig("NVDA", "Mega-cap Tech"),
    TickerConfig("AAPL", "Mega-cap Tech"),
    TickerConfig("MSFT", "Mega-cap Tech"),
    TickerConfig("GOOGL", "Mega-cap Tech"),
    TickerConfig("AMZN", "Mega-cap Tech"),
    TickerConfig("META", "Mega-cap Tech"),
    TickerConfig("TSLA", "Mega-cap Tech"),
    
    # Semiconductors
    TickerConfig("AMD", "Semiconductor"),
    TickerConfig("AVGO", "Semiconductor"),
    TickerConfig("MU", "Semiconductor"),
    TickerConfig("QCOM", "Semiconductor"),
    TickerConfig("AMAT", "Semiconductor"),
    TickerConfig("ASML", "Semiconductor"),
    TickerConfig("MRVL", "Semiconductor"),
    
    # High-beta Growth
    TickerConfig("SHOP", "Growth"),
    TickerConfig("COIN", "Growth"),
    TickerConfig("PLTR", "Growth"),
    TickerConfig("CRWD", "Growth"),
    TickerConfig("SNOW", "Growth"),
    TickerConfig("MSTR", "Growth"),
    TickerConfig("APP", "Growth"),
    
    # Infra / AI Data
    TickerConfig("VRT", "Infra"),
    TickerConfig("CLS", "Infra"),
    TickerConfig("ANET", "Infra"),
    TickerConfig("NET", "Infra"),
    TickerConfig("NOW", "Infra"),
    TickerConfig("ARM", "Infra"),
    
    # High-beta (from user D watch.csv)
    TickerConfig("EME", "High-beta Watchlist"),
    TickerConfig("CRDO", "High-beta Watchlist"),
    TickerConfig("COHR", "High-beta Watchlist"),
    TickerConfig("CIEN", "High-beta Watchlist"),
    TickerConfig("RDDT", "High-beta Watchlist"),
    TickerConfig("DASH", "High-beta Watchlist"),
    TickerConfig("HOOD", "High-beta Watchlist"),
    
    # Core ETFs
    TickerConfig("SPY", "Core ETF"),
    TickerConfig("QQQ", "Core ETF"),
    TickerConfig("IWM", "Core ETF"),
    TickerConfig("GDX", "Core ETF"),
    
    # SaaS / Cloud
    TickerConfig("CRM", "SaaS"),
    TickerConfig("WDAY", "SaaS"),
    TickerConfig("ZS", "SaaS"),
    TickerConfig("MDB", "SaaS"),
    TickerConfig("INTU", "SaaS"),
    TickerConfig("ADBE", "SaaS"),
]

def get_turbobounce_symbols() -> List[str]:
    """Returns a flat list of just the symbols."""
    return [config.symbol for config in TURBOBOUNCE_UNIVERSE]

def get_category_for_symbol(symbol: str) -> str:
    for config in TURBOBOUNCE_UNIVERSE:
        if config.symbol == symbol:
            return config.category
    return "Unknown"
