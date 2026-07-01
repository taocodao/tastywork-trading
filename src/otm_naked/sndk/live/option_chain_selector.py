import logging
import asyncio
from typing import List, Optional
from datetime import datetime
from ib_insync import Option, IB

logger = logging.getLogger(__name__)

class LiveOptionSelector:
    """Selects the best option strike from IB option chains based on target Delta and DTE."""
    
    def __init__(self, market_data_provider):
        self.md = market_data_provider
        self.ib = market_data_provider.ib_connector.get_ib()
        
    async def select_strike(self, ticker: str, target_dte: int, target_delta: float, right: str) -> Optional[dict]:
        """
        Find the option contract that best matches target_dte and target_delta.
        Returns a dict with contract details, pricing, and Greeks.
        """
        chains = await self.md.get_option_chain_data(ticker)
        if not chains:
            logger.error(f"No option chains found for {ticker}")
            return None
            
        chain = chains[0]
        expirations = sorted(list(chain.expirations))
        
        # 1. Find closest expiration
        today = datetime.now().date()
        best_exp = None
        min_diff = 999
        
        for exp_str in expirations:
            # format: YYYYMMDD
            exp_date = datetime.strptime(exp_str, "%Y%m%d").date()
            diff_days = (exp_date - today).days
            if diff_days <= 0:
                continue
                
            abs_diff = abs(diff_days - target_dte)
            if abs_diff < min_diff:
                min_diff = abs_diff
                best_exp = exp_str
                
        if not best_exp:
            logger.error(f"No valid expirations found for {ticker}")
            return None
            
        logger.info(f"Selected expiry {best_exp} (target DTE: {target_dte})")
        
        # 2. Query all strikes for this expiry
        strikes = sorted(list(chain.strikes))
        
        # We need to find the strike with delta closest to target_delta
        # Instead of querying ALL strikes (which is slow and hits IB limits),
        # we estimate the ATM strike, and query a few strikes around it.
        spot_price = await self.md.get_current_price(ticker)
        if spot_price <= 0:
            logger.error("Could not get current spot price.")
            return None
            
        # Filter strikes near spot price (e.g., within 40%)
        nearby_strikes = [s for s in strikes if spot_price * 0.6 <= s <= spot_price * 1.4]
        
        best_contract = None
        best_diff = 999
        best_data = None
        
        logger.info(f"Checking {len(nearby_strikes)} strikes near spot {spot_price:.2f} for {right} options...")
        
        # Fetch data concurrently in small batches to avoid pacing violations
        batch_size = 10
        for i in range(0, len(nearby_strikes), batch_size):
            batch = nearby_strikes[i:i+batch_size]
            tasks = []
            
            for strike in batch:
                opt = Option(ticker, best_exp, strike, right, 'SMART', tradingClass=ticker)
                tasks.append(self.md.get_contract_greeks_and_prices(opt))
                
            results = await asyncio.gather(*tasks)
            
            for strike, data in zip(batch, results):
                delta = abs(data.get("delta", 0.0))
                if delta == 0:
                    continue
                    
                diff = abs(delta - target_delta)
                if diff < best_diff:
                    best_diff = diff
                    opt = Option(ticker, best_exp, strike, right, 'SMART', tradingClass=ticker)
                    best_contract = opt
                    best_data = data
                    best_data["strike"] = strike
                    best_data["expiry"] = best_exp
                    
            await asyncio.sleep(0.5) # Pacing
            
        if best_contract:
            logger.info(f"Selected Strike {best_data['strike']} (Delta: {abs(best_data['delta']):.2f}, target: {target_delta:.2f})")
            best_data["contract"] = best_contract
            return best_data
            
        return None
