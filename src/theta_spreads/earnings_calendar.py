"""
Earnings calendar integration for Theta Sprint.

Fetches and caches earnings dates to implement blackout periods.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class EarningsCalendar:
    """
    Fetches and caches earnings dates for symbols.
    Uses yfinance with optional API fallbacks.
    """
    
    BLACKOUT_DAYS_BEFORE = 7   # Don't enter 7 days before earnings
    BLACKOUT_DAYS_AFTER = 1    # Don't enter day after earnings
    
    def __init__(self, cache_dir: str = "data/earnings"):
        """
        Initialize earnings calendar.
        
        Args:
            cache_dir: Directory to store earnings cache
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, List[date]] = {}
        self._cache_file = self.cache_dir / "earnings_cache.json"
        self._load_cache()
    
    def get_next_earnings_date(self, symbol: str) -> Optional[date]:
        """
        Get next earnings date for symbol.
        
        Args:
            symbol: Stock ticker symbol
            
        Returns:
            Next earnings date or None if not found
        """
        # Check memory cache first
        if symbol in self._memory_cache:
            today = date.today()
            upcoming = [d for d in self._memory_cache[symbol] if d >= today]
            if upcoming:
                return min(upcoming)
        
        # Fetch from APIs
        earnings_date = self._fetch_earnings_date(symbol)
        
        if earnings_date:
            if symbol not in self._memory_cache:
                self._memory_cache[symbol] = []
            if earnings_date not in self._memory_cache[symbol]:
                self._memory_cache[symbol].append(earnings_date)
            self._save_cache()
        
        return earnings_date
    
    def _fetch_earnings_date(self, symbol: str) -> Optional[date]:
        """Fetch earnings date from available sources."""
        
        # Skip ETFs/indices - they don't have earnings
        if symbol in {'SPY', 'QQQ', 'IWM', 'DIA', 'IVV', 'VOO', 'GLD', 'TLT', 'USO', 'XLF', 'XLE'}:
            return None
        
        # Try yfinance first
        result = self._fetch_yfinance(symbol)
        if result:
            return result
        
        logger.debug(f"Could not find earnings date for {symbol}")
        return None
    
    def _fetch_yfinance(self, symbol: str) -> Optional[date]:
        """Fetch earnings from yfinance."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            
            # Try calendar first
            try:
                calendar = ticker.calendar
                if calendar is not None and not calendar.empty:
                    if 'Earnings Date' in calendar.index:
                        earnings_row = calendar.loc['Earnings Date']
                        if hasattr(earnings_row, 'iloc') and len(earnings_row) > 0:
                            earnings_dt = earnings_row.iloc[0]
                            if hasattr(earnings_dt, 'date'):
                                return earnings_dt.date()
                            elif isinstance(earnings_dt, str):
                                return datetime.strptime(earnings_dt, '%Y-%m-%d').date()
            except Exception as e:
                logger.debug(f"yfinance calendar failed for {symbol}: {e}")
            
            # Try earnings_dates attribute
            try:
                if hasattr(ticker, 'earnings_dates') and ticker.earnings_dates is not None:
                    earnings_df = ticker.earnings_dates
                    if not earnings_df.empty:
                        today = datetime.now()
                        future_dates = earnings_df[earnings_df.index >= today]
                        if not future_dates.empty:
                            next_date = future_dates.index[0]
                            if hasattr(next_date, 'date'):
                                return next_date.date()
            except Exception as e:
                logger.debug(f"yfinance earnings_dates failed for {symbol}: {e}")
            
            return None
            
        except Exception as e:
            logger.debug(f"yfinance fetch failed for {symbol}: {e}")
            return None
    
    def is_in_blackout(
        self, 
        symbol: str, 
        position_dte: int = 28
    ) -> Tuple[bool, str]:
        """
        Check if symbol is in earnings blackout period.
        
        Args:
            symbol: Stock symbol
            position_dte: Days to expiration for new position
        
        Returns:
            Tuple of (is_blackout, reason)
        """
        earnings = self.get_next_earnings_date(symbol)
        
        if earnings is None:
            # ETFs or unknown - allow trading
            return False, "No earnings date found"
        
        today = date.today()
        days_to_earnings = (earnings - today).days
        
        # Check if within blackout window before earnings
        if days_to_earnings <= self.BLACKOUT_DAYS_BEFORE and days_to_earnings >= 0:
            reason = f"🚫 Earnings in {days_to_earnings} days ({earnings}) - BLACKOUT"
            logger.info(f"{symbol}: {reason}")
            return True, reason
        
        # Check if position would span across earnings
        if 0 < days_to_earnings < position_dte:
            reason = f"⚠️ Position (DTE={position_dte}) would span earnings ({earnings}, {days_to_earnings}d away)"
            logger.info(f"{symbol}: {reason}")
            return True, reason
        
        # Check blackout after earnings
        if days_to_earnings < 0 and abs(days_to_earnings) <= self.BLACKOUT_DAYS_AFTER:
            reason = f"🚫 Earnings just passed ({abs(days_to_earnings)}d ago) - BLACKOUT"
            logger.info(f"{symbol}: {reason}")
            return True, reason
        
        return False, f"OK - earnings {days_to_earnings}d away"
    
    def get_blackout_symbols(
        self, 
        symbols: List[str],
        position_dte: int = 28
    ) -> Dict[str, str]:
        """
        Get dict of symbols in blackout with reasons.
        
        Args:
            symbols: List of symbols to check
            position_dte: Days to expiration
            
        Returns:
            Dict of {symbol: reason} for blocked symbols
        """
        blackouts = {}
        for symbol in symbols:
            is_blackout, reason = self.is_in_blackout(symbol, position_dte)
            if is_blackout:
                blackouts[symbol] = reason
        return blackouts
    
    def filter_symbols(
        self, 
        symbols: List[str],
        position_dte: int = 28
    ) -> List[str]:
        """
        Filter out symbols in earnings blackout.
        
        Args:
            symbols: List of candidate symbols
            position_dte: Days to expiration
            
        Returns:
            Filtered list of symbols not in blackout
        """
        return [
            s for s in symbols 
            if not self.is_in_blackout(s, position_dte)[0]
        ]
    
    def _save_cache(self) -> None:
        """Save earnings cache to disk."""
        try:
            serializable = {
                symbol: [d.isoformat() for d in dates]
                for symbol, dates in self._memory_cache.items()
            }
            
            with open(self._cache_file, 'w') as f:
                json.dump(serializable, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to save earnings cache: {e}")
    
    def _load_cache(self) -> None:
        """Load earnings cache from disk."""
        if not self._cache_file.exists():
            return
        
        try:
            with open(self._cache_file) as f:
                data = json.load(f)
            
            self._memory_cache = {
                symbol: [datetime.fromisoformat(d).date() for d in dates]
                for symbol, dates in data.items()
            }
            
            logger.debug(f"Loaded earnings cache: {len(self._memory_cache)} symbols")
            
        except Exception as e:
            logger.warning(f"Failed to load earnings cache: {e}")
    
    def refresh_cache(self, symbols: List[str]) -> None:
        """
        Force refresh earnings data for symbols.
        
        Args:
            symbols: List of symbols to refresh
        """
        for symbol in symbols:
            # Clear existing cache
            if symbol in self._memory_cache:
                del self._memory_cache[symbol]
            
            # Fetch fresh
            self.get_next_earnings_date(symbol)
        
        self._save_cache()
        logger.info(f"Refreshed earnings cache for {len(symbols)} symbols")


# Module-level convenience
_default_calendar: Optional[EarningsCalendar] = None


def get_earnings_calendar() -> EarningsCalendar:
    """Get or create default EarningsCalendar instance."""
    global _default_calendar
    if _default_calendar is None:
        _default_calendar = EarningsCalendar()
    return _default_calendar


def check_earnings_blackout(symbol: str, dte: int = 28) -> Tuple[bool, str]:
    """
    Quick check if symbol is in earnings blackout.
    
    Returns:
        Tuple of (is_blackout, reason)
    """
    return get_earnings_calendar().is_in_blackout(symbol, dte)
