"""
Market-wide filters for Theta Sprint strategy.

Prevents entries during dangerous market conditions (high VIX, etc.)
"""

import logging
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class MarketFilters:
    """
    Global market condition filters.
    Prevents entries during dangerous market conditions.
    """
    
    # VIX thresholds
    VIX_DANGER_ZONE = 35       # Don't trade above this
    VIX_CAUTION_ZONE = 25      # Reduce position size
    VIX_ELEVATED_ZONE = 20     # Normal, but monitor
    
    def __init__(self, ib_connection=None):
        """
        Initialize market filters.
        
        Args:
            ib_connection: Optional IB connection for real-time data
        """
        self.ib = ib_connection
        self._vix_cache: Optional[float] = None
        self._vix_cache_time: Optional[datetime] = None
        self._cache_ttl = 300  # 5 minutes
    
    def get_current_vix(self) -> Optional[float]:
        """
        Fetch current VIX level.
        
        Returns:
            VIX value (0-100) or None if unavailable
        """
        # Check cache first
        if self._vix_cache is not None and self._vix_cache_time:
            age = (datetime.now() - self._vix_cache_time).seconds
            if age < self._cache_ttl:
                return self._vix_cache
        
        # Try IB first
        if self.ib:
            vix = self._fetch_vix_ib()
            if vix is not None:
                self._update_cache(vix)
                return vix
        
        # Fallback to yfinance
        vix = self._fetch_vix_yfinance()
        if vix is not None:
            self._update_cache(vix)
            return vix
        
        logger.warning("Could not fetch VIX from any source")
        return None
    
    def _update_cache(self, vix: float) -> None:
        """Update VIX cache."""
        self._vix_cache = vix
        self._vix_cache_time = datetime.now()
    
    def _fetch_vix_ib(self) -> Optional[float]:
        """Fetch VIX from Interactive Brokers."""
        try:
            if not self.ib or not self.ib.isConnected():
                return None
            
            from ib_insync import Index
            vix_contract = Index('VIX', 'CBOE')
            self.ib.qualifyContracts(vix_contract)
            ticker = self.ib.reqMktData(vix_contract, '', False, False)
            self.ib.sleep(1)
            
            if ticker.last and ticker.last > 0:
                logger.debug(f"VIX from IB: {ticker.last:.2f}")
                return float(ticker.last)
            
            if ticker.close and ticker.close > 0:
                logger.debug(f"VIX from IB (close): {ticker.close:.2f}")
                return float(ticker.close)
            
            return None
            
        except Exception as e:
            logger.debug(f"IB VIX fetch failed: {e}")
            return None
    
    def _fetch_vix_yfinance(self) -> Optional[float]:
        """Fetch VIX from yfinance as fallback."""
        try:
            import yfinance as yf
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="1d")
            
            if not hist.empty and 'Close' in hist.columns:
                vix_value = hist['Close'].iloc[-1]
                logger.debug(f"VIX from yfinance: {vix_value:.2f}")
                return float(vix_value)
            
            return None
            
        except Exception as e:
            logger.debug(f"yfinance VIX fetch failed: {e}")
            return None
    
    def check_vix_filter(self) -> Tuple[bool, str, float]:
        """
        Check if VIX allows trading.
        
        Returns:
            Tuple of (can_trade, reason, vix_level)
        """
        vix = self.get_current_vix()
        
        if vix is None:
            # Fail safe - if can't get VIX, allow trading with caution
            logger.warning("VIX unavailable - proceeding with caution")
            return True, "VIX unavailable - proceeding with caution", 0.0
        
        if vix >= self.VIX_DANGER_ZONE:
            reason = f"🚫 VIX {vix:.1f} >= {self.VIX_DANGER_ZONE} (DANGER ZONE - NO TRADING)"
            logger.warning(reason)
            return False, reason, vix
        
        if vix >= self.VIX_CAUTION_ZONE:
            reason = f"⚠️ VIX {vix:.1f} >= {self.VIX_CAUTION_ZONE} (CAUTION - reduce size)"
            logger.info(reason)
            return True, reason, vix
        
        if vix >= self.VIX_ELEVATED_ZONE:
            reason = f"📊 VIX {vix:.1f} (ELEVATED - monitor closely)"
            return True, reason, vix
        
        reason = f"✅ VIX {vix:.1f} (SAFE)"
        return True, reason, vix
    
    def get_position_size_multiplier(self) -> float:
        """
        Get position size multiplier based on VIX.
        
        Returns:
            Multiplier (0.0 - 1.0)
            - 0.0: No trading (VIX >= 35)
            - 0.5: Half size (VIX 25-35)
            - 0.75: 75% size (VIX 20-25)
            - 1.0: Full size (VIX < 20)
        """
        vix = self.get_current_vix()
        
        if vix is None:
            return 0.75  # Default to 75% if unknown
        
        if vix >= self.VIX_DANGER_ZONE:
            return 0.0   # No trading
        elif vix >= self.VIX_CAUTION_ZONE:
            return 0.5   # 50% position size
        elif vix >= self.VIX_ELEVATED_ZONE:
            return 0.75  # 75% position size
        else:
            return 1.0   # Full position size
    
    def get_vix_status(self) -> dict:
        """
        Get comprehensive VIX status for logging/display.
        
        Returns:
            Dict with VIX info
        """
        vix = self.get_current_vix()
        can_trade, reason, _ = self.check_vix_filter()
        multiplier = self.get_position_size_multiplier()
        
        if vix is None:
            status = "UNKNOWN"
        elif vix >= self.VIX_DANGER_ZONE:
            status = "DANGER"
        elif vix >= self.VIX_CAUTION_ZONE:
            status = "CAUTION"
        elif vix >= self.VIX_ELEVATED_ZONE:
            status = "ELEVATED"
        else:
            status = "SAFE"
        
        return {
            'vix': vix,
            'status': status,
            'can_trade': can_trade,
            'reason': reason,
            'position_size_multiplier': multiplier,
            'thresholds': {
                'danger': self.VIX_DANGER_ZONE,
                'caution': self.VIX_CAUTION_ZONE,
                'elevated': self.VIX_ELEVATED_ZONE
            }
        }


# Module-level convenience functions
_default_filters: Optional[MarketFilters] = None


def get_market_filters(ib_connection=None) -> MarketFilters:
    """Get or create default MarketFilters instance."""
    global _default_filters
    
    if _default_filters is None or ib_connection is not None:
        _default_filters = MarketFilters(ib_connection)
    
    return _default_filters


def check_vix_safe() -> Tuple[bool, str]:
    """
    Quick check if VIX allows trading.
    
    Returns:
        Tuple of (safe_to_trade, reason)
    """
    filters = get_market_filters()
    can_trade, reason, _ = filters.check_vix_filter()
    return can_trade, reason
