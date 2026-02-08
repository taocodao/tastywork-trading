"""
Diagonal Spread Selector
========================

Strike selection for diagonal spreads (Poor Man's Covered Call/Put).
Combines ITM long-dated options with OTM short-dated options.

Key concept:
- LONG LEG: Buy deep ITM option (Delta 0.70-0.80) at 45-90 DTE
- SHORT LEG: Sell OTM option (Delta 0.25-0.35) at 7-21 DTE
"""

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DiagonalSpreadSetup:
    """A complete diagonal spread trade setup."""
    symbol: str
    strategy: str  # "BULL_DIAGONAL", "BEAR_DIAGONAL", or "NEUTRAL_DIAGONAL" (calendar-like)
    direction: str  # "BULL", "BEAR", or "NEUTRAL"
    
    # Long leg (back month, ITM)
    long_strike: float
    long_expiration: date
    long_dte: int
    long_delta: float
    long_price: float  # Premium paid
    
    # Short leg (front month, OTM)
    short_strike: float
    short_expiration: date
    short_dte: int
    short_delta: float
    short_price: float  # Premium received
    
    option_type: str  # "C" for calls, "P" for puts
    
    # Economics
    net_debit: float  # long_price - short_price
    max_profit: float  # Theoretical max
    max_loss: float  # net_debit (if spreads collapse)
    break_even: float
    
    # Sizing
    contracts: int
    total_at_risk: float  # net_debit * 100 * contracts
    
    # Confidence
    confidence: int
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
        - DTE balance (short should be 7-21, long should be 45-90)
        """
        # Confidence (40%)
        conf_score = (self.confidence / 100) * 40
        
        # Risk/reward (30%)
        if self.max_loss > 0:
            rr_ratio = self.max_profit / self.max_loss
            rr_score = min(rr_ratio / 2, 1.0) * 30  # Cap at 2:1
        else:
            rr_score = 0
        
        # DTE balance (30%)
        short_dte_ideal = 7 <= self.short_dte <= 21
        long_dte_ideal = 45 <= self.long_dte <= 90
        dte_score = (15 if short_dte_ideal else 5) + (15 if long_dte_ideal else 5)
        
        return conf_score + rr_score + dte_score
    
    def __str__(self) -> str:
        return (
            f"{self.strategy} {self.symbol}: "
            f"Long ${self.long_strike} ({self.long_dte}d) / "
            f"Short ${self.short_strike} ({self.short_dte}d) | "
            f"Debit: ${self.net_debit:.2f} | "
            f"Conf: {self.confidence}%"
        )


class DiagonalSpreadSelector:
    """
    Selects optimal strikes for diagonal spreads.
    
    Given a directional signal, selects:
    - Long leg: Deep ITM, longer-dated (45-90 DTE)
    - Short leg: OTM, shorter-dated (7-21 DTE)
    """
    
    def __init__(
        self,
        max_loss_percent: float = 0.03,  # 3% max loss per trade
        long_target_delta: float = 0.75,  # Deep ITM
        short_target_delta: float = 0.30,  # OTM
        short_dte_min: int = 7,
        short_dte_max: int = 21,
        long_dte_min: int = 45,
        long_dte_max: int = 90
    ):
        """
        Initialize selector.
        
        Args:
            max_loss_percent: Maximum loss as fraction of account
            long_target_delta: Target delta for long leg (0.70-0.80)
            short_target_delta: Target delta for short leg (0.25-0.35)
            short_dte_min/max: Short leg DTE range
            long_dte_min/max: Long leg DTE range
        """
        self.max_loss_percent = max_loss_percent
        self.long_target_delta = long_target_delta
        self.short_target_delta = short_target_delta
        self.short_dte_min = short_dte_min
        self.short_dte_max = short_dte_max
        self.long_dte_min = long_dte_min
        self.long_dte_max = long_dte_max
    
    def select_spread(
        self,
        symbol: str,
        stock_price: float,
        direction: str,  # "BULL", "BEAR", or "NEUTRAL"
        confidence: int,
        iv: float,
        account_balance: float,
        available_expirations: List[date],
        options_chain: Optional[Dict] = None,
        risk_tolerance: str = "medium"
    ) -> Optional[DiagonalSpreadSetup]:
        """
        Select optimal diagonal spread for given direction.
        
        Args:
            symbol: Stock symbol
            stock_price: Current stock price
            direction: "BULL", "BEAR", or "NEUTRAL"
            confidence: Direction confidence 0-100
            iv: Implied volatility
            account_balance: Account balance for sizing
            available_expirations: Available expiration dates
            options_chain: Optional chain data for real prices
            risk_tolerance: "conservative", "medium", "aggressive"
        
        Returns:
            DiagonalSpreadSetup or None
        """
        if direction not in ("BULL", "BEAR", "NEUTRAL"):
            logger.warning(f"Invalid direction: {direction}")
            return None
        
        # Select expirations
        short_exp = self._select_short_expiration(available_expirations)
        long_exp = self._select_long_expiration(available_expirations)
        
        if not short_exp or not long_exp:
            logger.warning(f"{symbol}: Could not find suitable expirations")
            return None
        
        if short_exp >= long_exp:
            logger.warning(f"{symbol}: Short exp {short_exp} >= long exp {long_exp}")
            return None
        
        short_dte = (short_exp - date.today()).days
        long_dte = (long_exp - date.today()).days
        
        # Select strikes based on direction
        if direction == "BULL":
            return self._select_bull_diagonal(
                symbol=symbol,
                stock_price=stock_price,
                confidence=confidence,
                iv=iv,
                short_exp=short_exp,
                long_exp=long_exp,
                short_dte=short_dte,
                long_dte=long_dte,
                account_balance=account_balance,
                risk_tolerance=risk_tolerance,
                options_chain=options_chain
            )
        elif direction == "BEAR":
            return self._select_bear_diagonal(
                symbol=symbol,
                stock_price=stock_price,
                confidence=confidence,
                iv=iv,
                short_exp=short_exp,
                long_exp=long_exp,
                short_dte=short_dte,
                long_dte=long_dte,
                account_balance=account_balance,
                risk_tolerance=risk_tolerance,
                options_chain=options_chain
            )
        else:  # NEUTRAL - calendar-like structure
            return self._select_neutral_diagonal(
                symbol=symbol,
                stock_price=stock_price,
                confidence=confidence,
                iv=iv,
                short_exp=short_exp,
                long_exp=long_exp,
                short_dte=short_dte,
                long_dte=long_dte,
                account_balance=account_balance,
                risk_tolerance=risk_tolerance,
                options_chain=options_chain
            )
    
    def _select_short_expiration(self, available: List[date]) -> Optional[date]:
        """Select best short-dated expiration (7-21 DTE)."""
        today = date.today()
        valid = []
        
        for exp in available:
            if isinstance(exp, datetime):
                exp = exp.date()
            dte = (exp - today).days
            if self.short_dte_min <= dte <= self.short_dte_max:
                valid.append((exp, dte))
        
        if not valid:
            # Fallback: find closest to 14 DTE
            for exp in available:
                if isinstance(exp, datetime):
                    exp = exp.date()
                dte = (exp - today).days
                if 5 <= dte <= 30:
                    valid.append((exp, abs(dte - 14)))  # Distance from ideal
            
            if valid:
                valid.sort(key=lambda x: x[1])
                return valid[0][0]
            return None
        
        # Prefer ~14 DTE
        valid.sort(key=lambda x: abs(x[1] - 14))
        return valid[0][0]
    
    def _select_long_expiration(self, available: List[date]) -> Optional[date]:
        """Select best long-dated expiration (45-90 DTE)."""
        today = date.today()
        valid = []
        
        for exp in available:
            if isinstance(exp, datetime):
                exp = exp.date()
            dte = (exp - today).days
            if self.long_dte_min <= dte <= self.long_dte_max:
                valid.append((exp, dte))
        
        if not valid:
            # Fallback: find closest to 60 DTE
            for exp in available:
                if isinstance(exp, datetime):
                    exp = exp.date()
                dte = (exp - today).days
                if 30 <= dte <= 120:
                    valid.append((exp, abs(dte - 60)))
            
            if valid:
                valid.sort(key=lambda x: x[1])
                return valid[0][0]
            return None
        
        # Prefer ~60 DTE
        valid.sort(key=lambda x: abs(x[1] - 60))
        return valid[0][0]
    
    def _select_bull_diagonal(
        self,
        symbol: str,
        stock_price: float,
        confidence: int,
        iv: float,
        short_exp: date,
        long_exp: date,
        short_dte: int,
        long_dte: int,
        account_balance: float,
        risk_tolerance: str,
        options_chain: Optional[Dict] = None
    ) -> Optional[DiagonalSpreadSetup]:
        """
        Select bull diagonal (Poor Man's Covered Call).
        
        Structure:
        - Buy ITM Call (long-dated)
        - Sell OTM Call (short-dated)
        """
        # Calculate implied move for strike selection
        implied_move = stock_price * iv * math.sqrt(long_dte / 365)
        
        # Long strike: ITM by ~0.5 implied moves
        long_strike = self._round_strike(stock_price - (implied_move * 0.5))
        long_delta = 0.75  # Estimated for deep ITM
        
        # Short strike: OTM by ~0.5 implied moves
        short_strike = self._round_strike(stock_price + (implied_move * 0.5))
        short_delta = 0.30  # Estimated for OTM
        
        # Estimate prices if no chain provided
        if options_chain:
            long_price, short_price = self._get_actual_prices(
                options_chain, long_strike, short_strike, long_exp, short_exp, "C"
            )
        else:
            long_price, short_price = self._estimate_prices(
                stock_price, long_strike, short_strike, iv, long_dte, short_dte
            )
        
        net_debit = long_price - short_price
        if net_debit <= 0:
            logger.warning(f"{symbol}: Invalid net debit ${net_debit:.2f}")
            return None
        
        # Calculate P&L
        strike_width = short_strike - long_strike
        max_profit = (strike_width - net_debit) * 100  # Per contract
        max_loss = net_debit * 100  # Per contract
        break_even = long_strike + net_debit
        
        # Calculate contracts
        contracts = self._calculate_contracts(
            max_loss, account_balance, risk_tolerance
        )
        
        return DiagonalSpreadSetup(
            symbol=symbol,
            strategy="BULL_DIAGONAL",
            direction="BULL",
            long_strike=long_strike,
            long_expiration=long_exp,
            long_dte=long_dte,
            long_delta=long_delta,
            long_price=long_price,
            short_strike=short_strike,
            short_expiration=short_exp,
            short_dte=short_dte,
            short_delta=short_delta,
            short_price=short_price,
            option_type="C",
            net_debit=net_debit,
            max_profit=max_profit,
            max_loss=max_loss,
            break_even=break_even,
            contracts=contracts,
            total_at_risk=max_loss * contracts,
            confidence=confidence
        )
    
    def _select_bear_diagonal(
        self,
        symbol: str,
        stock_price: float,
        confidence: int,
        iv: float,
        short_exp: date,
        long_exp: date,
        short_dte: int,
        long_dte: int,
        account_balance: float,
        risk_tolerance: str,
        options_chain: Optional[Dict] = None
    ) -> Optional[DiagonalSpreadSetup]:
        """
        Select bear diagonal (Poor Man's Covered Put).
        
        Structure:
        - Buy ITM Put (long-dated)
        - Sell OTM Put (short-dated)
        """
        implied_move = stock_price * iv * math.sqrt(long_dte / 365)
        
        # Long strike: ITM by ~0.5 implied moves (higher than stock)
        long_strike = self._round_strike(stock_price + (implied_move * 0.5))
        long_delta = -0.75
        
        # Short strike: OTM by ~0.5 implied moves (lower than stock)
        short_strike = self._round_strike(stock_price - (implied_move * 0.5))
        short_delta = -0.30
        
        if options_chain:
            long_price, short_price = self._get_actual_prices(
                options_chain, long_strike, short_strike, long_exp, short_exp, "P"
            )
        else:
            long_price, short_price = self._estimate_prices(
                stock_price, long_strike, short_strike, iv, long_dte, short_dte
            )
        
        net_debit = long_price - short_price
        if net_debit <= 0:
            logger.warning(f"{symbol}: Invalid net debit ${net_debit:.2f}")
            return None
        
        strike_width = long_strike - short_strike
        max_profit = (strike_width - net_debit) * 100
        max_loss = net_debit * 100
        break_even = long_strike - net_debit
        
        contracts = self._calculate_contracts(
            max_loss, account_balance, risk_tolerance
        )
        
        return DiagonalSpreadSetup(
            symbol=symbol,
            strategy="BEAR_DIAGONAL",
            direction="BEAR",
            long_strike=long_strike,
            long_expiration=long_exp,
            long_dte=long_dte,
            long_delta=long_delta,
            long_price=long_price,
            short_strike=short_strike,
            short_expiration=short_exp,
            short_dte=short_dte,
            short_delta=short_delta,
            short_price=short_price,
            option_type="P",
            net_debit=net_debit,
            max_profit=max_profit,
            max_loss=max_loss,
            break_even=break_even,
            contracts=contracts,
            total_at_risk=max_loss * contracts,
            confidence=confidence
        )
    
    def _select_neutral_diagonal(
        self,
        symbol: str,
        stock_price: float,
        confidence: int,
        iv: float,
        short_exp: date,
        long_exp: date,
        short_dte: int,
        long_dte: int,
        account_balance: float,
        risk_tolerance: str,
        options_chain: Optional[Dict] = None
    ) -> Optional[DiagonalSpreadSetup]:
        """
        Select neutral diagonal (Calendar-like structure).
        
        Structure:
        - Both strikes at ATM (same strike, different expirations)
        - This is essentially a calendar spread under the diagonal framework
        """
        # Both strikes at ATM
        strike = self._round_strike(stock_price)
        
        # Use calls by default for neutral (ATM delta ~0.50)
        delta = 0.50
        
        if options_chain:
            long_price, short_price = self._get_actual_prices(
                options_chain, strike, strike, long_exp, short_exp, "C"
            )
        else:
            long_price, short_price = self._estimate_calendar_prices(
                stock_price, strike, iv, long_dte, short_dte
            )
        
        net_debit = long_price - short_price
        if net_debit <= 0:
            logger.warning(f"{symbol}: Invalid net debit ${net_debit:.2f}")
            return None
        
        # Calendar max profit is theoretical (when short expires worthless, long retains value)
        # Max profit is hard to estimate without Greeks, use ~50% of debit as target
        max_profit = net_debit * 100 * 0.50  # Conservative estimate
        max_loss = net_debit * 100  # Max loss = net debit
        break_even = strike  # Roughly ATM
        
        contracts = self._calculate_contracts(
            max_loss, account_balance, risk_tolerance
        )
        
        return DiagonalSpreadSetup(
            symbol=symbol,
            strategy="NEUTRAL_DIAGONAL",
            direction="NEUTRAL",
            long_strike=strike,
            long_expiration=long_exp,
            long_dte=long_dte,
            long_delta=delta,
            long_price=long_price,
            short_strike=strike,  # Same strike for calendar
            short_expiration=short_exp,
            short_dte=short_dte,
            short_delta=delta,
            short_price=short_price,
            option_type="C",
            net_debit=net_debit,
            max_profit=max_profit,
            max_loss=max_loss,
            break_even=break_even,
            contracts=contracts,
            total_at_risk=max_loss * contracts,
            confidence=confidence
        )
    
    def _estimate_calendar_prices(
        self,
        stock_price: float,
        strike: float,
        iv: float,
        long_dte: int,
        short_dte: int
    ) -> Tuple[float, float]:
        """
        Estimate ATM option prices for calendar spread.
        ATM options are roughly: price ≈ stock * IV * sqrt(DTE/365) * 0.4
        """
        long_price = stock_price * iv * math.sqrt(long_dte / 365) * 0.40
        short_price = stock_price * iv * math.sqrt(short_dte / 365) * 0.40
        return round(long_price, 2), round(short_price, 2)
    
    def _round_strike(self, price: float) -> float:
        """Round to nearest valid strike."""
        if price < 50:
            return round(price / 1) * 1  # $1 increments
        elif price < 200:
            return round(price / 5) * 5  # $5 increments
        else:
            return round(price / 10) * 10  # $10 increments
    
    def _estimate_prices(
        self,
        stock_price: float,
        long_strike: float,
        short_strike: float,
        iv: float,
        long_dte: int,
        short_dte: int
    ) -> Tuple[float, float]:
        """
        Estimate option prices using simplified Black-Scholes approximation.
        """
        # Long leg (ITM, longer-dated)
        intrinsic = max(0, stock_price - long_strike)
        time_value_long = stock_price * iv * math.sqrt(long_dte / 365) * 0.4
        long_price = intrinsic + time_value_long
        
        # Short leg (OTM, shorter-dated)
        time_value_short = stock_price * iv * math.sqrt(short_dte / 365) * 0.25
        short_price = time_value_short
        
        return round(long_price, 2), round(short_price, 2)
    
    def _get_actual_prices(
        self,
        chain: Dict,
        long_strike: float,
        short_strike: float,
        long_exp: date,
        short_exp: date,
        option_type: str
    ) -> Tuple[float, float]:
        """Get actual option prices from chain data."""
        # Implementation would look up real prices
        # For now, return estimated values
        return 0.0, 0.0
    
    def _calculate_contracts(
        self,
        max_loss_per_contract: float,
        account_size: float,
        risk_tolerance: str
    ) -> int:
        """Calculate number of contracts based on risk."""
        risk_pcts = {
            "conservative": 0.01,
            "medium": 0.02,
            "aggressive": 0.03
        }
        risk_pct = risk_pcts.get(risk_tolerance, 0.02)
        
        max_total_risk = account_size * risk_pct
        contracts = int(max_total_risk / max_loss_per_contract)
        
        return max(1, min(contracts, 10))  # 1-10 contracts


def get_available_expirations(weeks_ahead: int = 16) -> List[date]:
    """Generate list of Friday expirations for testing."""
    expirations = []
    current = date.today()
    
    # Find next Friday
    days_until_friday = (4 - current.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7
    next_friday = current + timedelta(days=days_until_friday)
    
    # Generate weekly expirations
    for i in range(weeks_ahead):
        expirations.append(next_friday + timedelta(weeks=i))
    
    return expirations
