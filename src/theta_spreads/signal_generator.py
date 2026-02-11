"""
Signal Generator for Theta Strategy
====================================

Generates entry and exit signals for cash-secured put selling.

Entry Signals:
- Apply 8 filters (delta, expiration, DTE, IV, liquidity, premium, capital, overlap)
- Include capital requirements and expected returns
- Respect max positions and heat limits

Exit Signals:
- Time-based profit targets (50%/60%/75%/90% by week)
- Close to expiration triggers
- Defensive exits (underlying breach)
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional
from enum import Enum
import uuid

from .options_analyzer import PutScore

# Import signal dataclasses from signal_publisher (they have to_dict() method)
from signal_publisher.theta import ThetaEntrySignal, ThetaExitSignal

logger = logging.getLogger(__name__)


class ExitReason(Enum):
    """Exit signal reasons."""
    PROFIT_TARGET = "PROFIT_TARGET"
    EXPIRATION_IMMINENT = "EXPIRATION_IMMINENT"
    DEFENSIVE_CLOSE = "DEFENSIVE_CLOSE"
    MAX_LOSS = "MAX_LOSS"


class ThetaSignalGenerator:
    """
    Generate entry and exit signals for Theta strategy.
    
    Usage:
        generator = ThetaSignalGenerator()
        entry_signals = generator.generate_entry_signals(ranked_puts, portfolio)
        exit_signals = generator.generate_exit_signals(open_positions)
    """
    
    def __init__(
        self,
        contracts_per_trade: int = 10,
        max_positions: int = 6,
        max_portfolio_heat: float = 50000,
        min_confidence: int = 60,
        week1_profit_pct: float = 50.0,
        week2_profit_pct: float = 60.0,
        week3_profit_pct: float = 75.0,
        week4_profit_pct: float = 90.0,
        dte_expiration_threshold: int = 3,
        defensive_breach_pct: float = 2.0
    ):
        """
        Initialize signal generator.
        
        Args:
            contracts_per_trade: Number of contracts per signal (default: 10)
            max_positions: Maximum open positions (default: 6)
            max_portfolio_heat: Maximum capital at risk (default: $50K)
            min_confidence: Minimum put confidence score (default: 60)
            week1_profit_pct: Week 1 profit target % (default: 50%)
            week2_profit_pct: Week 2 profit target % (default: 60%)
            week3_profit_pct: Week 3 profit target % (default: 75%)
            week4_profit_pct: Week 4 profit target % (default: 90%)
            dte_expiration_threshold: Close if DTE <= this (default: 3)
            defensive_breach_pct: Close if underlying < strike * (1 - pct/100) (default: 2%)
        """
        self.contracts_per_trade = contracts_per_trade
        self.max_positions = max_positions
        self.max_portfolio_heat = max_portfolio_heat
        self.min_confidence = min_confidence
        
        # Time-based exit targets
        self.week1_profit_pct = week1_profit_pct
        self.week2_profit_pct = week2_profit_pct
        self.week3_profit_pct = week3_profit_pct
        self.week4_profit_pct = week4_profit_pct
        
        self.dte_expiration_threshold = dte_expiration_threshold
        self.defensive_breach_pct = defensive_breach_pct
        
        # Initialize filters
        self._init_filters()
        
    @classmethod
    def from_risk_profile(cls, risk_level: Optional[str] = None):
        """Create generator instance from risk profile name."""
        try:
            from .risk_profiles import RiskLevel, get_risk_profile
            
            # Default to MEDIUM if not specified
            if not risk_level:
                risk_level = "MEDIUM"
                
            try:
                level = RiskLevel[risk_level.upper()]
            except KeyError:
                logger.warning(f"Invalid risk level '{risk_level}', defaulting to MEDIUM")
                level = RiskLevel.MEDIUM
                
            profile = get_risk_profile(level)
            logger.info(f"Initialized signal generator with {level.name} risk profile")
            
            return cls(
                contracts_per_trade=profile.contracts_per_trade,
                max_positions=profile.max_positions,
                max_portfolio_heat=profile.max_portfolio_heat,
                min_confidence=profile.min_confidence,
                week1_profit_pct=profile.week1_profit_pct,
                week2_profit_pct=profile.week2_profit_pct,
                week3_profit_pct=profile.week3_profit_pct,
                week4_profit_pct=profile.week4_profit_pct,
                dte_expiration_threshold=profile.dte_exit_threshold,
                defensive_breach_pct=profile.defensive_breach_pct
            )
        except ImportError:
            logger.warning("Risk profiles module not available, using defaults")
            return cls()
    
    @classmethod
    def from_symbol(cls, symbol: str, fallback_risk_level: Optional[str] = "MEDIUM"):
        """
        Create generator instance with symbol-specific optimized profile.
        
        Uses symbol_profiles module for per-symbol parameter tuning.
        If symbol not configured, falls back to standard risk profile.
        
        Args:
            symbol: Stock symbol (e.g., "QQQ", "SPY", "IWM")
            fallback_risk_level: Risk level if symbol not configured
            
        Returns:
            ThetaSignalGenerator configured for symbol
        """
        try:
            from .symbol_profiles import get_symbol_profile
            from .risk_profiles import RiskLevel
            
            # Get symbol-specific profile (with optimizations)
            try:
                level = RiskLevel[fallback_risk_level.upper()]
            except (KeyError, AttributeError):
                level = RiskLevel.MEDIUM
                
            profile = get_symbol_profile(symbol, default_risk_level=level)
            logger.info(f"Initialized signal generator for {symbol} with optimized profile")
            
            return cls(
                contracts_per_trade=profile.contracts_per_trade,
                max_positions=profile.max_positions,
                max_portfolio_heat=profile.max_portfolio_heat,
                min_confidence=profile.min_confidence,
                week1_profit_pct=profile.week1_profit_pct,
                week2_profit_pct=profile.week2_profit_pct,
                week3_profit_pct=profile.week3_profit_pct,
                week4_profit_pct=profile.week4_profit_pct,
                dte_expiration_threshold=profile.dte_exit_threshold,
                defensive_breach_pct=profile.defensive_breach_pct
            )
        except ImportError:
            logger.warning("Symbol profiles not available, using standard risk profile")
            return cls.from_risk_profile(fallback_risk_level)

    def _init_filters(self):
        """Initialize market filters for rule-based risk management."""
        try:
            from .market_filters import MarketFilters
            self.market_filters = MarketFilters()
        except ImportError:
            logger.warning("MarketFilters not available, VIX filtering disabled")
            self.market_filters = None
        
        try:
            from .earnings_calendar import EarningsCalendar
            self.earnings_calendar = EarningsCalendar()
        except ImportError:
            logger.warning("EarningsCalendar not available, earnings blackout disabled")
            self.earnings_calendar = None
        
        try:
            from .correlation_filter import CorrelationFilter
            self.correlation_filter = CorrelationFilter()
        except ImportError:
            logger.warning("CorrelationFilter not available, correlation filtering disabled")
            self.correlation_filter = None
        
        # Initialize defensive exit manager with trailing confirmation
        try:
            from .defensive_exits import DefensiveExitManager
            self.defensive_exit_manager = DefensiveExitManager(
                breach_threshold_pct=self.defensive_breach_pct / 100,  # Convert % to decimal
                breach_confirmation_days=3,  # Default: require 3 days to confirm
                dte_exit_threshold=self.dte_expiration_threshold
            )
            logger.info("DefensiveExitManager initialized with trailing confirmation")
        except ImportError:
            logger.warning("DefensiveExitManager not available, using static exits")
            self.defensive_exit_manager = None
    
    def generate_entry_signals(
        self,
        ranked_puts: List[PutScore],
        portfolio_state: Dict
    ) -> List[ThetaEntrySignal]:
        """
        Generate entry signals from ranked puts.
        
        Args:
            ranked_puts: List of PutScore objects (sorted by confidence)
            portfolio_state: Dict with:
                - available_capital: float
                - current_heat: float
                - open_positions: List[str] (symbols)
                - position_count: int
                
        Returns:
            List of ThetaEntrySignal objects
        """
        signals: List[ThetaEntrySignal] = []
        
        # ===== VIX filter with graceful degradation =====
        vix_level = 0.0
        adjusted_contracts = self.contracts_per_trade
        
        if self.market_filters:
            can_trade, vix_reason, vix_level = self.market_filters.check_vix_filter()
            if not can_trade:
                logger.warning(f"\ud83d\udeab ALL ENTRIES BLOCKED: {vix_reason}")
                return []  # No signals when VIX too high
            
            # Get position size multiplier based on VIX
            size_multiplier = self.market_filters.get_position_size_multiplier()
            adjusted_contracts = max(1, int(self.contracts_per_trade * size_multiplier))
            
            if size_multiplier < 1.0:
                logger.info(f"\u26a0\ufe0f VIX elevated ({vix_level:.1f}): Reducing position size to {adjusted_contracts} contracts")
        else:
            logger.debug("VIX filter not available, using default position size")
        
        available_capital = portfolio_state.get("available_capital", 0)
        current_heat = portfolio_state.get("current_heat", 0)
        open_symbols = set(portfolio_state.get("open_positions", []))
        open_symbols_list = list(open_symbols)  # For correlation filter
        position_count = portfolio_state.get("position_count", 0)
        
        logger.info(f"Generating entry signals from {len(ranked_puts)} ranked puts...")
        logger.info(f"Portfolio state: {position_count}/{self.max_positions} positions, ")
        logger.info(f"  Heat: ${current_heat:,.0f}/${self.max_portfolio_heat:,.0f}, ")
        logger.info(f"  Available: ${available_capital:,.0f}, VIX: {vix_level:.1f}")
        
        for put in ranked_puts:
            # Filter 1: Confidence threshold
            if put.total_score < self.min_confidence:
                continue
            
            # Filter 2: Max positions - MOVED TO CLIENT (log only)
            # Server publishes all qualifying signals, client filters by their max positions
            # if position_count >= self.max_positions:
            #     logger.debug("Max positions reached")
            #     break
            
            # Filter 3: Symbol overlap (no duplicate positions)
            if put.symbol in open_symbols:
                logger.debug(f"{put.symbol}: Already have position")
                continue
            
            # ===== Earnings blackout (with graceful degradation) =====
            if self.earnings_calendar:
                is_blackout, blackout_reason = self.earnings_calendar.is_in_blackout(
                    put.symbol, position_dte=put.dte
                )
                if is_blackout:
                    logger.info(f"{put.symbol}: {blackout_reason}")
                    continue
            
            # ===== Correlation check (with graceful degradation) =====
            if self.correlation_filter:
                can_open, corr_reason = self.correlation_filter.can_open_position(
                    put.symbol, open_symbols_list
                )
                if not can_open:
                    logger.info(f"{put.symbol}: {corr_reason}")
                    continue
            
            # Calculate position sizing (using VIX-adjusted contracts)
            capital_required = put.strike * 100 * adjusted_contracts
            premium_received = put.bid * 100 * adjusted_contracts
            
            # Capital and heat checks - MOVED TO CLIENT
            # Server generates signals for all qualifying puts,
            # client filters based on their account size and risk tolerance
            # Old filters kept as comments for reference:
            # if capital_required > available_capital:
            #     logger.debug(f"{put.symbol}: Insufficient capital")
            #     continue
            # if current_heat + capital_required > self.max_portfolio_heat:
            #     logger.debug(f"{put.symbol}: Would exceed max heat")
            #     continue
            
            # Calculate signal expiration (30 minutes default)
            import config
            expiry_minutes = getattr(config, 'THETA_SIGNAL_EXPIRY_MINUTES', 30)
            expires_at = datetime.now() + timedelta(minutes=expiry_minutes)
            
            # Create entry signal
            signal = ThetaEntrySignal(
                id=str(uuid.uuid4()),
                symbol=put.symbol,
                action="SELL_TO_OPEN",
                strike=put.strike,
                expiration=put.expiration,
                dte=put.dte,
                entry_price=put.bid,
                ask=put.ask,
                mid=put.mid,
                delta=put.delta,
                theta=put.theta,
                vega=put.vega,
                iv=put.iv,
                confidence=put.total_score,
                probability_otm=put.probability_otm,
                expected_premium=put.expected_premium,
                capital_required=put.capital_required,
                contracts=adjusted_contracts,  # Use VIX-adjusted size
                total_premium=premium_received,
                total_capital_required=capital_required,
                created_at=datetime.now(),
                expires_at=expires_at,  # Signal expires after 30 min
                status="pending"
            )
            
            signals.append(signal)
            
            # Track symbols to avoid duplicates within this batch
            # (counters removed - client handles position limits)
            open_symbols.add(put.symbol)
            open_symbols_list.append(put.symbol)  # For correlation filter
        
        logger.info(f"Generated {len(signals)} entry signals")
        self._log_entry_signals(signals)
        
        return signals
    
    def generate_exit_signals(
        self,
        open_positions: List[Dict],
        current_prices: Optional[Dict[str, float]] = None
    ) -> List[ThetaExitSignal]:
        """
        Generate exit signals for open positions.
        
        Args:
            open_positions: List of position dicts with:
                - position_id, symbol, strike, entry_price, entry_date
                - contracts, current_price (of option)
                - underlying_price (of stock)
                - delta, theta, etc.
            current_prices: Optional dict of {symbol: current_stock_price}
            
        Returns:
            List of ThetaExitSignal objects
        """
        signals: List[ThetaExitSignal] = []
        
        logger.info(f"Checking {len(open_positions)} positions for exit signals...")
        
        for position in open_positions:
            exit_signal = self._check_position_exit(position, current_prices)
            if exit_signal:
                signals.append(exit_signal)
        
        logger.info(f"Generated {len(signals)} exit signals")
        self._log_exit_signals(signals)
        
        return signals
    
    def _check_position_exit(
        self,
        position: Dict,
        current_prices: Optional[Dict[str, float]] = None
    ) -> Optional[ThetaExitSignal]:
        """Check if a position should be closed."""
        try:
            position_id = position["position_id"]
            symbol = position["symbol"]
            strike = position["strike"]
            entry_price = position["entry_price"]
            entry_date = position["entry_date"]
            contracts = position["contracts"]
            
            # Current option prices
            current_bid = position.get("current_bid", 0)
            current_ask = position.get("current_ask", 0)
            current_mid = (current_bid + current_ask) / 2
            
            # Calculate P&L
            # Remember: we SOLD the put, so profit when price goes DOWN
            unrealized_pnl = (entry_price - current_ask) * 100 * contracts
            unrealized_pnl_pct = ((entry_price - current_ask) / entry_price) * 100 if entry_price > 0 else 0
            
            # Calculate days in trade
            if isinstance(entry_date, str):
                entry_date = datetime.fromisoformat(entry_date).date()
            days_in_trade = (date.today() - entry_date).days
            
            # Get DTE
            expiration = position.get("expiration")
            if isinstance(expiration, str):
                expiration = datetime.fromisoformat(expiration).date()
            dte = (expiration - date.today()).days if expiration else 999
            
            # Check 1: Time-based profit target
            time_exit = self.check_time_based_exit(days_in_trade, unrealized_pnl_pct)
            if time_exit:
                reason, target_pct, urgency = time_exit
                return self._create_exit_signal(
                    position_id, position, current_ask, unrealized_pnl,
                    unrealized_pnl_pct, reason, urgency, days_in_trade, target_pct
                )
            
            # Check 2: Close to expiration
            if dte <= self.dte_expiration_threshold:
                return self._create_exit_signal(
                    position_id, position, current_ask, unrealized_pnl,
                    unrealized_pnl_pct, ExitReason.EXPIRATION_IMMINENT,
                    "CRITICAL", days_in_trade, 90.0
                )
            
            # Check 3: Defensive close with TRAILING CONFIRMATION
            # Instead of immediate exit, requires 2-3 consecutive days of breach
            if current_prices:
                underlying_price = current_prices.get(symbol)
                if underlying_price:
                    # Use trailing defensive exit manager if available
                    if self.defensive_exit_manager:
                        should_exit, reason, breach_days = self.defensive_exit_manager.check_defensive_exit(
                            position_id, symbol, strike, underlying_price
                        )
                        if should_exit:
                            logger.warning(f"🚫 {symbol}: {reason}")
                            return self._create_exit_signal(
                                position_id, position, current_ask, unrealized_pnl,
                                unrealized_pnl_pct, ExitReason.DEFENSIVE_CLOSE,
                                "HIGH", days_in_trade, 0.0
                            )
                        elif breach_days > 0:
                            # In breach but not confirmed yet - log for awareness
                            logger.info(f"⚠️ {symbol}: Breach day {breach_days}, watching...")
                    else:
                        # Fallback to static exit if manager not available
                        breach_threshold = strike * (1 - self.defensive_breach_pct / 100)
                        if underlying_price < breach_threshold:
                            return self._create_exit_signal(
                                position_id, position, current_ask, unrealized_pnl,
                                unrealized_pnl_pct, ExitReason.DEFENSIVE_CLOSE,
                                "HIGH", days_in_trade, 0.0
                            )
            
            # No exit signal
            return None
            
        except Exception as e:
            logger.error(f"Error checking position {position.get('position_id')}: {e}")
            return None
    
    def check_time_based_exit(
        self,
        days_in_trade: int,
        profit_pct: float
    ) -> Optional[tuple]:
        """
        Check if position meets time-based profit target.
        
        Returns:
            Tuple of (reason, target_pct, urgency) or None
        """
        # Week 1 (1-7 days): 50% profit target
        if 1 <= days_in_trade <= 7:
            if profit_pct >= self.week1_profit_pct:
                return (
                    ExitReason.PROFIT_TARGET,
                    self.week1_profit_pct,
                    "MEDIUM"
                )
        
        # Week 2 (8-14 days): 60% profit target
        elif 8 <= days_in_trade <= 14:
            if profit_pct >= self.week2_profit_pct:
                return (
                    ExitReason.PROFIT_TARGET,
                    self.week2_profit_pct,
                    "MEDIUM"
                )
        
        # Week 3 (15-21 days): 75% profit target
        elif 15 <= days_in_trade <= 21:
            if profit_pct >= self.week3_profit_pct:
                return (
                    ExitReason.PROFIT_TARGET,
                    self.week3_profit_pct,
                    "HIGH"
                )
        
        # Week 4 (22+ days): 90% profit target
        elif days_in_trade >= 22:
            if profit_pct >= self.week4_profit_pct:
                return (
                    ExitReason.PROFIT_TARGET,
                    self.week4_profit_pct,
                    "HIGH"
                )
        
        return None
    
    def _create_exit_signal(
        self,
        position_id: str,
        position: Dict,
        exit_price: float,
        unrealized_pnl: float,
        unrealized_pnl_pct: float,
        reason: ExitReason,
        urgency: str,
        days_in_trade: int,
        target_profit_pct: float
    ) -> ThetaExitSignal:
        """Create an exit signal."""
        return ThetaExitSignal(
            id=str(uuid.uuid4()),
            position_id=position_id,
            symbol=position["symbol"],
            action="BUY_TO_CLOSE",
            strike=position["strike"],
            exit_price=exit_price,
            entry_price=position["entry_price"],
            current_bid=position.get("current_bid", 0),
            current_ask=position.get("current_ask", 0),
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            reason=reason,
            urgency=urgency,
            days_in_trade=days_in_trade,
            target_profit_pct=target_profit_pct,
            contracts=position["contracts"],
            capital_to_release=position["strike"] * 100 * position["contracts"],
            created_at=datetime.now(),
            status="pending"
        )
    
    def _log_entry_signals(self, signals: List[ThetaEntrySignal]):
        """Log generated entry signals."""
        if not signals:
            return
        
        logger.info("\n" + "="*100)
        logger.info("ENTRY SIGNALS - EXECUTION PLAN")
        logger.info("="*100)
        logger.info(
            f"{'#':<3} {'Symbol':<8} {'Strike':<8} {'DTE':<5} {'Bid':<7} "
            f"{'Delta':<7} {'Score':<6} {'Contracts':<10} {'Capital':<12} {'Premium':<10}"
        )
        logger.info("-"*100)
        
        for idx, signal in enumerate(signals, 1):
            logger.info(
                f"{idx:<3} {signal.symbol:<8} {signal.strike:<8.2f} {signal.dte:<5} "
                f"${signal.entry_price:<6.2f} {signal.delta:<7.3f} {signal.confidence:<6} "
                f"{signal.contracts:<10} ${signal.total_capital_required:<11,.0f} ${signal.total_premium:<9.0f}"
            )
        
        total_capital = sum(s.total_capital_required for s in signals)
        total_premium = sum(s.total_premium for s in signals)
        
        logger.info("-"*100)
        logger.info(f"TOTAL: {len(signals)} signals | Capital: ${total_capital:,.0f} | Premium: ${total_premium:,.0f}")
        logger.info("="*100 + "\n")
    
    def _log_exit_signals(self, signals: List[ThetaExitSignal]):
        """Log generated exit signals."""
        if not signals:
            return
        
        logger.info("\n" + "="*100)
        logger.info("EXIT SIGNALS - CLOSE POSITIONS")
        logger.info("="*100)
        logger.info(
            f"{'#':<3} {'Symbol':<8} {'Strike':<8} {'Days':<5} {'P&L':<10} "
            f"{'P&L%':<8} {'Reason':<25} {'Urgency':<10}"
        )
        logger.info("-"*100)
        
        for idx, signal in enumerate(signals, 1):
            logger.info(
                f"{idx:<3} {signal.symbol:<8} {signal.strike:<8.2f} {signal.days_in_trade:<5} "
                f"${signal.unrealized_pnl:<9.0f} {signal.unrealized_pnl_pct:<7.1f}% "
                f"{signal.reason.value:<25} {signal.urgency:<10}"
            )
        
        logger.info("="*100 + "\n")
