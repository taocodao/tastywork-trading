"""
IB Data Provider
================

Implementation of the data provider interface using Interactive Brokers (ib_insync).
Fetches live market data from the IB Gateway.
"""

import logging
from datetime import date, datetime
from typing import List, Optional, Tuple
from ib_insync import IB, Stock, Option, util

from scanner import OptionQuote

logger = logging.getLogger(__name__)

class IBDataProvider:
    """
    Data provider that fetches real-time data from Interactive Brokers.
    """
    
    def __init__(self, host: str = "34.235.119.67", port: int = 4004, client_id: int = 3000):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self._connected = False
        
    def connect(self, timeout: int = 10) -> bool:
        """Connect to IB Gateway with timeout."""
        try:
            if not self.ib.isConnected():
                logger.info(f"Connecting to IB Gateway at {self.host}:{self.port}...")
                self.ib.RequestTimeout = timeout  # Set timeout
                self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=timeout)
                self._connected = True
                
                # Switch to Delayed Data (Type 3) by default to avoid permission errors
                # 1=Live, 2=Frozen, 3=Delayed, 4=Delayed Frozen
                self.ib.reqMarketDataType(3)
                logger.info("✅ Connected to IB Data Feed (Using Delayed Data)")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to IB: {e}")
            self._connected = False
            return False
            
    def disconnect(self):
        """Disconnect from IB."""
        if self.ib.isConnected():
            self.ib.disconnect()
            self._connected = False
            
    def get_price(self, symbol: str) -> float:
        """Get current market price for underlying."""
        if not self._connected and not self.connect():
            return 0.0
            
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            # Request market data
            ticker = self.ib.reqMktData(contract, '', False, False)
            
            # Wait for data (up to 2 seconds)
            start_time = datetime.now()
            while (ticker.last != ticker.last or ticker.last is None) and ticker.close != ticker.close:
                self.ib.sleep(0.1)
                if (datetime.now() - start_time).total_seconds() > 2:
                    break
            
            # Use last price, or close if market closed, or mid
            price = ticker.last if (ticker.last and ticker.last > 0) else ticker.close
            
            # Fallback to midpoint if no last/close
            if not price or price <= 0:
                 price = (ticker.bid + ticker.ask) / 2 if (ticker.bid > 0 and ticker.ask > 0) else 0.0
                 
            return price
            
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return 0.0

    def get_options(self, symbol: str, expiry: date, option_type: str = "call") -> List[OptionQuote]:
        """
        Get option chain for a specific expiry.
        """
        if not self._connected and not self.connect():
            return []
            
        try:
            # 1. Get underlying price first
            stock_price = self.get_price(symbol)
            if stock_price <= 0:
                logger.warning(f"Could not get stock price for {symbol}, skipping options.")
                return []
                
            # 2. Get option chain parameters
            if symbol in ['SPY', 'QQQ', 'IWM', 'VXX']:
                 exchange = 'SMART'
            else:
                 exchange = 'SMART'

            underlying = Stock(symbol, exchange, 'USD')
            self.ib.qualifyContracts(underlying)
            
            # 3. Request option chain details
            chains = self.ib.reqSecDefOptParams(underlying.symbol, '', underlying.secType, underlying.conId)
            
            # Combine all valid chains (Weeklys + Monthlies)
            smart_chains = [c for c in chains if c.exchange == 'SMART']
            
            if not smart_chains:
                logger.warning(f"No SMART option chains found for {symbol}")
                return []
            
            # Aggregate all expirations
            all_expirations = set()
            for c in smart_chains:
                all_expirations.update(c.expirations)
                
            sorted_expirations = sorted(list(all_expirations))
            
            # 4. Find the closest expiry
            # IB expiries are strings YYYYMMDD
            target_exp_str = expiry.strftime('%Y%m%d')
            
            if target_exp_str in sorted_expirations:
                final_exp_str = target_exp_str
            else:
                # Find nearest
                logger.info(f"Expiry {target_exp_str} not found for {symbol}. finding nearest...")
                
                # Convert all to dates
                try:
                    available_dates = [datetime.strptime(d, '%Y%m%d').date() for d in sorted_expirations]
                    available_dates.sort()
                    
                    if not available_dates:
                        return []
                        
                    # Find nearest
                    nearest_date = min(available_dates, key=lambda d: abs(d - expiry))
                    final_exp_str = nearest_date.strftime('%Y%m%d')
                    logger.info(f"  -> Using nearest expiry: {final_exp_str} (from {len(available_dates)} available)")
                except Exception as e:
                    logger.warning(f"Error parsing expirations: {e}")
                    return []
            
            # Re-select the specific chain that has this expiry
            # Note: Multiple chains might have it (e.g. different trading classes). Just pick one that works.
            selected_chain = next((c for c in smart_chains if final_exp_str in c.expirations), None)
            
            if not selected_chain:
                return []
                
            # 5. Filter strikes near money (e.g., +/- 5%)
            strikes = [k for k in selected_chain.strikes 
                      if 0.95 * stock_price <= k <= 1.05 * stock_price]
            
            if not strikes:
                return []
                
            # 6. Build contracts
            right = 'C' if option_type.lower() == 'call' else 'P'
            contracts = [Option(symbol, final_exp_str, k, right, 'SMART') for k in strikes]
            
            # 7. Qualify contracts (resolve conIds) - Batch request
            self.ib.qualifyContracts(*contracts)
            
            # 8. Request market data for all
            tickers = [self.ib.reqMktData(c, '', False, False) for c in contracts]
            
            # Wait for data
            start_wait = datetime.now()
            while (datetime.now() - start_wait).total_seconds() < 2.5:
                self.ib.sleep(0.1)
                ready_count = sum(1 for t in tickers if t.bid > 0 and t.ask > 0)
                if ready_count >= len(tickers) * 0.9: # 90% ready
                    break
            
            # 9. Build OptionQuote objects
            quotes = []
            final_expiry_date = datetime.strptime(final_exp_str, '%Y%m%d').date()
            
            for t in tickers:
                # Use close/last if bid/ask is missing (e.g. market closed)
                bid = t.bid if t.bid > 0 else (t.last if t.last else 0)
                ask = t.ask if t.ask > 0 else (t.last if t.last else 0)
                
                if bid <= 0 and ask <= 0: continue
                
                # Estimate IV (IB provides it via modelGreeks usually if requested, 
                # but reqMktData default might not have it unless generic ticks added)
                iv = t.modelGreeks.impliedVol if t.modelGreeks else 0.0
                
                quotes.append(OptionQuote(
                    symbol=symbol,
                    strike=t.contract.strike,
                    expiry=final_expiry_date,
                    bid=bid,
                    ask=ask,
                    last=t.last if t.last else (bid + ask)/2,
                    volume=t.volume if t.volume else 0,
                    open_interest=t.callOpenInterest if right == 'C' else t.putOpenInterest, 
                    iv=iv
                ))
                
            return quotes

        except Exception as e:
            logger.error(f"Error fetching options for {symbol}: {e}")
            return []

    def get_atm_iv(self, symbol: str, days_out: int = 30) -> float:
        """
        Get ATM (at-the-money) implied volatility for a symbol.
        
        Args:
            symbol: Stock symbol
            days_out: Days until expiration to look for (default: 30)
            
        Returns:
            ATM IV as decimal (e.g., 0.35 for 35%)
        """
        if not self._connected and not self.connect():
            return 0.0
            
        try:
            # Get stock price first
            stock_price = self.get_price(symbol)
            if stock_price <= 0:
                return 0.0
            
            # Get underlying contract
            underlying = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(underlying)
            
            # Get option chain parameters
            chains = self.ib.reqSecDefOptParams(
                underlying.symbol, '', underlying.secType, underlying.conId
            )
            
            smart_chains = [c for c in chains if c.exchange == 'SMART']
            if not smart_chains:
                return 0.0
            
            # Find nearest expiry ~30 days out
            from datetime import datetime, timedelta
            target_date = datetime.now().date() + timedelta(days=days_out)
            
            all_expirations = set()
            for c in smart_chains:
                all_expirations.update(c.expirations)
            
            if not all_expirations:
                return 0.0
            
            # Find nearest expiry
            available_dates = [datetime.strptime(d, '%Y%m%d').date() for d in all_expirations]
            nearest_date = min(available_dates, key=lambda d: abs((d - target_date).days))
            exp_str = nearest_date.strftime('%Y%m%d')
            
            # Get chain for this expiry
            selected_chain = next((c for c in smart_chains if exp_str in c.expirations), None)
            if not selected_chain:
                return 0.0
            
            # Find ATM strike (closest to stock price)
            strikes = sorted(selected_chain.strikes)
            atm_strike = min(strikes, key=lambda s: abs(s - stock_price))
            
            # Request IV for ATM call
            option = Option(symbol, exp_str, atm_strike, 'C', 'SMART')
            self.ib.qualifyContracts(option)
            
            # Request market data with Greeks (generic tick 106 = impliedVol)
            ticker = self.ib.reqMktData(option, '106', False, False)
            
            # Wait for IV data
            start_time = datetime.now()
            while ticker.modelGreeks is None:
                self.ib.sleep(0.1)
                if (datetime.now() - start_time).total_seconds() > 3:
                    break
            
            if ticker.modelGreeks and ticker.modelGreeks.impliedVol:
                iv = ticker.modelGreeks.impliedVol
                logger.debug(f"{symbol} ATM IV: {iv:.2%} (strike {atm_strike}, exp {nearest_date})")
                return iv
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting ATM IV for {symbol}: {e}")
            return 0.0

    def get_iv_percentile(self, current_iv: float, symbol: str = None) -> float:
        """
        Get IV percentile (rank) - how current IV compares to historical.
        
        For now, returns estimate based on typical IV ranges.
        Future: Could fetch historical IV from IB for accurate calculation.
        
        Args:
            current_iv: Current IV as decimal
            symbol: Stock symbol (for future historical lookup)
            
        Returns:
            IV percentile (0-100)
        """
        # Typical IV ranges for different percentiles
        # These are rough estimates - actual would require historical data
        if current_iv <= 0.15:
            return 10
        elif current_iv <= 0.20:
            return 25
        elif current_iv <= 0.30:
            return 50
        elif current_iv <= 0.40:
            return 70
        elif current_iv <= 0.50:
            return 85
        else:
            return 95

    def get_option_price_by_symbol(self, occ_symbol: str) -> Optional[Tuple[float, float, float]]:
        """
        Get option quote (bid, ask, mid) using OCC symbol.
        
        OCC Symbol Format: SYMBOL[YY][MM][DD][C/P][strike*1000]
        Example: AAPL260220C00150000 = AAPL Call expiring 2026-02-20 at $150 strike
        
        Args:
            occ_symbol: OCC-formatted option symbol
            
        Returns:
            Tuple of (bid, ask, mid) or None if not found
        """
        if not self._connected and not self.connect():
            return None
            
        try:
            # Parse OCC symbol
            # Format: SYMBOL[6 digits date][C/P][8 digits strike]
            # Example: AAPL260220C00150000
            
            # Find where the date starts (after the underlying symbol)
            # Date is always 6 digits, followed by C/P, then 8 digit strike
            if len(occ_symbol) < 15:  # Minimum length check
                logger.error(f"Invalid OCC symbol length: {occ_symbol}")
                return None
            
            # Extract parts - work backwards from the end
            # Last 8 chars = strike (padded)
            strike_str = occ_symbol[-8:]
            strike = float(strike_str) / 1000.0
            
            # Before that, 1 char = option type (C/P)
            option_type = occ_symbol[-9]
            right = 'C' if option_type == 'C' else 'P'
            
            # Before that, 6 chars = date (YYMMDD)
            date_str = occ_symbol[-15:-9]
            # Convert YYMMDD to YYYYMMDD
            expiry_str = f"20{date_str}"
            
            # Everything before is the underlying symbol
            symbol = occ_symbol[:-15]
            
            logger.debug(f"Parsed OCC {occ_symbol}: {symbol} {expiry_str} {right} {strike}")
            
            # Build IB contract
            contract = Option(symbol, expiry_str, strike, right, 'SMART')
            
            # Qualify contract
            qualified = self.ib.qualifyContracts(contract)
            if not qualified:
                logger.warning(f"Could not qualify contract: {occ_symbol}")
                return None
                
            contract = qualified[0]
            
            # Request market data
            ticker = self.ib.reqMktData(contract, '', False, False)
            
            # Wait for data
            start_wait = datetime.now()
            while (datetime.now() - start_wait).total_seconds() < 2.0:
                self.ib.sleep(0.1)
                if ticker.bid > 0 and ticker.ask > 0:
                    break
            
            # Get prices
            bid = ticker.bid if ticker.bid > 0 else (ticker.last if ticker.last else 0)
            ask = ticker.ask if ticker.ask > 0 else (ticker.last if ticker.last else 0)
            
            if bid <= 0 and ask <= 0:
                logger.warning(f"No valid prices for {occ_symbol}")
                return None
            
            mid = (bid + ask) / 2.0
            
            # Cancel market data to clean up
            self.ib.cancelMktData(contract)
            
            return (bid, ask, mid)
            
        except Exception as e:
            logger.error(f"Error getting option price for {occ_symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None
