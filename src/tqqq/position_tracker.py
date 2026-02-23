"""
TQQQ Position Tracker
=====================
Tracks the state of the active TQQQ spread position, including leg-out metrics.
"""

from dataclasses import dataclass
from typing import Optional
from src.tqqq import TQQQStrategyState

@dataclass
class TQQQPosition:
    """
    State container for an active TQQQ VIX-adaptive strategy position.
    """
    id: str
    symbol: str
    state: TQQQStrategyState = TQQQStrategyState.IDLE
    
    # Initial Spread Details
    short_strike: float = 0.0
    long_strike: float = 0.0
    expiration_date: str = ""
    quantity: int = 1
    
    # Entry Metrics
    original_credit: float = 0.0
    max_loss: float = 0.0
    
    # Leg-Out Tracking
    short_put_close_price: Optional[float] = None
    long_put_legout_value: Optional[float] = None
    
    # Exit Tracking
    final_exit_price: float = 0.0
    
    @property
    def is_active(self) -> bool:
        return self.state in [TQQQStrategyState.FULL_SPREAD, TQQQStrategyState.LONG_PUT_ONLY]
        
    @property
    def legout_cost(self) -> float:
        """If we legged out, the cost paid to close the short put."""
        return self.short_put_close_price if self.short_put_close_price is not None else 0.0
        
    def get_unrealized_pnl(self, current_spread_value: float) -> float:
        """
        Calculates unrealized PNL. 
        Note: If in LONG_PUT_ONLY state, current_spread_value should be the profit
        from selling the long put at the current bid.
        """
        if self.state == TQQQStrategyState.FULL_SPREAD:
            return self.original_credit - current_spread_value
        elif self.state == TQQQStrategyState.LONG_PUT_ONLY:
            # We already paid to close the short put, and received original credit.
            # Now we hold a long put (which has intrinsic value if sold)
            # Pnl = Original Credit - Cost To Leg Out + Value of Long Put
            return self.original_credit - self.legout_cost + current_spread_value
        return 0.0
