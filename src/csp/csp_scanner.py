"""
CSP Opportunity Scanner
=======================

Scans for the best Cash-Secured Put and Put Credit Spread opportunities.
Composes:
- Zebra RegimeDetector (VIX environment checks)
- Theta OptionsAnalyzer (Put scoring)
- VerticalSpreadSelector (Put credit spread construction)
- EarningsCalendar (Blackout windows)
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.theta_spreads.options_analyzer import OptionsAnalyzer, PutScore
from src.vertical_spreads.spread_selector import VerticalSpreadSelector, VerticalSpreadSetup
from src.zebra.regime_detector import RegimeDetector, MarketRegime
from src.theta_spreads.earnings_calendar import EarningsCalendar

logger = logging.getLogger(__name__)

@dataclass
class CSPCandidate:
    """Scored put selling candidate."""
    symbol: str
    tier: str
    underlying_price: float
    
    # Base option data
    sell_strike: float
    expiration: datetime.date
    dte: int
    delta: float
    
    # Strategy specific
    is_spread: bool
    buy_strike: Optional[float] = None  # Only if put credit spread
    
    # Capital & Return
    premium_credit: float
    capital_required: float
    annualized_return_pct: float
    
    # Context
    iv_rank: float
    probability_otm: float
    score: float
    rationale: str

class CSPScanner:
    """
    Scans the options chain for put-selling candidates that match 
    Dual-Core strategy parameters.
    """
    def __init__(self, data_provider=None):
        self.provider = data_provider
        self.options_analyzer = OptionsAnalyzer(
            target_delta=0.25,      # Blended average target
            delta_tolerance=0.10,   # Wide enough for both tiers
            dte_min=20,             # Lower bound for Aggressive
            dte_max=45,             # Upper bound for Conservative
            min_premium=0.30,
            min_liquidity=50
        )
        self.regime_detector = RegimeDetector()
        self.earnings_cal = EarningsCalendar()
        self.spread_selector = VerticalSpreadSelector(
            max_loss_percent=0.02,
            default_width=5.0
        )
        
    def scan_opportunities(
        self,
        symbols_with_scores: List[Tuple[str, float, Dict]], # [(symbol, fair_value_discount, chain_dict)]
        vix_level: float,
        tier: str,
        account_balance: float
    ) -> List[CSPCandidate]:
        """
        Run the full scanning pipeline.
        """
        logger.info(f"Running {tier.upper()} CSP scan for {len(symbols_with_scores)} symbols (VIX: {vix_level:.1f})")
        
        # 1. Regime Check
        regime = self.regime_detector.get_current_regime(symbols_with_scores[0][0]) if symbols_with_scores else MarketRegime.NORMAL
        
        if vix_level < 15.0 and tier == "conservative":
             logger.info("VIX below 15. Pausing Conservative CSP selling (premium too thin).")
             return []
             
        # 2. Iterate Symbols
        candidates = []
        for symbol, fv_discount, chain_data in symbols_with_scores:
            
            # 2a. Earnings Blackout Check
            if tier == "aggressive":
                if self.earnings_cal.is_in_blackout(symbol, chain_data.get('earnings_dates', [])):
                    logger.debug(f"Skipping {symbol}: Earnings blackout window.")
                    continue
                    
            # 2b. Set Delta Targets
            target_delta = 0.20 if tier == "conservative" else 0.30
            self.options_analyzer.target_delta = target_delta
            
            # 3. Analyze Puts 
            # We use the existing OptionsAnalyzer which scores based on theta, delta, etc.
            # Convert chain_data map to list of dicts expected by analyzer
            chain_list = chain_data.get('options', [])
            if not chain_list:
                continue
                
            raw_puts = self.options_analyzer.analyze_symbol(symbol, 50, chain_list)
            
            for put in raw_puts:
                # 4. Filter by IV Rank
                if tier == "aggressive" and put.iv_rank < 40:
                    continue
                elif tier == "conservative" and put.iv_rank < 30:
                    continue
                    
                # 5. Build Strategy (Spread vs Naked)
                if tier == "conservative":
                    # Build Put Credit Spread
                    spread_setup = self._build_credit_spread(symbol, put, account_balance, chain_list)
                    if not spread_setup:
                        continue
                        
                    capital_req = (spread_setup.sell_strike - spread_setup.buy_strike) * 100
                    credit = spread_setup.net_debit * -1 # It's a credit
                    is_spread = True
                    buy_strike_val = spread_setup.buy_strike
                else:
                    # Cash Secured Put
                    capital_req = put.strike * 100
                    credit = put.mid
                    is_spread = False
                    buy_strike_val = None
                    
                # 6. Calculate Final Score
                ann_return = (credit / capital_req) * (365 / put.dte)
                
                # Formula: Score = (AnnReturn × 0.4) + (IVRank × 0.3) + (FairValueDiscount × 0.2) + (LiquidityScore × 0.1)
                liquidity_score = put.liquidity_score / 100.0  # normalize
                iv_rank_score = min(put.iv_rank / 100.0, 1.0)
                fv_score = max(0, min(fv_discount, 0.5)) * 2.0 # Cap at 50% discount
                
                final_score = (ann_return * 0.4) + (iv_rank_score * 0.3) + (fv_score * 0.2) + (liquidity_score * 0.1)
                final_score *= 100
                
                candidates.append(CSPCandidate(
                    symbol=symbol,
                    tier=tier,
                    underlying_price=chain_data.get('current_price', 0),
                    sell_strike=put.strike,
                    expiration=put.expiration,
                    dte=put.dte,
                    delta=put.delta,
                    is_spread=is_spread,
                    buy_strike=buy_strike_val,
                    premium_credit=credit,
                    capital_required=capital_req,
                    annualized_return_pct=ann_return,
                    iv_rank=put.iv_rank,
                    probability_otm=put.probability_otm,
                    score=final_score,
                    rationale=f"Target Delta: {target_delta} | IVR: {put.iv_rank:.1f} | Ann. ROI: {ann_return*100:.1f}%"
                ))
                
        # Sort by score descending
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates
        
    def _build_credit_spread(self, symbol: str, sell_put: PutScore, account_balance: float, chain_list: List[Dict]) -> Optional[VerticalSpreadSetup]:
        """Leverages VerticalSpreadSelector to properly size and find the long leg."""
        # Using the base spread selector logic, adapted for our specific short put
        try:
            return self.spread_selector._select_bull_put_spread(
                symbol=symbol,
                stock_price=0.0, # Not strictly needed if we feed the exact strikes
                implied_move=0.0,
                confidence=70,
                expiration=sell_put.expiration,
                dte=sell_put.dte,
                account_balance=account_balance,
                risk_tolerance="conservative",
                options_chain={'options': chain_list},
                fixed_sell_strike=sell_put.strike # Assuming we patch VerticalSpreadSelector to accept this
            )
        except Exception as e:
            # Fallback if unpatched
            logger.debug(f"Could not build spread automatically, using heuristic: {e}")
            buy_strike = sell_put.strike - 5.0
            
            # Find the long put
            long_put = next((p for p in chain_list if p.get('strike') == buy_strike and p.get('type') == 'P' and p.get('expiration') == sell_put.expiration.strftime('%Y-%m-%d')), None)
            
            if not long_put:
                return None
                
            net_credit = sell_put.mid - ((long_put.get('bid', 0) + long_put.get('ask', 0)) / 2)
            if net_credit <= 0.10: # Minimum $10 credit
                return None
                
            return VerticalSpreadSetup(
                symbol=symbol,
                strategy="BULL_PUT_SPREAD",
                direction="BULL",
                sell_strike=sell_put.strike,
                buy_strike=buy_strike,
                option_type="P",
                expiration=sell_put.expiration,
                dte=sell_put.dte,
                net_debit=-net_credit, # It's a credit setup
                max_profit=net_credit,
                max_loss=(sell_put.strike - buy_strike) - net_credit,
                contracts=1,
                reasoning="Heuristic spread build",
                confidence=70
            )

