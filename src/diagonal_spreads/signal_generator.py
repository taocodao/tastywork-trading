"""
Diagonal Spread Signal Generator
================================

Combines direction prediction (from vertical spreads) with DTE selection
to generate actionable diagonal spread signals.

Key concept: Poor Man's Covered Call (PMCC) / Poor Man's Covered Put (PMCP)
- Use direction confidence > 70% for entry
- Long leg: Deep ITM call/put (mimics stock ownership)
- Short leg: OTM call/put (collects premium)
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Any
import uuid

# Import direction predictor from vertical spreads
from src.vertical_spreads.direction_predictor import (
    VerticalSpreadDirectionPredictor, 
    DirectionSignal
)
from .spread_selector import (
    DiagonalSpreadSelector, 
    DiagonalSpreadSetup, 
    get_available_expirations
)

logger = logging.getLogger(__name__)


@dataclass
class DiagonalSpreadSignal:
    """Complete signal ready for execution or display."""
    id: str
    symbol: str
    strategy: str  # "BULL_DIAGONAL", "BEAR_DIAGONAL", or "NEUTRAL_DIAGONAL"
    direction: str  # "bullish", "bearish", or "neutral"
    
    # Long leg (back month, ITM)
    long_strike: float
    long_expiration: str  # ISO date
    long_dte: int
    long_price: float
    
    # Short leg (front month, OTM)
    short_strike: float
    short_expiration: str  # ISO date
    short_dte: int
    short_price: float
    
    option_type: str  # "C" or "P"
    
    # Pricing
    net_debit: float
    max_profit: float
    max_loss: float
    break_even: float
    contracts: int
    total_risk: float
    
    # Analysis
    confidence: int
    return_percent: float
    risk_level: str  # "Low", "Medium", "High"
    rationale: str
    
    # Status
    status: str  # "pending", "executed", "rejected"
    created_at: str
    
    # Rolling opportunity
    days_until_roll: int  # When short leg expires
    roll_action: str  # "HOLD" or "ROLL_SOON"
    
    # Earnings context
    earnings_days: Optional[int] = None
    earnings_decision: Optional[str] = None


class DiagonalSpreadSignalGenerator:
    """
    Generates diagonal spread signals by combining:
    - VerticalSpreadDirectionPredictor for directional bias
    - DiagonalSpreadSelector for strike/expiration selection
    - Earnings intelligence for risk management
    """
    
    def __init__(
        self,
        min_directional_confidence: int = 70,  # Min confidence for directional trades
        neutral_threshold: int = 50,  # Below this = neutral/calendar mode
        earnings_enabled: bool = True,
        earnings_avoid_days: int = 3,
        earnings_reduce_days: int = 7
    ):
        """
        Initialize signal generator.
        
        Args:
            min_confidence: Minimum confidence to generate signal (default 70%)
            earnings_enabled: Whether to check earnings proximity
            earnings_avoid_days: Days before earnings to skip trades
            earnings_reduce_days: Days before earnings to reduce size
        """
        self.direction_predictor = VerticalSpreadDirectionPredictor(
            min_confidence_threshold=neutral_threshold
        )
        self.spread_selector = DiagonalSpreadSelector()
        
        self.min_directional_confidence = min_directional_confidence
        self.neutral_threshold = neutral_threshold
        self.earnings_enabled = earnings_enabled
        self.earnings_avoid_days = earnings_avoid_days
        self.earnings_reduce_days = earnings_reduce_days
        
        # Import earnings intelligence if available
        try:
            from src.earnings_intelligence.client import PerplexityClient
            from src.earnings_intelligence.router import EarningsStrategyRouter
            self.earnings_client = PerplexityClient()
            self.earnings_router = EarningsStrategyRouter({
                "EARNINGS_AVOID_DAYS": earnings_avoid_days,
                "EARNINGS_REDUCE_SIZE_DAYS": earnings_reduce_days
            })
        except ImportError:
            logger.warning("Earnings intelligence modules not available")
            self.earnings_client = None
            self.earnings_router = None
    
    def generate_signal(
        self,
        symbol: str,
        stock_data: Dict,
        account_data: Dict,
        available_expirations: Optional[List[date]] = None
    ) -> Optional[DiagonalSpreadSignal]:
        """
        Generate a diagonal spread signal for a symbol.
        
        Args:
            symbol: Stock symbol
            stock_data: Dict with price, technicals (RSI, BB, MAs, IV)
            account_data: Dict with balance, risk_tolerance, options_level
            available_expirations: List of available expiration dates
        
        Returns:
            DiagonalSpreadSignal or None if no signal
        """
        # Step 1: Direction prediction
        stock_data["symbol"] = symbol
        direction_signal = self.direction_predictor.calculate_direction_signal(stock_data)
        
        # Determine trade type based on confidence
        # High confidence (70%+) = directional diagonal (PMCC/PMCP)
        # Low confidence (<70%) = neutral diagonal (calendar-like)
        if direction_signal.confidence >= self.min_directional_confidence:
            # Use directional signal
            trade_direction = direction_signal.direction
        else:
            # Fall back to neutral/calendar mode
            trade_direction = "NEUTRAL"
            logger.debug(f"{symbol}: Low confidence ({direction_signal.confidence}%), using neutral mode")
        
        # Step 2: Earnings check
        earnings_context = None
        earnings_decision = None
        
        if self.earnings_enabled and self.earnings_client:
            earnings_context = self.earnings_client.get_earnings_context(symbol)
            
            if self.earnings_router:
                routing = self.earnings_router.decide(symbol, earnings_context)
                earnings_decision = routing.action
                
                if routing.action == "REJECT":
                    logger.info(f"{symbol}: Rejected due to earnings - {routing.reason}")
                    return self._create_rejected_signal(
                        symbol, direction_signal, routing.reason, earnings_context
                    )
        
        # Step 3: Get expirations
        if available_expirations is None:
            available_expirations = get_available_expirations()
        
        # Step 4: Spread selection
        iv = stock_data.get("iv", stock_data.get("atm_iv", 0.25))
        
        spread_setup = self.spread_selector.select_spread(
            symbol=symbol,
            stock_price=stock_data.get("price", 0),
            direction=trade_direction,  # Use trade_direction (includes NEUTRAL)
            confidence=direction_signal.confidence,
            iv=iv,
            account_balance=account_data.get("balance", 5000),
            available_expirations=available_expirations,
            risk_tolerance=account_data.get("risk_tolerance", "medium")
        )
        
        if not spread_setup:
            logger.warning(f"{symbol}: Could not select diagonal spread")
            return None
        
        # Step 5: Apply earnings size adjustment if needed
        if earnings_decision == "REDUCE_SIZE":
            spread_setup.contracts = max(1, int(spread_setup.contracts * 0.5))
            spread_setup.total_at_risk = spread_setup.max_loss * spread_setup.contracts
        
        # Step 6: Create final signal
        return self._create_signal(
            spread_setup,
            direction_signal,
            earnings_context,
            earnings_decision
        )
    
    def generate_signals_batch(
        self,
        symbols: List[str],
        stock_data_provider,  # Function(symbol) -> Dict
        account_data: Dict
    ) -> List[DiagonalSpreadSignal]:
        """
        Generate signals for multiple symbols.
        
        Args:
            symbols: List of stock symbols
            stock_data_provider: Function that returns stock data for a symbol
            account_data: Account information
        
        Returns:
            List of signals, sorted by score
        """
        signals = []
        
        for symbol in symbols:
            try:
                stock_data = stock_data_provider(symbol)
                signal = self.generate_signal(symbol, stock_data, account_data)
                
                if signal and signal.status == "pending":
                    signals.append(signal)
                    
            except Exception as e:
                logger.error(f"Error generating diagonal signal for {symbol}: {e}")
        
        # Sort by confidence (highest first)
        signals.sort(key=lambda x: x.confidence, reverse=True)
        
        return signals
    
    def _create_signal(
        self,
        setup: DiagonalSpreadSetup,
        direction: DirectionSignal,
        earnings_context: Optional[Dict],
        earnings_decision: Optional[str]
    ) -> DiagonalSpreadSignal:
        """Create a complete signal from setup and analysis."""
        
        # Calculate return percentage
        if setup.max_loss > 0:
            return_pct = (setup.max_profit / setup.max_loss) * 100
        else:
            return_pct = 0
        
        # Determine risk level
        risk_level = self._calculate_risk_level(
            setup.confidence,
            setup.short_dte,
            setup.long_dte,
            earnings_context.get("days_to_earnings") if earnings_context else None
        )
        
        # Build rationale
        rationale = self._build_rationale(direction, setup, earnings_context)
        
        # Calculate roll timing
        days_until_roll = setup.short_dte
        roll_action = "ROLL_SOON" if days_until_roll <= 5 else "HOLD"
        
        # Map direction to lowercase for signal
        direction_map = {"BULL": "bullish", "BEAR": "bearish", "NEUTRAL": "neutral"}
        direction_str = direction_map.get(setup.direction, "neutral")
        
        return DiagonalSpreadSignal(
            id=str(uuid.uuid4()),
            symbol=setup.symbol,
            strategy=setup.strategy,
            direction=direction_str,
            long_strike=setup.long_strike,
            long_expiration=setup.long_expiration.isoformat(),
            long_dte=setup.long_dte,
            long_price=round(setup.long_price, 2),
            short_strike=setup.short_strike,
            short_expiration=setup.short_expiration.isoformat(),
            short_dte=setup.short_dte,
            short_price=round(setup.short_price, 2),
            option_type=setup.option_type,
            net_debit=round(setup.net_debit, 2),
            max_profit=round(setup.max_profit, 2),
            max_loss=round(setup.max_loss, 2),
            break_even=round(setup.break_even, 2),
            contracts=setup.contracts,
            total_risk=round(setup.total_at_risk, 2),
            confidence=setup.confidence,
            return_percent=round(return_pct, 1),
            risk_level=risk_level,
            rationale=rationale,
            status="pending",
            created_at=datetime.now().isoformat(),
            days_until_roll=days_until_roll,
            roll_action=roll_action,
            earnings_days=earnings_context.get("days_to_earnings") if earnings_context else None,
            earnings_decision=earnings_decision
        )
    
    def _create_rejected_signal(
        self,
        symbol: str,
        direction: DirectionSignal,
        reason: str,
        earnings_context: Optional[Dict]
    ) -> DiagonalSpreadSignal:
        """Create a rejected signal for logging/display."""
        return DiagonalSpreadSignal(
            id=str(uuid.uuid4()),
            symbol=symbol,
            strategy="REJECTED",
            direction="bullish" if direction.direction == "BULL" else "bearish",
            long_strike=0,
            long_expiration="",
            long_dte=0,
            long_price=0,
            short_strike=0,
            short_expiration="",
            short_dte=0,
            short_price=0,
            option_type="",
            net_debit=0,
            max_profit=0,
            max_loss=0,
            break_even=0,
            contracts=0,
            total_risk=0,
            confidence=direction.confidence,
            return_percent=0,
            risk_level="High",
            rationale=reason,
            status="rejected",
            created_at=datetime.now().isoformat(),
            days_until_roll=0,
            roll_action="NONE",
            earnings_days=earnings_context.get("days_to_earnings") if earnings_context else None,
            earnings_decision="REJECT"
        )
    
    def _calculate_risk_level(
        self,
        confidence: int,
        short_dte: int,
        long_dte: int,
        earnings_days: Optional[int]
    ) -> str:
        """Determine risk level based on multiple factors."""
        # High risk conditions
        if earnings_days and earnings_days <= 3:
            return "High"
        if confidence < 70:
            return "High"
        if short_dte < 5:
            return "High"
        if long_dte < 30:
            return "High"
        
        # Low risk conditions
        if confidence >= 80 and short_dte >= 10 and long_dte >= 60:
            if not earnings_days or earnings_days > 14:
                return "Low"
        
        return "Medium"
    
    def _build_rationale(
        self,
        direction: DirectionSignal,
        setup: DiagonalSpreadSetup,
        earnings_context: Optional[Dict]
    ) -> str:
        """Build human-readable rationale for the signal."""
        parts = []
        
        # Strategy name
        if setup.direction == "BULL":
            strategy_name = "PMCC"
        elif setup.direction == "BEAR":
            strategy_name = "PMCP"
        else:
            strategy_name = "Calendar"
        parts.append(f"{strategy_name} ({setup.confidence}% confidence)")
        
        # Technical reasons
        bullish_indicators = [i["name"] for i in direction.indicators if i.get("vote", 0) > 0]
        bearish_indicators = [i["name"] for i in direction.indicators if i.get("vote", 0) < 0]
        
        if bullish_indicators and setup.direction == "BULL":
            parts.append(f"Bullish: {', '.join(bullish_indicators)}")
        elif bearish_indicators and setup.direction == "BEAR":
            parts.append(f"Bearish: {', '.join(bearish_indicators)}")
        
        # DTE info
        parts.append(f"DTEs: {setup.short_dte}/{setup.long_dte}")
        
        # Earnings context
        if earnings_context:
            days = earnings_context.get("days_to_earnings")
            if days and days <= 14:
                parts.append(f"Earnings in {days}d")
        
        return " | ".join(parts)


def signal_to_dict(signal: DiagonalSpreadSignal) -> Dict[str, Any]:
    """Convert signal to dictionary for JSON serialization."""
    return {
        "id": signal.id,
        "symbol": signal.symbol,
        "strategy": signal.strategy,
        "direction": signal.direction,
        "longStrike": signal.long_strike,
        "longExpiration": signal.long_expiration,
        "longDte": signal.long_dte,
        "longPrice": signal.long_price,
        "shortStrike": signal.short_strike,
        "shortExpiration": signal.short_expiration,
        "shortDte": signal.short_dte,
        "shortPrice": signal.short_price,
        "optionType": signal.option_type,
        "netDebit": signal.net_debit,
        "maxProfit": signal.max_profit,
        "maxLoss": signal.max_loss,
        "breakEven": signal.break_even,
        "contracts": signal.contracts,
        "totalRisk": signal.total_risk,
        "confidence": signal.confidence,
        "returnPercent": signal.return_percent,
        "riskLevel": signal.risk_level,
        "rationale": signal.rationale,
        "status": signal.status,
        "createdAt": signal.created_at,
        "daysUntilRoll": signal.days_until_roll,
        "rollAction": signal.roll_action,
        "earningsDays": signal.earnings_days,
        "earningsDecision": signal.earnings_decision
    }
