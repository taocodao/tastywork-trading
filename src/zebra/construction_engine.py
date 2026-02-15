"""
ZEBRA Construction Engine
==========================
Constructs optimal ZEBRA (Zero Extrinsic Back Ratio) spreads.
Supports both LONG (Call) and SHORT (Put) configurations.
"""

import logging
from typing import List, Optional, Dict, Tuple
from datetime import date, datetime, timedelta
from dataclasses import dataclass
import numpy as np

from tastytrade_client import TastytradeClient, OptionData
from config import (
    ZEBRA_LONG_DELTA_MIN, ZEBRA_LONG_DELTA_MAX,
    ZEBRA_SHORT_DELTA_MIN, ZEBRA_SHORT_DELTA_MAX,
    ZEBRA_MAX_NET_EXTRINSIC, ZEBRA_MAX_DEBIT_PCT,
    ZEBRA_SLIPPAGE_WARNING_PCT
)

logger = logging.getLogger(__name__)

@dataclass
class ZebraStructure:
    """Represents a fully constructed ZEBRA trade candidate."""
    symbol: str
    direction: str  # "LONG" or "SHORT"
    expiry: date
    dte: int
    
    # Legs
    long_leg: OptionData  # The ITM option (quantity 2)
    short_leg: OptionData # The ATM option (quantity 1)
    
    # Greeks (Net Position)
    net_delta: float
    net_theta: float
    net_vega: float
    net_gamma: float
    net_extrinsic: float
    
    # Implementation
    net_debit: float      # Cost to enter
    max_loss: float       # Defined risk
    breakeven: float
    capital_efficiency: float # Delta per $1000 invested relative to stock
    
    # Scoring
    construction_score: float
    slippage_warning: bool
    
    def __repr__(self):
        return (f"ZEBRA({self.symbol} {self.direction} {self.expiry} "
                f"Long:{self.long_leg.strike} Short:{self.short_leg.strike} "
                f"Debit:${self.net_debit:.2f} Score:{self.construction_score:.1f})")


class ZebraConstructionEngine:
    """
    Finds optimal ZEBRA structures for a given candidate.
    """
    
    def __init__(self, client: TastytradeClient):
        self.client = client
        
    def construct(
        self,
        symbol: str,
        stock_price: float,
        thesis_horizon_days: int = 30,
        direction: str = "LONG"
    ) -> List[ZebraStructure]:
        """
        Constructs and ranks ZEBRA structures.
        
        Args:
            symbol: Ticker symbol
            stock_price: Current underlying price
            thesis_horizon_days: Expected duration of move (default 30)
            direction: "LONG" (Bullish/Calls) or "SHORT" (Bearish/Puts)
            
        Returns:
            List of top ranked ZebraStructure objects
        """
        structures = []
        
        # 1. Determine target expiry window (2x rule)
        target_dte = thesis_horizon_days * 2
        min_dte = int(target_dte * 0.8)
        max_dte = int(target_dte * 1.5)
        
        logger.info(f"Scanning {symbol} ({direction}) for ZEBRA. Target DTE: {target_dte} ({min_dte}-{max_dte}d)")
        
        # 2. Fetch Option Chain
        try:
            chain = self.client.get_option_chain(symbol)
        except Exception as e:
            logger.error(f"Failed to fetch chain for {symbol}: {e}")
            return []
            
        # 3. Filter Expirations
        valid_expiries = []
        for expiry_date in chain.keys():
            dte = (expiry_date - date.today()).days
            if min_dte <= dte <= max_dte:
                valid_expiries.append(expiry_date)
        
        if not valid_expiries:
            logger.warning(f"No expiries found for {symbol} in range {min_dte}-{max_dte} dte")
            return []
            
        # 4. Iterate valid expiries
        option_type = 'C' if direction == "LONG" else 'P'
        
        for expiry in valid_expiries:
            options = chain[expiry]
            # Filter by option type
            options = [o for o in options if o.option_type == option_type]
            
            # Identify candidates for Long and Short legs
            long_candidates = []
            short_candidates = []
            
            for opt in options:
                delta = abs(opt.delta) if opt.delta is not None else 0
                
                # Long leg criteria (ITM, higher delta)
                if ZEBRA_LONG_DELTA_MIN <= delta <= ZEBRA_LONG_DELTA_MAX:
                    long_candidates.append(opt)
                    
                # Short leg criteria (ATM, ~0.50 delta)
                if ZEBRA_SHORT_DELTA_MIN <= delta <= ZEBRA_SHORT_DELTA_MAX:
                    short_candidates.append(opt)
            
            # 5. Construct Combinations
            for long_opt in long_candidates:
                for short_opt in short_candidates:
                    
                    # Validate strike relationship
                    if direction == "LONG":
                        # For Calls: Long strike < Short strike (ITM < ATM)
                        if long_opt.strike >= short_opt.strike:
                            continue
                    else:
                        # For Puts: Long strike > Short strike (ITM > ATM)
                        if long_opt.strike <= short_opt.strike:
                            continue
                            
                    # Build structure
                    structure = self._build_structure(
                        symbol, direction, expiry, long_opt, short_opt, stock_price
                    )
                    
                    if structure:
                        structures.append(structure)
        
        # 6. Rank Structures
        structures.sort(key=lambda x: x.construction_score, reverse=True)
        return structures[:5]  # Return top 5

    def _build_structure(
        self,
        symbol: str, 
        direction: str, 
        expiry: date, 
        long_leg: OptionData, 
        short_leg: OptionData,
        stock_price: float
    ) -> Optional[ZebraStructure]:
        """Calculates metrics and scores a specific ZEBRA combination."""
        
        # Pricing (Ask for Longs, Bid for Short)
        # Conservative debit calculation
        long_cost = long_leg.ask
        short_credit = short_leg.bid
        
        # 2 Longs, 1 Short
        net_debit = (2 * long_cost) - short_credit
        
        if net_debit <= 0:
            return None # Invalid pricing (arb? unlikely)
            
        # Calculate Net Extrinsic
        # Extrinsic = Price - Intrinsic
        def get_intrinsic(strike, price, kind):
            if kind == 'LONG': # Call
                return max(0, price - strike)
            else: # Put
                return max(0, strike - price)
                
        long_intrinsic = get_intrinsic(float(long_leg.strike), stock_price, direction)
        short_intrinsic = get_intrinsic(float(short_leg.strike), stock_price, direction)
        
        long_extrinsic = long_cost - long_intrinsic
        short_extrinsic = short_credit - short_intrinsic
        
        # Core ZEBRA Metric: Net Extrinsic should be ~0
        # We pay extrinsic on 2 longs, collect on 1 short
        net_extrinsic = (2 * long_extrinsic) - short_extrinsic
        
        # Filter high extrinsic (if requested, though score penalties usually handle this)
        # However, stricter filtering saves processing time
        # if abs(net_extrinsic) > 0.50: return None 
        
        # Greeks
        net_delta = (2 * (long_leg.delta or 0)) - (short_leg.delta or 0)
        net_theta = (2 * (long_leg.theta or 0)) - (short_leg.theta or 0)
        net_vega = (2 * (long_leg.vega or 0)) - (short_leg.vega or 0)
        
        # Breakeven & Efficiency
        if direction == "LONG":
            breakeven = float(long_leg.strike) + (net_debit / 2)
        else:
            breakeven = float(long_leg.strike) - (net_debit / 2)
            
        # Capital Efficiency: Delta per $1000
        # Stock: 100 delta costs (stock_price * 100)
        stock_cost = stock_price * 100
        zebra_cost = net_debit * 100
        
        if zebra_cost == 0: return None
        
        # leverage ratio
        cap_eff = (abs(net_delta) * 100 / zebra_cost) / (100 / stock_cost) 
        
        # Slippage Check
        # Aggregate width of bid-asks
        long_spread = long_leg.ask - long_leg.bid
        short_spread = short_leg.ask - short_leg.bid
        total_spread_cost = (2 * long_spread) + short_spread
        slippage_pct = (total_spread_cost / net_debit) * 100
        slippage_warning = slippage_pct > ZEBRA_SLIPPAGE_WARNING_PCT
        
        # SCORING ALGORITHM
        # 1. Extrinsic (35%): closer to 0 is better.
        score_extrinsic = max(0, 100 - (abs(net_extrinsic) * 200)) # e.g. $0.10 off -> 80pts
        
        # 2. Capital Efficiency (25%): higher is better
        # Cap eff usually 2.0 - 4.0. Map 2->50, 4->100
        score_capeff = min(100, max(0, (cap_eff - 1) * 33))
        
        # 3. Liquidity/Slippage (25%): lower spread is better
        score_liquid = max(0, 100 - (slippage_pct * 20))
        
        # 4. Open Interest (15%): higher is better
        min_oi = min(long_leg.open_interest or 0, short_leg.open_interest or 0)
        score_oi = min(100, min_oi / 10) # 1000 OI = 100 pts
        
        construction_score = (
            score_extrinsic * 0.35 +
            score_capeff * 0.25 + 
            score_liquid * 0.25 + 
            score_oi * 0.15
        )
        
        return ZebraStructure(
            symbol=symbol,
            direction=direction,
            expiry=expiry,
            dte=(expiry - date.today()).days,
            long_leg=long_leg,
            short_leg=short_leg,
            net_delta=net_delta,
            net_theta=net_theta,
            net_vega=net_vega,
            net_gamma=0.0, # Not usually primary factor
            net_extrinsic=net_extrinsic,
            net_debit=net_debit,
            max_loss=net_debit,
            breakeven=breakeven,
            capital_efficiency=cap_eff,
            construction_score=construction_score,
            slippage_warning=slippage_warning
        )

