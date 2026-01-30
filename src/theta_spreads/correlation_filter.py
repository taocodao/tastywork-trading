"""
Correlation filter to prevent concentrated sector exposure.

Limits positions in correlated symbols/sectors.
"""

import logging
from typing import Dict, List, Set, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class CorrelationFilter:
    """
    Prevents excessive correlation between open positions.
    Uses sector groupings and explicit high-correlation pairs.
    """
    
    # Maximum positions per sector
    MAX_PER_SECTOR = 2
    
    # Maximum positions in highly correlated pairs
    MAX_CORRELATED_PAIR = 1
    
    # Sector definitions
    SECTOR_GROUPS = {
        'TECH': {
            'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'META', 'AMZN', 
            'NVDA', 'AMD', 'INTC', 'CRM', 'ORCL', 'ADBE', 
            'CSCO', 'AVGO', 'QCOM', 'TXN', 'MU', 'AMAT'
        },
        'FINANCE': {
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 
            'AXP', 'BLK', 'SCHW', 'COF', 'USB', 'PNC'
        },
        'HEALTHCARE': {
            'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY', 
            'BMY', 'AMGN', 'GILD', 'CVS', 'MDT', 'ABT'
        },
        'ENERGY': {
            'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 
            'VLO', 'PSX', 'OXY', 'HAL', 'DVN', 'KMI'
        },
        'CONSUMER': {
            'WMT', 'HD', 'MCD', 'NKE', 'SBUX', 'TGT', 
            'LOW', 'TJX', 'COST', 'DG', 'LULU', 'CMG'
        },
        'INDUSTRIAL': {
            'CAT', 'BA', 'GE', 'HON', 'UNP', 'UPS', 
            'RTX', 'LMT', 'DE', 'MMM', 'FDX', 'NSC'
        },
        'INDEX_SP500': {'SPY', 'IVV', 'VOO'},
        'INDEX_NASDAQ': {'QQQ', 'QQQM', 'ONEQ'},
        'INDEX_SMALL': {'IWM', 'IJR', 'VB'},
        'INDEX_DOW': {'DIA'},
        'COMMODITY_GOLD': {'GLD', 'IAU', 'GDX'},
        'COMMODITY_OIL': {'USO', 'OIH'},
        'BONDS': {'TLT', 'IEF', 'BND', 'AGG'},
    }
    
    # High correlation pairs (more restrictive than sector)
    HIGH_CORRELATION_PAIRS = [
        ('SPY', 'QQQ'),       # Both large cap
        ('SPY', 'DIA'),       # Both large cap
        ('SPY', 'IWM'),       # Correlated in crashes
        ('QQQ', 'QQQM'),      # Same index
        ('AAPL', 'MSFT'),     # Mega-cap tech
        ('NVDA', 'AMD'),      # Semiconductors
        ('NVDA', 'AVGO'),     # Semiconductors
        ('AMD', 'INTC'),      # Semiconductors
        ('XOM', 'CVX'),       # Big oil
        ('JPM', 'BAC'),       # Big banks
        ('GS', 'MS'),         # Investment banks
        ('WMT', 'TGT'),       # Retail
        ('HD', 'LOW'),        # Home improvement
        ('UNH', 'CVS'),       # Health insurance/pharma
        ('GLD', 'IAU'),       # Same commodity
    ]
    
    def __init__(
        self,
        max_per_sector: int = 2,
        max_correlated_pair: int = 1
    ):
        """
        Initialize correlation filter.
        
        Args:
            max_per_sector: Max positions per sector (default 2)
            max_correlated_pair: Max for high-correlation pairs (default 1)
        """
        self.max_per_sector = max_per_sector
        self.max_correlated_pair = max_correlated_pair
        
        # Build reverse lookup: symbol -> sector
        self._symbol_to_sector: Dict[str, str] = {}
        for sector, symbols in self.SECTOR_GROUPS.items():
            for symbol in symbols:
                self._symbol_to_sector[symbol] = sector
        
        # Build pair lookup: symbol -> correlated symbols
        self._correlated_pairs: Dict[str, Set[str]] = defaultdict(set)
        for s1, s2 in self.HIGH_CORRELATION_PAIRS:
            self._correlated_pairs[s1].add(s2)
            self._correlated_pairs[s2].add(s1)
    
    def get_sector(self, symbol: str) -> str:
        """Get sector for a symbol."""
        return self._symbol_to_sector.get(symbol, 'OTHER')
    
    def get_correlated_symbols(self, symbol: str) -> Set[str]:
        """Get all symbols correlated with given symbol."""
        correlated = set()
        
        # Add same-sector symbols
        sector = self.get_sector(symbol)
        if sector != 'OTHER':
            correlated.update(self.SECTOR_GROUPS.get(sector, set()))
        
        # Add explicit pairs
        correlated.update(self._correlated_pairs.get(symbol, set()))
        
        # Remove self
        correlated.discard(symbol)
        
        return correlated
    
    def count_sector_exposure(
        self, 
        symbol: str, 
        open_positions: List[str]
    ) -> int:
        """Count positions in same sector."""
        sector = self.get_sector(symbol)
        if sector == 'OTHER':
            return 0
        
        sector_symbols = self.SECTOR_GROUPS.get(sector, set())
        return sum(1 for pos in open_positions if pos in sector_symbols)
    
    def count_pair_exposure(
        self,
        symbol: str,
        open_positions: List[str]
    ) -> int:
        """Count positions in high-correlation pairs."""
        pairs = self._correlated_pairs.get(symbol, set())
        return sum(1 for pos in open_positions if pos in pairs)
    
    def can_open_position(
        self, 
        symbol: str, 
        open_positions: List[str]
    ) -> Tuple[bool, str]:
        """
        Check if new position would violate correlation limits.
        
        Args:
            symbol: Symbol to check
            open_positions: List of current open position symbols
            
        Returns:
            Tuple of (can_open, reason)
        """
        sector = self.get_sector(symbol)
        
        # Check sector limit
        sector_count = self.count_sector_exposure(symbol, open_positions)
        if sector_count >= self.max_per_sector:
            overlapping = [
                p for p in open_positions 
                if p in self.SECTOR_GROUPS.get(sector, set())
            ]
            return False, f"🚫 Max {sector} positions ({sector_count}): {overlapping}"
        
        # Check high-correlation pair limit
        pair_count = self.count_pair_exposure(symbol, open_positions)
        if pair_count >= self.max_correlated_pair:
            pairs = self._correlated_pairs.get(symbol, set())
            overlapping = [p for p in open_positions if p in pairs]
            return False, f"🚫 High correlation with: {overlapping}"
        
        # Allow with warning if approaching limits
        if sector_count > 0:
            return True, f"⚠️ Caution: {sector_count} existing {sector} position(s)"
        
        return True, f"✅ OK - no correlation conflict"
    
    def get_portfolio_exposure(
        self, 
        open_positions: List[str]
    ) -> Dict[str, List[str]]:
        """Get breakdown of positions by sector."""
        exposure = defaultdict(list)
        
        for symbol in open_positions:
            sector = self.get_sector(symbol)
            exposure[sector].append(symbol)
        
        return dict(exposure)
    
    def filter_candidates(
        self, 
        candidates: List[str], 
        open_positions: List[str]
    ) -> List[str]:
        """
        Filter candidate symbols to those that pass correlation check.
        
        Args:
            candidates: List of symbols being considered
            open_positions: Current open position symbols
            
        Returns:
            Filtered list of symbols that can be opened
        """
        allowed = []
        blocked_count = 0
        
        # Track what we're adding to avoid stacking
        simulated_positions = list(open_positions)
        
        for symbol in candidates:
            can_open, reason = self.can_open_position(symbol, simulated_positions)
            if can_open:
                allowed.append(symbol)
                simulated_positions.append(symbol)  # Track for next iteration
            else:
                blocked_count += 1
                logger.info(f"{symbol}: Correlation block - {reason}")
        
        if blocked_count > 0:
            logger.info(f"Correlation filter blocked {blocked_count} candidates")
        
        return allowed
    
    def get_correlation_report(
        self, 
        open_positions: List[str]
    ) -> Dict:
        """
        Generate correlation report for current portfolio.
        
        Returns:
            Dict with sector breakdown and warnings
        """
        exposure = self.get_portfolio_exposure(open_positions)
        
        warnings = []
        for sector, symbols in exposure.items():
            if len(symbols) >= self.max_per_sector:
                warnings.append(f"{sector}: {len(symbols)} positions (MAX)")
            elif len(symbols) > 1:
                warnings.append(f"{sector}: {len(symbols)} positions")
        
        # Check pair correlations
        pair_warnings = []
        checked = set()
        for pos in open_positions:
            for correlated in self._correlated_pairs.get(pos, set()):
                if correlated in open_positions and (pos, correlated) not in checked:
                    pair_warnings.append(f"High correlation: {pos} + {correlated}")
                    checked.add((pos, correlated))
                    checked.add((correlated, pos))
        
        return {
            'sector_exposure': exposure,
            'warnings': warnings,
            'pair_warnings': pair_warnings,
            'total_positions': len(open_positions)
        }


# Module-level convenience
_default_filter: 'CorrelationFilter' = None


def get_correlation_filter() -> CorrelationFilter:
    """Get or create default CorrelationFilter instance."""
    global _default_filter
    if _default_filter is None:
        _default_filter = CorrelationFilter()
    return _default_filter


def check_correlation(
    symbol: str, 
    open_positions: List[str]
) -> Tuple[bool, str]:
    """
    Quick check if symbol passes correlation filter.
    
    Returns:
        Tuple of (can_open, reason)
    """
    return get_correlation_filter().can_open_position(symbol, open_positions)
