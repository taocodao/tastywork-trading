import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import pandas as pd
from datetime import datetime

# Adjust path to import from sibling roots
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.diagonal_spreads.liquidity_screener import LiquidityScreener, UniverseScanner, LiquidityResult
from src.diagonal_spreads.etf_universe import get_etf_universe, UniverseTier
from src.zebra.security_scorer import ZebraSecurityScorer
from ib_data_provider import IBDataProvider

logger = logging.getLogger(__name__)

@dataclass
class PMCCCandidate:
    """Represents a screened and scored PMCC candidate"""
    symbol: str
    price: float
    liquidity_score: float
    composite_score: float
    trend_score: float
    momentum_score: float
    vol_score: float
    iv_rank: float
    atr_pct: float
    rationale: str
    has_earnings_risk: bool = False
    
    # ML Feature Store fields (Rule 2: Persist computed features)
    features: Dict[str, float] = field(default_factory=dict)

class PMCCScreener:
    """
    Screener for PMCC candidates.
    Combines basic liquidity screening (from diagonal_spreads) with 
    advanced multi-factor scoring (from ZEBRA).
    """
    def __init__(self, data_provider: Optional[IBDataProvider] = None):
        self.ib = data_provider or IBDataProvider()
        self.liquidity_screener = LiquidityScreener(
            min_daily_volume=1_000_000, # Higher volume for PMCC
            min_options_volume=10_000,
            max_bid_ask_spread_pct=0.03
        )
        self.scanner = UniverseScanner(data_provider=self.ib, screener=self.liquidity_screener)
        self.zebra_scorer = ZebraSecurityScorer()
        
    def get_candidates(self, min_composite_score: float = 60.0) -> List[PMCCCandidate]:
        """
        Run the full PMCC screening pipeline:
        1. Base ETF/Equity Universe (Tiers 1, 2, 4)
        2. Liquidity Filter
        3. Historic Data Fetch
        4. ZEBRA Multi-factor Scoring
        5. IV & Trend Filtering
        """
        logger.info("Starting PMCC Screener pipeline...")
        
        # 1. Base Universe (Skip Tier 3 Opportunistic unless forced)
        universe = get_etf_universe()
        symbols_to_scan = universe.get_prioritized_scan_list(
            include_tier2=True,
            include_tier3=False,
            include_tier4=True # Include Mega Cap Equities for PMCC
        )
        logger.info(f"Generated universe of {len(symbols_to_scan)} symbols to scan")
        
        # 2. Liquidity Filter
        liquidity_results = self._run_liquidity_scan(symbols_to_scan)
        logger.info(f"{len(liquidity_results)} symbols passed liquidity checks")
        
        if not liquidity_results:
            return []
            
        # 3 & 4. Fetch Data and ZEBRA Score
        candidates = []
        for lq_res in liquidity_results:
            symbol = lq_res.symbol
            
            # Fetch at least 200 days of history for ZEBRA scoring
            hist_df = self._fetch_history(symbol)
            if hist_df is None or len(hist_df) < 200:
                logger.debug(f"{symbol} has insufficient history")
                continue
                
            # Score symbol
            score_data = self.zebra_scorer.score_symbol(symbol, hist_df)
            
            # 5. PMCC Specific Filters
            # PMCC requires a positive trend and lower IV
            trend_score = score_data.get('trend_score', 0)
            composite_score = score_data.get('composite_score', 0)
            
            if composite_score < min_composite_score:
                logger.debug(f"{symbol} failed composite score: {composite_score:.1f} < {min_composite_score}")
                continue
                
            if trend_score < 40:
                logger.debug(f"{symbol} failed trend score: {trend_score:.1f} < 40")
                continue
            
            # Fetch current IV and calculate Rank
            # Assuming IV is roughly the ATR% / Close for simplicity if get_atm_iv isn't cached
            price = hist_df['Close'].iloc[-1]
            atr = hist_df['ATR'].iloc[-1] if 'ATR' in hist_df.columns else 0.0
            atr_pct = (atr / price) * 100 if price > 0 else 0.0
            
            iv = self.ib.get_atm_iv(symbol)
            iv_rank = self.ib.get_iv_percentile(iv, symbol)
            
            # IV Rank filter: We want to BUY LEAPS when IV is relatively low
            if iv_rank > 40:
                logger.debug(f"{symbol} failed IV Rank: {iv_rank:.1f} > 40")
                continue
            
            # Build Candidate
            config = universe.get_security_config(symbol)
            has_earnings = config.has_earnings_risk if config else False
            
            # Extract features for ML store
            latest = hist_df.iloc[-1]
            features = {
                'rsi': latest.get('RSI', 50.0),
                'macd': latest.get('MACD', 0.0),
                'atr_pct': atr_pct,
                'iv_rank': iv_rank,
                'bb_p': latest.get('BB_P', 0.5),
                'liquidity_score': lq_res.liquidity_score
            }
            
            candidates.append(PMCCCandidate(
                symbol=symbol,
                price=price,
                liquidity_score=lq_res.liquidity_score,
                composite_score=composite_score,
                trend_score=trend_score,
                momentum_score=score_data.get('momentum_score', 0),
                vol_score=score_data.get('vol_score', 0),
                iv_rank=iv_rank,
                atr_pct=atr_pct,
                rationale=score_data.get('rationale', ''),
                has_earnings_risk=has_earnings,
                features=features
            ))
            
        # Sort candidates by composite ZEBRA score descending
        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        logger.info(f"PMCC Screener found {len(candidates)} valid candidates")
        return candidates
        
    def _run_liquidity_scan(self, symbols: List[str]) -> List[LiquidityResult]:
        """Fetch basic data and run liquidity screener"""
        securities_data = []
        for symbol in symbols:
            data = self.scanner.fetch_security_data(symbol)
            if data:
                securities_data.append(data)
                
        return self.liquidity_screener.screen_universe(securities_data)
        
    def _fetch_history(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch ~1 year of daily historic data required for scoring"""
        if not self.ib._connected and not self.ib.connect():
            return None
            
        try:
            from ib_insync import Stock
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.ib.qualifyContracts(contract)
            
            bars = self.ib.ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr='1 Y',
                barSizeSetting='1 day',
                whatToShow='TRADES',
                useRTH=True,
                formatDate=1
            )
            
            if not bars:
                return None
                
            df = pd.DataFrame([{
                'Date': b.date,
                'Open': b.open,
                'High': b.high,
                'Low': b.low,
                'Close': b.close,
                'Volume': b.volume
            } for b in bars])
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching history for {symbol}: {e}")
            return None
