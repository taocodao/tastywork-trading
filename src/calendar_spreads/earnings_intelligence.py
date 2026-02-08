"""
Earnings Intelligence for Calendar Spreads
============================================
IV Crush prediction and strategy routing

Key principle: Calendar spreads are vulnerable to IV crush after earnings
- Long leg loses more value than short leg when IV drops
- Must avoid or adapt strategy around earnings

Decision Matrix:
- >14 days to earnings: APPROVE
- 7-14 days, high crush: REVERSE_CALENDAR (profit from crush)
- 3-7 days, moderate crush: REDUCE_SIZE
- <=3 days, high crush: REJECT
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)


class StrategyDecision(Enum):
    """Possible strategy decisions based on earnings analysis"""
    APPROVE = "APPROVE"           # Proceed with normal calendar
    REJECT = "REJECT"             # Do not enter trade
    REDUCE_SIZE = "REDUCE_SIZE"   # Enter with reduced position size
    REVERSE_CALENDAR = "REVERSE_CALENDAR"  # Sell long, buy short (profit from crush)


@dataclass
class IVCrushPrediction:
    """Prediction results from IV crush model"""
    crush_probability: float = 0.5
    predicted_magnitude: float = 0.15  # 15% IV drop expected
    confidence: float = 0.5
    model_version: str = "rule_based_v1"
    
    # Historical context
    historical_avg_move: float = 0.0
    historical_crush_pct: float = 0.0
    
    def is_high_risk(self) -> bool:
        """Check if this is a high crush risk prediction"""
        return self.crush_probability > 0.70 and self.predicted_magnitude > 0.20


@dataclass
class EarningsDecision:
    """Complete earnings-based trading decision"""
    action: StrategyDecision
    reason: str
    size_multiplier: float = 1.0
    alternative_strategy: Optional[str] = None
    
    # Context
    symbol: str = ""
    days_to_earnings: int = 999
    earnings_date: Optional[date] = None
    
    # Prediction
    crush_probability: float = 0.0
    predicted_magnitude: float = 0.0
    
    # Flags
    requires_review: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/logging"""
        return {
            'action': self.action.value,
            'reason': self.reason,
            'size_multiplier': self.size_multiplier,
            'alternative_strategy': self.alternative_strategy,
            'symbol': self.symbol,
            'days_to_earnings': self.days_to_earnings,
            'earnings_date': self.earnings_date.isoformat() if self.earnings_date else None,
            'crush_probability': self.crush_probability,
            'predicted_magnitude': self.predicted_magnitude,
            'requires_review': self.requires_review
        }


@dataclass
class EarningsRouterConfig:
    """Configuration for earnings strategy router"""
    # Safety margins
    safe_days: int = 14  # No concern if earnings >14 days away
    
    # Reject thresholds
    reject_days: int = 3
    reject_crush_prob: float = 0.70
    
    # Reduce size thresholds  
    reduce_days: int = 7
    reduce_crush_prob: float = 0.50
    reduce_size_multiplier: float = 0.5
    
    # Reverse calendar threshold
    reverse_days: int = 7
    reverse_crush_prob: float = 0.60
    reverse_size_multiplier: float = 0.7
    
    # High crush probability threshold for immediate reject
    high_crush_threshold: float = 0.80


class IVCrushPredictor:
    """
    Predict IV crush magnitude after earnings
    
    Supports two modes:
    1. Rule-based heuristics (default, always available)
    2. ML Random Forest model (if available from src/earnings_intelligence)
    
    The ML model provides 4-class predictions:
    - NORMAL: 10-20% IV decline
    - SEVERE: >30% IV decline (dangerous for calendars)
    - EXPANSION: IV increases (rare, good for calendars)
    - NO_CRUSH: <5% IV change
    
    Factors considered:
    - Historical earnings moves
    - Current IV rank vs historical
    - Sector patterns
    - Expected move from straddle
    """
    
    def __init__(self, 
                 historical_data: Optional[Dict] = None,
                 use_ml_model: bool = True):
        """
        Initialize IV Crush Predictor
        
        Args:
            historical_data: Dict of historical earnings data by symbol
            use_ml_model: Whether to try loading and using the ML model
        """
        self.historical_data = historical_data or {}
        self.model_version = "rule_based_v1"
        self.ml_predictor = None
        
        # Try to load ML model if requested
        if use_ml_model:
            self._try_load_ml_model()
    
    def _try_load_ml_model(self):
        """Attempt to load the ML IV Crush predictor from earnings_intelligence"""
        try:
            from src.earnings_intelligence.iv_crush_model import get_predictor, IVCrushPredictor as MLPredictor
            self.ml_predictor = get_predictor()
            if self.ml_predictor and self.ml_predictor.is_trained:
                self.model_version = f"ml_rf_{self.ml_predictor.MODEL_VERSION}"
                logger.info(f"Loaded ML IV Crush model: {self.model_version}")
            else:
                logger.info("ML model not trained, using rule-based fallback")
                self.ml_predictor = None
        except ImportError as e:
            logger.debug(f"ML IV Crush model not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}")
            self.ml_predictor = None
    
    def predict(self, 
               symbol: str,
               days_to_earnings: int,
               current_iv_rank: float = 50.0,
               expected_move: float = 0.0) -> IVCrushPrediction:
        """
        Predict IV crush for upcoming earnings
        
        Args:
            symbol: Stock symbol
            days_to_earnings: Days until earnings announcement
            current_iv_rank: Current IV rank (0-100)
            expected_move: Market implied expected move percentage
        
        Returns:
            IVCrushPrediction with probability and magnitude
        """
        # Try ML model first if available
        if self.ml_predictor is not None:
            try:
                return self._predict_with_ml(symbol, days_to_earnings, current_iv_rank)
            except Exception as e:
                logger.warning(f"ML prediction failed, using rule-based: {e}")
        
        # Fallback to rule-based prediction
        return self._predict_rule_based(symbol, days_to_earnings, current_iv_rank, expected_move)
    
    def _predict_with_ml(self,
                         symbol: str,
                         days_to_earnings: int,
                         current_iv_rank: float) -> IVCrushPrediction:
        """Use ML model for prediction"""
        # Build context for ML model
        earnings_context = {
            'symbol': symbol,
            'days_to_earnings': days_to_earnings,
            'current_iv_rank': current_iv_rank,
            'crush_probability': 0.5  # Default for heuristic fallback
        }
        
        # Get ML prediction
        ml_result = self.ml_predictor.predict(earnings_context)
        
        # Map ML class to crush probability and magnitude
        predicted_class = ml_result.get('predicted_class', 'NORMAL')
        class_probs = ml_result.get('class_probabilities', {})
        
        # Calculate crush probability from SEVERE and NORMAL classes
        # SEVERE = high crush, NORMAL = moderate crush
        from src.earnings_intelligence.features import IVCrushClass
        severe_prob = class_probs.get(IVCrushClass.SEVERE, class_probs.get('SEVERE', 0))
        normal_prob = class_probs.get(IVCrushClass.NORMAL, class_probs.get('NORMAL', 0))
        crush_probability = severe_prob + normal_prob * 0.7  # Weight normal crush lower
        
        # Map class to magnitude
        magnitude_map = {
            IVCrushClass.SEVERE: 0.35,
            IVCrushClass.NORMAL: 0.15,
            IVCrushClass.NO_CRUSH: 0.02,
            IVCrushClass.EXPANSION: -0.10,
            'SEVERE': 0.35,
            'NORMAL': 0.15,
            'NO_CRUSH': 0.02,
            'EXPANSION': -0.10
        }
        predicted_magnitude = magnitude_map.get(predicted_class, 0.15)
        
        # Use predicted_crush_pct from ML if available
        if 'predicted_crush_pct' in ml_result:
            predicted_magnitude = abs(ml_result['predicted_crush_pct']) / 100
        
        prediction = IVCrushPrediction(
            crush_probability=round(crush_probability, 3),
            predicted_magnitude=round(predicted_magnitude, 3),
            confidence=round(ml_result.get('confidence', 50) / 100, 2),
            model_version=self.model_version,
            historical_avg_move=0.0,
            historical_crush_pct=predicted_magnitude
        )
        
        logger.info(
            f"IV Crush ML Prediction [{symbol}]: {crush_probability:.0%} probability, "
            f"{predicted_magnitude:.0%} magnitude (class: {predicted_class})"
        )
        
        return prediction
    
    def _predict_rule_based(self, 
                           symbol: str,
                           days_to_earnings: int,
                           current_iv_rank: float,
                           expected_move: float) -> IVCrushPrediction:
        """Rule-based fallback prediction"""
        # Get historical data for symbol
        hist = self.historical_data.get(symbol, {})
        hist_avg_crush = hist.get('avg_iv_crush', 0.20)  # Default 20%
        hist_avg_move = hist.get('avg_move', 0.05)  # Default 5%
        
        # Base crush probability from IV rank
        # High IV rank = higher probability of mean reversion (crush)
        if current_iv_rank > 80:
            base_prob = 0.80
        elif current_iv_rank > 60:
            base_prob = 0.65
        elif current_iv_rank > 40:
            base_prob = 0.50
        else:
            base_prob = 0.35
        
        # Adjust for days to earnings (closer = more certain of crush)
        if days_to_earnings <= 1:
            time_factor = 1.2
        elif days_to_earnings <= 3:
            time_factor = 1.1
        elif days_to_earnings <= 7:
            time_factor = 1.0
        else:
            time_factor = 0.8
        
        crush_probability = min(base_prob * time_factor, 0.95)
        
        # Predicted magnitude based on IV rank and historical
        if current_iv_rank > 70:
            predicted_magnitude = hist_avg_crush * 1.2  # Higher crush when IV elevated
        elif current_iv_rank > 50:
            predicted_magnitude = hist_avg_crush
        else:
            predicted_magnitude = hist_avg_crush * 0.8
        
        # Confidence based on data availability and distance
        confidence = 0.5
        if hist:
            confidence += 0.2  # Have historical data
        if days_to_earnings <= 7:
            confidence += 0.2  # Closer to event
        if expected_move > 0:
            confidence += 0.1  # Have market implied move
        
        prediction = IVCrushPrediction(
            crush_probability=round(crush_probability, 3),
            predicted_magnitude=round(predicted_magnitude, 3),
            confidence=round(min(confidence, 1.0), 2),
            model_version=self.model_version,
            historical_avg_move=hist_avg_move,
            historical_crush_pct=hist_avg_crush
        )
        
        logger.info(
            f"IV Crush Prediction [{symbol}]: {crush_probability:.0%} probability, "
            f"{predicted_magnitude:.0%} magnitude (conf: {prediction.confidence:.0%})"
        )
        
        return prediction
    
    def update_historical_data(self, symbol: str, data: Dict):
        """Update historical data for a symbol"""
        self.historical_data[symbol] = data


class EarningsStrategyRouter:
    """
    Make trading decisions based on earnings proximity and IV crush predictions
    
    Usage:
        router = EarningsStrategyRouter()
        
        # Get decision for a symbol
        decision = router.decide(
            symbol='AAPL',
            days_to_earnings=5,
            current_iv_rank=75.0
        )
        
        if decision.action == StrategyDecision.APPROVE:
            # Proceed with trade
            pass
        elif decision.action == StrategyDecision.REJECT:
            # Skip this symbol
            pass
    """
    
    def __init__(self,
                 config: Optional[EarningsRouterConfig] = None,
                 iv_predictor: Optional[IVCrushPredictor] = None,
                 earnings_calendar: Optional[Any] = None):
        self.config = config or EarningsRouterConfig()
        self.iv_predictor = iv_predictor or IVCrushPredictor()
        self.earnings_calendar = earnings_calendar
    
    def decide(self,
              symbol: str,
              days_to_earnings: Optional[int] = None,
              current_iv_rank: float = 50.0,
              expected_move: float = 0.0) -> EarningsDecision:
        """
        Make trading decision based on earnings intelligence
        
        Args:
            symbol: Stock symbol
            days_to_earnings: Days until next earnings (None = lookup)
            current_iv_rank: Current IV rank (0-100)
            expected_move: Market implied expected move
        
        Returns:
            EarningsDecision with action and context
        """
        # Get days to earnings if not provided
        if days_to_earnings is None:
            if self.earnings_calendar:
                days_to_earnings = self._lookup_earnings(symbol)
            else:
                days_to_earnings = 999  # Assume no earnings
        
        earnings_date = None
        if days_to_earnings < 999:
            earnings_date = date.today()
            from datetime import timedelta
            earnings_date = date.today() + timedelta(days=days_to_earnings)
        
        # Early exit: No earnings concern
        if days_to_earnings > self.config.safe_days:
            return EarningsDecision(
                action=StrategyDecision.APPROVE,
                reason=f"No earnings within {self.config.safe_days} days (next: {days_to_earnings}d)",
                size_multiplier=1.0,
                symbol=symbol,
                days_to_earnings=days_to_earnings,
                earnings_date=earnings_date
            )
        
        # Get IV crush prediction
        prediction = self.iv_predictor.predict(
            symbol=symbol,
            days_to_earnings=days_to_earnings,
            current_iv_rank=current_iv_rank,
            expected_move=expected_move
        )
        
        # Decision logic based on days and crush probability
        decision = self._apply_decision_matrix(
            symbol=symbol,
            days_to_earnings=days_to_earnings,
            prediction=prediction,
            earnings_date=earnings_date
        )
        
        logger.info(
            f"Earnings Decision [{symbol}]: {decision.action.value} - {decision.reason}"
        )
        
        return decision
    
    def _apply_decision_matrix(self,
                              symbol: str,
                              days_to_earnings: int,
                              prediction: IVCrushPrediction,
                              earnings_date: Optional[date]) -> EarningsDecision:
        """Apply decision matrix based on research"""
        
        crush_prob = prediction.crush_probability
        
        # Very close to earnings (<=3 days)
        if days_to_earnings <= self.config.reject_days:
            if crush_prob >= self.config.reject_crush_prob:
                return EarningsDecision(
                    action=StrategyDecision.REJECT,
                    reason=f"High crush risk ({crush_prob:.0%}) {days_to_earnings}d before earnings",
                    size_multiplier=0.0,
                    symbol=symbol,
                    days_to_earnings=days_to_earnings,
                    earnings_date=earnings_date,
                    crush_probability=crush_prob,
                    predicted_magnitude=prediction.predicted_magnitude
                )
            elif crush_prob >= self.config.reduce_crush_prob:
                return EarningsDecision(
                    action=StrategyDecision.REDUCE_SIZE,
                    reason=f"Moderate crush risk ({crush_prob:.0%}) close to earnings",
                    size_multiplier=self.config.reduce_size_multiplier,
                    symbol=symbol,
                    days_to_earnings=days_to_earnings,
                    earnings_date=earnings_date,
                    crush_probability=crush_prob,
                    predicted_magnitude=prediction.predicted_magnitude
                )
        
        # Within earnings window (3-7 days)
        elif days_to_earnings <= self.config.reduce_days:
            if crush_prob >= self.config.high_crush_threshold:
                return EarningsDecision(
                    action=StrategyDecision.REJECT,
                    reason=f"Very high crush risk ({crush_prob:.0%})",
                    size_multiplier=0.0,
                    symbol=symbol,
                    days_to_earnings=days_to_earnings,
                    earnings_date=earnings_date,
                    crush_probability=crush_prob,
                    predicted_magnitude=prediction.predicted_magnitude
                )
            elif crush_prob >= self.config.reverse_crush_prob:
                # Consider reverse calendar to profit from crush
                return EarningsDecision(
                    action=StrategyDecision.REVERSE_CALENDAR,
                    reason=f"High crush expected ({crush_prob:.0%}), reverse calendar favorable",
                    size_multiplier=self.config.reverse_size_multiplier,
                    alternative_strategy='reverse_calendar',
                    symbol=symbol,
                    days_to_earnings=days_to_earnings,
                    earnings_date=earnings_date,
                    crush_probability=crush_prob,
                    predicted_magnitude=prediction.predicted_magnitude,
                    requires_review=True
                )
            elif crush_prob >= self.config.reduce_crush_prob:
                return EarningsDecision(
                    action=StrategyDecision.REDUCE_SIZE,
                    reason=f"Moderate crush risk ({crush_prob:.0%})",
                    size_multiplier=self.config.reduce_size_multiplier,
                    symbol=symbol,
                    days_to_earnings=days_to_earnings,
                    earnings_date=earnings_date,
                    crush_probability=crush_prob,
                    predicted_magnitude=prediction.predicted_magnitude
                )
        
        # Somewhat close (7-14 days) but acceptable risk
        elif days_to_earnings <= self.config.safe_days:
            if crush_prob >= self.config.high_crush_threshold:
                return EarningsDecision(
                    action=StrategyDecision.REDUCE_SIZE,
                    reason=f"Elevated crush risk ({crush_prob:.0%}) with earnings approaching",
                    size_multiplier=0.75,
                    symbol=symbol,
                    days_to_earnings=days_to_earnings,
                    earnings_date=earnings_date,
                    crush_probability=crush_prob,
                    predicted_magnitude=prediction.predicted_magnitude,
                    requires_review=True
                )
        
        # Default: Approve
        return EarningsDecision(
            action=StrategyDecision.APPROVE,
            reason="Earnings risk acceptable",
            size_multiplier=1.0,
            symbol=symbol,
            days_to_earnings=days_to_earnings,
            earnings_date=earnings_date,
            crush_probability=crush_prob,
            predicted_magnitude=prediction.predicted_magnitude
        )
    
    def _lookup_earnings(self, symbol: str) -> int:
        """Look up days to earnings from calendar"""
        try:
            if hasattr(self.earnings_calendar, 'get_days_to_earnings'):
                return self.earnings_calendar.get_days_to_earnings(symbol)
            elif hasattr(self.earnings_calendar, 'days_to_earnings'):
                return self.earnings_calendar.days_to_earnings(symbol)
        except Exception as e:
            logger.warning(f"Failed to lookup earnings for {symbol}: {e}")
        
        return 999
    
    def batch_decide(self, 
                    symbols: List[str],
                    iv_ranks: Optional[Dict[str, float]] = None) -> Dict[str, EarningsDecision]:
        """
        Make decisions for multiple symbols
        
        Returns:
            Dictionary mapping symbol -> EarningsDecision
        """
        iv_ranks = iv_ranks or {}
        decisions = {}
        
        for symbol in symbols:
            iv_rank = iv_ranks.get(symbol, 50.0)
            decisions[symbol] = self.decide(symbol, current_iv_rank=iv_rank)
        
        # Summary logging
        approved = sum(1 for d in decisions.values() if d.action == StrategyDecision.APPROVE)
        rejected = sum(1 for d in decisions.values() if d.action == StrategyDecision.REJECT)
        modified = len(decisions) - approved - rejected
        
        logger.info(
            f"Earnings decisions: {approved} approved, {rejected} rejected, "
            f"{modified} modified (total {len(decisions)})"
        )
        
        return decisions
    
    def get_tradeable_symbols(self, 
                             symbols: List[str],
                             iv_ranks: Optional[Dict[str, float]] = None) -> List[str]:
        """
        Filter symbols to only those approved for trading
        
        Returns:
            List of symbols with APPROVE or REDUCE_SIZE decision
        """
        decisions = self.batch_decide(symbols, iv_ranks)
        
        tradeable = [
            symbol for symbol, decision in decisions.items()
            if decision.action in [StrategyDecision.APPROVE, StrategyDecision.REDUCE_SIZE]
        ]
        
        return tradeable
