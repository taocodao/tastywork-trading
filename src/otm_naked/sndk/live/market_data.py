import logging
import asyncio
import pandas as pd
from typing import Optional, List
from ib_insync import IB, Stock, Option, util
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SNDKMarketDataProvider:
    """Provides real market data and option chains from IB."""
    
    def __init__(self, ib_connector):
        self.ib_connector = ib_connector
        
    async def get_daily_bars(self, ticker: str, days: int = 100) -> pd.DataFrame:
        """Fetch daily OHLCV bars from IB."""
        ib = self.ib_connector.get_ib()
        contract = Stock(ticker, 'SMART', 'USD')
        await ib.qualifyContractsAsync(contract)
        
        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime='',
            durationStr=f"{days} D",
            barSizeSetting='1 day',
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        
        if not bars:
            logger.warning(f"No historical data received for {ticker}")
            return pd.DataFrame()
            
        df = util.df(bars)
        # Standardize column names for feature engineering
        df = df.rename(columns={
            'date': 'date',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'volume': 'volume'
        })
        df.set_index('date', inplace=True)
        # Ensure index is DatetimeIndex
        df.index = pd.to_datetime(df.index)
        return df

    async def get_current_price(self, ticker: str) -> float:
        """Get live (or delayed) last price."""
        ib = self.ib_connector.get_ib()
        contract = Stock(ticker, 'SMART', 'USD')
        await ib.qualifyContractsAsync(contract)
        
        ticker_data = await ib.reqTickersAsync(contract)
        if not ticker_data or len(ticker_data) == 0:
            return 0.0
            
        t = ticker_data[0]
        # Fallbacks: last price -> close price -> midpoint
        price = t.last
        if not price or price <= 0:
            price = t.close
        if not price or price <= 0:
            price = (t.bid + t.ask) / 2 if (t.bid and t.ask and t.bid > 0 and t.ask > 0) else 0.0
            
        return price
        
    async def get_vix_close(self) -> float:
        """Get current VIX approximation."""
        # Note: True VIX requires index data permissions. 
        # Using SPY implied volatility or VIX index if available.
        from ib_insync import Index
        ib = self.ib_connector.get_ib()
        contract = Index('VIX', 'CBOE')
        try:
            await ib.qualifyContractsAsync(contract)
            ticker_data = await ib.reqTickersAsync(contract)
            if ticker_data and len(ticker_data) > 0 and ticker_data[0].last > 0:
                return ticker_data[0].last
        except Exception:
            pass
            
        logger.warning("VIX Index unavailable. Defaulting to 20.0")
        return 20.0 # Default fallback
        
    async def get_option_chain_data(self, ticker: str) -> list:
        """Get all option chain parameters (expirations, strikes)."""
        ib = self.ib_connector.get_ib()
        contract = Stock(ticker, 'SMART', 'USD')
        await ib.qualifyContractsAsync(contract)
        
        chains = await ib.reqSecDefOptParamsAsync(
            underlyingSymbol=contract.symbol,
            futFopExchange='',
            underlyingSecType=contract.secType,
            underlyingConId=contract.conId
        )
        # SMART is usually a combination of exchanges. Look for SMART or the primary exchange.
        valid_chains = [c for c in chains if c.exchange == 'SMART' or c.exchange == 'CBOE']
        if not valid_chains:
            valid_chains = chains
            
        return valid_chains

    async def get_real_iv(self, option_contract: Option) -> float:
        """Get actual implied volatility for a specific option contract."""
        ib = self.ib_connector.get_ib()
        await ib.qualifyContractsAsync(option_contract)
        
        # Request generic tick 106 for Option Volume and IV
        ticker = ib.reqMktData(option_contract, "106", False, False)
        
        # Wait up to 5 seconds for IV to populate
        for _ in range(50):
            if ticker.modelGreeks and ticker.modelGreeks.impliedVol:
                ib.cancelMktData(option_contract)
                return ticker.modelGreeks.impliedVol
            await asyncio.sleep(0.1)
            
        ib.cancelMktData(option_contract)
        logger.warning(f"Could not fetch real IV for {option_contract.symbol} {option_contract.lastTradeDateOrContractMonth} {option_contract.strike}")
        return 0.0

    async def get_contract_greeks_and_prices(self, option_contract: Option) -> dict:
        """Get bid, ask, last, delta, gamma, vega, theta, IV."""
        ib = self.ib_connector.get_ib()
        await ib.qualifyContractsAsync(option_contract)
        
        ticker = ib.reqMktData(option_contract, "106", False, False)
        result = {"bid": 0.0, "ask": 0.0, "last": 0.0, "iv": 0.0, "delta": 0.0}
        
        # Wait for data
        for _ in range(50):
            has_price = ticker.bid > 0 or ticker.ask > 0 or ticker.last > 0
            has_greeks = ticker.modelGreeks is not None
            if has_price and has_greeks:
                break
            await asyncio.sleep(0.1)
            
        result["bid"] = ticker.bid
        result["ask"] = ticker.ask
        result["last"] = ticker.last
        result["mid"] = (ticker.bid + ticker.ask) / 2 if (ticker.bid > 0 and ticker.ask > 0) else 0.0
        
        if ticker.modelGreeks:
            result["iv"] = ticker.modelGreeks.impliedVol or 0.0
            result["delta"] = ticker.modelGreeks.delta or 0.0
            
        ib.cancelMktData(option_contract)
        return result
