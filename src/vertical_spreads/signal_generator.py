"""
Vertical Spread Signal Generator
================================

Combines direction prediction, strike selection, and earnings intelligence
to generate actionable vertical spread signals.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Any
import uuid

from .direction_predictor import VerticalSpreadDirectionPredictor, DirectionSignal
from .spread_selector import VerticalSpreadSelector, VerticalSpreadSetup, get_available_expirations

logger = logging.getLogger(__name__)


@dataclass
class VerticalSpreadSignal:
    """Complete signal ready for execution or display."""
    id: str
    symbol: str
    strategy: str  # "BULL_CALL_SPREAD" or "BEAR_PUT_SPREAD"
    direction: str  # "bullish" or "bearish"
    
    # Spread details
    buy_strike: float
    sell_strike: float
    option_type: str  # "C" or "P"
    expiration: str  # ISO date string
    dte: int
    
    # Pricing
    cost: float  # Net debit per contract
    max_profit: float
    max_loss: float
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
    
    # Earnings context (if applicable)
    earnings_days: Optional[int] = None
    earnings_decision: Optional[str] = None


class VerticalSpreadSignalGenerator:
    """
    Generates vertical spread signals by combining:
    - VerticalSpreadDirectionPredictor for directional bias
    - VerticalSpreadSelector for strike selection
    - Earnings intelligence for risk management
    """
    
    def __init__(
        self,
        min_confidence: int = 60,
        earnings_enabled: bool = True,
        earnings_avoid_days: int = 3,
        earnings_reduce_days: int = 7
    ):
        """
        Initialize signal generator.
        
        Args:
            min_confidence: Minimum confidence to generate signal
            earnings_enabled: Whether to check earnings proximity
            earnings_avoid_days: Days before earnings to skip trades
            earnings_reduce_days: Days before earnings to reduce size
        """
        self.direction_predictor = VerticalSpreadDirectionPredictor(
            min_confidence_threshold=min_confidence
        )
        self.spread_selector = VerticalSpreadSelector()
        
        self.min_confidence = min_confidence
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
    ) -> Optional[VerticalSpreadSignal]:
        """
        Generate a vertical spread signal for a symbol.
        
        Args:
            symbol: Stock symbol
            stock_data: Dict with price, technicals (RSI, BB, MAs, IV)
            account_data: Dict with balance, risk_tolerance, options_level
            available_expirations: List of available expiration dates
        
        Returns:
            VerticalSpreadSignal or None if no signal
        """
        # Step 1: Direction prediction
        stock_data["symbol"] = symbol
        direction_signal = self.direction_predictor.calculate_direction_signal(stock_data)
        
        if not self.direction_predictor.is_actionable(direction_signal):
            logger.debug(f"{symbol}: Direction not actionable - {direction_signal.direction} @ {direction_signal.confidence}%")
            return None
        
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
        
        # Step 3: Strike selection
        if available_expirations is None:
            available_expirations = get_available_expirations()
        
        iv = stock_data.get("iv", stock_data.get("atm_iv", 0.25))
        
        spread_setup = self.spread_selector.select_spread(
            symbol=symbol,
            stock_price=stock_data.get("price", 0),
            direction=direction_signal.direction,
            confidence=direction_signal.confidence,
            iv=iv,
            account_balance=account_data.get("balance", 5000),
            available_expirations=available_expirations,
            risk_tolerance=account_data.get("risk_tolerance", "medium")
        )
        
        if not spread_setup:
            logger.warning(f"{symbol}: Could not select spread")
            return None
        
        # Step 4: Apply earnings size adjustment if needed
        if earnings_decision == "REDUCE_SIZE":
            spread_setup.contracts = max(1, int(spread_setup.contracts * 0.7))
            spread_setup.total_at_risk = spread_setup.max_loss * spread_setup.contracts
        
        # Step 5: Create final signal
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
    ) -> List[VerticalSpreadSignal]:
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
                logger.error(f"Error generating signal for {symbol}: {e}")
        
        # Sort by confidence (highest first)
        signals.sort(key=lambda x: x.confidence, reverse=True)
        
        return signals
    
    def _create_signal(
        self,
        setup: VerticalSpreadSetup,
        direction: DirectionSignal,
        earnings_context: Optional[Dict],
        earnings_decision: Optional[str]
    ) -> VerticalSpreadSignal:
        """Create a complete signal from setup and analysis."""
        
        # Calculate return percentage
        if setup.max_loss > 0:
            return_pct = (setup.max_profit / setup.max_loss) * 100
        else:
            return_pct = 0
        
        # Determine risk level
        risk_level = self._calculate_risk_level(
            setup.confidence,
            setup.dte,
            earnings_context.get("days_to_earnings") if earnings_context else None
        )
        
        # Build rationale
        rationale = self._build_rationale(direction, setup, earnings_context)
        
        return VerticalSpreadSignal(
            id=str(uuid.uuid4()),
            symbol=setup.symbol,
            strategy=setup.strategy,
            direction="bullish" if setup.direction == "BULL" else "bearish",
            buy_strike=setup.buy_strike,
            sell_strike=setup.sell_strike,
            option_type=setup.option_type,
            expiration=setup.expiration.isoformat(),
            dte=setup.dte,
            cost=round(setup.net_debit * 100, 2),  # Total cost per contract
            max_profit=round(setup.max_profit, 2),
            max_loss=round(setup.max_loss, 2),
            contracts=setup.contracts,
            total_risk=round(setup.total_at_risk, 2),
            confidence=setup.confidence,
            return_percent=round(return_pct, 1),
            risk_level=risk_level,
            rationale=rationale,
            status="pending",
            created_at=datetime.now().isoformat(),
            earnings_days=earnings_context.get("days_to_earnings") if earnings_context else None,
            earnings_decision=earnings_decision
        )
    
    def _create_rejected_signal(
        self,
        symbol: str,
        direction: DirectionSignal,
        reason: str,
        earnings_context: Optional[Dict]
    ) -> VerticalSpreadSignal:
        """Create a rejected signal for logging/display."""
        return VerticalSpreadSignal(
            id=str(uuid.uuid4()),
            symbol=symbol,
            strategy="REJECTED",
            direction="bullish" if direction.direction == "BULL" else "bearish",
            buy_strike=0,
            sell_strike=0,
            option_type="",
            expiration="",
            dte=0,
            cost=0,
            max_profit=0,
            max_loss=0,
            contracts=0,
            total_risk=0,
            confidence=direction.confidence,
            return_percent=0,
            risk_level="High",
            rationale=reason,
            status="rejected",
            created_at=datetime.now().isoformat(),
            earnings_days=earnings_context.get("days_to_earnings") if earnings_context else None,
            earnings_decision="REJECT"
        )
    
    def _calculate_risk_level(
        self,
        confidence: int,
        dte: int,
        earnings_days: Optional[int]
    ) -> str:
        """Determine risk level based on multiple factors."""
        # High risk conditions
        if earnings_days and earnings_days <= 3:
            return "High"
        if confidence < 60:
            return "High"
        if dte < 5:
            return "High"
        
        # Low risk conditions
        if confidence >= 75 and dte >= 10:
            if not earnings_days or earnings_days > 14:
                return "Low"
        
        return "Medium"
    
    def _build_rationale(
        self,
        direction: DirectionSignal,
        setup: VerticalSpreadSetup,
        earnings_context: Optional[Dict]
    ) -> str:
        """Build human-readable rationale for the signal."""
        parts = []
        
        # Direction reasoning
        parts.append(f"{setup.direction} signal ({setup.confidence}% confidence)")
        
        # Technical reasons
        bullish_indicators = [i["name"] for i in direction.indicators if i.get("vote", 0) > 0]
        bearish_indicators = [i["name"] for i in direction.indicators if i.get("vote", 0) < 0]
        
        if bullish_indicators and setup.direction == "BULL":
            parts.append(f"Bullish: {', '.join(bullish_indicators)}")
        elif bearish_indicators and setup.direction == "BEAR":
            parts.append(f"Bearish: {', '.join(bearish_indicators)}")
        
        # Risk/reward
        if setup.max_loss > 0:
            rr_ratio = setup.max_profit / setup.max_loss
            parts.append(f"R/R: {rr_ratio:.1f}:1")
        
        # Earnings context
        if earnings_context:
            days = earnings_context.get("days_to_earnings")
            if days and days <= 14:
                parts.append(f"Earnings in {days} days")
        
        return " | ".join(parts)


def signal_to_dict(signal: VerticalSpreadSignal) -> Dict[str, Any]:
    """Convert signal to dictionary for JSON serialization."""
    return {
        "id": signal.id,
        "symbol": signal.symbol,
        "strategy": signal.strategy,
        "direction": signal.direction,
        "buyStrike": signal.buy_strike,
        "sellStrike": signal.sell_strike,
        "optionType": signal.option_type,
        "expiration": signal.expiration,
        "dte": signal.dte,
        "cost": signal.cost,
        "maxProfit": signal.max_profit,
        "maxLoss": signal.max_loss,
        "contracts": signal.contracts,
        "totalRisk": signal.total_risk,
        "confidence": signal.confidence,
        "returnPercent": signal.return_percent,
        "riskLevel": signal.risk_level,
        "rationale": signal.rationale,
        "status": signal.status,
        "createdAt": signal.created_at,
        "earningsDays": signal.earnings_days,
        "earningsDecision": signal.earnings_decision
    }
