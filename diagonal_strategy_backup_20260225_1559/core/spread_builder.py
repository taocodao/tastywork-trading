"""
Diagonal Spread Builder
=======================
Selects optimal anchor and hedge legs with varying expirations.
"""

from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

class DiagonalSpreadBuilder:
    def __init__(self, config, iv_monitor=None):
        self.config = config
        self.iv_monitor = iv_monitor

    def select_diagonal_entry(self, regime: str, ta_features: Dict[str, Any], tqqq_price: float, chain_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Returns optimal diagonal entry dict.
        """
        if regime not in self.config.TQQQ_DIAGONAL_PARAMS:
            logger.warning(f"No diagonal params for regime {regime}")
            return {}
            
        params = self.config.TQQQ_DIAGONAL_PARAMS[regime]
        
        anchor_dte_target = params['anchor_dte'] # 45-60
        anchor_delta_target = params['anchor_delta'] # -0.18 to -0.22
        
        if self.iv_monitor and ta_features:
            term_slope = ta_features.get('term_slope', 0.0)
            if term_slope > 0.15:
                anchor_dte_target = min(anchor_dte_target + 7, 75)
                
        anchor_candidates = self._filter_options(
            chain_data, 'PUT',
            dte_range=(anchor_dte_target - 10, anchor_dte_target + 14),
            delta_range=(anchor_delta_target - 0.05, anchor_delta_target + 0.05)
        )
        
        hedge_dte_target = params['hedge_dte']
        hedge_delta_target = params['hedge_delta']
        
        hedge_candidates = self._filter_options(
            chain_data, 'PUT',
            dte_range=(hedge_dte_target - 5, hedge_dte_target + 7),
            delta_range=(hedge_delta_target - 0.05, hedge_delta_target + 0.05)
        )
        
        return self._optimize_pair(anchor_candidates, hedge_candidates, tqqq_price)

    def select_new_hedge(self, anchor_strike: float, chain_data: List[Dict[str, Any]], tqqq_price: float, params: Dict[str, Any]) -> Dict[str, Any]:
        hedge_dte_target = params['hedge_dte']
        hedge_delta_target = params['hedge_delta']
        
        hedge_candidates = self._filter_options(
            chain_data, 'PUT',
            dte_range=(hedge_dte_target - 5, hedge_dte_target + 7),
            delta_range=(hedge_delta_target - 0.05, hedge_delta_target + 0.05)
        )
        
        best_hedge = None
        best_score = -999.0
        
        for h in hedge_candidates:
            # prioritize cheapness and proximity to target delta
            score = - abs(h['delta'] - hedge_delta_target) * 10 - h.get('ask', 9.9)
            if score > best_score:
                best_score = score
                best_hedge = h
                
        if best_hedge:
            return {'hedge': best_hedge}
        return {}

    def _filter_options(self, chain: List[Dict[str, Any]], right: str, dte_range: tuple, delta_range: tuple) -> List[Dict[str, Any]]:
        filtered = []
        for opt in chain:
            if opt.get('right', '').upper() != right.upper(): continue
            dte = opt.get('dte', 0)
            if not (dte_range[0] <= dte <= dte_range[1]): continue
            delta = opt.get('delta', 0.0)
            if not (delta_range[0] <= delta <= delta_range[1]): continue
            
            bid = opt.get('bid', 0.0)
            if bid <= 0.01: continue
            
            filtered.append(opt)
        return filtered

    def _optimize_pair(self, anchors: List[Dict[str, Any]], hedges: List[Dict[str, Any]], tqqq_price: float) -> Dict[str, Any]:
        best_pair = {}
        best_score = -999.0
        
        for anchor in anchors:
            for hedge in hedges:
                if anchor['dte'] <= hedge['dte']: continue
                
                credit = anchor.get('bid', 0.0) - hedge.get('ask', 0.0)
                if credit <= 0.10: continue
                
                margin_risk = max(0.01, float(anchor['strike'] - hedge['strike']))
                roi = credit / margin_risk
                
                score = roi * 100
                if score > best_score:
                    best_score = score
                    best_pair = {
                        'anchor': anchor,
                        'hedge': hedge,
                        'net_credit': credit,
                        'max_risk': margin_risk,
                        'roi': roi,
                        'breakeven': anchor['strike'] - credit
                    }
                    
        return best_pair
