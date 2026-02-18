"""
Calendar Spreads Bot - Configuration
====================================

All configuration parameters for the Calendar Spreads trading system.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import time

# =============================================================================
# UNDERLYINGS - Highly liquid ETFs for calendar spreads
# =============================================================================
UNDERLYINGS: List[str] = ["IWM", "SPY", "QQQ"]

# =============================================================================
# SPREAD PARAMETERS
# =============================================================================
SHORT_EXPIRY_DAYS: int = 3      # Sell 3 days out (Tuesday/Wednesday)
LONG_EXPIRY_DAYS: int = 10      # Buy 10 days out (Next week)
STRIKE_SELECTION: str = "ATM"   # ATM = At-The-Money (closest to current price)
STRIKE_TOLERANCE_PCT: float = 0.5  # Accept strikes within 0.5% of ATM

# =============================================================================
# ACCOUNT & RISK PARAMETERS
# =============================================================================
ACCOUNT_SIZE: float = 50000     # Starting account size (adjusted for Theta strategy)
RISK_PER_TRADE_PCT: float = 2.0   # Risk 2% of account per trade
MAX_CONCURRENT_POSITIONS: int = 3  # Maximum simultaneous positions
PROFIT_TARGET_PCT: float = 5.0    # Close at +5% profit
STOP_LOSS_PCT: float = -10.0      # Close at -10% loss
MAX_DAILY_LOSS_PCT: float = 3.0   # Stop trading if down 3% in a day

# =============================================================================
# POSITION SIZING
# =============================================================================
MIN_TRADE_COST: float = 150     # Minimum spread cost to consider
MAX_TRADE_COST: float = 400     # Maximum spread cost per trade
DEFAULT_CONTRACTS: int = 1      # Start with 1 contract

# =============================================================================
# LIQUIDITY FILTERS
# =============================================================================
MIN_OPEN_INTEREST: int = 100    # Minimum open interest
MAX_BID_ASK_SPREAD: float = 0.05  # Maximum bid-ask spread ($0.05)
MIN_VOLUME: int = 50            # Minimum daily volume

# =============================================================================
# VOLATILITY FILTERS
# =============================================================================
MIN_VIX: float = 12             # Skip trading if VIX too low
MAX_VIX: float = 25             # Skip trading if VIX too high
VIX_SYMBOL: str = "VIX"

# =============================================================================
# THETA STRATEGY PARAMETERS
# =============================================================================
THETA_DELTA_TOLERANCE: float = 0.10  # Accept puts within 0.10 delta of target
THETA_MIN_PREMIUM: float = 0.50       # Minimum premium per contract ($50 per contract)

# =============================================================================
# SCHEDULE
# =============================================================================
ENTRY_TIME: time = time(15, 50)   # 3:50 PM - Enter spreads
EXIT_CHECK_TIME: time = time(9, 35)  # 9:35 AM - Check positions
MAX_HOLD_HOURS: float = 6.5      # Close by 10:00 AM if still open

# =============================================================================
# BROKER SETTINGS - HYBRID ARCHITECTURE
# =============================================================================
# Market Data: Interactive Brokers Gateway
# Order Execution: Tastytrade API
# =============================================================================

# Interactive Brokers (Market Data Source + IB Paper Trading Execution)
# EC2 IB Gateway: 34.235.119.67:4004 (Production)
# Local Paper: 127.0.0.1:7497, Local Live: 127.0.0.1:7496
IB_HOST: str = "34.235.119.67"
IB_PORT: int = 4004              # EC2 Gateway port
IB_CLIENT_ID: int = 100

# Tastytrade (Order Execution)
# Credentials strategy:
# 1. Google Secret Manager (if GOOGLE_CLOUD_PROJECT is set)
# 2. Environment Variables (fallback)

import os
try:
    from google_secrets import get_tastytrade_creds
except ImportError:
    # Google cloud libraries not available, fallback to env vars only
    def get_tastytrade_creds():
        return {}

# Try fetching from Google Secret Manager first
_creds = get_tastytrade_creds()

# OAuth Credentials (Preferred)
TASTYTRADE_CLIENT_ID: str = _creds.get('client_id') or os.getenv('TASTYTRADE_CLIENT_ID', '')
TASTYTRADE_CLIENT_SECRET: str = _creds.get('client_secret') or os.getenv('TASTYTRADE_CLIENT_SECRET', '')
TASTYTRADE_REFRESH_TOKEN: str = _creds.get('refresh_token') or os.getenv('TASTYTRADE_REFRESH_TOKEN', '')

# Legacy Credentials (Deprecated)
TASTYTRADE_USERNAME: str = _creds.get('username') or os.getenv('TASTYTRADE_USERNAME', '')
TASTYTRADE_PASSWORD: str = _creds.get('password') or os.getenv('TASTYTRADE_PASSWORD', '')

TASTYTRADE_USE_SANDBOX: bool = os.getenv('TASTYTRADE_USE_SANDBOX', 'true').lower() == 'true'

# =============================================================================
# LOGGING & PERSISTENCE
# =============================================================================
LOG_DIR: str = "logs"
TRADE_JOURNAL_FILE: str = "trades.csv"
POSITIONS_FILE: str = "positions.json"

# =============================================================================
# EARNINGS INTELLIGENCE (Perplexity AI)
# =============================================================================
EARNINGS_ENABLED: bool = True
EARNINGS_AVOID_DAYS: int = 3
EARNINGS_REDUCE_SIZE_DAYS: int = 7
PERPLEXITY_API_KEY: str = os.getenv("PERPLEXITY_API_KEY", "")


# =============================================================================
# VERTICAL SPREAD SETTINGS
# =============================================================================
VERTICAL_SPREAD_ENABLED: bool = True
VERTICAL_MIN_CONFIDENCE: int = 60      # Minimum confidence score to generate signal
VERTICAL_DEFAULT_DTE_MIN: int = 7       # Minimum days to expiration
VERTICAL_DEFAULT_DTE_MAX: int = 21      # Maximum days to expiration  
VERTICAL_PREFERRED_DTE: int = 14        # Preferred DTE for spread selection
VERTICAL_MAX_RISK_PCT: float = 2.0      # Max risk per trade as % of account
VERTICAL_PROFIT_TARGET_PCT: float = 75.0  # Close at 75% of max profit
VERTICAL_STOP_LOSS_PCT: float = 50.0    # Close at 50% of max loss
VERTICAL_MIN_ACCOUNT_SIZE: float = 2000  # Minimum account size for verticals
VERTICAL_MIN_OPTIONS_LEVEL: int = 2     # Options approval level required

# =============================================================================
# THETA STRATEGY SETTINGS (Cash-Secured Puts)
# =============================================================================
THETA_ENABLED: bool = True
THETA_RISK_LEVEL: str = "MEDIUM"        # Default risk profile (client can override)

# Server-side quality filters (generate signals meeting minimum bar)
THETA_MIN_CONFIDENCE: int = 45          # Low bar - client filters by risk level
THETA_TARGET_DELTA: float = 0.30        # Target put delta (30-delta)
THETA_DELTA_TOLERANCE: float = 0.05     # Delta range tolerance (±5 delta)
THETA_DTE_MIN: int = 21                 # Minimum days to expiration (widened from 28)
THETA_DTE_MAX: int = 45                 # Maximum days to expiration (widened from 35)
THETA_MIN_PREMIUM: float = 0.30         # Minimum bid price ($0.30, lowered for more signals)
THETA_MIN_IV: float = 0.15              # Minimum implied volatility (15%)
THETA_MIN_LIQUIDITY: int = 100          # Minimum open interest

# Client-side filters (defaults - client provides actual values)
THETA_CONTRACTS_PER_TRADE: int = 1      # Default contracts per signal
THETA_MAX_POSITIONS: int = 6            # Default max positions (client can change)
THETA_MAX_PORTFOLIO_HEAT: float = 50000 # Default max heat (client can change)

# Signal expiration (time-sensitive signals)
THETA_SIGNAL_EXPIRY_MINUTES: int = 30   # Signals expire after 30 minutes
THETA_SIGNAL_EXPIRY_SAME_DAY: bool = True  # Signals always expire at market close


# Time-based exit targets (key differentiator)
THETA_WEEK1_PROFIT_PCT: float = 50.0    # Days 1-7: Exit at 50% profit
THETA_WEEK2_PROFIT_PCT: float = 60.0    # Days 8-14: Exit at 60% profit
THETA_WEEK3_PROFIT_PCT: float = 75.0    # Days 15-21: Exit at 75% profit
THETA_WEEK4_PROFIT_PCT: float = 90.0    # Days 22-28: Exit at 90% profit
THETA_EXPIRATION_THRESHOLD: int = 3     # Close if DTE <= 3
THETA_DEFENSIVE_BREACH_PCT: float = 2.0 # Close if underlying < strike * 98%

# Symbol selection parameters
THETA_SELECT_TOP_N: int = 12            # Select top 12 symbols daily
THETA_MIN_IV_PERCENTILE: int = 20       # Minimum IV percentile
THETA_EXCLUDE_PRE_EARNINGS_DAYS: int = 21  # Skip if earnings within N days
THETA_MAX_SECTOR_PCT: float = 25.0      # Max % per sector in watchlist

# Symbol universe (50+ liquid ETFs and stocks)
THETA_UNIVERSE: List[str] = [
    # Large Cap ETFs
    "SPY", "QQQ", "IWM", "DIA",
    # Bond/Fixed Income
    "TLT", "IEF", "LQD", "HYG", "SHY", "AGG",
    # Commodities
    "GLD", "SLV", "USO", "UNG", "DBC", "PDBC",
    # Sector ETFs
    "XLV", "XLK", "XLF", "XLI", "XLY", "XLE", "XLRE", "XLU", "XLP", "XLB",
    # Volatility
    "VXX", "UVXY",
    # International
    "EEM", "FXI", "EWJ", "EWG", "EWZ", "EWU",
    # Growth
    "ARKK", "QQQM", "VUG", "IWF",
    # Value/Dividend
    "VTV", "VYM", "SCHV", "DVY",
    # Small/Mid Cap
    "MDY", "IJR", "VB",
    # Real Estate
    "VNQ", "IYR",
    # Additional Liquid
    "RSP", "EFA", "VEA", "VWO", "BND",
]


# =============================================================================
# SMART ORDER MANAGEMENT
# =============================================================================
# Controls how limit orders are monitored and adjusted for fills.
# After placing a limit order, the system polls status every MONITOR_INTERVAL
# seconds. If still "Working" after PRICE_ADJUST_INTERVAL, the limit price is
# adjusted by PRICE_STEP (reducing credit asked or increasing debit offered).
# This repeats up to MAX_PRICE_ADJUSTMENTS times over MAX_WAIT seconds total.
# If still unfilled after all adjustments, the order expires (no market fallback).
ORDER_MONITOR_INTERVAL: int = 5         # Seconds between status checks
ORDER_PRICE_ADJUST_INTERVAL: int = 30   # Seconds before each price adjustment
ORDER_PRICE_STEP: float = 0.05          # Price adjustment per step ($)
ORDER_MAX_WAIT: int = 120               # Max seconds to wait for fill
ORDER_MAX_PRICE_ADJUSTMENTS: int = 3    # Max number of price adjustments

# =============================================================================
# COMMISSION ESTIMATES (for P&L calculation)
# =============================================================================

# =============================================================================
# ZEBRA STRATEGY SETTINGS
# =============================================================================
ZEBRA_ENABLED: bool = True

# === ZEBRA WATCHLIST (3-Tier) ===
ZEBRA_WATCHLIST: List[str] = [
    # Tier 1: Core List (Liquid Blue Chips)
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",  # Mag 7
    "JPM", "V", "MA",                                         # Finance
    "JNJ", "LLY", "UNH",                                      # Healthcare
    "XOM", "CVX",                                             # Energy
    "PG", "KO", "PEP",                                        # Staples
    "HD", "MCD", "SBUX",                                      # Discretionary
    "CAT", "DE",                                              # Industrial
    "GLD", "SLV", "TLT", "SPY", "QQQ", "IWM", "DIA"           # ETFs
]
ZEBRA_MOVER_SCAN_SYMBOLS = "SP500_NDX"  # Trigger for Tier 2 scanner
ZEBRA_MOVER_DROP_PCT: float = 5.0       # Min drop % to qualify as a "mover"
ZEBRA_MOVER_EXPIRY_DAYS: int = 14       # Auto-expiry for mover candidates

# === DIP DETECTION ===
ZEBRA_DIP_LOOKBACK_DAYS: int = 20
ZEBRA_DIP_MIN_SCORE: int = 60

# === SCORING WEIGHTS (11 Factors) ===
ZEBRA_SCORING_WEIGHTS = {
    'dip': 0.20, 
    'trend': 0.10, 
    'momentum': 0.10, 
    'volatility': 0.05,
    'volume': 0.05, 
    'mean_reversion': 0.05,
    'iv_rank': 0.15, 
    'iv_spread': 0.10, 
    'fundamentals': 0.10,
    'momentum_stage': 0.05, 
    'anti_crowding': 0.05
}

# === ENTRY TIMING ===
ZEBRA_MAX_IV_RANK_ENTRY: int = 50
ZEBRA_RSI_BULL_RANGE: Tuple[int, int] = (40, 65)
ZEBRA_RSI_BEAR_RANGE: Tuple[int, int] = (35, 60)
ZEBRA_VIX_CRISIS: float = 35.0
ZEBRA_FOMC_BLOCK_DAYS: int = 2

# === ANTI-CROWDING ===
ZEBRA_MAX_CALL_PUT_RATIO: float = 3.0
ZEBRA_MAX_VOL_OI_RATIO: float = 3.0
ZEBRA_MAX_IV_RV_DIVERGENCE: float = 0.30

# === RISK VALIDATION ===
ZEBRA_MAX_SECTOR_CONCENTRATION: float = 0.30
ZEBRA_MAX_LOSS_PCT: float = 0.30        # Max loss < 30% of capital

# === CONSTRUCTION ===
ZEBRA_DTE_RANGE: Tuple[int, int] = (45, 120)
ZEBRA_BREAKEVEN_MAX_PCT: float = 3.0    # Breakeven within +/- 3%
ZEBRA_LONG_DELTA_MIN: float = 0.65
ZEBRA_LONG_DELTA_MAX: float = 0.80
ZEBRA_SHORT_DELTA_MIN: float = 0.45
ZEBRA_SHORT_DELTA_MAX: float = 0.55
ZEBRA_MAX_NET_EXTRINSIC: float = 0.15

# === PERPLEXITY ENRICHMENT ===
ZEBRA_PERPLEXITY_TOP_N: int = 5
ZEBRA_PERPLEXITY_CACHE_HOURS: int = 6

# Lifecycle & Execution
ZEBRA_PROFIT_TARGET_PCT: float = 0.50  # 50% (Hard target, optional if trailing)
ZEBRA_TRAILING_STOP_PCT: float = 0.15  # 15% (Optimized from 2y backtest)
ZEBRA_TIME_EXIT_PCT: float = 50.0       
ZEBRA_STOP_LOSS_PCT: float = 0.40      # -40% (Hard safety net)
ZEBRA_RECENTER_DOWN_PCT: float = -8.0   
ZEBRA_RECENTER_UP_PCT: float = 15.0     
ZEBRA_ASSIGNMENT_DTE: int = 5           
ZEBRA_DIVIDEND_DAYS: int = 3            
ZEBRA_MAX_RECENTERS: int = 2            

ZEBRA_ENTRY_WINDOW_START: time = time(10, 0)   
ZEBRA_ENTRY_WINDOW_END: time = time(11, 30)    
ZEBRA_SCAN_INTERVAL_MIN: int = 30       
ZEBRA_POSITION_CHECK_MIN: int = 15      
ZEBRA_AUTO_TRADE: bool = False
ZEBRA_MAX_PORTFOLIO_Alloc_PCT: float = 0.10

# =============================================================================



@dataclass
class SpreadConfig:
    """Configuration for a single spread setup."""
    symbol: str
    short_expiry_days: int = SHORT_EXPIRY_DAYS
    long_expiry_days: int = LONG_EXPIRY_DAYS
    profit_target_pct: float = PROFIT_TARGET_PCT
    stop_loss_pct: float = STOP_LOSS_PCT
    max_contracts: int = 1


# Default configurations for each underlying
SPREAD_CONFIGS = {
    "IWM": SpreadConfig(symbol="IWM", max_contracts=2),
    "SPY": SpreadConfig(symbol="SPY", max_contracts=1),  # SPY is more expensive
    "QQQ": SpreadConfig(symbol="QQQ", max_contracts=1),
}


def get_max_risk_per_trade() -> float:
    """Calculate maximum risk per trade in dollars."""
    return ACCOUNT_SIZE * (RISK_PER_TRADE_PCT / 100)


def get_max_daily_loss() -> float:
    """Calculate maximum daily loss in dollars."""
    return ACCOUNT_SIZE * (MAX_DAILY_LOSS_PCT / 100)


# =============================================================================
# ZEBRA STRATEGY CONFIGURATION
# =============================================================================

# Service control
ZEBRA_ENABLED: bool = True

# Scan intervals (minutes)
ZEBRA_SCAN_INTERVAL_MIN: int = 15        # How often to scan for new entries
ZEBRA_POSITION_CHECK_MIN: int = 5        # How often to check open positions

# Trading window (ET)
ZEBRA_ENTRY_WINDOW_START: str = "09:45"  # Don't enter before this time
ZEBRA_ENTRY_WINDOW_END: str = "15:30"    # Don't enter after this time

# Signal quality thresholds
ZEBRA_MIN_DIRECTIONAL_CONFIDENCE: float = 0.55   # ML minimum confidence to enter
ZEBRA_MIN_COMPOSITE_SCORE: float = 60.0          # Minimum composite score (0-100)
ZEBRA_MIN_CONSTRUCTION_SCORE: float = 70.0       # Minimum construction quality score

# Position sizing
ZEBRA_MAX_ALLOCATION_PCT: float = 0.15   # Max 15% of equity per position
ZEBRA_DEFAULT_CONTRACTS: int = 1         # Default contract count

# Exit parameters
ZEBRA_PROFIT_TARGET_PCT: float = 0.50    # Close at 50% of max profit
ZEBRA_STOP_LOSS_PCT: float = 1.50        # Close at 150% of debit paid (loss)
ZEBRA_MAX_DTE_THRESHOLD: int = 7         # Exit if DTE falls below this


if __name__ == "__main__":
    print("Calendar Spreads Configuration")
    print("=" * 50)
    print(f"Account Size: ${ACCOUNT_SIZE:,.0f}")
    print(f"Max Risk/Trade: ${get_max_risk_per_trade():,.0f} ({RISK_PER_TRADE_PCT}%)")
    print(f"Max Daily Loss: ${get_max_daily_loss():,.0f} ({MAX_DAILY_LOSS_PCT}%)")
    print(f"Underlyings: {', '.join(UNDERLYINGS)}")
    print(f"Entry Time: {ENTRY_TIME}")
    print(f"Exit Check: {EXIT_CHECK_TIME}")
