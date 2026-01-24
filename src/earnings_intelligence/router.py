"""
Strategy Router for Earnings Intelligence.
Uses ML IV Crush predictions to decide trade actions.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Decision output from the strategy router."""
    action: str  # "APPROVE", "REJECT", "REDUCE_SIZE", "ALTERNATIVE"
    multiplier: float  # Position size multiplier (e.g. 1.0, 0.7, 0.0)
    reason: str
    risk_factor: float  # Stop loss multiplier (e.g. 1.0, 1.5)
    
    # ML model outputs (optional)
    predicted_class: Optional[str] = None
    confidence: Optional[float] = None
    predicted_crush_pct: Optional[float] = None
    
    # Alternative strategy recommendation (when action="ALTERNATIVE")
    alternative_strategy: Optional[str] = None  # "REVERSE_CALENDAR", "STRADDLE", "SKIP"
    alternative_reason: Optional[str] = None


@dataclass
class AlternativeStrategy:
    """
    Alternative trading strategy when calendar spread is rejected.
    Based on docs: Reverse Calendar, Straddle, or Skip.
    """
    strategy_type: str  # "REVERSE_CALENDAR", "STRADDLE", "SKIP"
    description: str
    win_rate_estimate: float  # Expected win rate
    risk_profile: str  # "DEFINED", "UNDEFINED"
    best_for: str  # When to use this strategy
    
    @classmethod
    def reverse_calendar(cls, expected_crush_pct: float = -30) -> "AlternativeStrategy":
        """Create Reverse Calendar Spread recommendation."""
        return cls(
            strategy_type="REVERSE_CALENDAR",
            description=f"BUY short-term call, SELL long-term call. Profits from IV crush ({expected_crush_pct}% expected).",
            win_rate_estimate=0.60,
            risk_profile="DEFINED",
            best_for="1-2 days before earnings with >70% crush probability"
        )
    
    @classmethod
    def long_straddle(cls) -> "AlternativeStrategy":
        """Create Long Straddle recommendation."""
        return cls(
            strategy_type="STRADDLE",
            description="BUY ATM Call + BUY ATM Put (same strike, same expiry). Profits from big move either direction.",
            win_rate_estimate=0.65,
            risk_profile="DEFINED",
            best_for="Expected move > Historical move by >15%"
        )
    
    @classmethod
    def skip_trade(cls, reason: str = "High risk") -> "AlternativeStrategy":
        """Create Skip recommendation."""
        return cls(
            strategy_type="SKIP",
            description=f"Wait for next signal. {reason}",
            win_rate_estimate=1.0,  # Can't lose if you don't trade
            risk_profile="NONE",
            best_for="IV Crush >75% AND Days < 2"
        )



class EarningsStrategyRouter:
    """
    Strategy router that uses ML IV Crush predictions to make trading decisions.
    Falls back to heuristic-based decisions if ML model is unavailable.
    """
    
    def __init__(self, config: dict = None, use_ml_model: bool = True):
        """
        Initialize the strategy router.
        
        Args:
            config: Configuration dictionary
            use_ml_model: Whether to use ML model for predictions
        """
        self.config = config or {}
        self.avoid_days = self.config.get("EARNINGS_AVOID_DAYS", 3)
        self.reduce_days = self.config.get("EARNINGS_REDUCE_SIZE_DAYS", 7)
        self.use_ml_model = use_ml_model
        
        # Lazy load ML model
        self._predictor = None
        
    @property
    def predictor(self):
        """Lazy load the IV Crush predictor."""
        if self._predictor is None and self.use_ml_model:
            try:
                from .iv_crush_model import get_predictor
                self._predictor = get_predictor()
            except Exception as e:
                logger.warning(f"Failed to load ML predictor: {e}")
                self._predictor = None
        return self._predictor

    def decide(
        self,
        symbol: str,
        earnings_context: dict,
        technical_data: Optional[Dict[str, Any]] = None,
        market_data: Optional[Dict[str, Any]] = None
    ) -> RoutingDecision:
        """
        Make a trading decision based on earnings context and ML predictions.
        
        Args:
            symbol: Stock symbol
            earnings_context: Data from Perplexity API
            technical_data: Technical indicators (optional)
            market_data: VIX, sector momentum (optional)
        
        Returns:
            RoutingDecision with action, multiplier, and reason
        """
        if not earnings_context:
            return RoutingDecision(
                action="APPROVE",
                multiplier=1.0,
                reason="No earnings data available",
                risk_factor=1.0
            )
        
        days = earnings_context.get("days_to_earnings", 999)
        
        # Safe zone: >7 days from earnings - approve without ML check
        if days > self.reduce_days:
            return RoutingDecision(
                action="APPROVE",
                multiplier=1.0,
                reason=f"Earnings safe ({days} days away)",
                risk_factor=1.0
            )
        
        # Within earnings window: Use ML model for prediction
        ml_prediction = None
        if self.predictor:
            try:
                ml_prediction = self.predictor.predict(
                    earnings_context,
                    technical_data,
                    market_data
                )
            except Exception as e:
                logger.warning(f"ML prediction failed for {symbol}: {e}")
        
        # Make decision based on ML prediction or fall back to heuristics
        if ml_prediction:
            return self._decide_with_ml(symbol, days, earnings_context, ml_prediction)
        else:
            return self._decide_heuristic(symbol, days, earnings_context)

    def _decide_with_ml(
        self,
        symbol: str,
        days: int,
        earnings_context: dict,
        prediction: Dict[str, Any]
    ) -> RoutingDecision:
        """Make decision using ML model prediction."""
        predicted_class = prediction.get("predicted_class", "NORMAL")
        confidence = prediction.get("confidence", 50)
        predicted_crush = prediction.get("predicted_crush_pct", -15)
        
        # SEVERE crush predicted with high confidence = REJECT
        if predicted_class == "SEVERE" and confidence >= 60:
            return RoutingDecision(
                action="REJECT",
                multiplier=0.0,
                reason=f"ML: SEVERE crush predicted ({confidence:.0f}% conf, {predicted_crush:.0f}% IV drop)",
                risk_factor=1.5,
                predicted_class=predicted_class,
                confidence=confidence,
                predicted_crush_pct=predicted_crush
            )
        
        # SEVERE with lower confidence = REDUCE SIZE significantly
        if predicted_class == "SEVERE" and confidence >= 40:
            return RoutingDecision(
                action="REDUCE_SIZE",
                multiplier=0.5,
                reason=f"ML: Possible SEVERE crush ({confidence:.0f}% conf)",
                risk_factor=1.4,
                predicted_class=predicted_class,
                confidence=confidence,
                predicted_crush_pct=predicted_crush
            )
        
        # Very close to earnings = always risky
        if days <= self.avoid_days:
            if predicted_class in ["NORMAL", "SEVERE"]:
                return RoutingDecision(
                    action="REJECT",
                    multiplier=0.0,
                    reason=f"Too close to earnings ({days} days), {predicted_class} crush expected",
                    risk_factor=1.5,
                    predicted_class=predicted_class,
                    confidence=confidence,
                    predicted_crush_pct=predicted_crush
                )
        
        # EXPANSION predicted = good for calendars, but rare
        if predicted_class == "EXPANSION":
            return RoutingDecision(
                action="APPROVE",
                multiplier=1.0,
                reason=f"ML: IV EXPANSION predicted ({confidence:.0f}% conf) - favorable for calendars",
                risk_factor=0.9,  # Slightly tighter stops OK
                predicted_class=predicted_class,
                confidence=confidence,
                predicted_crush_pct=predicted_crush
            )
        
        # NORMAL crush = reduce size moderately
        if predicted_class == "NORMAL":
            multiplier = 0.7 if days <= 5 else 0.85
            return RoutingDecision(
                action="REDUCE_SIZE",
                multiplier=multiplier,
                reason=f"ML: NORMAL crush expected ({days} days, {confidence:.0f}% conf)",
                risk_factor=1.2,
                predicted_class=predicted_class,
                confidence=confidence,
                predicted_crush_pct=predicted_crush
            )
        
        # NO_CRUSH = approve
        if predicted_class == "NO_CRUSH":
            return RoutingDecision(
                action="APPROVE",
                multiplier=0.9,  # Slight reduction for caution
                reason=f"ML: Minimal crush expected ({predicted_crush:.0f}%)",
                risk_factor=1.1,
                predicted_class=predicted_class,
                confidence=confidence,
                predicted_crush_pct=predicted_crush
            )
        
        # Default: reduce size with caution
        return RoutingDecision(
            action="REDUCE_SIZE",
            multiplier=0.7,
            reason=f"ML: {predicted_class} ({confidence:.0f}% conf)",
            risk_factor=1.2,
            predicted_class=predicted_class,
            confidence=confidence,
            predicted_crush_pct=predicted_crush
        )

    def _decide_heuristic(
        self,
        symbol: str,
        days: int,
        earnings_context: dict
    ) -> RoutingDecision:
        """Fallback heuristic-based decision when ML not available."""
        crush_prob = earnings_context.get("crush_probability", 0.5)
        
        # DANGER ZONE: High crush probability OR very close (<= 3 days)
        if crush_prob >= 0.7 or days <= self.avoid_days:
            reason = f"HIGH risk: {days} days, {crush_prob*100:.0f}% crush prob (heuristic)"
            return RoutingDecision(
                action="REJECT",
                multiplier=0.0,
                reason=reason,
                risk_factor=1.5
            )
        
        # CAUTION ZONE: Medium crush probability (50-70%) or 4-7 days
        if crush_prob >= 0.5 or days <= self.reduce_days:
            reason = f"MEDIUM risk: {days} days, {crush_prob*100:.0f}% crush prob (heuristic)"
            
            if days <= 1:
                risk_factor = 1.5
            elif days <= 3:
                risk_factor = 1.3
            else:
                risk_factor = 1.1
                
            return RoutingDecision(
                action="REDUCE_SIZE",
                multiplier=0.7,
                reason=reason,
                risk_factor=risk_factor
            )
        
        # LOW risk: proceed normally
        return RoutingDecision(
            action="APPROVE",
            multiplier=1.0,
            reason=f"LOW risk: {days} days, {crush_prob*100:.0f}% crush prob (heuristic)",
            risk_factor=1.0
        )

    def get_model_status(self) -> Dict[str, Any]:
        """Get status of the ML model."""
        if not self.predictor:
            return {"model_loaded": False, "using_heuristics": True}
        
        return {
            "model_loaded": True,
            "model_trained": self.predictor.is_trained,
            "model_version": self.predictor.MODEL_VERSION if self.predictor.is_trained else None,
            "using_heuristics": not self.predictor.is_trained
        }
