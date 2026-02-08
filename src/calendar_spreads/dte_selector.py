"""
DTE Selection for Calendar Spreads
===================================
Optimized Days-to-Expiration selection based on IV regime

Research basis:
- Short leg: 7-14 DTE (rapid theta decay)
- Long leg: 30-45 DTE (preserves value, provides hedge)
- IV adjustment: Higher IV → shorter DTEs (faster moves)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass  
class DTEConfig:
    """
    DTE selection configuration by IV regime
    
    High IV (>70 rank): Use shorter timeframes - volatility mean reverts faster
    Normal IV (30-70): Standard calendar window
    Low IV (<30): Need more time for trade to work
    """
    # High IV regime (IV rank > 70)
    high_iv_short_dte: int = 7
    high_iv_long_dte: int = 30
    
    # Normal IV regime (IV rank 30-70)
    normal_iv_short_dte: int = 10
    normal_iv_long_dte: int = 40
    
    # Low IV regime (IV rank < 30)
    low_iv_short_dte: int = 14
    low_iv_long_dte: int = 45
    
    # Thresholds
    high_iv_threshold: float = 70.0
    low_iv_threshold: float = 30.0
    
    # Minimum gap between expirations (for theta differential)
    min_dte_gap: int = 14


class DTESelector:
    """
    Select optimal DTE for calendar spreads based on IV conditions
    
    Usage:
        selector = DTESelector()
        
        # Get optimal DTEs for given IV rank
        short_dte, long_dte = selector.select_optimal_dte(iv_rank=65.0)
        
        # Find actual expiration dates from available chain
        short_exp = selector.find_nearest_expiration(short_dte, expirations)
        long_exp = selector.find_nearest_expiration(long_dte, expirations)
    """
    
    def __init__(self, config: Optional[DTEConfig] = None):
        self.config = config or DTEConfig()
    
    def select_optimal_dte(self, iv_rank: float) -> Tuple[int, int]:
        """
        Select optimal short and long DTE based on IV rank
        
        Args:
            iv_rank: Current IV rank (0-100 percentile)
        
        Returns:
            Tuple of (short_dte, long_dte)
        
        Logic:
            - High IV: Shorter timeframes (7/30) - volatility mean reverts
            - Normal IV: Standard window (10/40)
            - Low IV: Longer timeframes (14/45) - need time for theta
        """
        if iv_rank > self.config.high_iv_threshold:
            short_dte = self.config.high_iv_short_dte
            long_dte = self.config.high_iv_long_dte
            regime = "HIGH IV"
        elif iv_rank >= self.config.low_iv_threshold:
            short_dte = self.config.normal_iv_short_dte
            long_dte = self.config.normal_iv_long_dte
            regime = "NORMAL IV"
        else:
            short_dte = self.config.low_iv_short_dte
            long_dte = self.config.low_iv_long_dte
            regime = "LOW IV"
        
        logger.info(
            f"DTE Selection: {regime} (IV rank {iv_rank:.0f}) → "
            f"Short: {short_dte} DTE, Long: {long_dte} DTE"
        )
        
        return short_dte, long_dte
    
    def find_nearest_expiration(self,
                               target_dte: int,
                               available_expirations: List[datetime],
                               reference_date: Optional[datetime] = None) -> Optional[datetime]:
        """
        Find expiration closest to target DTE from available chain
        
        Args:
            target_dte: Target days to expiration
            available_expirations: List of available expiration dates
            reference_date: Reference date (default: today)
        
        Returns:
            Nearest available expiration or None if no valid options
        """
        if not available_expirations:
            logger.warning("No available expirations provided")
            return None
        
        reference = reference_date or datetime.now()
        if isinstance(reference, datetime):
            reference = reference.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate DTE for each expiration
        valid_expirations = []
        for exp in available_expirations:
            # Normalize to datetime if it's a date
            if hasattr(exp, 'hour'):
                exp_dt = exp
            else:
                exp_dt = datetime.combine(exp, datetime.min.time())
            
            dte = (exp_dt - reference).days
            if dte > 0:  # Only future expirations
                valid_expirations.append((exp_dt, dte))
        
        if not valid_expirations:
            logger.warning("No future expirations available")
            return None
        
        # Find closest to target DTE
        closest = min(valid_expirations, key=lambda x: abs(x[1] - target_dte))
        
        actual_dte = closest[1]
        logger.info(f"Target DTE {target_dte} → Found {actual_dte} DTE ({closest[0].date()})")
        
        return closest[0]
    
    def select_calendar_expirations(self,
                                   iv_rank: float,
                                   available_expirations: List[datetime]) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Convenience method to select both expirations at once
        
        Args:
            iv_rank: Current IV rank
            available_expirations: Available expiration dates
        
        Returns:
            Tuple of (short_expiration, long_expiration) or (None, None) if invalid
        """
        short_dte, long_dte = self.select_optimal_dte(iv_rank)
        
        short_exp = self.find_nearest_expiration(short_dte, available_expirations)
        long_exp = self.find_nearest_expiration(long_dte, available_expirations)
        
        if short_exp is None or long_exp is None:
            logger.error("Failed to find valid expirations")
            return None, None
        
        # Validate: short must be before long with sufficient gap
        gap_days = (long_exp - short_exp).days
        
        if gap_days < self.config.min_dte_gap:
            logger.warning(
                f"Insufficient DTE gap: {gap_days} days (minimum: {self.config.min_dte_gap})"
            )
            # Try to find a better long expiration
            extended_long_dte = long_dte + self.config.min_dte_gap
            long_exp = self.find_nearest_expiration(extended_long_dte, available_expirations)
            
            if long_exp is None or (long_exp - short_exp).days < self.config.min_dte_gap:
                logger.error("Cannot find expirations with sufficient gap")
                return None, None
            
            gap_days = (long_exp - short_exp).days
        
        logger.info(
            f"Calendar expirations: Short {short_exp.date()} ({(short_exp - datetime.now()).days}d) | "
            f"Long {long_exp.date()} ({(long_exp - datetime.now()).days}d) | Gap: {gap_days}d"
        )
        
        return short_exp, long_exp
    
    def get_iv_regime(self, iv_rank: float) -> str:
        """Get the IV regime label for given IV rank"""
        if iv_rank > self.config.high_iv_threshold:
            return "HIGH"
        elif iv_rank >= self.config.low_iv_threshold:
            return "NORMAL"
        else:
            return "LOW"
    
    def validate_expirations(self,
                            short_exp: datetime,
                            long_exp: datetime) -> Tuple[bool, str]:
        """
        Validate expiration pair for calendar spread
        
        Returns:
            (is_valid, reason)
        """
        now = datetime.now()
        
        # Short must be in the future
        short_dte = (short_exp - now).days
        if short_dte <= 0:
            return False, "Short expiration is not in the future"
        
        # Long must be after short
        gap = (long_exp - short_exp).days
        if gap <= 0:
            return False, "Long expiration must be after short expiration"
        
        # Gap must be sufficient
        if gap < self.config.min_dte_gap:
            return False, f"DTE gap ({gap}d) is less than minimum ({self.config.min_dte_gap}d)"
        
        # Long shouldn't be too far out (>60 DTE has lower theta)
        long_dte = (long_exp - now).days
        if long_dte > 60:
            return True, f"Warning: Long DTE ({long_dte}) is quite far out"
        
        return True, "Valid calendar spread expirations"


# Weekly expiration utilities
def get_next_weekly_expirations(count: int = 8,
                                reference_date: Optional[datetime] = None) -> List[datetime]:
    """
    Generate list of upcoming Friday expirations (for SPY, QQQ, etc.)
    
    Args:
        count: Number of weekly expirations to generate
        reference_date: Starting reference date
    
    Returns:
        List of datetime objects for Friday expirations
    """
    reference = reference_date or datetime.now()
    reference = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Find next Friday
    days_until_friday = (4 - reference.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7  # If today is Friday, get next Friday
    
    next_friday = reference + timedelta(days=days_until_friday)
    
    expirations = []
    for i in range(count):
        exp = next_friday + timedelta(weeks=i)
        expirations.append(exp)
    
    return expirations


def get_next_monthly_expirations(count: int = 4,
                                 reference_date: Optional[datetime] = None) -> List[datetime]:
    """
    Generate list of upcoming third-Friday monthly expirations
    
    Args:
        count: Number of monthly expirations to generate
        reference_date: Starting reference date
    
    Returns:
        List of datetime objects for monthly expirations
    """
    reference = reference_date or datetime.now()
    
    expirations = []
    year = reference.year
    month = reference.month
    
    for _ in range(count):
        # Find third Friday of the month
        first_day = datetime(year, month, 1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
        third_friday = first_friday + timedelta(weeks=2)
        
        # Only add if it's in the future
        if third_friday > reference:
            expirations.append(third_friday)
        
        # Move to next month
        month += 1
        if month > 12:
            month = 1
            year += 1
    
    return expirations[:count]
