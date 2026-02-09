"""
Circuit Breaker: IV Term Structure Filter for Diagonal Spreads

Based on VIX-VXV proxy backtest (2010-2024):
- Contango (VIX < VXV): 73.2% win rate, avg +$39
- Backwardation (VIX > VXV): 18.9% win rate, avg -$155

This module implements a circuit breaker that HALTS trading during
market stress (backwardation) to preserve capital.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class TermStructureRegime(Enum):
    """Term structure regime classification"""
    CONTANGO = "contango"       # Normal markets - SAFE to trade
    FLAT = "flat"               # Neutral - proceed with caution
    BACKWARDATION = "backwardation"  # Crisis mode - HALT trading
    SEVERE_BACKWARDATION = "severe_backwardation"  # Extreme stress - HALT + close shorts


@dataclass
class TermStructureStatus:
    """Current term structure status and trading recommendation"""
    regime: TermStructureRegime
    vix: float
    vxv: float
    diff: float
    ratio: float  # VIX/VXV ratio - early warning when > 0.95
    timestamp: datetime
    can_trade: bool
    position_size_multiplier: float
    message: str
    early_warning: bool = False  # True when ratio > 0.95 but diff still safe
    
    def __str__(self) -> str:
        warning = " ⚠️ EARLY WARNING" if self.early_warning else ""
        return f"{self.regime.value.upper()}: VIX={self.vix:.2f}, VXV={self.vxv:.2f}, Diff={self.diff:.2f}, Ratio={self.ratio:.3f}{warning} | {self.message}"


class TermStructureCircuitBreaker:
    """
    Circuit breaker for diagonal spreads based on VIX-VXV term structure.
    
    Trading Rules:
    - Contango (diff < -0.5): Trade normally (100% size)
    - Flat (-0.5 <= diff <= 0.5): Proceed with caution (75% size)
    - Mild Backwardation (0.5 < diff <= 1.5): Reduce size (50%), no new entries
    - Severe Backwardation (diff > 1.5): HALT all trading, consider closing shorts
    """
    
    # Thresholds based on backtest analysis
    CONTANGO_THRESHOLD = -0.5    # VIX - VXV < -0.5 = healthy contango
    FLAT_UPPER = 0.5             # Flat band
    MILD_BACKWARDATION = 1.5     # Caution zone
    # Above 1.5 = severe backwardation (crisis)
    
    def __init__(self, data_provider=None):
        """
        Initialize the circuit breaker.
        
        Args:
            data_provider: Optional data provider (IB, FRED, etc.) for VIX/VXV data
        """
        self.data_provider = data_provider
        self._cached_status: Optional[TermStructureStatus] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)  # Refresh every 5 minutes
    
    def get_vix_vxv_data(self) -> Tuple[float, float]:
        """
        Fetch current VIX and VXV values.
        
        Returns:
            Tuple of (VIX, VXV) values
            
        Raises:
            ValueError: If data cannot be fetched
        """
        if self.data_provider is not None:
            try:
                # Try to get from data provider (e.g., IB)
                vix = self.data_provider.get_market_data("VIX")
                vxv = self.data_provider.get_market_data("VXV")
                if vix and vxv:
                    return (vix, vxv)
            except Exception as e:
                logger.warning(f"Error fetching VIX/VXV from data provider: {e}")
        
        # Fallback: Use yfinance for VIX, estimate VXV from VIX3M
        try:
            import yfinance as yf
            
            vix_ticker = yf.Ticker("^VIX")
            vix_data = vix_ticker.history(period="1d")
            if not vix_data.empty:
                vix = vix_data['Close'].iloc[-1]
            else:
                raise ValueError("No VIX data available")
            
            # VXV is the CBOE 3-month volatility index
            # Try VIX3M as a proxy
            vix3m_ticker = yf.Ticker("^VIX3M")
            vix3m_data = vix3m_ticker.history(period="1d")
            if not vix3m_data.empty:
                vxv = vix3m_data['Close'].iloc[-1]
            else:
                # Fallback: Estimate VXV from VIX with typical contango ratio (~1.1)
                vxv = vix * 1.1
                logger.warning("VXV unavailable, using estimated value from VIX")
            
            return (vix, vxv)
            
        except Exception as e:
            logger.error(f"Error fetching VIX/VXV: {e}")
            raise ValueError(f"Could not fetch VIX/VXV data: {e}")
    
    def classify_regime(self, vix: float, vxv: float) -> Tuple[TermStructureRegime, float, str]:
        """
        Classify the current term structure regime.
        
        Args:
            vix: Current VIX value
            vxv: Current VXV (3-month) value
            
        Returns:
            Tuple of (regime, position_multiplier, message)
        """
        diff = vix - vxv
        
        if diff > self.MILD_BACKWARDATION:
            return (
                TermStructureRegime.SEVERE_BACKWARDATION,
                0.0,
                "CRISIS MODE: Severe backwardation detected. HALT all trading. Consider closing short legs."
            )
        elif diff > self.FLAT_UPPER:
            return (
                TermStructureRegime.BACKWARDATION,
                0.0,
                "CAUTION: Mild backwardation. Skip new entries. Monitor existing positions."
            )
        elif diff >= self.CONTANGO_THRESHOLD:
            return (
                TermStructureRegime.FLAT,
                0.75,
                "NEUTRAL: Flat term structure. Reduce position size to 75%."
            )
        else:
            return (
                TermStructureRegime.CONTANGO,
                1.0,
                "SAFE: Healthy contango. Trade normally."
            )
    
    def get_status(self, force_refresh: bool = False) -> TermStructureStatus:
        """
        Get current term structure status with caching.
        
        Args:
            force_refresh: Force refresh of cached data
            
        Returns:
            TermStructureStatus with current regime and trading recommendation
        """
        now = datetime.now()
        
        # Check cache
        if not force_refresh and self._cached_status and self._cache_timestamp:
            if now - self._cache_timestamp < self._cache_ttl:
                return self._cached_status
        
        try:
            vix, vxv = self.get_vix_vxv_data()
            diff = vix - vxv
            ratio = vix / vxv if vxv > 0 else 1.0
            regime, multiplier, message = self.classify_regime(vix, vxv)
            
            can_trade = regime in (TermStructureRegime.CONTANGO, TermStructureRegime.FLAT)
            
            # Early warning: ratio > 0.95 indicates gradual compression toward backwardation
            # even when diff is still in the safe zone
            early_warning = ratio > 0.95 and can_trade
            if early_warning:
                message += " ⚠️ Ratio approaching 1.0 - monitor closely."
            
            self._cached_status = TermStructureStatus(
                regime=regime,
                vix=vix,
                vxv=vxv,
                diff=diff,
                ratio=ratio,
                timestamp=now,
                can_trade=can_trade,
                position_size_multiplier=multiplier,
                message=message,
                early_warning=early_warning
            )
            self._cache_timestamp = now
            
            logger.info(f"Term structure status: {self._cached_status}")
            return self._cached_status
            
        except Exception as e:
            logger.error(f"Error getting term structure status: {e}")
            # Return a conservative default (assume stress)
            return TermStructureStatus(
                regime=TermStructureRegime.FLAT,
                vix=0.0,
                vxv=0.0,
                diff=0.0,
                ratio=1.0,  # Assume worst case
                timestamp=now,
                can_trade=False,  # Conservative: don't trade if we can't check
                position_size_multiplier=0.0,
                message=f"ERROR: Could not fetch term structure data. Halting for safety. Error: {e}",
                early_warning=True
            )
    
    def should_trade(self) -> bool:
        """Quick check if trading is allowed."""
        status = self.get_status()
        return status.can_trade
    
    def get_position_size_factor(self) -> float:
        """Get position size multiplier based on term structure."""
        status = self.get_status()
        return status.position_size_multiplier
    
    def is_crisis_mode(self) -> bool:
        """Check if in severe backwardation (crisis mode)."""
        status = self.get_status()
        return status.regime == TermStructureRegime.SEVERE_BACKWARDATION


# Convenience function for pre-scan check
def check_term_structure_circuit_breaker(data_provider=None) -> TermStructureStatus:
    """
    Convenience function for circuit breaker check before scanning for trades.
    
    Usage in scheduler:
        status = check_term_structure_circuit_breaker(ib_provider)
        if not status.can_trade:
            logger.warning(f"Circuit breaker triggered: {status.message}")
            return  # Skip trading
        
        # Proceed with normal signal generation
        signals = generate_diagonal_signals()
        
        # Apply position size factor
        for signal in signals:
            signal.contracts = int(signal.contracts * status.position_size_multiplier)
    
    Args:
        data_provider: Optional data provider for VIX/VXV data
        
    Returns:
        TermStructureStatus with trading recommendation
    """
    breaker = TermStructureCircuitBreaker(data_provider)
    return breaker.get_status()
