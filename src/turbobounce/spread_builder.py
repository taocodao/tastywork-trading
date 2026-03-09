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
        
        # LEAPS (180 DTE) only have monthly expirations, so a +/- 5 day window will miss them. Widen to +/- 30 days.
        if target_dte > 90:
            min_dte, max_dte = target_dte - 30, target_dte + 30
        else:
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

def build_turbobounce_spread_legs(
    symbol: str, current_price: float, direction: str, strategy_type: str,
    target_anchor_dte: int, target_hedge_dte: Optional[int] = None,
    target_delta: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Uses IBDataProvider to fetch near-real-time options for the target DTEs
    and builds explicit OCC strings + cost estimates.
    """
    try:
        from ib_market_data_hub import get_hub
        hub = get_hub()
        
        from ib_data_provider import IBDataProvider
        ib = IBDataProvider() # will use hub internally
        
        anchor_date = date.today() + timedelta(days=target_anchor_dte)
        right = 'P' if direction == "BULLISH" else 'C'
        
        anchor_chain = None
        for attempt in range(3):
            try:
                anchor_chain = ib.get_options(symbol, anchor_date, option_type="call" if right == 'C' else "put")
                if anchor_chain:
                    break
            except Exception as e:
                logger.warning(f"IB Gateway error on anchor chain fetch for {symbol} (attempt {attempt+1}): {e}")
            import time
            time.sleep(1.5)
            
        if not anchor_chain:
            logger.warning(f"No {symbol} anchor chain found near {anchor_date} after 3 retries")
            return None
            
        anchor_options = []
        for opt in anchor_chain:
            delta = abs(opt.delta) if hasattr(opt, 'delta') and opt.delta else 0.40 # Proxy if missing
            anchor_options.append({
                'strike': opt.strike,
                'expiration_date': opt.expiry,
                'delta': delta,
                'bid': opt.bid,
                'ask': opt.ask,
                'volume': opt.volume,
                'open_interest': getattr(opt, 'open_interest', 0)
            })
            
        builder = StrategyBuilder(ib)
        liquid_anchors = builder._filter_liquidity(anchor_options)
        
        anchor_leg = None
        if liquid_anchors:
            # Anchor is usually ~0.40
            anchor_candidates = sorted(liquid_anchors, key=lambda x: abs(x.get('delta', 0.4)-0.40))
            a_dict = anchor_candidates[0]
            anchor_leg = OptionLeg(symbol, a_dict['strike'], a_dict['expiration_date'], right, a_dict['delta'], a_dict['bid'], a_dict['ask'], a_dict['volume'], getattr(a_dict, 'open_interest', 0))

        if not anchor_leg:
            logger.warning(f"No liquid anchor option for {symbol}")
            return None

        # Build OCC strings
        def format_occ(sym: str, dt: date, right: str, strike: float) -> str:
            d_str = dt.strftime('%y%m%d')
            s_str = f"{int(strike * 1000):08d}"
            # Left align symbol to 6 chars
            padded_sym = sym.ljust(6, ' ')
            return f"{padded_sym}{d_str}{right}{s_str}"

        anchor_occ = format_occ(symbol, anchor_leg.expiration, right, anchor_leg.strike)

        if strategy_type == "DIAGONAL" and target_hedge_dte:
            hedge_date = date.today() + timedelta(days=target_hedge_dte)
            hedge_chain = None
            for attempt in range(3):
                try:
                    hedge_chain = ib.get_options(symbol, hedge_date, option_type="call" if right == 'C' else "put")
                    if hedge_chain:
                        break
                except Exception as e:
                    logger.warning(f"IB Gateway error on hedge chain fetch for {symbol} (attempt {attempt+1}): {e}")
                import time
                time.sleep(1.5)
                
            if not hedge_chain:
                logger.warning(f"No {symbol} hedge chain found near {hedge_date} after 3 retries")
                return None
            
            hedge_options = []
            for opt in hedge_chain:
                delta = abs(opt.delta) if hasattr(opt, 'delta') and opt.delta else 0.20
                hedge_options.append({
                    'strike': opt.strike,
                    'expiration_date': opt.expiry,
                    'delta': delta,
                    'bid': opt.bid,
                    'ask': opt.ask,
                    'volume': opt.volume,
                    'open_interest': getattr(opt, 'open_interest', 0)
                })
                
            liquid_hedges = builder._filter_liquidity(hedge_options)
            hedge_leg = None
            if liquid_hedges:
                hedge_candidates = sorted(liquid_hedges, key=lambda x: abs(x.get('delta', 0.2)-0.20))
                h_dict = hedge_candidates[0]
                hedge_leg = OptionLeg(symbol, h_dict['strike'], h_dict['expiration_date'], right, h_dict['delta'], h_dict['bid'], h_dict['ask'], h_dict['volume'], getattr(h_dict, 'open_interest', 0))

            if not hedge_leg:
                logger.warning(f"No liquid hedge option for {symbol}")
                return None

            hedge_occ = format_occ(symbol, hedge_leg.expiration, right, hedge_leg.strike)
            
            anchor_mid = (anchor_leg.bid + anchor_leg.ask) / 2.0
            hedge_mid = (hedge_leg.bid + hedge_leg.ask) / 2.0
            
            # Diagonal: Buy Anchor (long), Sell Hedge (short)
            net_ask_cost = anchor_leg.ask - hedge_leg.bid
            net_mid_cost = anchor_mid - hedge_mid
            
            # Prevent Division by Zero on Free Spreads
            if net_mid_cost <= 0:
                logger.warning(f"Rejected {symbol} Diagonal: Mid cost <= 0")
                return None
                
            # Slippage Check (Reject > 20% deviation from mid)
            if net_ask_cost > (net_mid_cost * 1.20):
                logger.warning(f"Rejected {symbol} Diagonal: Wide spread {net_ask_cost:.2f} > 20% of mid {net_mid_cost:.2f}")
                return None
            
            return {
                "legs": [
                    {"symbol": anchor_occ, "action": "BUY", "quantity": 1},
                    {"symbol": hedge_occ, "action": "SELL", "quantity": 1}
                ],
                "cost": net_ask_cost,
                "mid_price": net_mid_cost,
                "price_range": net_mid_cost * 1.05, # Acceptable up to +5% slippage on AutoApprove
                "frontExpiry": hedge_leg.expiration.isoformat(),
                "backExpiry": anchor_leg.expiration.isoformat(),
                "strike": anchor_leg.strike
            }

        else: # NAKED_LONG
            anchor_mid = (anchor_leg.bid + anchor_leg.ask) / 2.0
            net_ask_cost = anchor_leg.ask
            
            if anchor_mid <= 0:
                logger.warning(f"Rejected {symbol} Naked Long: Mid cost <= 0")
                return None

            if net_ask_cost > (anchor_mid * 1.20):
                logger.warning(f"Rejected {symbol} Naked Long: Wide spread {net_ask_cost:.2f} > 20% of mid {anchor_mid:.2f}")
                return None
                
            return {
                "legs": [
                    {"symbol": anchor_occ, "action": "BUY", "quantity": 1}
                ],
                "cost": net_ask_cost,
                "mid_price": anchor_mid,
                "price_range": anchor_mid * 1.05,
                "frontExpiry": anchor_leg.expiration.isoformat(),
                "strike": anchor_leg.strike
            }

    except Exception as e:
        logger.error(f"Failed forming precise option legs for {symbol}: {e}")
        return None
