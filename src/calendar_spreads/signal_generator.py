"""
Calendar Spread Signal Generator
==================================
Combines VOSS filter, DTE/Strike selectors, and Earnings Intelligence
to generate validated calendar spread entry signals.

Process:
1. Check earnings safety (EarningsStrategyRouter)
2. Select DTEs based on IV (DTESelector)
3. Filter options for liquidity (VOSSLiquidityFilter)
4. Select optimal strike (CalendarStrikeSelector)
5. Calculate Greeks and pricing
6. Generate signal with confidence score
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Dict, Any
import pandas as pd
import logging

from .voss_filter import VOSSLiquidityFilter, VOSSCriteria
from .dte_selector import DTESelector, DTEConfig
from .strike_selector import CalendarStrikeSelector, StrikeConfig
from .earnings_intelligence import (
    EarningsStrategyRouter, 
    EarningsRouterConfig,
    StrategyDecision,
    EarningsDecision,
    IVCrushPredictor
)

logger = logging.getLogger(__name__)


@dataclass
class CalendarSpreadSignal:
    """
    Complete signal for calendar spread entry
    
    Contains all information needed to execute the trade
    """
    # Identifier
    id: str = ""
    
    # Core trade parameters
    symbol: str = ""
    strike: float = 0.0
    short_expiry: date = None
    long_expiry: date = None
    option_type: str = "C"  # 'C' for calls, 'P' for puts
    
    # Pricing
    net_debit: float = 0.0  # Cost to enter
    short_price: float = 0.0  # Credit from short leg
    long_price: float = 0.0  # Debit for long leg
    stock_price: float = 0.0
    
    # Greeks (net position)
    net_delta: float = 0.0
    net_gamma: float = 0.0
    net_theta: float = 0.0  # Daily theta (positive = earning)
    net_vega: float = 0.0   # Vega exposure
    
    # Scoring
    confidence_score: float = 0.0
    liquidity_score: float = 0.0
    theta_edge: float = 0.0  # Daily theta in dollars
    
    # IV context
    iv_rank: float = 0.0
    short_iv: float = 0.0
    long_iv: float = 0.0
    iv_differential: float = 0.0  # short_iv - long_iv
    
    # Earnings context
    days_to_earnings: int = 999
    earnings_decision: str = "APPROVE"
    earnings_date: Optional[date] = None
    
    # Position sizing
    quantity: int = 1
    max_risk: float = 0.0  # Maximum loss (net debit * 100)
    
    # Targets
    profit_target_pct: float = 35.0  # 35% target
    stop_loss_pct: float = 50.0  # 50% stop
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    expiry_window: str = ""  # e.g., "7/40 DTE"
    rationale: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'strike': self.strike,
            'short_expiry': self.short_expiry.isoformat() if self.short_expiry else None,
            'long_expiry': self.long_expiry.isoformat() if self.long_expiry else None,
            'option_type': self.option_type,
            'net_debit': round(self.net_debit, 2),
            'stock_price': round(self.stock_price, 2),
            'net_delta': round(self.net_delta, 3),
            'net_theta': round(self.net_theta, 3),
            'net_vega': round(self.net_vega, 3),
            'confidence_score': round(self.confidence_score, 1),
            'liquidity_score': round(self.liquidity_score, 2),
            'theta_edge': round(self.theta_edge, 2),
            'iv_rank': round(self.iv_rank, 1),
            'iv_differential': round(self.iv_differential * 100, 1),  # As percentage
            'days_to_earnings': self.days_to_earnings,
            'earnings_decision': self.earnings_decision,
            'quantity': self.quantity,
            'max_risk': round(self.max_risk, 2),
            'profit_target_pct': self.profit_target_pct,
            'stop_loss_pct': self.stop_loss_pct,
            'created_at': self.created_at.isoformat(),
            'expiry_window': self.expiry_window,
            'rationale': self.rationale
        }
    
    def get_cost(self) -> float:
        """Total cost to enter the spread"""
        return self.net_debit * 100 * self.quantity
    
    def get_profit_target(self) -> float:
        """Dollar profit target"""
        return self.get_cost() * (self.profit_target_pct / 100)
    
    def get_stop_loss(self) -> float:
        """Dollar stop loss amount"""
        return self.get_cost() * (self.stop_loss_pct / 100)


@dataclass
class GeneratorConfig:
    """Configuration for signal generator"""
    min_confidence_score: float = 60.0
    min_liquidity_score: float = 0.3
    min_theta_edge: float = 0.50  # $0.50/day minimum theta
    
    # Targets
    default_profit_target_pct: float = 35.0
    default_stop_loss_pct: float = 50.0
    
    # Position sizing
    max_contracts: int = 5
    max_risk_per_trade: float = 500.0  # Max $500 per trade


class CalendarSignalGenerator:
    """
    Generate calendar spread entry signals
    
    Integrates:
    - VOSS liquidity filtering
    - DTE selection
    - Strike selection  
    - Earnings intelligence
    
    Usage:
        generator = CalendarSignalGenerator()
        
        signals = generator.generate_signals(
            symbol='SPY',
            stock_price=450.0,
            iv_rank=65.0,
            options_data=chain_data,
            expirations=[exp1, exp2, exp3, ...]
        )
        
        for signal in signals:
            if signal.confidence_score >= 70:
                # Execute trade
                pass
    """
    
    def __init__(self,
                 config: Optional[GeneratorConfig] = None,
                 voss_filter: Optional[VOSSLiquidityFilter] = None,
                 dte_selector: Optional[DTESelector] = None,
                 strike_selector: Optional[CalendarStrikeSelector] = None,
                 earnings_router: Optional[EarningsStrategyRouter] = None):
        
        self.config = config or GeneratorConfig()
        self.voss_filter = voss_filter or VOSSLiquidityFilter()
        self.dte_selector = dte_selector or DTESelector()
        self.strike_selector = strike_selector or CalendarStrikeSelector()
        self.earnings_router = earnings_router or EarningsStrategyRouter()
    
    def generate_signals(self,
                        symbol: str,
                        stock_price: float,
                        iv_rank: float,
                        options_data: Dict[str, pd.DataFrame],
                        expirations: List[datetime],
                        option_type: str = 'C') -> List[CalendarSpreadSignal]:
        """
        Generate calendar spread signals for a symbol
        
        Args:
            symbol: Underlying symbol
            stock_price: Current stock price
            iv_rank: Current IV rank (0-100)
            options_data: Dictionary of options chains by expiration date string
            expirations: List of available expiration dates
            option_type: 'C' for calls, 'P' for puts
        
        Returns:
            List of CalendarSpreadSignal objects (may be empty)
        """
        signals = []
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Generating signals for {symbol} @ ${stock_price:.2f}")
        logger.info(f"IV Rank: {iv_rank:.0f}% | Available expirations: {len(expirations)}")
        logger.info(f"{'='*60}")
        
        # Step 1: Check earnings
        earnings_decision = self.earnings_router.decide(
            symbol=symbol,
            current_iv_rank=iv_rank
        )
        
        if earnings_decision.action == StrategyDecision.REJECT:
            logger.info(f"[SKIP] {symbol}: {earnings_decision.reason}")
            return signals
        
        # Step 2: Select DTEs based on IV
        short_exp, long_exp = self.dte_selector.select_calendar_expirations(
            iv_rank=iv_rank,
            available_expirations=expirations
        )
        
        if short_exp is None or long_exp is None:
            logger.warning(f"[SKIP] {symbol}: No valid expirations found")
            return signals
        
        # Step 3: Get option chains for selected expirations
        short_key = short_exp.strftime('%Y%m%d')
        long_key = long_exp.strftime('%Y%m%d')
        
        short_chain = options_data.get(short_key)
        long_chain = options_data.get(long_key)
        
        if short_chain is None or long_chain is None:
            # Try alternative key formats
            for key in options_data.keys():
                if short_exp.strftime('%Y-%m-%d') in key:
                    short_chain = options_data[key]
                if long_exp.strftime('%Y-%m-%d') in key:
                    long_chain = options_data[key]
        
        if short_chain is None or short_chain.empty:
            logger.warning(f"[SKIP] {symbol}: Missing short expiry chain ({short_key})")
            return signals
        
        if long_chain is None or long_chain.empty:
            logger.warning(f"[SKIP] {symbol}: Missing long expiry chain ({long_key})")
            return signals
        
        # Filter by option type (calls or puts)
        if 'right' in short_chain.columns:
            short_chain = short_chain[short_chain['right'] == option_type]
            long_chain = long_chain[long_chain['right'] == option_type]
        
        # Step 4: Apply VOSS liquidity filter
        short_filtered = self.voss_filter.filter_options_chain(short_chain)
        long_filtered = self.voss_filter.filter_options_chain(long_chain)
        
        if short_filtered.empty:
            logger.info(f"[SKIP] {symbol}: No liquid options at short expiry")
            return signals
        
        if long_filtered.empty:
            logger.info(f"[SKIP] {symbol}: No liquid options at long expiry")
            return signals
        
        # Step 5: Select optimal strike
        # Try theta-optimal first, then delta-based
        strike = self.strike_selector.select_theta_optimal_strike(
            short_chain=short_filtered,
            long_chain=long_filtered,
            current_price=stock_price
        )
        
        if strike is None:
            strike = self.strike_selector.select_strike(
                chain=short_filtered,
                current_price=stock_price,
                strategy_bias='neutral'
            )
        
        if strike is None:
            logger.warning(f"[SKIP] {symbol}: Could not select strike")
            return signals
        
        # Step 6: Get option data at selected strike
        short_opt = short_filtered[short_filtered['strike'] == strike]
        long_opt = long_filtered[long_filtered['strike'] == strike]
        
        if short_opt.empty or long_opt.empty:
            logger.warning(f"[SKIP] {symbol}: Strike ${strike} not available in both chains")
            return signals
        
        # Extract pricing
        short_data = short_opt.iloc[0]
        long_data = long_opt.iloc[0]
        
        short_mid = (short_data.get('bid', 0) + short_data.get('ask', 0)) / 2
        long_mid = (long_data.get('bid', 0) + long_data.get('ask', 0)) / 2
        net_debit = long_mid - short_mid
        
        if net_debit <= 0:
            logger.warning(f"[SKIP] {symbol}: Invalid net debit ${net_debit:.2f}")
            return signals
        
        # Step 7: Calculate Greeks
        net_delta = short_data.get('delta', 0) - long_data.get('delta', 0)
        net_gamma = short_data.get('gamma', 0) - long_data.get('gamma', 0)
        net_theta = abs(short_data.get('theta', 0)) - abs(long_data.get('theta', 0))
        net_vega = long_data.get('vega', 0) - short_data.get('vega', 0)
        
        # Theta edge in dollars (per day)
        theta_edge = net_theta * 100
        
        # IV differential
        short_iv = short_data.get('impliedVolatility', 0) or short_data.get('iv', 0)
        long_iv = long_data.get('impliedVolatility', 0) or long_data.get('iv', 0)
        iv_diff = short_iv - long_iv if short_iv and long_iv else 0
        
        # Step 8: Calculate confidence score
        liquidity_score = short_data.get('liquidity_score', 0.5)
        confidence = self._calculate_confidence(
            iv_rank=iv_rank,
            liquidity_score=liquidity_score,
            theta_edge=theta_edge,
            iv_differential=iv_diff,
            days_to_earnings=earnings_decision.days_to_earnings,
            net_debit=net_debit
        )
        
        # Step 9: Check thresholds
        if confidence < self.config.min_confidence_score:
            logger.info(
                f"[SKIP] {symbol}: Confidence {confidence:.0f} < {self.config.min_confidence_score}"
            )
            return signals
        
        if liquidity_score < self.config.min_liquidity_score:
            logger.info(
                f"[SKIP] {symbol}: Liquidity {liquidity_score:.2f} < {self.config.min_liquidity_score}"
            )
            return signals
        
        if theta_edge < self.config.min_theta_edge:
            logger.info(
                f"[SKIP] {symbol}: Theta edge ${theta_edge:.2f} < ${self.config.min_theta_edge}"
            )
            return signals
        
        # Step 10: Calculate position size
        quantity = self._calculate_quantity(
            net_debit=net_debit,
            size_multiplier=earnings_decision.size_multiplier
        )
        
        max_risk = net_debit * 100 * quantity
        
        # Step 11: Build signal
        import uuid
        
        short_dte = (short_exp - datetime.now()).days
        long_dte = (long_exp - datetime.now()).days
        
        signal = CalendarSpreadSignal(
            id=str(uuid.uuid4()),
            symbol=symbol,
            strike=strike,
            short_expiry=short_exp.date(),
            long_expiry=long_exp.date(),
            option_type=option_type,
            net_debit=net_debit,
            short_price=short_mid,
            long_price=long_mid,
            stock_price=stock_price,
            net_delta=net_delta,
            net_gamma=net_gamma,
            net_theta=net_theta,
            net_vega=net_vega,
            confidence_score=confidence,
            liquidity_score=liquidity_score,
            theta_edge=theta_edge,
            iv_rank=iv_rank,
            short_iv=short_iv,
            long_iv=long_iv,
            iv_differential=iv_diff,
            days_to_earnings=earnings_decision.days_to_earnings,
            earnings_decision=earnings_decision.action.value,
            earnings_date=earnings_decision.earnings_date,
            quantity=quantity,
            max_risk=max_risk,
            profit_target_pct=self.config.default_profit_target_pct,
            stop_loss_pct=self.config.default_stop_loss_pct,
            expiry_window=f"{short_dte}/{long_dte} DTE",
            rationale=self._build_rationale(
                symbol=symbol,
                strike=strike,
                iv_rank=iv_rank,
                theta_edge=theta_edge,
                confidence=confidence,
                earnings_decision=earnings_decision
            )
        )
        
        signals.append(signal)
        
        logger.info(f"✅ Signal generated: {symbol} ${strike} calendar")
        logger.info(f"   Cost: ${net_debit:.2f} | Theta: ${theta_edge:.2f}/day | Conf: {confidence:.0f}")
        logger.info(f"   Expirations: {short_exp.date()} / {long_exp.date()}")
        
        return signals
    
    def _calculate_confidence(self,
                            iv_rank: float,
                            liquidity_score: float,
                            theta_edge: float,
                            iv_differential: float,
                            days_to_earnings: int,
                            net_debit: float) -> float:
        """
        Calculate confidence score (0-100)
        
        Components:
        - IV rank: Higher is better for calendars (30%)
        - Liquidity: Higher is better (25%)
        - Theta edge: More theta = better (20%)
        - IV differential: Positive is ideal (10%)
        - Earnings safety: Further is better (15%)
        """
        # IV rank contribution (higher IV = better for vega-long calendars)
        iv_score = min(iv_rank, 100) * 0.30
        
        # Liquidity contribution
        liq_score = min(liquidity_score, 1.0) * 100 * 0.25
        
        # Theta edge contribution (cap at $2/day = 100%)
        theta_pct = min(theta_edge / 2.0, 1.0) * 100 * 0.20
        
        # IV differential (positive = backwardation = good)
        iv_diff_score = 0.10 * 100 if iv_differential > 0 else 0.05 * 100
        
        # Earnings safety
        if days_to_earnings > 14:
            earnings_score = 100 * 0.15
        elif days_to_earnings > 7:
            earnings_score = 75 * 0.15
        elif days_to_earnings > 3:
            earnings_score = 50 * 0.15
        else:
            earnings_score = 25 * 0.15
        
        total = iv_score + liq_score + theta_pct + iv_diff_score + earnings_score
        
        return round(total, 1)
    
    def _calculate_quantity(self,
                          net_debit: float,
                          size_multiplier: float = 1.0) -> int:
        """Calculate position size based on risk limits"""
        cost_per_contract = net_debit * 100
        
        if cost_per_contract <= 0:
            return 0
        
        # Max contracts from risk limit
        max_from_risk = int(self.config.max_risk_per_trade / cost_per_contract)
        
        # Apply size multiplier from earnings decision
        adjusted = int(max_from_risk * size_multiplier)
        
        # Cap at maximum contracts
        quantity = min(adjusted, self.config.max_contracts)
        
        return max(quantity, 1)  # At least 1 contract
    
    def _build_rationale(self,
                        symbol: str,
                        strike: float,
                        iv_rank: float,
                        theta_edge: float,
                        confidence: float,
                        earnings_decision: EarningsDecision) -> str:
        """Build human-readable rationale for the signal"""
        parts = []
        
        # IV context
        if iv_rank >= 70:
            parts.append(f"High IV ({iv_rank:.0f}%)")
        elif iv_rank >= 50:
            parts.append(f"Elevated IV ({iv_rank:.0f}%)")
        else:
            parts.append(f"Moderate IV ({iv_rank:.0f}%)")
        
        # Theta edge
        parts.append(f"${theta_edge:.2f}/day theta edge")
        
        # Confidence
        if confidence >= 80:
            parts.append("high confidence setup")
        elif confidence >= 70:
            parts.append("good confidence")
        else:
            parts.append("acceptable confidence")
        
        # Earnings
        if earnings_decision.days_to_earnings < 999:
            parts.append(f"{earnings_decision.days_to_earnings}d to earnings")
        
        return "; ".join(parts)
    
    def batch_generate(self,
                      symbols: List[str],
                      market_data: Dict[str, dict],
                      options_data: Dict[str, Dict[str, pd.DataFrame]]) -> List[CalendarSpreadSignal]:
        """
        Generate signals for multiple symbols
        
        Args:
            symbols: List of symbols to analyze
            market_data: Dict of {symbol: {stock_price, iv_rank, expirations}}
            options_data: Dict of {symbol: {exp_date: chain_df}}
        
        Returns:
            List of all generated signals across symbols
        """
        all_signals = []
        
        for symbol in symbols:
            if symbol not in market_data:
                logger.warning(f"No market data for {symbol}")
                continue
            
            data = market_data[symbol]
            chains = options_data.get(symbol, {})
            
            signals = self.generate_signals(
                symbol=symbol,
                stock_price=data.get('stock_price', 0),
                iv_rank=data.get('iv_rank', 50),
                options_data=chains,
                expirations=data.get('expirations', [])
            )
            
            all_signals.extend(signals)
        
        # Sort by confidence
        all_signals.sort(key=lambda s: s.confidence_score, reverse=True)
        
        logger.info(f"\nBatch complete: {len(all_signals)} signals from {len(symbols)} symbols")
        
        return all_signals
