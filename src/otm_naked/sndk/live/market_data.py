import logging
import pandas as pd
from typing import Optional, List
from ib_insync import IB, Stock, Option, Index, util
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class SNDKMarketDataProvider:
    """Provides real market data and option chains from IB."""
    
    def __init__(self, ib_connector):
        self.ib_connector = ib_connector
        self.live_bars = None
        self.bar_update_callbacks = []
        
    def _get_ib(self) -> IB:
        return self.ib_connector.get_ib()
        
    def get_daily_bars(self, ticker: str, days: int = 150) -> pd.DataFrame:
        """Fetch daily OHLCV bars from IB (synchronous)."""
        ib = self._get_ib()
        contract = Stock(ticker, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr=f"{days} D",
            barSizeSetting='1 day',
            whatToShow='MIDPOINT',
            useRTH=True,
            formatDate=1
        )
        
        if not bars:
            logger.warning(f"No daily historical data received for {ticker}")
            return pd.DataFrame()
            
        df = util.df(bars)
        df = df.rename(columns={'date': 'date'})
        df.set_index('date', inplace=True)
        df.index = pd.to_datetime(df.index)
        return df

    def subscribe_5min_bars(self, ticker: str, callback):
        """Initialize polling subscription for 5-min bars."""
        ib = self._get_ib()
        contract = Stock(ticker, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        if callback not in self.bar_update_callbacks:
            self.bar_update_callbacks.append(callback)
            
        self.live_bars = []
        logger.info(f"Initialized polling 5-min bars for {ticker}.")
        
    def poll_5min_bars(self, ticker: str):
        """Polls for new bars and triggers callbacks if a new bar closed."""
        ib = self._get_ib()
        contract = Stock(ticker, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='5 mins',
            whatToShow='MIDPOINT',
            useRTH=True,
            formatDate=1,
            keepUpToDate=False
        )
        
        if not bars:
            return
            
        has_new_bar = False
        if not self.live_bars or len(self.live_bars) == 0 or bars[-1].date > self.live_bars[-1].date:
            has_new_bar = True
            
        self.live_bars = bars
        
        if has_new_bar:
            self._on_bar_update(bars, True)
        
    def _on_bar_update(self, bars, has_new_bar):
        """Internal callback for ib_insync barUpdateEvent."""
        logger.debug(f"_on_bar_update fired. has_new_bar={has_new_bar}, total_bars={len(bars)}")
        if has_new_bar:
            # Trigger our custom callbacks
            for cb in self.bar_update_callbacks:
                cb(bars, has_new_bar)
                
    def unsubscribe_5min_bars(self):
        """Cleanup subscription."""
        self.live_bars = None
        self.bar_update_callbacks = []
            
    def get_intraday_move(self, ticker: str) -> float:
        """Calculate today's move from open to current price using live bars."""
        if not self.live_bars or len(self.live_bars) == 0:
            return 0.0
        
        df = util.df(self.live_bars)
        # Use today's first bar open
        today = datetime.now().date()
        df['date_only'] = pd.to_datetime(df['date']).dt.date
        today_bars = df[df['date_only'] == today]
        
        if today_bars.empty:
            return 0.0
            
        open_price = today_bars.iloc[0]['open']
        current_price = today_bars.iloc[-1]['close']
        
        if open_price > 0:
            return ((current_price - open_price) / open_price) * 100
        return 0.0

    def get_current_price(self, ticker: str) -> float:
        """Get live (or delayed) last price."""
        if self.live_bars and len(self.live_bars) > 0:
            return self.live_bars[-1].close
            
        ib = self._get_ib()
        contract = Stock(ticker, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        try:
            ticker_data = ib.reqTickers(contract)
            if not ticker_data or len(ticker_data) == 0:
                return 0.0
                
            t = ticker_data[0]
            price = t.last
            if not price or price <= 0 or price != price:
                price = t.close
            if not price or price <= 0 or price != price:
                if t.bid and t.ask and t.bid > 0 and t.ask > 0 and t.bid != -1 and t.ask != -1:
                    price = (t.bid + t.ask) / 2
                else:
                    price = 0.0
                
            return price
        except Exception:
            return 0.0
        
    def get_vix_history(self, days: int = 150) -> pd.Series:
        """Get historical VIX daily closes."""
        ib = self._get_ib()
        contract = Index('VIX', 'CBOE')
        try:
            ib.qualifyContracts(contract)
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=f"{days} D",
                barSizeSetting='1 day',
                whatToShow='MIDPOINT',
                useRTH=True,
                formatDate=1
            )
            if bars:
                df = util.df(bars)
                df.set_index('date', inplace=True)
                df.index = pd.to_datetime(df.index)
                return df['close']
        except Exception as e:
            logger.warning(f"Could not fetch VIX history: {e}")
            
        # Fallback dummy VIX series
        logger.warning("Defaulting to flat VIX 20.0")
        dates = pd.date_range(end=datetime.now(), periods=days, freq='B')
        return pd.Series(20.0, index=dates)

    def get_vix3m_history(self, days: int = 150) -> pd.Series:
        """Get historical VIX3M daily closes."""
        ib = self._get_ib()
        contract = Index('VIX3M', 'CBOE')
        try:
            ib.qualifyContracts(contract)
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=f"{days} D",
                barSizeSetting='1 day',
                whatToShow='MIDPOINT',
                useRTH=True,
                formatDate=1
            )
            if bars:
                df = util.df(bars)
                df.set_index('date', inplace=True)
                df.index = pd.to_datetime(df.index)
                return df['close']
        except Exception as e:
            logger.warning(f"Could not fetch VIX3M history: {e}")
            
        # Fallback dummy VIX3M series
        logger.warning("Defaulting to flat VIX3M 22.0")
        dates = pd.date_range(end=datetime.now(), periods=days, freq='B')
        return pd.Series(22.0, index=dates)
        
    def get_option_chain_data(self, ticker: str) -> list:
        """Get all option chain parameters (expirations, strikes)."""
        ib = self._get_ib()
        contract = Stock(ticker, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        
        chains = ib.reqSecDefOptParams(
            underlyingSymbol=contract.symbol,
            futFopExchange='',
            underlyingSecType=contract.secType,
            underlyingConId=contract.conId
        )
        valid_chains = [c for c in chains if c.exchange == 'SMART' or c.exchange == 'CBOE']
        if not valid_chains:
            valid_chains = chains
            
        return valid_chains

    def get_contract_greeks_and_prices(self, contracts: List[Option]) -> dict:
        """
        Batch fetch Greeks and prices for multiple contracts.
        Returns a dict mapping conId to its data.
        """
        ib = self._get_ib()
        # Qualify first
        ib.qualifyContracts(*contracts)
        valid_contracts = [c for c in contracts if c.conId > 0]
        
        if not valid_contracts:
            return {}
            
        # Empty genericTickList to get modelGreeks
        tickers = [ib.reqMktData(c, "", False, False) for c in valid_contracts]
        
        # Wait for Greeks to populate (usually 2-5 seconds)
        ib.sleep(5)
        
        results = {}
        for t, c in zip(tickers, valid_contracts):
            res = {"bid": 0.0, "ask": 0.0, "last": 0.0, "mid": 0.0, "iv": 0.0, "delta": 0.0, "theta": 0.0}
            
            # Sanitize negative values which mean "no data" in IB API
            if t.bid and t.bid > 0 and t.bid != -1: res["bid"] = t.bid
            if t.ask and t.ask > 0 and t.ask != -1: res["ask"] = t.ask
            if t.last and t.last > 0 and t.last != -1: res["last"] = t.last
            
            if res["bid"] > 0 and res["ask"] > 0:
                res["mid"] = (res["bid"] + res["ask"]) / 2
                
            if t.modelGreeks:
                res["iv"] = t.modelGreeks.impliedVol or 0.0
                res["delta"] = t.modelGreeks.delta or 0.0
                res["theta"] = t.modelGreeks.theta or 0.0
                
            results[c.conId] = res
            
        # Cleanup
        for c in valid_contracts:
            ib.cancelMktData(c)
            
        return results
