"""
Tastytrade Client - API Integration
====================================

Wraps the tastytrade Python SDK for calendar spread trading.
Provides session management, options chain fetching, order placement, and position tracking.
"""

import os
import logging
import time as time_module
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import date, datetime, timedelta
from dataclasses import dataclass

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class OptionData:
    """Option quote data."""
    symbol: str
    streamer_symbol: str
    strike: Decimal
    expiry: date
    option_type: str  # 'C' or 'P'
    bid: float
    ask: float
    volume: int
    open_interest: int
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    
    @property
    def mid(self) -> float:
        """Mid-point price."""
        return (self.bid + self.ask) / 2
    
    @property
    def spread(self) -> float:
        """Bid-ask spread."""
        return self.ask - self.bid


class TastytradeClient:
    """
    Tastytrade API client for calendar spread trading.
    
    Handles authentication, options chain fetching, order placement,
    and position monitoring via the tastytrade Python SDK.
    """
    
    def __init__(
        self,
        username: str = None,
        password: str = None,
        use_sandbox: bool = None,
        refresh_token: str = None,
        client_secret: str = None
    ):
        """
        Initialize client.
        
        Args:
            username: Tastytrade username (default: from env TASTYTRADE_USERNAME)
            password: Tastytrade password (default: from env TASTYTRADE_PASSWORD)
            use_sandbox: Use sandbox/paper trading (default: from env TASTYTRADE_USE_SANDBOX)
            refresh_token: Tastytrade refresh token (default: from env TASTYTRADE_REFRESH_TOKEN)
            client_secret: Tastytrade client secret (default: from env TASTYTRADE_CLIENT_SECRET)
        """
        self.username = username or os.getenv('TASTYTRADE_USERNAME', '')
        self.password = password or os.getenv('TASTYTRADE_PASSWORD', '')
        self.refresh_token = refresh_token or os.getenv('TASTYTRADE_REFRESH_TOKEN', '')
        self.client_secret = client_secret or os.getenv('TASTYTRADE_CLIENT_SECRET', '')
        self.use_sandbox = use_sandbox if use_sandbox is not None else \
            os.getenv('TASTYTRADE_USE_SANDBOX', 'true').lower() == 'true'
        
        self._session = None
        self._account = None
        self._streamer = None
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to Tastytrade."""
        return self._session is not None
    
    def connect(self) -> bool:
        """
        Connect to Tastytrade API.
        
        Returns:
            True if connection successful
        """
        try:
            from tastytrade import Session
            from tastytrade.session import Session as TastySession
            import httpx
            
            # Set longer timeout for initial connection (default is 5s)
            os.environ.setdefault('HTTPX_TIMEOUT', '15')
            
            logger.info(f"Connecting to Tastytrade {'(sandbox)' if self.use_sandbox else '(live)'}...")
            
            # Try OAuth2 with client_secret + refresh_token (preferred method)
            if self.client_secret and self.refresh_token:
                logger.info(f"Authenticating with OAuth2 (client_secret + refresh_token)...")
                try:
                    # Correct syntax: Session(client_secret, refresh_token)
                    self._session = Session(self.client_secret, self.refresh_token)
                    logger.info("OAuth2 authentication successful!")
                except Exception as e:
                    logger.warning(f"OAuth2 auth failed: {e}")
                    # Fallback to username/password if available
                    if self.username and self.password:
                        logger.info("Trying username/password fallback...")
                        self._session = Session(self.username, self.password, is_test=self.use_sandbox)
                    else:
                        raise ValueError(f"OAuth2 failed ({e}) and no username/password provided.")
            
            elif self.username and self.password:
                self._session = Session(
                    self.username,
                    self.password,
                    is_test=self.use_sandbox
                )
            else:
                raise ValueError(
                    "Tastytrade credentials not set. "
                    "Set TASTYTRADE_REFRESH_TOKEN or TASTYTRADE_USERNAME/PASSWORD."
                )
            
            logger.info("Successfully connected to Tastytrade")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Tastytrade: {e}")
            raise

    
    def disconnect(self):
        """Disconnect from Tastytrade."""
        if self._streamer:
            # Streamer cleanup handled by context manager
            self._streamer = None
        self._session = None
        self._account = None
        logger.info("Disconnected from Tastytrade")
    
    def get_account(self):
        """
        Get the primary trading account.
        
        Returns:
            Account object
        """
        if not self.is_connected:
            raise RuntimeError("Not connected. Call connect() first.")
        
        if self._account is None:
            from tastytrade import Account
            accounts = Account.get(self._session)
            if not accounts:
                raise RuntimeError("No accounts found for this user")
            self._account = accounts[0]
            logger.info(f"Using account: {self._account.account_number}")
        
        return self._account
    
    def get_account_balance(self) -> Dict[str, float]:
        """
        Get account balance information.
        
        Returns:
            Dict with buying_power, net_liquidating_value, cash_balance
        """
        account = self.get_account()
        balances = account.get_balances(self._session)
        
        return {
            'buying_power': float(balances.derivative_buying_power or 0),
            'net_liquidating_value': float(balances.net_liquidating_value or 0),
            'cash_balance': float(balances.cash_balance or 0),
            'equity_buying_power': float(balances.equity_buying_power or 0),
        }
    
    def get_stock_price(self, symbol: str) -> float:
        """
        Get the current stock price.
        
        Uses IB Gateway for reliable real-time pricing.
        
        Args:
            symbol: Stock symbol (e.g., 'SPY')
            
        Returns:
            Current price as float
        """
        try:
            from ib_data_provider import IBDataProvider
            ib_data = IBDataProvider()
            price = ib_data.get_price(symbol)
            if price > 0:
                logger.info(f"Stock price for {symbol}: ${price:.2f}")
                return price
        except Exception as e:
            logger.warning(f"IB data provider failed for {symbol}: {e}")
        
        # Fallback: try tastytrade API
        try:
            from tastytrade.instruments import Equity
            equity = Equity.get(self._session, symbol)
            # Try different attribute names that might exist
            for attr in ['mark', 'last', 'close', 'bid']:
                if hasattr(equity, attr):
                    price = getattr(equity, attr)
                    if price and float(price) > 0:
                        logger.info(f"Stock price for {symbol} from tastytrade: ${float(price):.2f}")
                        return float(price)
        except Exception as e:
            logger.error(f"Could not get price for {symbol}: {e}")
        
        logger.error(f"All price sources failed for {symbol}")
        return 0.0
    
    def get_live_option_quote(self, option_symbol: str) -> Optional[Tuple[float, float, float]]:
        """
        Get live quote (bid, ask, mid) for an option.
        
        Fetches real-time prices from IB data provider.
        Note: DXLinkStreamer integration requires async context which causes
        recursion issues when called from sync methods. Using IB as primary source.
        
        Args:
            option_symbol: Option OCC symbol (e.g., 'SPY  250213P00575000')
            
        Returns:
            Tuple of (bid, ask, mid) or None if unavailable
        """
        if not self.is_connected:
            logger.warning("Not connected, cannot fetch live quote")
            return None
        
        # Use IB data provider for live quotes
        try:
            from ib_data_provider import IBDataProvider
            ib_data = IBDataProvider()
            ib_quote = ib_data.get_option_price_by_symbol(option_symbol)
            if ib_quote and ib_quote[0] > 0:
                logger.info(f"Live quote for {option_symbol}: bid=${ib_quote[0]:.2f} ask=${ib_quote[1]:.2f}")
                return ib_quote
        except Exception as e:
            logger.warning(f"IB data provider failed for {option_symbol}: {e}")
        
        return None
    
    
    def get_option_chain(
        self,
        symbol: str,
        expiry_filter: Optional[date] = None
    ) -> Dict[date, List[OptionData]]:
        """
        Get options chain for a symbol.
        
        Args:
            symbol: Underlying symbol (e.g., 'SPY')
            expiry_filter: Optional specific expiration date to filter
            
        Returns:
            Dict mapping expiry dates to lists of OptionData
        """
        if not self.is_connected:
            raise RuntimeError("Not connected. Call connect() first.")
        
        from tastytrade.instruments import get_option_chain, NestedOptionChain
        
        chain = get_option_chain(self._session, symbol)
        
        result: Dict[date, List[OptionData]] = {}
        
        for expiry, options in chain.items():
            # Filter by expiry if specified
            if expiry_filter and expiry != expiry_filter:
                continue
            
            option_list = []
            for option in options:
                try:
                    option_data = OptionData(
                        symbol=option.symbol,
                        streamer_symbol=option.streamer_symbol,
                        strike=option.strike_price,
                        expiry=expiry,
                        option_type='C' if option.option_type.value == 'C' else 'P',
                        bid=float(option.bid or 0),
                        ask=float(option.ask or 0),
                        volume=int(option.volume or 0),
                        open_interest=int(option.open_interest or 0),
                    )
                    option_list.append(option_data)
                except Exception as e:
                    logger.debug(f"Skipping option {option.symbol}: {e}")
                    continue
            
            if option_list:
                result[expiry] = option_list
        
        return result
    
    def get_options_for_expiry(
        self,
        symbol: str,
        expiry: date,
        option_type: str = 'C'
    ) -> List[OptionData]:
        """
        Get options for a specific expiration.
        
        Args:
            symbol: Underlying symbol
            expiry: Expiration date
            option_type: 'C' for calls, 'P' for puts
            
        Returns:
            List of OptionData for that expiration
        """
        chain = self.get_option_chain(symbol, expiry_filter=expiry)
        
        if expiry not in chain:
            return []
        
        return [opt for opt in chain[expiry] if opt.option_type == option_type]
    
    def find_atm_option(
        self,
        symbol: str,
        expiry: date,
        stock_price: float,
        option_type: str = 'C'
    ) -> Optional[OptionData]:
        """
        Find the at-the-money option for a given expiration.
        
        Args:
            symbol: Underlying symbol
            expiry: Expiration date
            stock_price: Current stock price
            option_type: 'C' for calls, 'P' for puts
            
        Returns:
            ATM OptionData or None if not found
        """
        options = self.get_options_for_expiry(symbol, expiry, option_type)
        
        if not options:
            return None
        
        # Find closest strike to stock price
        return min(options, key=lambda o: abs(float(o.strike) - stock_price))
    
    def get_next_expiry(self, days_out: int = 1) -> date:
        """
        Get the next expiration date approximately N days from now.
        
        Args:
            days_out: Number of days ahead
            
        Returns:
            Expiration date
        """
        from tastytrade.utils import get_tasty_monthly
        
        target = date.today() + timedelta(days=days_out)
        
        # For 0-7 day expirations, we need weekly/daily options
        # Try to find the exact target date first
        return target
    
    def build_calendar_spread_order(
        self,
        short_option: OptionData,
        long_option: OptionData,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ):
        """
        Build a calendar spread order (same strike, different expirations).
        
        Args:
            short_option: Near-term option to SELL (same strike as long)
            long_option: Longer-term option to BUY (same strike as short)
            quantity: Number of contracts
            limit_price: Optional limit price (negative for debit)
            
        Returns:
            NewOrder object ready for submission
            
        Note:
            - Calendar spread: SAME strike, different expiration (neutral play)
            - Diagonal spread: DIFFERENT strikes + expirations (directional play)
            - Use build_diagonal_spread_order() for different strikes
        """
        from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
        from tastytrade.instruments import Option
        
        # Get option instruments for building legs
        short_instrument = Option.get(self._session, short_option.symbol)
        long_instrument = Option.get(self._session, long_option.symbol)
        
        # Build legs
        short_leg = short_instrument.build_leg(
            Decimal(str(quantity)),
            OrderAction.SELL_TO_OPEN
        )
        long_leg = long_instrument.build_leg(
            Decimal(str(quantity)),
            OrderAction.BUY_TO_OPEN
        )
        
        # Calculate price if not provided - use LIVE quotes for better fills
        if limit_price is None:
            # Try live quotes first
            short_quote = self.get_live_option_quote(short_option.streamer_symbol)
            long_quote = self.get_live_option_quote(long_option.streamer_symbol)
            
            if short_quote and long_quote and short_quote[0] > 0 and long_quote[1] > 0:
                # Net debit = long ask - short bid (what we pay)
                limit_price = -(long_quote[1] - short_quote[0])
                logger.info(f"Calendar spread LIVE: sell @ ${short_quote[0]:.2f}, buy @ ${long_quote[1]:.2f}, net ${limit_price:.2f}")
            else:
                # Fallback to stale data
                limit_price = -(long_option.ask - short_option.bid)
                logger.warning(f"Calendar spread using stale prices: net ${limit_price:.2f}")
        
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[short_leg, long_leg],
            price=Decimal(str(limit_price))
        )
        
        return order
    
    def build_diagonal_spread_order(
        self,
        short_option: OptionData,
        long_option: OptionData,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ):
        """
        Build a diagonal spread order.
        
        A diagonal spread is similar to a calendar spread but with different strikes.
        Combines directional bias (different strikes) with time decay (different expirations).
        
        Args:
            short_option: Near-term option to SELL (typically different strike)
            long_option: Longer-term option to BUY (typically different strike)
            quantity: Number of contracts
            limit_price: Optional limit price (negative for debit)
            
        Returns:
            NewOrder object ready for submission
            
        Note:
            - True calendar spread: same strike, different expiration
            - Diagonal spread: different strikes AND different expirations (PMCC)
        """
        # Diagonal spreads use the same mechanics as calendar spreads
        return self.build_calendar_spread_order(
            short_option=short_option,
            long_option=long_option,
            quantity=quantity,
            limit_price=limit_price
        )
    
    
    def build_calendar_spread_close_order(
        self,
        short_option_symbol: str,
        long_option_symbol: str,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ):
        """
        Build a closing order for a calendar spread position.
        
        This reverses the original position:
        - BUY TO CLOSE the short option (front month)
        - SELL TO CLOSE the long option (back month)
        
        Args:
            short_option_symbol: OCC symbol of the short option to close
            long_option_symbol: OCC symbol of the long option to close
            quantity: Number of contracts to close
            limit_price: Optional limit price (positive for credit)
            
        Returns:
            NewOrder object ready for submission
        """
        from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
        from tastytrade.instruments import Option
        
        # Get option instruments
        short_instrument = Option.get(self._session, short_option_symbol)
        long_instrument = Option.get(self._session, long_option_symbol)
        
        # Build closing legs (reverse of opening)
        short_close_leg = short_instrument.build_leg(
            Decimal(str(quantity)),
            OrderAction.BUY_TO_CLOSE  # Was SELL_TO_OPEN
        )
        long_close_leg = long_instrument.build_leg(
            Decimal(str(quantity)),
            OrderAction.SELL_TO_CLOSE  # Was BUY_TO_OPEN
        )
        
        # For closing, we typically receive a credit
        # If no price provided, get current market prices
        if limit_price is None:
            # Fetch current quotes
            try:
                from tastytrade.api import MarketData
                market = MarketData(self._session)
                
                # Get quotes for both options
                quotes = market.get_quotes(self._session, [short_option_symbol, long_option_symbol])
                
                short_quote = quotes.get(short_option_symbol)
                long_quote = quotes.get(long_option_symbol)
                
                if short_quote and long_quote:
                    # Net credit = long bid - short ask (what we receive)
                    limit_price = float(long_quote.bid) - float(short_quote.ask)
            except Exception as e:
                logger.warning(f"Could not fetch live quotes for close order: {e}")
                # Will need to be provided by caller
        
        order_params = {
            'time_in_force': OrderTimeInForce.DAY,
            'order_type': OrderType.LIMIT if limit_price else OrderType.MARKET,
            'legs': [short_close_leg, long_close_leg],
        }
        
        if limit_price:
            order_params['price'] = Decimal(str(limit_price))
        
        order = NewOrder(**order_params)
        
        return order
    
    def close_calendar_spread_position(
        self,
        short_option_symbol: str,
        long_option_symbol: str,
        quantity: int = 1,
        limit_price: Optional[float] = None,
        dry_run: bool = False
    ):
        """
        Close a calendar spread position by placing a closing order.
        
        Args:
            short_option_symbol: OCC symbol of the short option
            long_option_symbol: OCC symbol of the long option
            quantity: Number of contracts
            limit_price: Optional limit price
            dry_run: If True, validate only without placing
            
        Returns:
            Order response from Tastytrade
        """
        order = self.build_calendar_spread_close_order(
            short_option_symbol=short_option_symbol,
            long_option_symbol=long_option_symbol,
            quantity=quantity,
            limit_price=limit_price
        )
        
        return self.place_order(order, dry_run=dry_run)
    
    def build_equity_order(
        self,
        symbol: str,
        quantity: int,
        action: str,
        limit_price: Optional[float] = None
    ):
        """
        Build a standard equity (stock/ETF) order.
        
        Args:
            symbol: Ticker symbol (e.g. 'TQQQ')
            quantity: Number of shares
            action: 'BUY' or 'SELL'
            limit_price: Optional limit price. If None, places a MARKET order.
            
        Returns:
            NewOrder object ready for submission
        """
        from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
        from tastytrade.instruments import Equity
        
        # Get equity instrument
        instrument = Equity.get(self._session, symbol)
        
        # Parse action
        action_upper = action.upper()
        if action_upper == 'BUY':
            order_action = OrderAction.BUY
        elif action_upper == 'SELL':
            order_action = OrderAction.SELL
        else:
            raise ValueError(f"Invalid equity action: {action}")
            
        # Build leg
        leg = instrument.build_leg(
            Decimal(str(quantity)),
            order_action
        )
        
        order_params = {
            'time_in_force': OrderTimeInForce.DAY,
            'order_type': OrderType.LIMIT if limit_price else OrderType.MARKET,
            'legs': [leg],
        }
        
        if limit_price:
            order_params['price'] = Decimal(str(limit_price))
            
        order = NewOrder(**order_params)
        
        return order
        
    def build_vertical_spread_order(
        self,
        symbol: str,
        buy_strike: float,
        sell_strike: float,
        expiry: date,
        option_type: str = 'C',
        quantity: int = 1,
        limit_price: Optional[float] = None
    ):
        """
        Build a vertical spread order.
        
        Args:
            symbol: Underlying symbol (e.g., 'SPY')
            buy_strike: Strike price to BUY (long leg)
            sell_strike: Strike price to SELL (short leg)
            expiry: Expiration date
            option_type: 'C' for calls, 'P' for puts
            quantity: Number of contracts
            limit_price: Optional limit price (negative for debit spreads)
            
        Returns:
            NewOrder object ready for submission
            
        Examples:
            Bull call spread (debit): buy lower strike call, sell higher strike call
            Bear put spread (debit): buy higher strike put, sell lower strike put
            Bull put spread (credit): sell higher strike put, buy lower strike put
            Bear call spread (credit): sell lower strike call, buy higher strike call
        """
        from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
        from tastytrade.instruments import Option
        
        if not self.is_connected:
            raise RuntimeError("Not connected. Call connect() first.")
        
        # Find the options at the specified strikes
        buy_option = self.find_option_at_strike(symbol, expiry, buy_strike, option_type)
        sell_option = self.find_option_at_strike(symbol, expiry, sell_strike, option_type)
        
        if not buy_option or not sell_option:
            raise ValueError(f"Could not find options at strikes {buy_strike}/{sell_strike} for {symbol} exp {expiry}")
        
        # Get option instruments
        buy_instrument = Option.get(self._session, buy_option.symbol)
        sell_instrument = Option.get(self._session, sell_option.symbol)
        
        # Build legs
        buy_leg = buy_instrument.build_leg(
            Decimal(str(quantity)),
            OrderAction.BUY_TO_OPEN
        )
        sell_leg = sell_instrument.build_leg(
            Decimal(str(quantity)),
            OrderAction.SELL_TO_OPEN
        )
        
        # Calculate price if not provided - use LIVE quotes for better fills
        if limit_price is None:
            # Try live quotes first
            buy_quote = self.get_live_option_quote(buy_option.streamer_symbol)
            sell_quote = self.get_live_option_quote(sell_option.streamer_symbol)
            
            if buy_quote and sell_quote and buy_quote[1] > 0 and sell_quote[0] > 0:
                # Use live mid prices for vertical spreads
                buy_mid = buy_quote[2]  # live mid
                sell_mid = sell_quote[2]  # live mid
                limit_price = -(buy_mid - sell_mid)  # Negative = debit
                logger.info(f"Vertical spread LIVE: buy mid ${buy_mid:.2f}, sell mid ${sell_mid:.2f}, net ${limit_price:.2f}")
            else:
                # Fallback to stale data
                buy_mid = buy_option.mid
                sell_mid = sell_option.mid
                limit_price = -(buy_mid - sell_mid)  # Negative = debit
                logger.warning(f"Vertical spread using stale mids: net ${limit_price:.2f}")
        
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[buy_leg, sell_leg],
            price=Decimal(str(round(limit_price, 2)))
        )
        
        logger.info(f"Built vertical spread: {symbol} {buy_strike}/{sell_strike} {option_type} x{quantity}")
        
        return order
    
    def find_option_at_strike(
        self,
        symbol: str,
        expiry: date,
        strike: float,
        option_type: str = 'C'
    ) -> Optional[OptionData]:
        """
        Find option at a specific strike.
        
        Args:
            symbol: Underlying symbol
            expiry: Expiration date
            strike: Target strike price
            option_type: 'C' for calls, 'P' for puts
            
        Returns:
            OptionData or None if not found
        """
        options = self.get_options_for_expiry(symbol, expiry, option_type)
        
        if not options:
            return None
        
        # Find exact strike match or closest
        for opt in options:
            if abs(float(opt.strike) - strike) < 0.01:
                return opt
        
        # If no exact match, find closest
        return min(options, key=lambda o: abs(float(o.strike) - strike))
    
    def build_cash_secured_put_order(
        self,
        symbol: str,
        strike: float,
        expiry: date,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ):
        """
        Build a cash-secured put (SELL TO OPEN) order for Theta strategy.
        
        Args:
            symbol: Underlying symbol (e.g., 'IWM')
            strike: Put strike price
            expiry: Expiration date
            quantity: Number of contracts to sell
            limit_price: Optional limit price (positive = credit received)
            
        Returns:
            NewOrder object ready for submission
        """
        from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
        from tastytrade.instruments import Option
        
        if not self.is_connected:
            raise RuntimeError("Not connected. Call connect() first.")
        
        # Find the put option at the specified strike
        put_option = self.find_option_at_strike(symbol, expiry, strike, option_type='P')
        
        if not put_option:
            raise ValueError(f"Could not find put option at strike {strike} for {symbol} exp {expiry}")
        
        # Get option instrument
        put_instrument = Option.get(self._session, put_option.symbol)
        
        # Build SELL TO OPEN leg
        put_leg = put_instrument.build_leg(
            Decimal(str(quantity)),
            OrderAction.SELL_TO_OPEN
        )
        
        # Calculate limit price if not provided - use LIVE quote for better fills
        if limit_price is None:
            # Try to get live quote first
            live_quote = self.get_live_option_quote(put_option.streamer_symbol)
            if live_quote and live_quote[0] > 0:
                limit_price = live_quote[0]  # bid (credit we receive)
                logger.info(f"Using LIVE bid: ${limit_price:.2f}")
            else:
                # Fallback to stale REST API data
                limit_price = put_option.bid
                logger.warning(f"Using stale bid (no live quote): ${limit_price:.2f}")
        
        order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=OrderType.LIMIT,
            legs=[put_leg],
            price=Decimal(str(round(limit_price, 2)))  # Positive = credit
        )
        
        logger.info(f"Built cash-secured put: SELL {symbol} {strike}P x{quantity} @ ${limit_price:.2f}")
        
        return order
    
    def build_close_put_order(
        self,
        put_option_symbol: str,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ):
        """
        Build a BUY TO CLOSE order for exiting a short put position.
        
        Args:
            put_option_symbol: OCC symbol of the put option
            quantity: Number of contracts to close
            limit_price: Optional limit price (negative = debit paid)
            
        Returns:
            NewOrder object ready for submission
        """
        from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
        from tastytrade.instruments import Option
        
        if not self.is_connected:
            raise RuntimeError("Not connected. Call connect() first.")
        
        # Get option instrument
        put_instrument = Option.get(self._session, put_option_symbol)
        
        # Build BUY TO CLOSE leg
        put_leg = put_instrument.build_leg(
            Decimal(str(quantity)),
            OrderAction.BUY_TO_CLOSE
        )
        
        if not limit_price:
            raise ValueError("limit_price is required — Tastytrade rejects market orders for options")
        
        order_params = {
            'time_in_force': OrderTimeInForce.DAY,
            'order_type': OrderType.LIMIT,
            'legs': [put_leg],
            'price': Decimal(str(round(-abs(limit_price), 2))),  # Negative = debit
        }
        
        order = NewOrder(**order_params)
        logger.info(f"Built close order: BUY TO CLOSE {put_option_symbol} x{quantity} @ ${limit_price:.2f}")
        
        return order
    
    def execute_theta_entry(
        self,
        symbol: str,
        strike: float,
        expiry: date,
        quantity: int = 1,
        limit_price: Optional[float] = None,
        dry_run: bool = True
    ):
        """
        Execute a Theta strategy ENTRY (sell cash-secured put).
        
        Args:
            symbol: Underlying symbol
            strike: Put strike price
            expiry: Expiration date
            quantity: Number of contracts
            limit_price: Optional limit price
            dry_run: If True, validate only
            
        Returns:
            Order response
        """
        order = self.build_cash_secured_put_order(
            symbol=symbol,
            strike=strike,
            expiry=expiry,
            quantity=quantity,
            limit_price=limit_price
        )
        return self.place_order(order, dry_run=dry_run)
    
    def execute_theta_exit(
        self,
        put_option_symbol: str,
        quantity: int = 1,
        limit_price: Optional[float] = None,
        dry_run: bool = True
    ):
        """
        Execute a Theta strategy EXIT (buy to close put).
        
        Args:
            put_option_symbol: OCC symbol of the put
            quantity: Number of contracts
            limit_price: Optional limit price
            dry_run: If True, validate only
            
        Returns:
            Order response
        """
        order = self.build_close_put_order(
            put_option_symbol=put_option_symbol,
            quantity=quantity,
            limit_price=limit_price
        )
        return self.place_order(order, dry_run=dry_run)
    
    def place_order(self, order, dry_run: bool = True):
        """
        Place an order.
        
        Args:
            order: NewOrder object
            dry_run: If True, just validate without placing
            
        Returns:
            PlacedOrderResponse
        """
        account = self.get_account()
        
        logger.info(f"{'Validating' if dry_run else 'Placing'} order...")
        response = account.place_order(self._session, order, dry_run=dry_run)
        
        if not dry_run:
            logger.info(f"Order placed: {response.fee_calculation.order.id}")
        
        return response
    
    def get_positions(self) -> List:
        """
        Get all open positions.
        
        Returns:
            List of CurrentPosition objects
        """
        account = self.get_account()
        return account.get_positions(self._session)
    
    def get_option_positions(self) -> List:
        """
        Get only option positions.
        
        Returns:
            List of option CurrentPosition objects
        """
        from tastytrade import InstrumentType
        
        positions = self.get_positions()
        return [p for p in positions if p.instrument_type == InstrumentType.EQUITY_OPTION]
    
    def get_equity_positions(self) -> Dict[str, int]:
        """
        Get only equity/ETF positions mapped to their symbol and integer share count.
        Used by the Target Allocation Sizer Engine.
        
        Returns:
            Dict mapping symbol string to integer share quantity. e.g. {"TQQQ": 100, "SGOV": 50}
        """
        from tastytrade import InstrumentType
        
        positions = self.get_positions()
        equity_dict = {}
        
        for p in positions:
            if p.instrument_type == InstrumentType.EQUITY:
                # Tastytrade tracks quantity as a string representation of a Decimal
                qty_val = float(p.quantity) if hasattr(p, 'quantity') else 0
                
                # Check directional bias (Long vs Short)
                if hasattr(p, 'quantity_direction') and p.quantity_direction.value == 'Short':
                    qty_val = -qty_val
                    
                equity_dict[p.symbol] = int(qty_val)
                
        return equity_dict

    def build_equity_order(
        self,
        symbol: str,
        quantity: int,
        action: str,
        limit_price: Optional[float] = None
    ):
        """
        Build an equity (stock/ETF) limit or market order.
        
        Args:
            symbol: Ticker symbol (e.g. 'TQQQ')
            quantity: Number of shares (integer)
            action: 'BUY' or 'SELL'
            limit_price: Optional limit price. If None, sends a Market order.
            
        Returns:
            NewOrder object ready for submission
        """
        from tastytrade.order import NewOrder, OrderAction, OrderTimeInForce, OrderType
        from tastytrade.instruments import Equity
        
        if not self.is_connected:
            raise RuntimeError("Not connected. Call connect() first.")
        
        instrument = Equity.get(self._session, symbol)
        
        order_action = OrderAction.BUY if action.upper() == 'BUY' else OrderAction.SELL
        
        leg = instrument.build_leg(
            Decimal(str(quantity)),
            order_action
        )
        
        order_params = {
            'time_in_force': OrderTimeInForce.DAY,
            'legs': [leg]
        }
        
        if limit_price is not None:
            order_params['order_type'] = OrderType.LIMIT
            order_params['price'] = Decimal(str(round(limit_price, 2)))
        else:
            order_params['order_type'] = OrderType.MARKET
            
        order = NewOrder(**order_params)
        logger.info(f"Built equity order: {action} {quantity} {symbol} @ {'Market' if limit_price is None else f'${limit_price:.2f}'}")
        
        return order

    
    def get_orders(self, status: str = None) -> List:
        """
        Get orders.
        
        Args:
            status: Optional filter ('Live', 'Filled', etc.)
            
        Returns:
            List of orders
        """
        account = self.get_account()
        orders = account.get_orders(self._session)
        
        if status:
            orders = [o for o in orders if o.status.value == status]
        
        return orders
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancelled successfully
        """
        account = self.get_account()
        
        try:
            account.cancel_order(self._session, order_id)
            logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def replace_order(self, order_id: str, new_price: float) -> bool:
        """
        Replace an existing order with a new limit price.
        
        Only the price can be modified; to change quantity or legs,
        cancel and re-submit a new order.
        
        Args:
            order_id: ID of the order to modify
            new_price: New limit price (positive = credit, negative = debit)
            
        Returns:
            True if replacement was accepted
        """
        account = self.get_account()
        
        try:
            # Get the existing order
            orders = account.get_orders(self._session)
            target = None
            for o in orders:
                if str(o.id) == str(order_id):
                    target = o
                    break
            
            if not target:
                logger.error(f"Order {order_id} not found for replacement")
                return False
            
            # Update the price on the order object
            target.price = Decimal(str(round(new_price, 2)))
            
            # Submit replacement
            account.replace_order(self._session, order_id, target)
            logger.info(f"Order {order_id} price replaced to ${new_price:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to replace order {order_id}: {e}")
            return False
    
    def monitor_and_fill(
        self,
        order_id: str,
        initial_price: float,
        is_credit: bool = True,
        monitor_interval: int = None,
        price_adjust_interval: int = None,
        price_step: float = None,
        max_wait: int = None,
        max_adjustments: int = None,
    ) -> Dict[str, Any]:
        """
        Monitor an order until filled, adjusting the limit price periodically.
        
        For CREDIT orders (selling puts): reduces the credit demanded.
        For DEBIT orders (buying to close): increases the debit offered.
        
        If the order is still unfilled after all adjustments + max_wait,
        it is left to expire (no market fallback per user preference).
        
        Args:
            order_id: Order ID to monitor
            initial_price: The original limit price
            is_credit: True for STO credit orders, False for BTC debit orders
            monitor_interval: Seconds between polls (default from config)
            price_adjust_interval: Seconds before each adjustment (default from config)
            price_step: Dollar amount to adjust per step (default from config)
            max_wait: Max total seconds to wait (default from config)
            max_adjustments: Max price adjustments (default from config)
            
        Returns:
            Dict with keys:
                - filled: bool
                - fill_price: float or None
                - adjustments_made: int
                - final_status: str
                - order_id: str
        """
        from config import (
            ORDER_MONITOR_INTERVAL, ORDER_PRICE_ADJUST_INTERVAL,
            ORDER_PRICE_STEP, ORDER_MAX_WAIT, ORDER_MAX_PRICE_ADJUSTMENTS,
        )
        
        monitor_interval = monitor_interval or ORDER_MONITOR_INTERVAL
        price_adjust_interval = price_adjust_interval or ORDER_PRICE_ADJUST_INTERVAL
        price_step = price_step or ORDER_PRICE_STEP
        max_wait = max_wait or ORDER_MAX_WAIT
        max_adjustments = max_adjustments or ORDER_MAX_PRICE_ADJUSTMENTS
        
        start_time = time_module.time()
        current_price = initial_price
        adjustments_made = 0
        last_adjust_time = start_time
        
        logger.info(
            f"📡 Monitoring order {order_id} | "
            f"Price: ${current_price:.2f} | "
            f"Max wait: {max_wait}s | "
            f"Adjust every {price_adjust_interval}s by ${price_step:.2f}"
        )
        
        while True:
            elapsed = time_module.time() - start_time
            
            # Check timeout
            if elapsed >= max_wait:
                logger.warning(
                    f"⏰ Order {order_id} timed out after {elapsed:.0f}s | "
                    f"Adjustments made: {adjustments_made} | "
                    f"Last price: ${current_price:.2f}"
                )
                return {
                    "filled": False,
                    "fill_price": None,
                    "adjustments_made": adjustments_made,
                    "final_status": "Expired",
                    "order_id": order_id,
                }
            
            # Poll order status
            try:
                orders = self.get_orders()
                target = None
                for o in orders:
                    if str(o.id) == str(order_id):
                        target = o
                        break
                
                if target is None:
                    # Order no longer in list — check if it was filled
                    # (filled orders may be removed from live list)
                    logger.info(f"Order {order_id} no longer live — checking if filled")
                    
                    # Check positions to confirm fill
                    positions = self.get_positions()
                    if positions:
                        logger.info(f"✅ Order {order_id} likely FILLED (found {len(positions)} positions)")
                    
                    return {
                        "filled": True,
                        "fill_price": current_price,
                        "adjustments_made": adjustments_made,
                        "final_status": "Filled",
                        "order_id": order_id,
                    }
                
                status = target.status.value if hasattr(target.status, 'value') else str(target.status)
                
                if status in ("Filled", "filled"):
                    avg_fill = float(target.price) if target.price else current_price
                    logger.info(
                        f"✅ Order {order_id} FILLED @ ${avg_fill:.2f} | "
                        f"Adjustments: {adjustments_made}"
                    )
                    return {
                        "filled": True,
                        "fill_price": avg_fill,
                        "adjustments_made": adjustments_made,
                        "final_status": "Filled",
                        "order_id": order_id,
                    }
                
                if status in ("Cancelled", "Rejected", "Expired", "cancelled", "rejected", "expired"):
                    logger.warning(f"❌ Order {order_id} {status}")
                    return {
                        "filled": False,
                        "fill_price": None,
                        "adjustments_made": adjustments_made,
                        "final_status": status,
                        "order_id": order_id,
                    }
                
                # Order is still Working — check if we should adjust price
                time_since_last_adjust = time_module.time() - last_adjust_time
                
                if (time_since_last_adjust >= price_adjust_interval and
                        adjustments_made < max_adjustments):
                    
                    # Adjust price to improve fill chances
                    if is_credit:
                        # Credit order: lower the credit we demand
                        new_price = round(current_price - price_step, 2)
                    else:
                        # Debit order: increase the debit we're willing to pay
                        new_price = round(current_price + price_step, 2)
                    
                    # Safety: don't adjust below $0.01 for credit orders
                    if is_credit and new_price < 0.01:
                        logger.warning(f"Price adjustment would go below $0.01, skipping")
                    else:
                        success = self.replace_order(order_id, new_price)
                        if success:
                            adjustments_made += 1
                            current_price = new_price
                            last_adjust_time = time_module.time()
                            logger.info(
                                f"🔄 Price adjusted #{adjustments_made}: "
                                f"${current_price:.2f} | "
                                f"Elapsed: {elapsed:.0f}s"
                            )
                        else:
                            logger.warning(f"Price adjustment failed, will retry")
                
                # Log periodic status
                if int(elapsed) % 15 == 0 and int(elapsed) > 0:
                    logger.info(
                        f"⏳ Order {order_id} still {status} | "
                        f"Price: ${current_price:.2f} | "
                        f"Elapsed: {elapsed:.0f}s"
                    )
                    
            except Exception as e:
                logger.error(f"Error monitoring order {order_id}: {e}")
            
            # Wait before next poll
            time_module.sleep(monitor_interval)


# Convenience function for quick testing
def test_connection():
    """Test Tastytrade connection."""
    client = TastytradeClient()
    client.connect()
    
    print("Connection successful!")
    print(f"Account: {client.get_account().account_number}")
    
    balances = client.get_account_balance()
    print(f"Buying Power: ${balances['buying_power']:,.2f}")
    print(f"Net Liq: ${balances['net_liquidating_value']:,.2f}")
    
    client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_connection()
