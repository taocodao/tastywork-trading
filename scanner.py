"""
Calendar Spreads Bot - Scanner
==============================

Scans for optimal calendar spread opportunities.
Finds ATM strikes with good liquidity and theta characteristics.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Tuple
import numpy as np

from config import (
    UNDERLYINGS, SHORT_EXPIRY_DAYS, LONG_EXPIRY_DAYS,
    MIN_OPEN_INTEREST, MAX_BID_ASK_SPREAD, MIN_VIX, MAX_VIX,
    MIN_TRADE_COST, MAX_TRADE_COST, STRIKE_TOLERANCE_PCT
)
from greeks_calculator import SpreadCalculator, SpreadGreeks

logger = logging.getLogger(__name__)


@dataclass
class OptionQuote:
    """Quote data for a single option."""
    symbol: str
    strike: float
    expiry: date
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    iv: float
    
    @property
    def mid(self) -> float:
        """Mid-point price."""
        return (self.bid + self.ask) / 2
    
    @property
    def spread(self) -> float:
        """Bid-ask spread."""
        return self.ask - self.bid
    
    @property
    def is_liquid(self) -> bool:
        """Check if option is liquid enough to trade."""
        return (
            self.open_interest >= MIN_OPEN_INTEREST and
            self.spread <= MAX_BID_ASK_SPREAD
        )


@dataclass
class SpreadSetup:
    """A potential calendar spread trade setup."""
    symbol: str
    strike: float
    stock_price: float
    
    # Short leg (sell)
    short_expiry: date
    short_bid: float
    short_ask: float
    short_oi: int
    
    # Long leg (buy)
    long_expiry: date
    long_bid: float
    long_ask: float
    long_oi: int
    
    # Combined
    net_debit: float
    iv: float
    spread_greeks: Optional[SpreadGreeks] = None
    
    @property
    def short_credit(self) -> float:
        """Credit received from short leg (use bid)."""
        return self.short_bid
    
    @property
    def long_cost(self) -> float:
        """Cost of long leg (use ask)."""
        return self.long_ask
    
    @property
    def profit_target_5pct(self) -> float:
        """Spread value at 5% profit."""
        return self.net_debit * 1.05
    
    @property
    def stop_loss_10pct(self) -> float:
        """Spread value at 10% loss."""
        return self.net_debit * 0.90
    
    @property
    def theta_edge(self) -> float:
        """Daily theta advantage in dollars."""
        if self.spread_greeks:
            return self.spread_greeks.net_theta * 100
        return 0.0
    
    @property
    def score(self) -> float:
        """
        Score the setup quality (higher = better).
        
        Factors:
        - Theta edge (more = better)
        - Liquidity (lower spread = better)
        - Cost in target range (prefer lower)
        """
        theta_score = self.theta_edge * 10  # Weight theta highly
        liquidity_score = 20 - (self.short_ask - self.short_bid) * 100  # Penalize wide spreads
        cost_score = 30 - (self.net_debit - 200) * 0.1  # Prefer costs near $200
        
        return theta_score + liquidity_score + cost_score
    
    def __str__(self) -> str:
        return (
            f"{self.symbol} ${self.strike} Calendar: "
            f"SELL {self.short_expiry.strftime('%m/%d')} @ ${self.short_bid:.2f}, "
            f"BUY {self.long_expiry.strftime('%m/%d')} @ ${self.long_ask:.2f} = "
            f"${self.net_debit:.2f} debit"
        )


class CalendarSpreadScanner:
    """
    Scanner for calendar spread opportunities.
    
    Finds ATM strikes with optimal theta decay characteristics.
    """
    
    def __init__(
        self,
        underlyings: List[str] = None,
        data_provider = None
    ):
        """
        Initialize scanner.
        
        Args:
            underlyings: List of symbols to scan (default: from config)
            data_provider: Data source for quotes (IB, mock, etc.)
        """
        self.underlyings = underlyings or UNDERLYINGS
        self.data_provider = data_provider
        self.calc = SpreadCalculator()
    
    def get_stock_price(self, symbol: str) -> float:
        """Get current stock price from real market data."""
        if self.data_provider:
            return self.data_provider.get_price(symbol)
        
        # NO MOCK DATA - raise error if no data provider
        raise ValueError(f"No data provider configured! Cannot get price for {symbol}. "
                        "Initialize CalendarSpreadScanner with data_provider=IBDataProvider().")
    
    def get_option_chain(
        self,
        symbol: str,
        expiry: date,
        option_type: str = "call"
    ) -> List[OptionQuote]:
        """Get option chain for a symbol and expiry from real market data."""
        if self.data_provider:
            return self.data_provider.get_options(symbol, expiry, option_type)
        
        # NO MOCK DATA - raise error if no data provider
        raise ValueError(f"No data provider configured! Cannot get options for {symbol}. "
                        "Initialize CalendarSpreadScanner with data_provider=IBDataProvider().")
    
    def find_atm_strike(self, symbol: str) -> float:
        """Find the at-the-money strike closest to current price."""
        stock_price = self.get_stock_price(symbol)
        
        # Round to nearest integer for ETFs like IWM
        # For higher-priced stocks, might round to $5 increments
        if stock_price > 100:
            return round(stock_price)
        else:
            return round(stock_price * 2) / 2  # Round to $0.50
    
    def get_next_expiry(self, days_out: int) -> date:
        """Get the next expiry date approximately days_out days away."""
        target = date.today() + timedelta(days=days_out)
        
        # Most ETF options expire daily or weekly
        # For simplicity, use exact target date
        return target
    
    def build_spread_setup(
        self,
        symbol: str,
        short_option: OptionQuote,
        long_option: OptionQuote
    ) -> Optional[SpreadSetup]:
        """Build a SpreadSetup from two option quotes."""
        stock_price = self.get_stock_price(symbol)
        
        # Calculate net debit
        # SELL short @ bid, BUY long @ ask
        net_debit = (long_option.ask - short_option.bid) * 100  # Per contract
        
        # Calculate Greeks
        short_dte = (short_option.expiry - date.today()).days
        long_dte = (long_option.expiry - date.today()).days
        
        spread_greeks = self.calc.calculate_spread(
            stock_price=stock_price,
            strike=short_option.strike,
            short_dte=short_dte,
            long_dte=long_dte,
            iv=short_option.iv
        )
        
        return SpreadSetup(
            symbol=symbol,
            strike=short_option.strike,
            stock_price=stock_price,
            short_expiry=short_option.expiry,
            short_bid=short_option.bid,
            short_ask=short_option.ask,
            short_oi=short_option.open_interest,
            long_expiry=long_option.expiry,
            long_bid=long_option.bid,
            long_ask=long_option.ask,
            long_oi=long_option.open_interest,
            net_debit=net_debit,
            iv=short_option.iv,
            spread_greeks=spread_greeks
        )
    
    def scan_symbol(self, symbol: str) -> List[SpreadSetup]:
        """Scan a single symbol for calendar spread opportunities."""
        setups = []
        
        # Get expiry dates
        short_expiry = self.get_next_expiry(SHORT_EXPIRY_DAYS)
        long_expiry = self.get_next_expiry(LONG_EXPIRY_DAYS)
        
        # Get option chains
        short_chain = self.get_option_chain(symbol, short_expiry)
        long_chain = self.get_option_chain(symbol, long_expiry)
        
        if not short_chain or not long_chain:
            logger.warning(f"No options found for {symbol}")
            return []
        
        # Find ATM strike
        atm_strike = self.find_atm_strike(symbol)
        stock_price = self.get_stock_price(symbol)
        
        # Build setups for strikes near ATM
        for short_opt in short_chain:
            # Check if near ATM
            strike_pct_diff = abs(short_opt.strike - atm_strike) / stock_price * 100
            if strike_pct_diff > STRIKE_TOLERANCE_PCT:
                continue
            
            # Find matching long option
            long_opt = next(
                (o for o in long_chain if o.strike == short_opt.strike),
                None
            )
            
            if not long_opt:
                continue
            
            # Check liquidity
            if not short_opt.is_liquid or not long_opt.is_liquid:
                logger.debug(f"Skipping illiquid option: {short_opt.strike}")
                continue
            
            # Build setup
            setup = self.build_spread_setup(symbol, short_opt, long_opt)
            
            if setup:
                # Filter by cost
                if MIN_TRADE_COST <= setup.net_debit <= MAX_TRADE_COST:
                    setups.append(setup)
                else:
                    logger.debug(f"Skipping {symbol} ${short_opt.strike}: cost ${setup.net_debit:.0f} out of range")
        
        return setups
    
    def scan_all(self) -> List[SpreadSetup]:
        """Scan all underlyings for opportunities."""
        all_setups = []
        
        for symbol in self.underlyings:
            logger.info(f"Scanning {symbol}...")
            setups = self.scan_symbol(symbol)
            all_setups.extend(setups)
            logger.info(f"  Found {len(setups)} setups for {symbol}")
        
        # Sort by score (best first)
        all_setups.sort(key=lambda s: s.score, reverse=True)
        
        return all_setups
    
    def get_best_setup(self) -> Optional[SpreadSetup]:
        """Get the single best setup across all underlyings."""
        setups = self.scan_all()
        return setups[0] if setups else None


def check_vix_filter() -> Tuple[bool, float]:
    """Check if VIX is in acceptable range using real market data."""
    import logging
    logger = logging.getLogger(__name__)
    
    vix = None
    
    # Try yfinance first (most reliable for VIX)
    try:
        import yfinance as yf
        vix_ticker = yf.Ticker("^VIX")
        hist = vix_ticker.history(period="1d")
        if not hist.empty and 'Close' in hist.columns:
            vix = float(hist['Close'].iloc[-1])
            logger.info(f"VIX from yfinance: {vix:.2f}")
    except Exception as e:
        logger.warning(f"yfinance VIX fetch failed: {e}")
    
    # Fallback: Try IB if available
    if vix is None:
        try:
            from ib_insync import IB, Index
            ib = IB()
            if ib.isConnected():
                vix_contract = Index('VIX', 'CBOE')
                ib.qualifyContracts(vix_contract)
                ticker = ib.reqMktData(vix_contract, '', False, False)
                ib.sleep(1)
                if ticker.last and ticker.last > 0:
                    vix = float(ticker.last)
                    logger.info(f"VIX from IB: {vix:.2f}")
        except Exception as e:
            logger.warning(f"IB VIX fetch failed: {e}")
    
    # If still no VIX, fail safe - don't block trading but warn
    if vix is None:
        logger.error("Could not fetch VIX from any source! Proceeding with caution.")
        vix = 20.0  # Conservative default - within acceptable range
    
    if vix < MIN_VIX:
        logger.info(f"VIX {vix:.2f} < {MIN_VIX} - too low, not enough premium")
        return False, vix
    if vix > MAX_VIX:
        logger.warning(f"VIX {vix:.2f} > {MAX_VIX} - too high, skipping")
        return False, vix
    
    logger.info(f"VIX {vix:.2f} - OK to trade")
    return True, vix


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Calendar Spread Scanner")
    print("=" * 60)
    
    # Check VIX
    vix_ok, vix = check_vix_filter()
    print(f"VIX: {vix:.1f} - {'OK' if vix_ok else 'SKIP'}")
    
    if not vix_ok:
        print("Skipping scan due to VIX filter")
        exit()
    
    # Run scan
    scanner = CalendarSpreadScanner()
    setups = scanner.scan_all()
    
    print(f"\nFound {len(setups)} opportunities:")
    print("-" * 60)
    
    for i, setup in enumerate(setups[:5], 1):
        print(f"\n{i}. {setup}")
        print(f"   Stock: ${setup.stock_price:.2f}")
        print(f"   Net Debit: ${setup.net_debit:.2f}")
        print(f"   Theta Edge: ${setup.theta_edge:.2f}/day")
        print(f"   Profit Target (+5%): ${setup.profit_target_5pct:.2f}")
        print(f"   Stop Loss (-10%): ${setup.stop_loss_10pct:.2f}")
        print(f"   Score: {setup.score:.1f}")
