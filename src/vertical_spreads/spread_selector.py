"""
Vertical Spread Selector
========================

Strike selection and spread construction for vertical spreads.
Calculates optimal strikes based on direction signal, implied move, and account risk.
"""

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class VerticalSpreadSetup:
    """A complete vertical spread trade setup."""
    symbol: str
    strategy: str  # "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD", etc.
    direction: str  # "BULL" or "BEAR"
    
    # Strikes
    buy_strike: float
    sell_strike: float
    option_type: str  # "C" (call) or "P" (put)
    
    # Expiration
    expiration: date
    dte: int
    
    # Pricing
    net_debit: float  # Cost to enter (per contract)
    max_profit: float  # Max profit (per contract)
    max_loss: float  # Max loss (per contract)
    
    # Position sizing
    contracts: int
    total_at_risk: float
    
    # Analysis
    implied_move: float
    confidence: int
    stock_price: float
    
    # Score for ranking
    score: float = 0.0
    
    def __post_init__(self):
        """Calculate score after initialization."""
        self.score = self._calculate_score()
    
    def _calculate_score(self) -> float:
        """
        Score the setup quality (higher = better).
        
        Factors:
        - Confidence level
        - Risk/reward ratio
        - Distance to target
        """
        if self.max_loss == 0:
            return 0
        
        risk_reward = self.max_profit / self.max_loss
        confidence_factor = self.confidence / 100
        
        # Base score on risk/reward and confidence
        score = (risk_reward * 30) + (confidence_factor * 50)
        
        # Bonus for optimal DTE range (7-14 days)
        if 7 <= self.dte <= 14:
            score += 10
        elif 14 < self.dte <= 21:
            score += 5
        
        return round(score, 2)
    
    def __str__(self) -> str:
        return (
            f"{self.strategy} {self.symbol} "
            f"${self.buy_strike}/{self.sell_strike} "
            f"exp {self.expiration.isoformat()} "
            f"({self.contracts}x @ ${self.net_debit:.2f})"
        )


class VerticalSpreadSelector:
    """
    Selects optimal strikes for vertical spreads.
    
    Given a directional signal, selects appropriate strikes based on:
    - Directional confidence
    - Account size & risk tolerance
    - Implied move calculation
    """
    
    def __init__(
        self,
        max_loss_percent: float = 0.02,  # 2% max loss per trade
        default_width: float = 5.0,  # $5 wide spreads
        target_dte_min: int = 7,
        target_dte_max: int = 21,
        preferred_dte: int = 14
    ):
        """
        Initialize selector.
        
        Args:
            max_loss_percent: Maximum loss as fraction of account (0.02 = 2%)
            default_width: Default strike width in dollars
            target_dte_min: Minimum days to expiration
            target_dte_max: Maximum days to expiration
            preferred_dte: Preferred DTE if available
        """
        self.max_loss_percent = max_loss_percent
        self.default_width = default_width
        self.target_dte_min = target_dte_min
        self.target_dte_max = target_dte_max
        self.preferred_dte = preferred_dte
    
    def select_spread(
        self,
        symbol: str,
        stock_price: float,
        direction: str,  # "BULL" or "BEAR"
        confidence: int,  # 0-100
        iv: float,  # Implied volatility (e.g., 0.25 for 25%)
        account_balance: float,
        available_expirations: List[date],
        options_chain: Optional[Dict] = None,
        risk_tolerance: str = "medium"
    ) -> Optional[VerticalSpreadSetup]:
        """
        Select optimal vertical spread for given direction.
        
        Args:
            symbol: Stock symbol
            stock_price: Current stock price
            direction: "BULL" or "BEAR"
            confidence: Direction confidence 0-100
            iv: Implied volatility
            account_balance: Account balance for sizing
            available_expirations: List of available option expiration dates
            options_chain: Optional dict with actual option prices
            risk_tolerance: "conservative", "medium", or "aggressive"
        
        Returns:
            VerticalSpreadSetup or None if no suitable spread found
        """
        if direction == "NEUTRAL":
            logger.debug(f"{symbol}: Neutral direction, skipping")
            return None
        
        # Select expiration
        expiration = self._select_expiration(available_expirations)
        if not expiration:
            logger.warning(f"{symbol}: No suitable expiration found")
            return None
        
        dte = (expiration - date.today()).days
        
        # Calculate implied move
        implied_move = self._calculate_implied_move(stock_price, iv, dte)
        
        # Select strikes based on direction
        if direction == "BULL":
            setup = self._select_bull_call_spread(
                symbol=symbol,
                stock_price=stock_price,
                implied_move=implied_move,
                confidence=confidence,
                expiration=expiration,
                dte=dte,
                account_balance=account_balance,
                risk_tolerance=risk_tolerance,
                options_chain=options_chain
            )
        else:  # BEAR
            setup = self._select_bear_put_spread(
                symbol=symbol,
                stock_price=stock_price,
                implied_move=implied_move,
                confidence=confidence,
                expiration=expiration,
                dte=dte,
                account_balance=account_balance,
                risk_tolerance=risk_tolerance,
                options_chain=options_chain
            )
        
        return setup
    
    def _select_expiration(self, available: List[date]) -> Optional[date]:
        """Select best expiration from available dates."""
        today = date.today()
        
        # Filter to target DTE range
        suitable = [
            exp for exp in available
            if self.target_dte_min <= (exp - today).days <= self.target_dte_max
        ]
        
        if not suitable:
            # Fall back to closest available
            suitable = [
                exp for exp in available
                if (exp - today).days >= self.target_dte_min
            ]
        
        if not suitable:
            return None
        
        # Prefer closest to preferred DTE
        return min(
            suitable, 
            key=lambda x: abs((x - today).days - self.preferred_dte)
        )
    
    def _calculate_implied_move(
        self, 
        price: float, 
        iv: float, 
        dte: int
    ) -> float:
        """
        Calculate expected move based on implied volatility.
        
        Formula: Implied Move ≈ Price × IV × √(DTE/365)
        
        Args:
            price: Current stock price
            iv: Implied volatility (e.g., 0.25)
            dte: Days to expiration
        
        Returns:
            Expected move in dollar terms
        """
        if dte <= 0:
            return 0
        return price * iv * math.sqrt(dte / 365)
    
    def _select_bull_call_spread(
        self,
        symbol: str,
        stock_price: float,
        implied_move: float,
        confidence: int,
        expiration: date,
        dte: int,
        account_balance: float,
        risk_tolerance: str,
        options_chain: Optional[Dict] = None
    ) -> VerticalSpreadSetup:
        """
        Select bull call spread (buy lower strike, sell higher strike).
        
        Bull call spread profits when stock goes UP.
        """
        # Determine strike width based on confidence
        width = self._calculate_strike_width(stock_price, implied_move, confidence)
        
        # Buy strike at current price (ATM or slightly ITM)
        buy_strike = self._round_strike(stock_price)
        
        # Sell strike above based on confidence
        # Higher confidence = sell further OTM (more aggressive, higher reward)
        if confidence >= 75:
            sell_strike = self._round_strike(stock_price + implied_move * 1.2)
        elif confidence >= 60:
            sell_strike = self._round_strike(stock_price + implied_move * 0.8)
        else:
            sell_strike = self._round_strike(stock_price + implied_move * 0.5)
        
        # Ensure valid spread
        if sell_strike <= buy_strike:
            sell_strike = buy_strike + width
        
        # Get pricing (use options_chain if available, otherwise estimate)
        if options_chain:
            net_debit, max_profit = self._get_actual_prices(
                options_chain, buy_strike, sell_strike, "C"
            )
        else:
            net_debit, max_profit = self._estimate_prices(
                buy_strike, sell_strike, stock_price
            )
        
        max_loss = net_debit * 100  # Per contract
        max_profit_per = max_profit * 100
        
        # Calculate contracts based on account and risk
        contracts = self._calculate_contracts(
            max_loss, account_balance, risk_tolerance
        )
        
        return VerticalSpreadSetup(
            symbol=symbol,
            strategy="BULL_CALL_SPREAD",
            direction="BULL",
            buy_strike=buy_strike,
            sell_strike=sell_strike,
            option_type="C",
            expiration=expiration,
            dte=dte,
            net_debit=net_debit,
            max_profit=max_profit_per,
            max_loss=max_loss,
            contracts=contracts,
            total_at_risk=max_loss * contracts,
            implied_move=implied_move,
            confidence=confidence,
            stock_price=stock_price
        )
    
    def _select_bear_put_spread(
        self,
        symbol: str,
        stock_price: float,
        implied_move: float,
        confidence: int,
        expiration: date,
        dte: int,
        account_balance: float,
        risk_tolerance: str,
        options_chain: Optional[Dict] = None
    ) -> VerticalSpreadSetup:
        """
        Select bear put spread (buy higher strike, sell lower strike).
        
        Bear put spread profits when stock goes DOWN.
        """
        # Determine strike width based on confidence
        width = self._calculate_strike_width(stock_price, implied_move, confidence)
        
        # Buy strike at current price (ATM or slightly ITM)
        buy_strike = self._round_strike(stock_price)
        
        # Sell strike below based on confidence
        # Higher confidence = sell further OTM (more aggressive, higher reward)
        if confidence >= 75:
            sell_strike = self._round_strike(stock_price - implied_move * 1.2)
        elif confidence >= 60:
            sell_strike = self._round_strike(stock_price - implied_move * 0.8)
        else:
            sell_strike = self._round_strike(stock_price - implied_move * 0.5)
        
        # Ensure valid spread
        if sell_strike >= buy_strike:
            sell_strike = buy_strike - width
        
        # Get pricing
        if options_chain:
            net_debit, max_profit = self._get_actual_prices(
                options_chain, buy_strike, sell_strike, "P"
            )
        else:
            net_debit, max_profit = self._estimate_prices(
                buy_strike, sell_strike, stock_price
            )
        
        max_loss = net_debit * 100
        max_profit_per = max_profit * 100
        
        contracts = self._calculate_contracts(
            max_loss, account_balance, risk_tolerance
        )
        
        return VerticalSpreadSetup(
            symbol=symbol,
            strategy="BEAR_PUT_SPREAD",
            direction="BEAR",
            buy_strike=buy_strike,
            sell_strike=sell_strike,
            option_type="P",
            expiration=expiration,
            dte=dte,
            net_debit=net_debit,
            max_profit=max_profit_per,
            max_loss=max_loss,
            contracts=contracts,
            total_at_risk=max_loss * contracts,
            implied_move=implied_move,
            confidence=confidence,
            stock_price=stock_price
        )
    
    def _calculate_strike_width(
        self, 
        price: float, 
        implied_move: float, 
        confidence: int
    ) -> float:
        """Calculate strike width based on price and confidence."""
        # Base width
        if price < 20:
            base_width = 1.0
        elif price < 50:
            base_width = 2.5
        elif price < 200:
            base_width = 5.0
        else:
            base_width = 10.0
        
        # Adjust based on confidence
        if confidence >= 75:
            return base_width * 1.5  # Wider for high confidence
        elif confidence >= 60:
            return base_width  # Standard
        else:
            return base_width * 0.8  # Narrower for lower confidence
    
    def _round_strike(self, price: float) -> float:
        """Round price to nearest valid strike increment."""
        if price < 20:
            return round(price * 2) / 2  # $0.50 increments
        elif price < 200:
            return round(price)  # $1 increments
        else:
            return round(price / 5) * 5  # $5 increments
    
    def _get_actual_prices(
        self,
        chain: Dict,
        buy_strike: float,
        sell_strike: float,
        option_type: str
    ) -> Tuple[float, float]:
        """Get actual option prices from chain."""
        # This would query the actual options chain
        # For now, return estimates
        return self._estimate_prices(buy_strike, sell_strike, 0)
    
    def _estimate_prices(
        self,
        buy_strike: float,
        sell_strike: float,
        stock_price: float
    ) -> Tuple[float, float]:
        """
        Estimate debit and profit for spread.
        
        Returns:
            Tuple of (net_debit per share, max_profit per share)
        """
        width = abs(sell_strike - buy_strike)
        
        # Rough estimate: debit is ~40-60% of width
        # depending on how far OTM the sold option is
        net_debit = width * 0.5
        max_profit = width - net_debit
        
        return (net_debit, max_profit)
    
    def _calculate_contracts(
        self,
        max_loss_per_contract: float,
        account_balance: float,
        risk_tolerance: str = "medium"
    ) -> int:
        """
        Calculate number of contracts based on account and risk.
        
        Args:
            max_loss_per_contract: Max loss per contract
            account_balance: Account balance
            risk_tolerance: "conservative" (1%), "medium" (2%), "aggressive" (5%)
        
        Returns:
            Number of contracts (min 1, max 10)
        """
        risk_levels = {
            "conservative": 0.01,
            "medium": 0.02,
            "aggressive": 0.05
        }
        
        max_risk_pct = risk_levels.get(risk_tolerance, 0.02)
        max_total_risk = account_balance * max_risk_pct
        
        if max_loss_per_contract <= 0:
            return 1
        
        contracts = int(max_total_risk / max_loss_per_contract)
        
        return max(1, min(contracts, 10))  # Min 1, max 10


def get_available_expirations(
    target_dte_min: int = 7,
    target_dte_max: int = 21
) -> List[date]:
    """
    Get list of potential expiration dates (mock for testing).
    
    In production, this would query the Tastytrade API.
    """
    today = date.today()
    expirations = []
    
    # Generate weekly expirations for next 4 weeks
    for days in range(target_dte_min, target_dte_max + 7):
        exp_date = today + timedelta(days=days)
        # Friday expirations (options typically expire on Friday)
        if exp_date.weekday() == 4:  # Friday
            expirations.append(exp_date)
    
    return sorted(expirations)
