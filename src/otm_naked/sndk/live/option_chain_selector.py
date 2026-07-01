import logging
from typing import Optional
from datetime import datetime
import pandas as pd
from ib_insync import Option, Stock

logger = logging.getLogger(__name__)

class LiveOptionSelector:
    """Selects the best option strike from IB option chains based on target Delta and DTE."""
    
    def __init__(self, market_data_provider):
        self.md = market_data_provider
        self.ib = market_data_provider.ib_connector.get_ib()
        
    def select_strike(self, ticker: str, target_dte: int, target_delta: float, right: str) -> Optional[dict]:
        """
        Find the option contract that best matches target_dte and target_delta.
        Returns a dict with contract details, pricing, and Greeks.
        """
        chains = self.md.get_option_chain_data(ticker)
        if not chains:
            logger.error(f"No option chains found for {ticker}")
            return None
            
        smart = next((c for c in chains if c.exchange == 'SMART'), chains[0])
        
        # 1. Find closest expiration
        today = datetime.now().date()
        target_date = today + pd.Timedelta(days=target_dte)
        
        valid_expirations = [e for e in smart.expirations if (datetime.strptime(e, "%Y%m%d").date() - today).days > 0]
        if not valid_expirations:
            logger.error(f"No valid future expirations found for {ticker}")
            return None
            
        best_exp = min(
            valid_expirations,
            key=lambda e: abs((datetime.strptime(e, "%Y%m%d").date() - target_date).days)
        )
                
        logger.info(f"Selected expiry {best_exp} (target DTE: {target_dte})")
        
        # 2. Select candidate strikes
        all_strikes = sorted(smart.strikes)
        spot_price = self.md.get_current_price(ticker)
        if spot_price <= 0:
            logger.error("Could not get current spot price.")
            return None
            
        if right == 'P':
            # Puts: strikes below spot (OTM)
            candidates = [s for s in all_strikes if spot_price * 0.50 <= s <= spot_price * 1.05]
            candidates.sort(reverse=True) # Start closest to ATM
        else:
            # Calls: strikes above spot (OTM)
            candidates = [s for s in all_strikes if spot_price * 0.95 <= s <= spot_price * 1.50]
            candidates.sort() # Start closest to ATM
            
        # Limit to 20 options to avoid hitting 100-line limits
        candidates = candidates[:20]
        
        logger.info(f"Checking {len(candidates)} strikes near spot {spot_price:.2f} for {right} options...")
        
        # 3. Create Option contracts with REQUIRED tradingClass
        contracts = []
        for strike in candidates:
            # SNDK specifically requires tradingClass='SNDK'
            opt = Option(ticker, best_exp, strike, right, 'SMART', currency='USD', tradingClass=ticker)
            contracts.append(opt)
            
        # Qualify and fetch Greeks
        greeks_data = self.md.get_contract_greeks_and_prices(contracts)
        
        if not greeks_data:
            logger.error("Failed to get greeks data for candidates")
            return None
            
        # 4. Find closest delta
        best_contract = None
        best_diff = float('inf')
        best_data = None
        
        for contract in contracts:
            if contract.conId not in greeks_data:
                continue
                
            data = greeks_data[contract.conId]
            delta = abs(data.get("delta", 0.0))
            if delta == 0:
                continue
                
            diff = abs(delta - target_delta)
            if diff < best_diff:
                best_diff = diff
                best_contract = contract
                best_data = data
                best_data["strike"] = contract.strike
                best_data["expiry"] = best_exp
                
        if best_contract:
            logger.info(f"Selected Strike {best_data['strike']} (Delta: {abs(best_data['delta']):.2f}, target: {target_delta:.2f})")
            best_data["contract"] = best_contract
            return best_data
            
        return None
