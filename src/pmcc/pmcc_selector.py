import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.diagonal_spreads.spread_selector import DiagonalSpreadSelector, DiagonalSpreadSetup
from ib_data_provider import IBDataProvider

logger = logging.getLogger(__name__)

@dataclass
class PMCCSetup(DiagonalSpreadSetup):
    """
    Extends DiagonalSpreadSetup with PMCC specific fields.
    """
    bci_formula_met: bool = False
    extrinsic_ratio: float = 0.0

class PMCCSelector(DiagonalSpreadSelector):
    """
    Extends DiagonalSpreadSelector for PMCC-specific rules:
    - Long leg: LEAPS (300-800 DTE), Target Delta 0.80
    - Short leg: Near-term (7-45 DTE), Target Delta 0.20-0.30
    - Real market data fetching via IB
    - Extrinsic value/BCI formula validation
    """
    
    def __init__(self, data_provider: Optional[IBDataProvider] = None):
        super().__init__(
            max_loss_percent=0.03,
            long_target_delta=0.80,
            short_target_delta=0.25,
            short_dte_min=7,
            short_dte_max=45,
            long_dte_min=300,
            long_dte_max=800
        )
        self.ib = data_provider or IBDataProvider()

    def select_pmcc_entry(
        self,
        symbol: str,
        stock_price: float,
        confidence: int,
        account_balance: float,
        risk_tolerance: str = "medium",
        iv_signal: Optional[Dict] = None
    ) -> Optional[PMCCSetup]:
        """
        Select the optimal initial PMCC structure (LEAPS + first short call).
        Fetches live option chains to make the selection.
        """
        # 1. Fetch available expirations to pick dates
        # Using ib_data_provider method to get nearest ~365 and ~30
        long_exp = self.ib.get_next_expiry(symbol, 365)
        short_exp = self.ib.get_next_expiry(symbol, 30)
        
        if not long_exp or not short_exp:
            logger.warning(f"{symbol}: Could not find expirations for PMCC")
            return None
            
        long_dte = (long_exp - date.today()).days
        short_dte = (short_exp - date.today()).days
        
        # 1.5. Evaluate ML IV Signal
        # If the Deep Learning LSTM predicts that IV will drop significantly over the next
        # 30 days, we should delay buying the LEAPS leg to avoid taking a Vega crush loss.
        # Conversely, buying right before IV expands ('UP') is highly advantageous.
        if iv_signal:
            iv_dir = iv_signal.get('direction', 'UNKNOWN')
            iv_conf = iv_signal.get('confidence', 0.0)
            
            # Confidence gating threshold: 0.70
            if iv_dir == 'DOWN' and iv_conf > 0.70:
                logger.info(f"{symbol}: ML IV Forecaster predicts IV crush ('DOWN', conf: {iv_conf:.2f}). Rejecting LEAPS entry to wait for cheaper prices.")
                return None
            elif iv_dir == 'UP' and iv_conf > 0.70:
                logger.info(f"{symbol}: ML IV Forecaster predicts IV expansion ('UP', conf: {iv_conf:.2f}). Highly favorable LEAPS entry environment.")
                # We could artificially boost 'confidence' parameter here for sizing
                confidence = min(100, confidence + 15)
        
        # 2. Fetch Option Chains
        logger.info(f"{symbol}: Fetching LEAPS chain for {long_exp} ({long_dte} DTE)")
        leaps_chain = self.ib.get_call_chain_for_pmcc(
            symbol=symbol, 
            expiry=long_exp, 
            delta_min=0.70, 
            delta_max=0.90, 
            is_leaps=True
        )
        
        logger.info(f"{symbol}: Fetching Short Call chain for {short_exp} ({short_dte} DTE)")
        short_chain = self.ib.get_call_chain_for_pmcc(
            symbol=symbol,
            expiry=short_exp,
            delta_min=0.15,
            delta_max=0.35,
            is_leaps=False
        )
        
        if not leaps_chain or not short_chain:
            logger.warning(f"{symbol}: Missing valid option chains for PMCC strikes")
            return None
            
        # 3. Select Best LEAPS (Closest to target 0.80 delta)
        leaps_chain.sort(key=lambda x: abs(x['delta'] - self.long_target_delta))
        best_leaps = leaps_chain[0]
        
        # 4. Select Best Short Call (Closest to target 0.25 delta)
        # TODO: Phase 2.2/2.3 - Incorporate resistance level matching
        short_chain.sort(key=lambda x: abs(x['delta'] - self.short_target_delta))
        best_short = short_chain[0]
        
        long_strike = best_leaps['strike']
        long_price = best_leaps['ask'] if best_leaps['ask'] > 0 else best_leaps['bid']
        
        short_strike = best_short['strike']
        short_price = best_short['bid'] if best_short['bid'] > 0 else best_short['ask']
        
        if long_price <= 0 or short_price <= 0:
            logger.warning(f"{symbol}: Invalid option prices long={long_price}, short={short_price}")
            return None
            
        net_debit = long_price - short_price
        
        if net_debit <= 0:
            logger.warning(f"{symbol}: Invalid net debit ${net_debit:.2f}")
            return None
        
        # 5. PMCC Economics & BCI Validation
        # Intrinsic value of LEAPS
        intrinsic_val = max(0, stock_price - long_strike)
        # Extrinsic value of LEAPS
        extrinsic_val = long_price - intrinsic_val
        
        # Extrinsic Ratio (Extrinsic / Stock Price) - Should be low
        extrinsic_ratio = extrinsic_val / stock_price
        
        # BCI Formula Rule of Thumb: Short premium should cover extrinsic value of LEAPS in ~2-3 cycles
        # Technically: (Long Strike + Net Debit) < Short Strike for guaranteed no-loss if called away
        break_even = long_strike + net_debit
        bci_formula_met = break_even < short_strike
        
        if not bci_formula_met:
            logger.info(f"{symbol}: BCI Formula not met (Break Even {break_even:.2f} > Short Strike {short_strike:.2f})")
            # We might still accept it if confidence is high, but BCI is preferred
            
        strike_width = short_strike - long_strike
        max_profit = (strike_width - net_debit) * 100
        max_loss = net_debit * 100
        
        contracts = self._calculate_contracts(
            max_loss, account_balance, risk_tolerance
        )
        
        return PMCCSetup(
            symbol=symbol,
            strategy="PMCC",
            direction="BULL",
            long_strike=long_strike,
            long_expiration=best_leaps['expiration'],
            long_dte=long_dte,
            long_delta=best_leaps['delta'],
            long_price=long_price,
            short_strike=short_strike,
            short_expiration=best_short['expiration'],
            short_dte=short_dte,
            short_delta=best_short['delta'],
            short_price=short_price,
            option_type="C",
            net_debit=net_debit,
            max_profit=max_profit,
            max_loss=max_loss,
            break_even=break_even,
            contracts=contracts,
            total_at_risk=max_loss * contracts,
            confidence=confidence,
            bci_formula_met=bci_formula_met,
            extrinsic_ratio=extrinsic_ratio
        )
