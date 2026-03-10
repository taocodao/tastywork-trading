"""
IB Data Provider
================

Implementation of the data provider interface using Interactive Brokers (ib_insync).
Fetches live market data from the IB Gateway via the centralized hub.
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
    Uses the centralized IBMarketDataHub for shared connections.
    """
    
    def __init__(self, host: str = None, port: int = None, client_id: int = None):
        """
        Initialize data provider.
        
        Note: host, port, client_id params are kept for backward compatibility
        but are now managed by the hub.
        """
        # Try to use hub (new pattern)
        try:
            from ib_market_data_hub import get_hub
            self._hub = get_hub()
            self._use_hub = True
            self._connected = True  # Hub manages connection state
            logger.info("IBDataProvider initialized with hub")
        except ImportError:
            # Fallback to direct connection (legacy)
            import config
            self.host = host or config.IB_HOST
            self.port = port or config.IB_PORT
            self.client_id = client_id or config.IB_CLIENT_ID
            self.ib = IB()
            self._use_hub = False
            self._connected = False
            logger.info("IBDataProvider initialized with direct connection (legacy)")
    
    @property
    def ib(self):
        """Get IB client - from hub or direct connection."""
        if self._use_hub:
            return self._hub.data_client
        return self._ib
    
    @ib.setter
    def ib(self, value):
        """Set IB client (for legacy mode)."""
        self._ib = value
        
    def connect(self, timeout: int = 10) -> bool:
        """Connect to IB Gateway with timeout."""
        if self._use_hub:
            return self._hub.connect_data(timeout)
        
        # Legacy direct connection
        try:
            if not self.ib.isConnected():
                logger.info(f"Connecting to IB Gateway at {self.host}:{self.port}...")
                self.ib.RequestTimeout = timeout
                self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=timeout)
                self._connected = True
                self.ib.reqMarketDataType(1)  # 1 = Live data
                logger.info("Connected to IB Data Feed (Live Data)")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IB: {e}")
            self._connected = False
            return False
            
    def disconnect(self):
        """Disconnect from IB."""
        if self._use_hub:
            # Don't disconnect hub - other components may be using it
            logger.debug("IBDataProvider: Not disconnecting hub (shared)")
            return
        
        # Legacy
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

    def get_equity_quote(self, symbol: str) -> Optional[Tuple[float, float, float]]:
        """Get current market quote (bid, ask, mid) for an equity symbol."""
        if not self._connected and not self.connect():
            return None
            
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            
            # Request market data
            ticker = self.ib.reqMktData(contract, '', False, False)
            
            # Wait for data (up to 2 seconds)
            start_time = datetime.now()
            while (ticker.bid <= 0 or ticker.ask <= 0) and (ticker.last != ticker.last or ticker.last is None):
                self.ib.sleep(0.1)
                if (datetime.now() - start_time).total_seconds() > 2:
                    break
            
            bid = ticker.bid if (ticker.bid and ticker.bid > 0) else (ticker.last if ticker.last else 0.0)
            ask = ticker.ask if (ticker.ask and ticker.ask > 0) else (ticker.last if ticker.last else 0.0)
            
            if bid <= 0 and ask <= 0:
                # Try close price if market is closed
                if ticker.close and ticker.close > 0:
                    bid = ask = ticker.close
                else:
                    logger.warning(f"No valid bid/ask or last price for {symbol}")
                    self.ib.cancelMktData(contract)
                    return None
                    
            mid = (bid + ask) / 2.0
            
            self.ib.cancelMktData(contract)
            return (bid, ask, mid)
            
        except Exception as e:
            logger.error(f"Error getting equity quote for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return None

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

    def get_put_chain_for_theta(
        self, 
        symbol: str, 
        expiry: date,
        delta_min: float = 0.25,
        delta_max: float = 0.35
    ) -> List[dict]:
        """
        Get put option chain filtered by delta range with full Greeks for Theta strategy.
        
        For 30-delta puts, we need OTM strikes (typically 5-10% below stock price).
        
        Args:
            symbol: Stock symbol
            expiry: Target expiration date
            delta_min: Minimum delta (default: 0.25)
            delta_max: Maximum delta (default: 0.35)
            
        Returns:
            List of put dicts with: strike, expiration, bid, ask, delta, theta, vega, gamma, iv, volume, open_interest
        """
        if not self._connected and not self.connect():
            return []
            
        try:
            # Get stock price first
            stock_price = self.get_price(symbol)
            if stock_price <= 0:
                logger.warning(f"Could not get stock price for {symbol}")
                return []
            
            # Get underlying contract
            underlying = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(underlying)
            
            # Get option chain parameters
            chains = self.ib.reqSecDefOptParams(underlying.symbol, '', underlying.secType, underlying.conId)
            smart_chains = [c for c in chains if c.exchange == 'SMART']
            
            if not smart_chains:
                logger.warning(f"No SMART option chains found for {symbol}")
                return []
            
            # Find nearest expiry to target
            all_expirations = set()
            for c in smart_chains:
                all_expirations.update(c.expirations)
            
            target_exp_str = expiry.strftime('%Y%m%d')
            if target_exp_str in all_expirations:
                final_exp_str = target_exp_str
            else:
                # Find nearest
                available_dates = [datetime.strptime(d, '%Y%m%d').date() for d in all_expirations]
                nearest_date = min(available_dates, key=lambda d: abs(d - expiry))
                final_exp_str = nearest_date.strftime('%Y%m%d')
            
            selected_chain = next((c for c in smart_chains if final_exp_str in c.expirations), None)
            if not selected_chain:
                return []
            
            # For 30-delta OTM puts, we need strikes BELOW the stock price
            # Typically 5-15% OTM for 30-delta range
            strikes = [k for k in selected_chain.strikes 
                      if 0.85 * stock_price <= k <= 0.98 * stock_price]
            
            if not strikes:
                logger.warning(f"No OTM put strikes found for {symbol}")
                return []
            
            # Build put contracts
            contracts = [Option(symbol, final_exp_str, k, 'P', 'SMART') for k in strikes]
            
            # Qualify contracts
            self.ib.qualifyContracts(*contracts)
            
            # Request market data with Greeks (generic tick 106)
            tickers = [self.ib.reqMktData(c, '106', False, False) for c in contracts]
            
            # Wait for data
            start_wait = datetime.now()
            while (datetime.now() - start_wait).total_seconds() < 3.0:
                self.ib.sleep(0.1)
                ready_count = sum(1 for t in tickers if t.bid > 0 and t.ask > 0)
                if ready_count >= len(tickers) * 0.8:
                    break
            
            # Build result
            result = []
            final_expiry_date = datetime.strptime(final_exp_str, '%Y%m%d').date()
            
            for t in tickers:
                bid = t.bid if t.bid > 0 else (t.last if t.last else 0)
                ask = t.ask if t.ask > 0 else (t.last if t.last else 0)
                
                if bid <= 0 and ask <= 0:
                    continue
                
                # Get Greeks if available
                if t.modelGreeks:
                    delta = abs(t.modelGreeks.delta) if t.modelGreeks.delta else 0.30
                    theta = t.modelGreeks.theta or 0
                    vega = t.modelGreeks.vega or 0
                    gamma = t.modelGreeks.gamma or 0
                    iv = t.modelGreeks.impliedVol or 0.30
                else:
                    # Estimate delta from moneyness
                    moneyness = t.contract.strike / stock_price
                    if moneyness < 0.90:
                        delta = 0.15
                    elif moneyness < 0.95:
                        delta = 0.25
                    elif moneyness < 0.97:
                        delta = 0.30
                    else:
                        delta = 0.40
                    
                    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else bid or ask
                    dte = (final_expiry_date - date.today()).days
                    theta = -mid / max(dte, 1) * 0.7
                    vega = mid * 0.01
                    gamma = 0.015
                    iv = 0.30
                
                result.append({
                    "strike": t.contract.strike,
                    "expiration": final_expiry_date,
                    "bid": bid,
                    "ask": ask,
                    "delta": delta,
                    "theta": theta,
                    "vega": vega,
                    "gamma": gamma,
                    "iv": iv,
                    "volume": t.volume if t.volume else 0,
                    "open_interest": t.putOpenInterest if t.putOpenInterest else 0
                })
            
            # Cancel market data
            for t in tickers:
                try:
                    self.ib.cancelMktData(t.contract)
                except:
                    pass
            
            logger.info(f"{symbol}: Found {len(result)} OTM puts (strikes {min(strikes):.0f}-{max(strikes):.0f})")
            return result
            
        except Exception as e:
            logger.error(f"Error getting put chain for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_call_chain_for_pmcc(
        self, 
        symbol: str, 
        expiry: date,
        delta_min: float = 0.70,
        delta_max: float = 0.90,
        is_leaps: bool = True
    ) -> List[dict]:
        """
        Get call option chain filtered by delta range with full Greeks for PMCC strategy.
        
        Args:
            symbol: Stock symbol
            expiry: Target expiration date
            delta_min: Minimum absolute delta
            delta_max: Maximum absolute delta
            is_leaps: If True, looks for ITM calls (strikes below stock price). If False, looks for OTM calls (strikes above).
            
        Returns:
            List of call dicts with: strike, expiration, bid, ask, delta, theta, vega, gamma, iv, volume, open_interest
        """
        if not self._connected and not self.connect():
            return []
            
        try:
            # Get stock price first
            stock_price = self.get_price(symbol)
            if stock_price <= 0:
                logger.warning(f"Could not get stock price for {symbol}")
                return []
            
            # Get underlying contract
            underlying = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(underlying)
            
            # Get option chain parameters
            chains = self.ib.reqSecDefOptParams(underlying.symbol, '', underlying.secType, underlying.conId)
            smart_chains = [c for c in chains if c.exchange == 'SMART']
            
            if not smart_chains:
                logger.warning(f"No SMART option chains found for {symbol}")
                return []
            
            # Find nearest expiry to target
            all_expirations = set()
            for c in smart_chains:
                all_expirations.update(c.expirations)
            
            target_exp_str = expiry.strftime('%Y%m%d')
            if target_exp_str in all_expirations:
                final_exp_str = target_exp_str
            else:
                from datetime import datetime
                # Find nearest
                available_dates = [datetime.strptime(d, '%Y%m%d').date() for d in all_expirations]
                if not available_dates:
                    return []
                nearest_date = min(available_dates, key=lambda d: abs(d - expiry))
                final_exp_str = nearest_date.strftime('%Y%m%d')
            
            selected_chain = next((c for c in smart_chains if final_exp_str in c.expirations), None)
            if not selected_chain:
                return []
            
            # Filter strikes based on LEAPS (ITM) vs Short Call (OTM)
            if is_leaps:
                # ITM calls have strikes lower than the stock price
                # A 70-90 delta call is deeply ITM (e.g. 10-30% below stock price)
                strikes = [k for k in selected_chain.strikes 
                          if 0.50 * stock_price <= k <= 0.95 * stock_price]
            else:
                # OTM calls have strikes higher than the stock price
                # A 15-35 delta call is slightly OTM (e.g. 5-20% above stock price)
                strikes = [k for k in selected_chain.strikes 
                          if 1.05 * stock_price <= k <= 1.30 * stock_price]
            
            if not strikes:
                logger.warning(f"No appropriate call strikes found for {symbol} (is_leaps={is_leaps})")
                return []
            
            # Build call contracts
            contracts = [Option(symbol, final_exp_str, k, 'C', 'SMART') for k in strikes]
            
            # Qualify contracts
            self.ib.qualifyContracts(*contracts)
            
            # Request market data with Greeks (generic tick 106)
            tickers = [self.ib.reqMktData(c, '106', False, False) for c in contracts]
            
            # Wait for data
            from datetime import datetime
            start_wait = datetime.now()
            while (datetime.now() - start_wait).total_seconds() < 3.0:
                self.ib.sleep(0.1)
                ready_count = sum(1 for t in tickers if t.bid > 0 and t.ask > 0)
                if ready_count >= len(tickers) * 0.8:
                    break
            
            # Build result
            result = []
            final_expiry_date = datetime.strptime(final_exp_str, '%Y%m%d').date()
            
            for t in tickers:
                bid = t.bid if t.bid > 0 else (t.last if t.last else 0)
                ask = t.ask if t.ask > 0 else (t.last if t.last else 0)
                
                if bid <= 0 and ask <= 0:
                    continue
                
                # Get Greeks if available
                if t.modelGreeks:
                    delta = t.modelGreeks.delta if t.modelGreeks.delta else (0.80 if is_leaps else 0.20)
                    theta = t.modelGreeks.theta or 0
                    vega = t.modelGreeks.vega or 0
                    gamma = t.modelGreeks.gamma or 0
                    iv = t.modelGreeks.impliedVol or 0.30
                else:
                    # Estimate delta from moneyness if Greeks are missing
                    moneyness = stock_price / t.contract.strike if is_leaps else t.contract.strike / stock_price
                    if is_leaps:
                        delta = 0.80
                    else:
                        if moneyness < 1.05:
                            delta = 0.40
                        elif moneyness < 1.10:
                            delta = 0.25
                        elif moneyness < 1.15:
                            delta = 0.15
                        else:
                            delta = 0.05
                    
                    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else bid or ask
                    from datetime import date
                    dte = max((final_expiry_date - date.today()).days, 1)
                    theta = -mid / max(dte, 1) * 0.7
                    vega = mid * 0.01
                    gamma = 0.015
                    iv = 0.30
                
                # Double check the delta is within range before adding to result
                if delta_min <= delta <= delta_max:
                    result.append({
                        "strike": t.contract.strike,
                        "expiration": final_expiry_date,
                        "bid": bid,
                        "ask": ask,
                        "delta": delta,
                        "theta": theta,
                        "vega": vega,
                        "gamma": gamma,
                        "iv": iv,
                        "volume": t.volume if t.volume else 0,
                        "open_interest": t.callOpenInterest if t.callOpenInterest else 0
                    })
            
            # Cancel market data
            for t in tickers:
                try:
                    self.ib.cancelMktData(t.contract)
                except:
                    pass
            
            if result:
                logger.info(f"{symbol}: Found {len(result)} PMCC calls (is_leaps={is_leaps}, strikes {min(r['strike'] for r in result):.0f}-{max(r['strike'] for r in result):.0f})")
            else:
                logger.info(f"{symbol}: No PMCC calls found matching delta criteria")
            return result
            
        except Exception as e:
            logger.error(f"Error getting PMCC call chain for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_next_expiry(self, symbol: str, days_out: int = 45) -> Optional[date]:
        """
        Get the next expiration date approximately N days from now.
        
        Args:
            symbol: Stock symbol
            days_out: Number of days ahead (default: 45)
            
        Returns:
            Expiration date or None if not found
        """
        if not self._connected and not self.connect():
            return None
            
        try:
            underlying = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(underlying)
            
            chains = self.ib.reqSecDefOptParams(underlying.symbol, '', underlying.secType, underlying.conId)
            smart_chains = [c for c in chains if c.exchange == 'SMART']
            
            if not smart_chains:
                return None
                
            all_expirations = set()
            for c in smart_chains:
                all_expirations.update(c.expirations)
                
            if not all_expirations:
                return None
            
            target_date = date.today() + timedelta(days=days_out)
            available_dates = [datetime.strptime(d, '%Y%m%d').date() for d in all_expirations]
            
            # Find nearest
            nearest_date = min(available_dates, key=lambda d: abs((d - target_date).days))
            return nearest_date
            
        except Exception as e:
            logger.error(f"Error getting next expiry for {symbol}: {e}")
            return None
