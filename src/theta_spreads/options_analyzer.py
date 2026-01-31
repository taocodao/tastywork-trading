"""
Options Analyzer for Theta Strategy
====================================

Analyzes options chains and scores individual puts based on:
1. Delta Precision (30 pts) - Target 0.30 delta (±0.05)
2. Premium Quality (25 pts) - Higher premiums preferred ($0.50+)
3. Theta/Time Decay (20 pts) - Higher theta = faster profit
4. Liquidity (15 pts) - Volume and tight spreads
5. Vega (10 pts) - Lower vega = less IV risk

Scores puts on 0-100 scale for confidence ranking.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class PutScore:
    """Scored put option ready for signal generation."""
    symbol: str
    strike: float
    expiration: date
    dte: int
    
    # Pricing
    bid: float
    ask: float
    mid: float
    
    # Greeks
    delta: float
    theta: float
    vega: float
    gamma: float
    iv: float
    
    # Liquidity
    volume: int
    open_interest: int
    bid_ask_spread: float
    bid_ask_spread_pct: float
    
    # Scoring
    total_score: int
    delta_score: int
    premium_score: int
    theta_score: int
    liquidity_score: int
    vega_score: int
    symbol_base_score: int  # From symbol selection
    
    # Additional
    probability_otm: float
    expected_premium: float
    capital_required: float


class OptionsAnalyzer:
    """
    Analyzes options chains to identify and score optimal puts for selling.
    
    Usage:
        analyzer = OptionsAnalyzer()
        scored_puts = analyzer.analyze_symbol("QQQ", 85, options_chain)
        # Returns list of PutScore objects sorted by confidence
    """
    
    def __init__(
        self,
        target_delta: float = 0.30,
        delta_tolerance: float = 0.05,
        dte_min: int = 28,
        dte_max: int = 35,
        min_premium: float = 0.50,
        min_liquidity: int = 100,
        min_iv: float = 0.15,  # NEW: Minimum implied volatility (15%)
        confidence_threshold: int = 60
    ):
        """
        Initialize options analyzer.
        
        Args:
            target_delta: Target delta for puts (default: 0.30)
            delta_tolerance: Delta tolerance ±  (default: 0.05)
            dte_min: Minimum days to expiration (default: 28)
            dte_max: Maximum days to expiration (default: 35)
            min_premium: Minimum bid price (default: $0.50)
            min_liquidity: Minimum open interest (default: 100)
            min_iv: Minimum implied volatility (default: 0.15 = 15%)
            confidence_threshold: Minimum score to include (default: 60)
        """
        self.target_delta = target_delta
        self.delta_tolerance = delta_tolerance
        self.dte_min = dte_min
        self.dte_max = dte_max
        self.min_premium = min_premium
        self.min_liquidity = min_liquidity
        self.min_iv = min_iv  # NEW: Store min IV threshold
        self.confidence_threshold = confidence_threshold
    
    def analyze_symbol(
        self,
        symbol: str,
        symbol_score: int,
        options_chain: List[Dict]
    ) -> List[PutScore]:
        """
        Analyze options chain for a symbol and return scored puts.
        
        Args:
            symbol: Stock symbol
            symbol_score: Base score from symbol selection (0-100)
            options_chain: List of option data dicts from IB Gateway
            
        Returns:
            List of PutScore objects that pass filters, sorted by score
        """
        logger.debug(f"Analyzing {len(options_chain)} options for {symbol}")
        
        scored_puts: List[PutScore] = []
        
        for option in options_chain:
            # Apply pre-filters
            if not self._passes_filters(option):
                continue
            
            # Score this put
            put_score = self.score_put(symbol, option, symbol_score)
            
            if put_score and put_score.total_score >= self.confidence_threshold:
                scored_puts.append(put_score)
        
        # Sort by total score (highest first)
        scored_puts.sort(key=lambda x: x.total_score, reverse=True)
        
        logger.info(f"{symbol}: {len(scored_puts)} qualified puts (threshold: {self.confidence_threshold})")
        
        return scored_puts
    
    def score_put(
        self,
        symbol: str,
        option: Dict,
        symbol_base_score: int
    ) -> Optional[PutScore]:
        """
        Score a put option across 5 factors (0-100 scale).
        
        Args:
            symbol: Stock symbol
            option: Option data dict
            symbol_base_score: Base score from symbol selection
            
        Returns:
            PutScore object or None if invalid
        """
        try:
            # Extract data
            strike = option["strike"]
            expiration = option["expiration"]
            dte = (expiration - date.today()).days
            
            bid = option["bid"]
            ask = option["ask"]
            mid = (bid + ask) / 2
            
            delta = abs(option.get("delta", 0))  # Convert to absolute
            theta = option.get("theta", 0)
            vega = option.get("vega", 0)
            gamma = option.get("gamma", 0)
            iv = option.get("iv", 0)
            
            volume = option.get("volume", 0)
            open_interest = option.get("open_interest", 0)
            
            bid_ask_spread = ask - bid
            bid_ask_spread_pct = (bid_ask_spread / mid) * 100 if mid > 0 else 100
            
            # Factor 1: Delta Precision (30 points max)
            delta_diff = abs(delta - self.target_delta)
            if delta_diff <= 0.02:
                delta_score = 30
            elif delta_diff <= 0.03:
                delta_score = 25
            elif delta_diff <= 0.04:
                delta_score = 20
            elif delta_diff <= self.delta_tolerance:
                delta_score = 15
            else:
                delta_score = 0
            
            # Factor 2: Premium Quality (25 points max)
            if bid >= 1.50:
                premium_score = 25
            elif bid >= 1.00:
                premium_score = 20
            elif bid >= 0.75:
                premium_score = 15
            elif bid >= self.min_premium:
                premium_score = 10
            else:
                premium_score = 0
            
            # Factor 3: Theta/Time Decay (20 points max)
            # Higher theta (more negative) = faster time decay = better
            theta_abs = abs(theta)
            if theta_abs >= 0.10:
                theta_score = 20
            elif theta_abs >= 0.08:
                theta_score = 16
            elif theta_abs >= 0.06:
                theta_score = 12
            elif theta_abs >= 0.04:
                theta_score = 8
            else:
                theta_score = 4
            
            # Factor 4: Liquidity (15 points max)
            if open_interest >= 1000 and bid_ask_spread_pct < 5:
                liquidity_score = 15
            elif open_interest >= 500 and bid_ask_spread_pct < 8:
                liquidity_score = 12
            elif open_interest >= 250 and bid_ask_spread_pct < 10:
                liquidity_score = 9
            elif open_interest >= self.min_liquidity and bid_ask_spread_pct < 15:
                liquidity_score = 6
            else:
                liquidity_score = 0
            
            # Factor 5: Vega (10 points max)
            # Lower vega = less sensitive to IV changes = better
            vega_abs = abs(vega)
            if vega_abs <= 0.15:
                vega_score = 10
            elif vega_abs <= 0.20:
                vega_score = 8
            elif vega_abs <= 0.25:
                vega_score = 6
            elif vega_abs <= 0.30:
                vega_score = 4
            else:
                vega_score = 2
            
            # Calculate total score
            # Weight symbol score at 10% of total
            total_score = int(
                delta_score + premium_score + theta_score + 
                liquidity_score + vega_score + (symbol_base_score * 0.1)
            )
            
            # Calculate additional metrics
            probability_otm = (1 - delta) * 100  # Approximation
            expected_premium = bid * 100  # Per contract
            capital_required = strike * 100  # For cash-secured put
            
            return PutScore(
                symbol=symbol,
                strike=strike,
                expiration=expiration,
                dte=dte,
                bid=bid,
                ask=ask,
                mid=mid,
                delta=delta,
                theta=theta,
                vega=vega,
                gamma=gamma,
                iv=iv,
                volume=volume,
                open_interest=open_interest,
                bid_ask_spread=bid_ask_spread,
                bid_ask_spread_pct=bid_ask_spread_pct,
                total_score=total_score,
                delta_score=delta_score,
                premium_score=premium_score,
                theta_score=theta_score,
                liquidity_score=liquidity_score,
                vega_score=vega_score,
                symbol_base_score=symbol_base_score,
                probability_otm=probability_otm,
                expected_premium=expected_premium,
                capital_required=capital_required
            )
            
        except Exception as e:
            logger.error(f"Error scoring put {symbol} {option.get('strike')}: {e}")
            return None
    
    def _passes_filters(self, option: Dict) -> bool:
        """Apply pre-filters to option."""
        # Check delta range
        delta = abs(option.get("delta", 0))
        if not (self.target_delta - self.delta_tolerance <= delta <= self.target_delta + self.delta_tolerance):
            return False
        
        # Check DTE range
        expiration = option.get("expiration")
        if not expiration:
            return False
        
        dte = (expiration - date.today()).days
        if not (self.dte_min <= dte <= self.dte_max):
            return False
        
        # Check minimum premium
        bid = option.get("bid", 0)
        if bid < self.min_premium:
            return False
        
        # Check minimum liquidity
        open_interest = option.get("open_interest", 0)
        if open_interest < self.min_liquidity:
            return False
        
        # NEW: Check minimum IV (filters out low-volatility options)
        iv = option.get("iv", 0)
        if iv < self.min_iv:
            logger.debug(f"Option rejected: IV {iv:.2%} < minimum {self.min_iv:.2%}")
            return False
        
        return True
    
    def rank_all_puts(
        self,
        symbols_with_scores: List[tuple],  # [(symbol, score, options_chain), ...]
    ) -> List[PutScore]:
        """
        Analyze and rank puts across multiple symbols.
        
        Args:
            symbols_with_scores: List of (symbol, symbol_score, options_chain) tuples
            
        Returns:
            Flat list of all qualified puts, sorted by total score
        """
        all_puts: List[PutScore] = []
        
        for symbol, symbol_score, options_chain in symbols_with_scores:
            puts = self.analyze_symbol(symbol, symbol_score, options_chain)
            all_puts.extend(puts)
        
        # Sort globally by score
        all_puts.sort(key=lambda x: x.total_score, reverse=True)
        
        logger.info(f"Ranked {len(all_puts)} total puts across {len(symbols_with_scores)} symbols")
        self._log_top_puts(all_puts[:20])  # Log top 20
        
        return all_puts
    
    def _log_top_puts(self, puts: List[PutScore]):
        """Log top-ranked puts."""
        if not puts:
            return
        
        logger.info("\n" + "="*100)
        logger.info("TOP RANKED PUTS FOR THETA STRATEGY")
        logger.info("="*100)
        logger.info(
            f"{'Rank':<5} {'Symbol':<8} {'Strike':<8} {'Exp':<12} {'DTE':<5} "
            f"{'Bid':<7} {'Delta':<7} {'Score':<6} {'Premium':<10}"
        )
        logger.info("-"*100)
        
        for rank, put in enumerate(puts, 1):
            logger.info(
                f"{rank:<5} {put.symbol:<8} {put.strike:<8.2f} "
                f"{put.expiration.strftime('%Y-%m-%d'):<12} {put.dte:<5} "
                f"${put.bid:<6.2f} {put.delta:<7.3f} {put.total_score:<6} "
                f"${put.expected_premium:<9.0f}"
            )
        
        logger.info("="*100 + "\n")


def get_third_friday(year: int, month: int) -> date:
    """Get third Friday of a given month (standard options expiration)."""
    first_day = date(year, month, 1)
    # Find first Friday
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)
    # Third Friday is 2 weeks later
    third_friday = first_friday + timedelta(weeks=2)
    return third_friday


def get_available_expirations(dte_min: int = 28, dte_max: int = 35) -> List[date]:
    """
    Get list of available third-Friday expirations within DTE range.
    
    Args:
        dte_min: Minimum days to expiration
        dte_max: Maximum days to expiration
        
    Returns:
        List of expiration dates
    """
    today = date.today()
    expirations = []
    
    # Check next 3 months
    for month_offset in range(0, 4):
        target_date = today + timedelta(days=30 * month_offset)
        third_fri = get_third_friday(target_date.year, target_date.month)
        
        dte = (third_fri - today).days
        if dte_min <= dte <= dte_max and third_fri not in expirations:
            expirations.append(third_fri)
    
    return sorted(expirations)
