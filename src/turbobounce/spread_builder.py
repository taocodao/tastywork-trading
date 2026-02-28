"""
TurboBounce Options: Strategy Builder
=====================================
Selects optimal strike and expiration combinations for Multi-Ticker Strategies.
Supports Diagonals, Verticals (Credit Spreads), and Naked Longs.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class OptionLeg:
    symbol: str
    strike: float
    expiration: date
    right: str  # 'P' or 'C'
    delta: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    
    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2.0

@dataclass
class SpreadMetrics:
    short_leg: Optional[OptionLeg]
    long_leg: Optional[OptionLeg]
    credit: float
    max_risk: float
    reward_to_risk: float
    liquidity_score: float
    strategy_type: str

class StrategyBuilder:
    """
    Selects optimal option legs for various structures natively 
    across any ticker.
    """
    
    def __init__(self, data_provider=None):
        self.data_provider = data_provider
        
    def build_strategy(self, 
                      symbol: str, 
                      current_price: float, 
                      chain_data: List[Dict[str, Any]], 
                      routed_strategy) -> Optional[SpreadMetrics]:
        """
        Main entry point that dispatches to the correct builder.
        """
        stype = routed_strategy.strategy_type
        
        if stype == "DIAGONAL":
            return self.select_optimal_diagonal(
                symbol, current_price, chain_data, 
                routed_strategy.direction,
                anchor_dte=routed_strategy.target_anchor_dte or 45,
                hedge_dte=routed_strategy.target_hedge_dte or 10
            )
        elif stype == "CREDIT_SPREAD":
            return self.select_optimal_vertical(
                symbol, current_price, chain_data, 
                routed_strategy.direction,
                target_dte=routed_strategy.target_anchor_dte or 30,
                target_delta=routed_strategy.target_delta or 0.20
            )
        elif stype == "NAKED_LONG":
            return self.select_optimal_naked(
                symbol, current_price, chain_data, 
                routed_strategy.direction,
                target_dte=routed_strategy.target_anchor_dte or 14,
                target_delta=routed_strategy.target_delta or 0.30
            )
        
        return None

    def select_optimal_diagonal(self,
                              symbol: str,
                              current_price: float,
                              chain_data: List[Dict[str, Any]],
                              direction: str,
                              anchor_dte: int,
                              hedge_dte: int) -> Optional[SpreadMetrics]:
        """
        Builds a Put Diagonal (Bullish) or Call Diagonal (Bearish).
        Anchor: ~0.40 delta
        Hedge: ~0.20 delta
        """
        right = 'P' if direction == "BULLISH" else 'C'
        
        anchor_options = self._filter_structural(chain_data, right, anchor_dte)
        anchor_liquid = self._filter_liquidity(anchor_options)
        if not anchor_liquid: return None
            
        anchor_candidates = sorted(anchor_liquid, key=lambda x: abs(abs(x.get('delta', 0.0)) - 0.40))
        if not anchor_candidates: return None
        anchor_leg = self._dict_to_leg(anchor_candidates[0], right)

        hedge_options = self._filter_structural(chain_data, right, hedge_dte)
        hedge_liquid = self._filter_liquidity(hedge_options)
        if not hedge_liquid: return None

        hedge_candidates = sorted(hedge_liquid, key=lambda x: abs(abs(x.get('delta', 0.0)) - 0.20))
        if not hedge_candidates: return None
        hedge_leg = self._dict_to_leg(hedge_candidates[0], right)

        net_credit = anchor_leg.bid - hedge_leg.ask
        max_risk = max(0.0, abs(anchor_leg.strike - hedge_leg.strike) - net_credit)
        cmb_liquidity = (anchor_leg.volume + hedge_leg.volume) / 5000.0

        return SpreadMetrics(
            short_leg=anchor_leg,
            long_leg=hedge_leg,
            credit=net_credit,
            max_risk=max_risk,
            reward_to_risk=net_credit / max_risk if max_risk > 0 else 0,
            liquidity_score=cmb_liquidity,
            strategy_type="DIAGONAL"
        )

    def select_optimal_vertical(self,
                              symbol: str,
                              current_price: float,
                              chain_data: List[Dict[str, Any]],
                              direction: str,
                              target_dte: int,
                              target_delta: float) -> Optional[SpreadMetrics]:
        """
        Builds a Bull Put Credit Spread or Bear Call Credit Spread.
        """
        right = 'P' if direction == "BULLISH" else 'C'
        
        valid_options = self._filter_structural(chain_data, right, target_dte)
        liquid_options = self._filter_liquidity(valid_options)
        if not liquid_options: return None
        
        # We need a dynamic spread width based on the underlying price.
        # Approx 1% of the stock price, rounded to nearest friendly strike ($1 for $100 stock, $5 for $500 stock)
        width_approx = max(0.5, round((current_price * 0.01) * 2) / 2.0)
        s_width = 1.0 if width_approx <= 1.0 else (5.0 if width_approx >= 4.0 else 2.5)

        short_candidates = sorted(liquid_options, key=lambda x: abs(abs(x.get('delta', 0.0)) - target_delta))
        
        candidate_spreads = []
        for short_dict in short_candidates[:5]:
            short_leg = self._dict_to_leg(short_dict, right)
            
            # Put Credit Spread: Long leg is lower strike
            # Call Credit Spread: Long leg is higher strike
            if right == 'P':
                target_long_strike = short_leg.strike - s_width
            else:
                target_long_strike = short_leg.strike + s_width
                
            long_candidates = [
                opt for opt in liquid_options
                if opt['expiration'] == short_dict['expiration'] and 
                   abs(opt['strike'] - target_long_strike) <= (s_width * 0.25) # Give +/- 25% slack on strike distance
            ]
            
            if long_candidates:
                long_candidates.sort(key=lambda x: abs(x['strike'] - target_long_strike))
                long_leg = self._dict_to_leg(long_candidates[0], right)
                
                credit = short_leg.bid - long_leg.ask
                if credit > 0.05:
                    max_loss = abs(short_leg.strike - long_leg.strike) - credit
                    r_to_r = credit / max_loss if max_loss > 0 else 0
                    liq = (short_leg.volume + long_leg.volume) / 5000.0
                    
                    candidate_spreads.append(SpreadMetrics(
                        short_leg=short_leg, long_leg=long_leg,
                        credit=credit, max_risk=max_loss, reward_to_risk=r_to_r,
                        liquidity_score=liq, strategy_type="VERTICAL"
                    ))
                    
        if not candidate_spreads: return None
        
        return sorted(candidate_spreads, key=lambda x: x.reward_to_risk * x.liquidity_score, reverse=True)[0]

    def select_optimal_naked(self,
                           symbol: str, current_price: float, chain_data: List[Dict[str, Any]],
                           direction: str, target_dte: int, target_delta: float) -> Optional[SpreadMetrics]:
        """
        Builds a Naked Long Call (Bullish) or Long Put (Bearish) when IV is extremely low.
        """
        right = 'C' if direction == "BULLISH" else 'P'
        valid = self._filter_structural(chain_data, right, target_dte)
        liquid = self._filter_liquidity(valid)
        if not liquid: return None
        
        candidates = sorted(liquid, key=lambda x: abs(abs(x.get('delta', 0.0)) - target_delta))
        if not candidates: return None
        
        leg = self._dict_to_leg(candidates[0], right)
        cost = leg.ask
        
        return SpreadMetrics(
            short_leg=None,
            long_leg=leg,
            credit=-cost,      # Negative credit means debit cost
            max_risk=cost,     # Risk is exactly the premium paid
            reward_to_risk=3.0, # Target 3:1 theoretical on naked momentum wings
            liquidity_score=leg.volume / 2500.0,
            strategy_type="NAKED"
        )
        
    def _filter_structural(self, chain_data: List[Dict[str, Any]], right: str, target_dte: int) -> List[Dict[str, Any]]:
        valid = []
        today = date.today()
        min_dte, max_dte = target_dte - 5, target_dte + 5
        
        for opt in chain_data:
            if opt.get('right', '').upper()[0] != right: continue
                
            try:
                expiry_date = datetime.strptime(opt.get('expiration', ''), "%Y-%m-%d").date()
            except:
                continue
                
            dte = (expiry_date - today).days
            if min_dte <= dte <= max_dte:
                opt['dte'] = dte
                opt['expiration_date'] = expiry_date
                valid.append(opt)
        return valid

    def _filter_liquidity(self, options: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        liquid = []
        for opt in options:
            vol = opt.get('volume', 0)
            oi = opt.get('open_interest', 0)
            bid = opt.get('bid', 0.0)
            ask = opt.get('ask', 0.0)
            
            if bid <= 0 or ask <= 0: continue
            
            spread = ask - bid
            
            # Universal thresholds: significantly lower than TQQQ-specifc to allow 47-ticker breadth,
            # but strict enough to weed out junk.
            if vol >= 10 and oi >= 50 and spread <= 1.00:
                liquid.append(opt)
        return liquid

    def _dict_to_leg(self, opt_dict: Dict[str, Any], right: str) -> OptionLeg:
        return OptionLeg(
            symbol=opt_dict.get('symbol', 'UNK'),
            strike=opt_dict['strike'],
            expiration=opt_dict['expiration_date'],
            right=right,
            delta=opt_dict.get('delta', 0.0),
            bid=opt_dict['bid'],
            ask=opt_dict['ask'],
            volume=opt_dict.get('volume', 0),
            open_interest=opt_dict.get('open_interest', 0)
        )
